"""OpenAI Agents SDK loop (agent_loop=openai_agents); hard-gated to OpenAI-class LLMs."""

from __future__ import annotations

import inspect
import json as _json
import logging
import time as _time
from uuid import uuid4

from agents import (
    Agent,
    FunctionTool,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RawResponsesStreamEvent,
    RunConfig,
    RunItemStreamEvent,
    Runner,
)
from agents.items import (
    MessageOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from fastapi import HTTPException
from openai import AsyncOpenAI
from openai.types.responses import ResponseTextDeltaEvent

from restai.database import DBWrapper
from restai.models.models import ChatModel, LLMModel, QuestionModel, User
from restai.project import Project
from restai.projects import agent_shared
from restai.tools import tokens_from_string


logger = logging.getLogger("restai.openai_agents_loop")


# Strictly OpenAI-cloud; OpenAILike/vLLM/Grok are not auto-accepted because
# the Agents SDK's tracing dashboard and hosted-tool integrations are
# OpenAI-specific.
_OPENAI_LLM_CLASSES = {"OpenAI"}


_INTERNAL_PARAM_NAMES = {"kwargs", "_brain", "_chat_id", "_project_id"}


def _resolve_openai_config(project: Project, db: DBWrapper) -> tuple[str, str, str | None]:
    """Return (model, api_key, base_url) for the project's OpenAI LLM; raises 400 otherwise."""
    llm_name = project.props.llm
    if not llm_name:
        raise HTTPException(400, detail="agent_loop=openai_agents requires an LLM configured on the project.")
    llm_db = db.get_llm_by_name(llm_name)
    if llm_db is None:
        raise HTTPException(400, detail=f"LLM '{llm_name}' not found.")
    if llm_db.class_name not in _OPENAI_LLM_CLASSES:
        raise HTTPException(
            400,
            detail=(
                f"agent_loop=openai_agents requires an OpenAI-class LLM (one of "
                f"{sorted(_OPENAI_LLM_CLASSES)}), but project LLM '{llm_name}' is "
                f"class '{llm_db.class_name}'. Switch the project's LLM or pick a "
                f"different agent_loop."
            ),
        )
    options = LLMModel.model_validate(llm_db).options or {}
    api_key = options.get("api_key")
    base_url = options.get("base_url") or options.get("api_base")
    model = options.get("model") or options.get("model_name") or llm_name
    if not api_key:
        raise HTTPException(
            400,
            detail=f"LLM '{llm_name}' has no api_key configured. Set it in /admin/llms.",
        )
    return model, api_key, base_url


def _strip_internal_params(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}
    props = dict(schema.get("properties") or {})
    required = [r for r in (schema.get("required") or []) if r not in _INTERNAL_PARAM_NAMES]
    for name in _INTERNAL_PARAM_NAMES:
        props.pop(name, None)
    cleaned = dict(schema)
    cleaned["properties"] = props
    if required:
        cleaned["required"] = required
    else:
        cleaned.pop("required", None)
    cleaned.setdefault("type", "object")
    # OpenAI strict schemas reject additionalProperties=true.
    cleaned.setdefault("additionalProperties", False)
    return cleaned


def _function_tool_schema(ft) -> dict:
    try:
        meta = ft.metadata
        if hasattr(meta, "get_parameters_dict"):
            s = meta.get_parameters_dict()
            if s:
                return _strip_internal_params(s)
        if hasattr(meta, "fn_schema_str") and meta.fn_schema_str:
            try:
                return _strip_internal_params(_json.loads(meta.fn_schema_str))
            except Exception:
                pass
        if hasattr(meta, "fn_schema") and meta.fn_schema is not None:
            return _strip_internal_params(meta.fn_schema.schema())
    except Exception:
        pass
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _wrap_function_tool(ft, *, brain, chat_id, project_id) -> FunctionTool:
    inner = ft.fn
    sig = inspect.signature(inner)
    has_var_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    accepts_brain = "_brain" in sig.parameters or has_var_kwargs
    accepts_chat = "_chat_id" in sig.parameters or has_var_kwargs
    accepts_project = "_project_id" in sig.parameters or has_var_kwargs
    is_async = inspect.iscoroutinefunction(inner)
    name = ft.metadata.name
    description = ft.metadata.description or name
    schema = _function_tool_schema(ft)

    async def _on_invoke(_ctx, args_str: str):
        try:
            args = _json.loads(args_str) if args_str else {}
        except _json.JSONDecodeError:
            return f"ERROR: invalid JSON arguments: {args_str!r}"
        if accepts_brain and "_brain" not in args:
            args["_brain"] = brain
        if accepts_chat and "_chat_id" not in args:
            args["_chat_id"] = chat_id
        if accepts_project and "_project_id" not in args:
            args["_project_id"] = project_id
        try:
            result = await inner(**args) if is_async else inner(**args)
        except Exception as e:
            logger.exception("Platform tool %s raised", name)
            return f"ERROR: {e}"
        if result is None:
            return ""
        if isinstance(result, (dict, list)):
            return _json.dumps(result, default=str)
        return str(result)

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=schema,
        on_invoke_tool=_on_invoke,
        strict_json_schema=False,
    )


