"""Claude Agent SDK loop (agent_loop=claude); same SSE shape as agent2 loop."""

from __future__ import annotations

import json
import logging
import time as _time
from uuid import uuid4

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    UserMessage,
)

from fastapi import HTTPException

from restai import docker as _docker
from restai.database import DBWrapper
from restai.models.models import ChatModel, User
from restai.project import Project
from restai.projects import agent_shared
from restai.projects._claude_sdk_tools import build_builtins_mcp
from restai.tools import tokens_from_string


logger = logging.getLogger("restai.claude_loop")


# LLM class names that talk to Anthropic; loop only works for these.
_ANTHROPIC_LLM_CLASSES = {"Anthropic", "AnthropicGrok"}


def _resolve_anthropic_config(project: Project, db: DBWrapper) -> tuple[str, str]:
    """Return (model, api_key) for the project's Anthropic LLM; raises 400 otherwise."""
    llm_name = project.props.llm
    if not llm_name:
        raise HTTPException(400, detail="agent_loop=claude requires an LLM configured on the project.")
    llm_db = db.get_llm_by_name(llm_name)
    if llm_db is None:
        raise HTTPException(400, detail=f"LLM '{llm_name}' not found.")
    if llm_db.class_name not in _ANTHROPIC_LLM_CLASSES:
        raise HTTPException(
            400,
            detail=(
                f"agent_loop=claude requires an Anthropic-class LLM (one of "
                f"{sorted(_ANTHROPIC_LLM_CLASSES)}), but project LLM '{llm_name}' is "
                f"class '{llm_db.class_name}'. Switch the project's LLM or set "
                f"agent_loop=restai."
            ),
        )
    # LLMModel auto-decrypts api_key via decrypt_sensitive_options.
    from restai.models.models import LLMModel
    options = LLMModel.model_validate(llm_db).options or {}
    api_key = options.get("api_key")
    model = options.get("model") or options.get("model_name") or llm_name
    if not api_key:
        raise HTTPException(
            400,
            detail=f"LLM '{llm_name}' has no api_key configured. Set it in /admin/llms.",
        )
    return model, api_key


def _block_text(block) -> str:
    text = getattr(block, "text", None)
    return text if isinstance(text, str) else ""