def _wrap_project_tool(row, *, brain, chat_id) -> FunctionTool:
    try:
        schema = (
            _json.loads(row.parameters)
            if isinstance(row.parameters, str)
            else (row.parameters or {"type": "object", "properties": {}})
        )
    except (_json.JSONDecodeError, TypeError):
        schema = {"type": "object", "properties": {}}
    schema = _strip_internal_params(schema)

    tool_code = row.code
    name = row.name
    description = row.description or name

    async def _on_invoke(_ctx, args_str: str):
        if not brain or not getattr(brain, "docker_manager", None):
            return "ERROR: Docker is not configured."
        try:
            args = _json.loads(args_str) if args_str else {}
        except _json.JSONDecodeError:
            return f"ERROR: invalid JSON arguments: {args_str!r}"
        args_json = _json.dumps(args)
        script = (
            "import json, sys\n"
            "args = json.loads(sys.stdin.readline() or '{}')\n"
            f"{tool_code}"
        )
        try:
            return brain.docker_manager.run_script(chat_id or "ephemeral", script, stdin_data=args_json)
        except Exception as e:
            logger.exception("Project tool %s raised", name)
            return f"ERROR: {e}"

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=schema,
        on_invoke_tool=_on_invoke,
        strict_json_schema=False,
    )


def _gather_tools(project: Project, agent_self, db: DBWrapper, chat_id: str) -> list[FunctionTool]:
    raw_names = {
        t.strip() for t in (project.props.options.tools or "").split(",") if t.strip()
    }
    builtins = agent_self.brain.get_tools(raw_names) if raw_names else []

    out: list[FunctionTool] = []
    for ft in builtins:
        try:
            out.append(_wrap_function_tool(
                ft, brain=agent_self.brain, chat_id=chat_id, project_id=project.props.id,
            ))
        except Exception as e:
            logger.warning("Failed to wrap builtin %s: %s", getattr(ft.metadata, "name", "?"), e)

    try:
        for row in db.get_project_tools(project.props.id) or []:
            if not getattr(row, "enabled", True):
                continue
            try:
                out.append(_wrap_project_tool(row, brain=agent_self.brain, chat_id=chat_id))
            except Exception as e:
                logger.warning("Failed to wrap project tool %s: %s", row.name, e)
    except Exception:
        pass
    return out


def _extract_tool_call(item: ToolCallItem) -> tuple[str | None, str, str]:
    """Return (call_id, tool_name, args_json_str); raw_item shape varies across APIs."""
    raw = item.raw_item
    call_id = getattr(raw, "call_id", None) or getattr(raw, "id", None)
    name = getattr(raw, "name", None) or "unknown"
    args = getattr(raw, "arguments", None)
    if args is None:
        # Chat-completions shape: arguments live on raw.function.arguments.
        fn = getattr(raw, "function", None)
        if fn is not None:
            name = getattr(fn, "name", None) or name
            args = getattr(fn, "arguments", None)
    return call_id, name, args or ""