def _tool_result_text(block) -> str:
    content = getattr(block, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                parts.append(str(c["text"]))
            else:
                t = getattr(c, "text", None)
                if t:
                    parts.append(str(t))
        return "\n".join(parts)
    return str(content)


def _build_options(project, db, brain, *, system_prompt: str, chat_id: str,
                   model: str, api_key: str) -> ClaudeAgentOptions:
    """Compose ClaudeAgentOptions for one chat (ANTHROPIC_API_KEY env is enough)."""
    # ClaudeSDKClient has no native API for seeding history — render prior
    # turns as text and prepend to system prompt. Same source of truth as
    # every other external loop.
    history = agent_shared.load_chat_history(brain, chat_id)
    history_block = agent_shared.chat_history_as_text(history)
    augmented = agent_shared.augment_system_prompt_with_memory_bank(project, db, system_prompt)
    augmented = agent_shared.augment_system_prompt_with_memory_search_hint(project, augmented)
    augmented = agent_shared.prepend_current_time(augmented)
    if history_block:
        augmented = f"{augmented}\n\n{history_block}" if augmented else history_block

    # The SDK orchestrator process needs *some* cwd, but it has no host file
    # tools (tools=[] below), so this stays an empty, isolated per-chat host
    # dir that is NOT mounted into the container — no agent data reaches the
    # host. (Kept off the RESTai source dir so a hypothetical leaked host tool
    # still couldn't touch our code.)
    cwd = _docker._ensure_chat_workspace(chat_id) if hasattr(_docker, "_ensure_chat_workspace") else None

    builtins_server, builtin_allowed = build_builtins_mcp(project, db, brain, chat_id)
    mcp_servers: dict = {}
    if builtins_server is not None:
        mcp_servers["restai_builtins"] = builtins_server

    raw_external = getattr(project.props.options, "mcp_servers", None) or ""
    if isinstance(raw_external, dict):
        mcp_servers.update(raw_external)
    elif raw_external:
        try:
            mcp_servers.update(json.loads(raw_external))
        except Exception:
            logger.warning("Failed to parse mcp_servers JSON for project %s", project.props.id)

    # Nothing executes on the host. tools=[] disables EVERY native SDK built-in
    # (Read/Write/Edit/Glob/Grep/WebFetch/Bash/...), so the model's only tools
    # are our `restai_builtins` MCP tools — and those run inside the per-chat
    # Docker sandbox. File + shell work go through the `terminal` builtin
    # in-container; there is no host-side execution path at all.
    if any(t.endswith("__terminal") for t in builtin_allowed):
        hint = (
            "Tooling: you have NO native filesystem or shell tools. Use the "
            "`terminal` tool (a shell inside your sandbox) for every file and "
            "command operation — there is no Read/Write/Edit."
        )
        augmented = f"{augmented}\n\n{hint}" if augmented else hint

    return ClaudeAgentOptions(
        env={"ANTHROPIC_API_KEY": api_key,
             "DISABLE_TELEMETRY": "1",
             "DISABLE_ERROR_REPORTING": "1"},
        model=model,
        cwd=cwd,
        system_prompt=augmented or "",
        mcp_servers=mcp_servers,
        tools=[],                       # no host-side built-in tools at all
        allowed_tools=builtin_allowed,  # auto-approve our Docker-backed MCP builtins
        permission_mode="default",
        max_turns=int(getattr(project.props.options, "max_iterations", 50) or 50),
    )


async def _drive(project, db, brain, user, *, prompt_text: str, chat_id: str,
                 system_prompt: str, stream: bool, image_url: str | None = None):
    """Async generator yielding (kind, payload) tuples:
        ("text", str delta)
        ("event", dict with tool_call_started / tool_call_completed)
        ("result", dict with answer / tokens / tool_trace)
    """
    model, api_key = _resolve_anthropic_config(project, db)
    options = _build_options(
        project, db, brain,
        system_prompt=system_prompt, chat_id=chat_id,
        model=model, api_key=api_key,
    )

    tool_call_started_at: dict[str, float] = {}
    pending: dict = {}
    tool_trace: list[dict] = []
    harvested_image_urls: list[str] = []
    result_meta = {"text": "", "input_tokens": 0, "output_tokens": 0, "stop_reason": None}

    # With an image, send an Anthropic-shaped content block list (text +
    # base64 image) instead of a plain string.
    decoded = agent_shared.parse_data_url(image_url) if image_url else None
    if decoded is not None:
        import base64 as _b64
        mime, raw = decoded
        query_payload = [
            {"type": "text", "text": prompt_text},
            {"type": "image", "source": {
                "type": "base64",
                "media_type": mime,
                "data": _b64.b64encode(raw).decode("ascii"),
            }},
        ]
    else:
        query_payload = prompt_text

    async with ClaudeSDKClient(options=options) as client:
        await client.query(query_payload)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content or []:
                    if isinstance(block, TextBlock):
                        text = _block_text(block)
                        if text:
                            result_meta["text"] += text
                            if stream:
                                yield ("text", text)
                    elif isinstance(block, ThinkingBlock):
                        thinking = getattr(block, "thinking", None) or ""
                        if thinking:
                            chunk = f"<think>{thinking}</think>"
                            result_meta["text"] += chunk
                            if stream:
                                yield ("text", chunk)
                    elif isinstance(block, ToolUseBlock):
                        started = _time.monotonic()
                        tool_call_started_at[block.id] = started
                        pending[block.id] = block
                        try:
                            args_preview = json.dumps(block.input, default=str)
                        except Exception:
                            args_preview = str(block.input)
                        if len(args_preview) > 500:
                            args_preview = args_preview[:500] + "…"
                        if stream:
                            yield ("event", {"tool_call_started": {
                                "id": block.id, "tool": block.name, "args": args_preview,
                            }})

            elif isinstance(message, UserMessage):
                content = getattr(message, "content", None) or []
                if isinstance(content, str):
                    continue
                for block in content:
                    tool_use_id = getattr(block, "tool_use_id", None)
                    if tool_use_id is None:
                        continue
                    tool_call = pending.pop(tool_use_id, None)
                    raw_content_text = _tool_result_text(block)
                    content_text = agent_shared.truncate_tool_output(raw_content_text)
                    harvested_image_urls.extend(agent_shared.harvest_image_urls(content_text))
                    started = tool_call_started_at.pop(tool_use_id, None)
                    latency_ms = int((_time.monotonic() - started) * 1000) if started else None
                    status = (
                        "error" if str(content_text).strip().startswith("ERROR:")
                        or getattr(block, "is_error", False)
                        else "ok"
                    )
                    tool_name = getattr(tool_call, "name", None) or "unknown"
                    try:
                        input_preview = json.dumps(getattr(tool_call, "input", None), default=str)
                    except Exception:
                        input_preview = str(getattr(tool_call, "input", ""))
                    if len(input_preview) > 500:
                        input_preview = input_preview[:500] + "…"
                    err_preview = str(content_text)[:500] if status == "error" else None
                    tool_trace.append({
                        "tool": tool_name, "args": input_preview,
                        "latency_ms": latency_ms, "status": status, "error": err_preview,
                    })
                    output_preview = str(content_text)[:500]
                    if len(str(content_text)) > 500:
                        output_preview += "…"
                    if stream:
                        yield ("event", {"tool_call_completed": {
                            "id": tool_use_id, "tool": tool_name, "status": status,
                            "latency_ms": latency_ms, "output": output_preview, "error": err_preview,
                        }})

            elif isinstance(message, ResultMessage):
                usage = getattr(message, "usage", None) or {}
                result_meta["input_tokens"] = int(usage.get("input_tokens", 0))
                result_meta["output_tokens"] = int(usage.get("output_tokens", 0))
                result_meta["stop_reason"] = getattr(message, "subtype", None)
                result_text = getattr(message, "result", None)
                if result_text and not result_meta["text"]:
                    result_meta["text"] = str(result_text)

            elif isinstance(message, SystemMessage):
                continue

    final_answer_text = result_meta["text"]

    # Claude SDK emits ResultMessage.subtype = "error_max_turns" when
    # max_turns is hit without a final response. Append the standard
    # "say continue" notice.
    if result_meta["stop_reason"] == "error_max_turns":
        max_iters = getattr(project.props.options, "max_iterations", None)
        final_answer_text = (final_answer_text or "").rstrip() + agent_shared.max_turns_notice(max_iters)

    final_answer_text = agent_shared.append_unreferenced_image_urls(final_answer_text, harvested_image_urls)

    yield ("result", {
        "answer": final_answer_text,
        "tokens": {
            "input": result_meta["input_tokens"] or tokens_from_string(prompt_text),
            "output": result_meta["output_tokens"] or tokens_from_string(final_answer_text),
        },
        "tool_trace": tool_trace or None,
        "stop_reason": result_meta["stop_reason"],
    })


async def chat(agent_self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
    """Drop-in replacement for Agent.chat() when agent_loop=claude."""
    chat_id = chatModel.id or str(uuid4())
    output = {
        "question": chatModel.question,
        "type": "agent",
        "sources": [],
        "guard": False,
        "tokens": {"input": 0, "output": 0},
        "project": project.props.name,
        "id": chat_id,
        "agent_loop": "claude",
    }

    # Container + host workspace + session below are keyed by this scoped id
    # (bound to the authenticated user + project) so users can't collide on a
    # shared chat_id and reach each other's sandbox / workspace files. The
    # client already got the raw id via output["id"] above.
    chat_id = agent_shared.sandbox_chat_id(project.props.id, user.id, chat_id)

    if agent_self.check_input_guard(project, chatModel.question, user, db, output):
        if chatModel.stream:
            yield "data: " + json.dumps({"text": output.get("answer", "")}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return

    prompt_text, image_url = agent_shared.route_attachments(
        getattr(chatModel, "files", None), chat_id, chatModel.question, agent_self.brain,
        existing_image=chatModel.image, project=project,
    )

    streamed_any_text = False
    try:
        async for kind, payload in _drive(
            project, db, agent_self.brain, user,
            prompt_text=prompt_text, chat_id=chat_id,
            system_prompt=(chatModel.system or project.props.system or ""), stream=chatModel.stream,
            image_url=image_url,
        ):
            if kind == "text":
                streamed_any_text = True
                if chatModel.stream:
                    yield "data: " + json.dumps({"text": payload}) + "\n\n"
            elif kind == "event":
                if chatModel.stream:
                    yield "data: " + json.dumps(payload) + "\n\n"
            elif kind == "result":
                output["answer"] = payload["answer"]
                output["tokens"] = payload["tokens"]
                if payload.get("tool_trace"):
                    output["tool_trace"] = payload["tool_trace"]
                if payload.get("stop_reason"):
                    output["stop_reason"] = payload["stop_reason"]
    except HTTPException as e:
        err = f"claude loop config error: {e.detail}"
        output["answer"] = err
        output["status"] = "error"
        if chatModel.stream:
            yield "data: " + json.dumps({"text": err}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return
    except Exception as e:
        logger.exception("claude loop failed for project %s", project.props.name)
        err = f"claude loop error: {e}"
        output["answer"] = err
        output["status"] = "error"
        if chatModel.stream:
            if not streamed_any_text:
                yield "data: " + json.dumps({"text": err}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return

    agent_self.check_output_guard(project, user, db, output)

    # Persist into shared agent_shared history so future /chat calls see it
    # even if agent_loop is switched to llamaindex / smolagents / openai_agents.
    agent_shared.spawn_persist_chat_turn(
        agent_self.brain, chat_id,
        agent_shared.load_chat_history(agent_self.brain, chat_id),
        chatModel.question, output.get("answer", ""),
    )

    if chatModel.stream:
        if not streamed_any_text and output.get("answer"):
            yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
        yield "data: " + json.dumps(output) + "\n"
        yield "event: close\n\n"
    else:
        yield output