def _extract_tool_output(item: ToolCallOutputItem) -> tuple[str | None, str]:
    raw = item.raw_item
    call_id = None
    if isinstance(raw, dict):
        call_id = raw.get("call_id") or raw.get("tool_call_id") or raw.get("id")
    else:
        call_id = getattr(raw, "call_id", None) or getattr(raw, "tool_call_id", None) or getattr(raw, "id", None)
    output_text = str(item.output) if item.output is not None else ""
    return call_id, output_text


def _extract_message_text(item: MessageOutputItem) -> str:
    raw = item.raw_item
    parts = []
    for c in getattr(raw, "content", None) or []:
        text = getattr(c, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


async def _drive(project, db, agent_self, *, prompt_text: str, system_prompt: str,
                 stream: bool, chat_id: str, image_url: str | None = None):
    """Async generator yielding (kind, payload) tuples; same protocol as _claude_sdk_loop._drive."""
    from restai.agent2.mcp_client import MCPSessionPool

    model_name, api_key, base_url = _resolve_openai_config(project, db)
    tools = _gather_tools(project, agent_self, db, chat_id)

    mcp_servers = getattr(project.props.options, "mcp_servers", None) or []
    mcp_pool = None
    if mcp_servers:
        try:
            mcp_pool = MCPSessionPool()
            await mcp_pool.__aenter__()
            adapted_tools = await mcp_pool.connect_servers(mcp_servers)
            for a in adapted_tools:
                try:
                    li_ft = agent_shared.adapted_to_function_tool(a)
                    tools.append(_wrap_function_tool(
                        li_ft, brain=agent_self.brain, chat_id=chat_id, project_id=project.props.id,
                    ))
                except Exception as e:
                    logger.warning("Failed to wrap MCP tool %s: %s", getattr(a, "name", "?"), e)
        except Exception as e:
            logger.warning("MCP pool connect failed: %s", e)
            if mcp_pool is not None:
                try:
                    await mcp_pool.__aexit__(None, None, None)
                except Exception:
                    pass
                mcp_pool = None

    augmented = agent_shared.augment_system_prompt_with_memory_bank(project, db, system_prompt)
    augmented = agent_shared.augment_system_prompt_with_memory_search_hint(project, augmented)
    augmented = agent_shared.prepend_current_time(augmented)

    # Agents SDK accepts input= as string or list of message dicts. With an
    # image we MUST use list form with an input_image content part (OpenAI's
    # vision input shape).
    history = agent_shared.load_chat_history(agent_self.brain, chat_id)
    user_turn_content: list[dict] | str
    if image_url:
        user_turn_content = [
            {"type": "input_text", "text": prompt_text},
            {"type": "input_image", "image_url": image_url, "detail": "auto"},
        ]
    else:
        user_turn_content = prompt_text

    if history or isinstance(user_turn_content, list):
        input_payload = [
            {"role": (getattr(m, "role", None).value if hasattr(getattr(m, "role", None), "value") else (m.role or "user")),
             "content": (m.content if isinstance(m.content, str) else str(m.content))}
            for m in history
        ]
        input_payload.append({"role": "user", "content": user_turn_content})
    else:
        input_payload = prompt_text

    openai_client = AsyncOpenAI(api_key=api_key, base_url=base_url) if base_url else AsyncOpenAI(api_key=api_key)
    model = OpenAIChatCompletionsModel(model=model_name, openai_client=openai_client)

    agent = Agent(
        name="restai_agent",
        instructions=augmented or None,
        tools=tools,
        model=model,
    )

    tool_started_at: dict[str, float] = {}
    harvested_image_urls: list[str] = []
    recent_assistant_texts: list[str] = []
    tool_args_cache: dict[str, tuple[str, str]] = {}  # call_id -> (tool_name, args_preview)
    tool_trace: list[dict] = []
    answer_buf: list[str] = []
    fallback_text_buf: list[str] = []

    max_turns = int(getattr(project.props.options, "max_iterations", 10) or 10)

    # Tracing OFF by default — SDK's hosted tracing needs its own API key
    # and would otherwise emit a noisy "OPENAI_API_KEY is not set, skipping
    # trace export" warning on every run.
    run_config = RunConfig(tracing_disabled=True)

    result = Runner.run_streamed(agent, input=input_payload, max_turns=max_turns, run_config=run_config)

    async for ev in result.stream_events():
        if isinstance(ev, RawResponsesStreamEvent):
            data = ev.data
            if isinstance(data, ResponseTextDeltaEvent):
                delta = data.delta or ""
                if delta:
                    answer_buf.append(delta)
                    if stream:
                        yield ("text", delta)
        elif isinstance(ev, RunItemStreamEvent):
            item = ev.item
            if isinstance(item, ToolCallItem):
                call_id, name, args = _extract_tool_call(item)
                key = call_id or f"call_{len(tool_trace)}"
                tool_started_at[key] = _time.monotonic()
                args_preview = args
                if len(args_preview) > 500:
                    args_preview = args_preview[:500] + "…"
                tool_args_cache[key] = (name, args_preview)
                if stream:
                    yield ("event", {"tool_call_started": {
                        "id": key, "tool": name, "args": args_preview,
                    }})
            elif isinstance(item, ToolCallOutputItem):
                # Tool ran = real progress; reset the spinning detector.
                recent_assistant_texts.clear()
                call_id, raw_output_text = _extract_tool_output(item)
                output_text = agent_shared.truncate_tool_output(raw_output_text)
                harvested_image_urls.extend(agent_shared.harvest_image_urls(output_text))
                key = call_id or (next(iter(tool_started_at), None) or f"call_{len(tool_trace)}")
                started = tool_started_at.pop(key, None)
                latency_ms = int((_time.monotonic() - started) * 1000) if started else None
                tool_name, args_preview = tool_args_cache.pop(key, ("unknown", ""))
                status = "error" if output_text.strip().startswith("ERROR:") else "ok"
                output_preview = output_text[:500]
                if len(output_text) > 500:
                    output_preview += "…"
                err_preview = output_text[:500] if status == "error" else None
                tool_trace.append({
                    "tool": tool_name, "args": args_preview,
                    "latency_ms": latency_ms, "status": status, "error": err_preview,
                })
                if stream:
                    yield ("event", {"tool_call_completed": {
                        "id": key, "tool": tool_name, "status": status,
                        "latency_ms": latency_ms, "output": output_preview, "error": err_preview,
                    }})
            elif isinstance(item, MessageOutputItem):
                turn_text = _extract_message_text(item)
                fallback_text_buf.append(turn_text)
                if turn_text.strip():
                    recent_assistant_texts.append(turn_text)
                    if len(recent_assistant_texts) > 3:
                        recent_assistant_texts.pop(0)

    answer = "".join(answer_buf).strip()
    if not answer:
        answer = "".join(fallback_text_buf).strip()
    if not answer:
        final = getattr(result, "final_output", None)
        if final is not None:
            answer = str(final).strip()

    if agent_shared.looks_repetitive(recent_assistant_texts):
        logger.warning("openai_agents loop: repetition guard fired for chat %s", chat_id)
        answer = (answer or "").rstrip() + "\n\n" + agent_shared.REPETITION_NOTICE

    # max-turns notice: openai_agents raises MaxTurnsExceeded inside
    # the stream; if we didn't get a final MessageOutputItem AND the
    # last RunItem was a tool call, assume we hit the cap.
    if not fallback_text_buf and tool_trace:
        answer = (answer or "").rstrip() + agent_shared.max_turns_notice(max_turns)

    answer = agent_shared.append_unreferenced_image_urls(answer, harvested_image_urls)

    if mcp_pool is not None:
        try:
            await mcp_pool.__aexit__(None, None, None)
        except Exception:
            pass

    yield ("result", {
        "answer": answer,
        "tokens": {
            "input": tokens_from_string(prompt_text),
            "output": tokens_from_string(answer),
        },
        "tool_trace": tool_trace or None,
        "stop_reason": None,
    })


async def chat(agent_self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
    chat_id = chatModel.id or str(uuid4())
    output = {
        "question": chatModel.question,
        "type": "agent",
        "sources": [],
        "guard": False,
        "tokens": {"input": 0, "output": 0},
        "project": project.props.name,
        "id": chat_id,
        "agent_loop": "openai_agents",
    }

    if agent_self.check_input_guard(project, chatModel.question, user, db, output):
        if chatModel.stream:
            yield "data: " + _json.dumps({"text": output.get("answer", "")}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
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
            project, db, agent_self,
            prompt_text=prompt_text, system_prompt=project.props.system or "",
            stream=chatModel.stream, chat_id=chat_id, image_url=image_url,
        ):
            if kind == "text":
                streamed_any_text = True
                if chatModel.stream:
                    yield "data: " + _json.dumps({"text": payload}) + "\n\n"
            elif kind == "event":
                if chatModel.stream:
                    yield "data: " + _json.dumps(payload) + "\n\n"
            elif kind == "result":
                output["answer"] = payload["answer"]
                output["tokens"] = payload["tokens"]
                if payload.get("tool_trace"):
                    output["tool_trace"] = payload["tool_trace"]
    except HTTPException as e:
        err = f"openai_agents loop config error: {e.detail}"
        output["answer"] = err
        output["status"] = "error"
        if chatModel.stream:
            yield "data: " + _json.dumps({"text": err}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return
    except Exception as e:
        logger.exception("openai_agents loop failed for project %s", project.props.name)
        err = f"openai_agents loop error: {e}"
        output["answer"] = err
        output["status"] = "error"
        if chatModel.stream:
            if not streamed_any_text:
                yield "data: " + _json.dumps({"text": err}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return

    agent_self.check_output_guard(project, user, db, output)

    agent_shared.spawn_persist_chat_turn(
        agent_self.brain, chat_id,
        agent_shared.load_chat_history(agent_self.brain, chat_id),
        chatModel.question, output.get("answer", ""),
    )

    if chatModel.stream:
        if not streamed_any_text and output.get("answer"):
            yield "data: " + _json.dumps({"text": output["answer"]}) + "\n\n"
        yield "data: " + _json.dumps(output) + "\n"
        yield "event: close\n\n"
    else:
        yield output


async def question(agent_self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper,
                   *, system_prompt: str | None = None):
    chat_id = "ephemeral-" + uuid4().hex[:12]
    output = {
        "question": questionModel.question,
        "type": "agent",
        "sources": [],
        "guard": False,
        "tokens": {"input": 0, "output": 0},
        "project": project.props.name,
        "agent_loop": "openai_agents",
    }

    if agent_self.check_input_guard(project, questionModel.question, user, db, output):
        if questionModel.stream:
            yield "data: " + _json.dumps({"text": output.get("answer", "")}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return

    prompt_text, image_url = agent_shared.route_attachments(
        getattr(questionModel, "files", None), chat_id, questionModel.question, agent_self.brain,
        existing_image=getattr(questionModel, "image", None), project=project,
    )

    streamed_any_text = False
    try:
        async for kind, payload in _drive(
            project, db, agent_self,
            prompt_text=prompt_text,
            system_prompt=system_prompt or project.props.system or "",
            stream=questionModel.stream, chat_id=chat_id, image_url=image_url,
        ):
            if kind == "text":
                streamed_any_text = True
                if questionModel.stream:
                    yield "data: " + _json.dumps({"text": payload}) + "\n\n"
            elif kind == "event":
                if questionModel.stream:
                    yield "data: " + _json.dumps(payload) + "\n\n"
            elif kind == "result":
                output["answer"] = payload["answer"]
                output["tokens"] = payload["tokens"]
                if payload.get("tool_trace"):
                    output["tool_trace"] = payload["tool_trace"]
    except HTTPException as e:
        err = f"openai_agents loop config error: {e.detail}"
        output["answer"] = err
        output["status"] = "error"
        if questionModel.stream:
            yield "data: " + _json.dumps({"text": err}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return
    except Exception as e:
        logger.exception("openai_agents loop failed for project %s", project.props.name)
        err = f"openai_agents loop error: {e}"
        output["answer"] = err
        output["status"] = "error"
        if questionModel.stream:
            if not streamed_any_text:
                yield "data: " + _json.dumps({"text": err}) + "\n\n"
            yield "data: " + _json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
        return

    agent_self.check_output_guard(project, user, db, output)

    if questionModel.stream:
        if not streamed_any_text and output.get("answer"):
            yield "data: " + _json.dumps({"text": output["answer"]}) + "\n\n"
        yield "data: " + _json.dumps(output) + "\n"
        yield "event: close\n\n"
    else:
        yield output
