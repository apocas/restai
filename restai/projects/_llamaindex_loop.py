"""LlamaIndex AgentWorkflow loop (agent_loop=llamaindex); same SSE shape as others."""

from __future__ import annotations

import json as _json
import logging
import time as _time
from uuid import uuid4

from fastapi import HTTPException
from llama_index.core.agent.workflow import (
    AgentOutput,
    AgentStream,
    FunctionAgent,
    ReActAgent,
    ToolCall,
    ToolCallResult,
)
from llama_index.core.base.llms.types import ImageBlock, TextBlock
from llama_index.core.llms import ChatMessage
from llama_index.core.tools import FunctionTool

from restai.database import DBWrapper
from restai.models.models import ChatModel, User
from restai.project import Project
from restai.projects import agent_shared
from restai.tools import tokens_from_string


logger = logging.getLogger("restai.llamaindex_loop")


def _resolve_llm(project: Project, agent_self, db: DBWrapper, llm_override: str | None = None):
    llm_name = llm_override or project.props.llm
    if not llm_name:
        raise HTTPException(400, detail="agent_loop=llamaindex requires an LLM configured on the project.")
    wrapper = agent_self.brain.get_llm(llm_name, db)
    if wrapper is None or getattr(wrapper, "llm", None) is None:
        raise HTTPException(400, detail=f"LLM '{llm_name}' not found or not loadable.")
    return wrapper.llm


def _wrap_project_tool_as_function_tool(tool_row, brain, policy) -> FunctionTool:
    """ProjectToolDatabase row → FunctionTool; runs user code in per-chat Docker sandbox."""
    tool_code = tool_row.code
    tool_name = tool_row.name
    tool_desc = tool_row.description or tool_name

    async def _run(**kwargs):
        _brain = kwargs.pop("_brain", brain)
        chat_id = kwargs.pop("_chat_id", None)
        kwargs.pop("_project_id", None)
        if not _brain or not getattr(_brain, "docker_manager", None):
            return "ERROR: Docker is not configured."
        args_json = _json.dumps(kwargs)
        script = (
            "import json, sys\n"
            "args = json.loads(sys.stdin.readline() or '{}')\n"
            f"{tool_code}"
        )
        # run_script blocks on docker exec — the policy threads it (keeps
        # the event loop free) and enforces tool_timeout + the loop guard.
        text, _err = await policy.run_async(
            tool_name, kwargs,
            call_sync=lambda: _brain.docker_manager.run_script(
                chat_id or "ephemeral", script, stdin_data=args_json,
            ),
        )
        return text

    return FunctionTool.from_defaults(
        fn=_run,
        name=tool_name,
        description=tool_desc,
        fn_schema=None,
    )


def _wrap_adapted_with_policy(li_ft: FunctionTool, policy) -> FunctionTool:
    """Re-wrap an MCP-adapted FunctionTool so its (async) call goes through
    the shared tool policy (timeout / loop guard / output cap), preserving
    the pydantic fn_schema `adapted_to_function_tool` synthesized.

    Use the tool's REAL async fn — `.fn` on an async-built FunctionTool is
    llama-index's sync bridge, whose return value is not awaitable."""
    inner_async = getattr(li_ft, "async_fn", None)
    inner_sync = li_ft.fn
    name = li_ft.metadata.name
    description = li_ft.metadata.description or name

    async def _pol(**kwargs):
        if inner_async is not None:
            text, _err = await policy.run_async(
                name, kwargs, call_async=lambda: inner_async(**kwargs),
            )
        else:
            text, _err = await policy.run_async(
                name, kwargs, call_sync=lambda: inner_sync(**kwargs),
            )
        return text

    return FunctionTool.from_defaults(
        fn=_pol,
        name=name,
        description=description,
        fn_schema=getattr(li_ft.metadata, "fn_schema", None),
    )


# Internal kwargs the LLM must never see; injected by _bind_request_kwargs.
_INTERNAL_PARAM_NAMES = {"kwargs", "_brain", "_chat_id", "_project_id"}


def _bind_request_kwargs(ft: FunctionTool, *, brain, chat_id, project_id, policy) -> FunctionTool:
    """Rebuild FunctionTool so per-request context is injected on every call.

    FunctionAgent only forwards LLM-supplied kwargs; tools like terminal /
    browser_* / create_tool read request-scoped values from **kwargs and
    would otherwise bail with "Docker is not configured". Also strips
    internal params from the schema the LLM sees, and routes every call
    through the shared ToolRunPolicy (worker thread for sync fns, timeout,
    loop guard, model-visible output cap).
    """
    import inspect as _inspect

    # `real_fn` is the original callable — for async-built FunctionTools
    # `.fn` is llama-index's sync bridge (runs on a fresh event loop).
    inner = getattr(ft, "real_fn", None) or ft.fn
    sig = _inspect.signature(inner)
    has_var_kwargs = any(
        p.kind is _inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    accepts_brain = "_brain" in sig.parameters or has_var_kwargs
    accepts_chat = "_chat_id" in sig.parameters or has_var_kwargs
    accepts_project = "_project_id" in sig.parameters or has_var_kwargs
    is_async = _inspect.iscoroutinefunction(inner)
    name = ft.metadata.name
    description = ft.metadata.description or name

    async def _bound(**kwargs):
        visible_args = {
            k: v for k, v in kwargs.items()
            if k not in _INTERNAL_PARAM_NAMES and not k.startswith("_")
        }
        if accepts_brain and "_brain" not in kwargs:
            kwargs["_brain"] = brain
        if accepts_chat and "_chat_id" not in kwargs:
            kwargs["_chat_id"] = chat_id
        if accepts_project and "_project_id" not in kwargs:
            kwargs["_project_id"] = project_id
        if is_async:
            text, _err = await policy.run_async(
                name, visible_args, call_async=lambda: inner(**kwargs),
            )
        else:
            text, _err = await policy.run_async(
                name, visible_args, call_sync=lambda: inner(**kwargs),
            )
        return text

    # Clean signature so llama-index only introspects LLM-visible params
    # (skip internal **kwargs + explicit _brain/_chat_id/_project_id).
    visible_params = [
        p for p in sig.parameters.values()
        if p.kind is not _inspect.Parameter.VAR_KEYWORD
        and p.name not in _INTERNAL_PARAM_NAMES
    ]
    _bound.__signature__ = _inspect.Signature(parameters=visible_params)
    _bound.__name__ = name
    _bound.__doc__ = inner.__doc__

    return FunctionTool.from_defaults(fn=_bound, name=name, description=description)


def _gather_tools(project: Project, agent_self, db: DBWrapper, chat_id: str, policy) -> list[FunctionTool]:
    raw_names = {
        t.strip() for t in (project.props.options.tools or "").split(",") if t.strip()
    }
    raw_builtins = agent_self.brain.get_tools(raw_names) if raw_names else []
    builtins: list[FunctionTool] = []
    for ft in raw_builtins:
        try:
            builtins.append(_bind_request_kwargs(
                ft, brain=agent_self.brain, chat_id=chat_id, project_id=project.props.id,
                policy=policy,
            ))
        except Exception as e:
            logger.warning("Failed to wrap builtin %s: %s", getattr(ft.metadata, "name", "?"), e)

    custom: list[FunctionTool] = []
    try:
        for row in db.get_project_tools(project.props.id) or []:
            if getattr(row, "enabled", True):
                try:
                    custom.append(_wrap_project_tool_as_function_tool(row, agent_self.brain, policy))
                except Exception as e:
                    logger.warning("Failed to wrap project tool %s: %s", row.name, e)
    except Exception:
        pass
    return builtins + custom


def _pick_agent_class(project: Project):
    """agent_mode: 'react' → ReActAgent; anything else → FunctionAgent."""
    mode = (getattr(project.props.options, "agent_mode", None) or "auto").lower()
    return ReActAgent if mode == "react" else FunctionAgent


async def _drive(project, db, agent_self, *, prompt_text: str, system_prompt: str,
                 stream: bool, chat_id: str, image_url: str | None = None,
                 llm_override: str | None = None, run_state: dict | None = None):
    """Async generator yielding (kind, payload) tuples; same protocol as _claude_sdk_loop._drive."""
    from restai.agent2.mcp_client import MCPSessionPool

    llm = _resolve_llm(project, agent_self, db, llm_override)
    policy = agent_shared.ToolRunPolicy(project)
    tools = _gather_tools(project, agent_self, db, chat_id, policy)

    augmented = agent_shared.augment_system_prompt_with_memory_bank(project, db, system_prompt)
    augmented = agent_shared.augment_system_prompt_with_memory_search_hint(project, augmented)
    augmented = agent_shared.prepend_current_time(augmented)

    history = agent_shared.load_chat_history(agent_self.brain, chat_id)

    mcp_servers = getattr(project.props.options, "mcp_servers", None) or []
    mcp_pool = None
    if mcp_servers:
        try:
            mcp_pool = MCPSessionPool()
            await mcp_pool.__aenter__()
            adapted_tools = await mcp_pool.connect_servers(mcp_servers)
            for a in adapted_tools:
                try:
                    tools.append(_wrap_adapted_with_policy(
                        agent_shared.adapted_to_function_tool(a), policy,
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

    AgentCls = _pick_agent_class(project)
    agent = AgentCls(
        name="restai_agent",
        llm=llm,
        tools=tools,
        system_prompt=augmented or "",
        streaming=stream,
    )
    max_iters = int(getattr(project.props.options, "max_iterations", 10) or 10)

    tool_started_at: dict[str, float] = {}
    harvested_image_urls: list[str] = []
    recent_assistant_texts: list[str] = []
    tool_trace: list[dict] = []
    answer_buf: list[str] = []
    final_output = None
    # thinking_delta arrives as many tiny chunks; wrapping each in its own
    # <think>…</think> would make post_processing_reasoning split them into
    # one thought per delta. Track open/close so the whole stream collapses.
    thinking_open = False

    def _close_thinking_if_open(buf, want_stream):
        nonlocal thinking_open
        if not thinking_open:
            return None
        thinking_open = False
        closer = "</think>"
        buf.append(closer)
        return closer if want_stream else None

    # Image attachments piggyback on the chat_history slot — FunctionAgent.run
    # takes user_msg as a string only with no separate images= kwarg. The
    # image becomes the LAST user message so prompt + image arrive together.
    decoded = agent_shared.parse_data_url(image_url) if image_url else None
    if decoded is not None:
        mime, raw = decoded
        try:
            multimodal_msg = ChatMessage(
                role="user",
                blocks=[
                    TextBlock(text=prompt_text),
                    ImageBlock(image=raw, image_mimetype=mime),
                ],
            )
            handler = agent.run(
                user_msg=None,
                chat_history=(history or []) + [multimodal_msg],
                max_iterations=max_iters,
            )
        except Exception as e:
            logger.warning("llamaindex loop: failed to wire image block: %s", e)
            handler = agent.run(user_msg=prompt_text, chat_history=history or None,
                                max_iterations=max_iters)
    else:
        handler = agent.run(user_msg=prompt_text, chat_history=history or None,
                            max_iterations=max_iters)

    hit_max_iterations = False
    events_iter = handler.stream_events().__aiter__()
    while True:
        try:
            ev = await events_iter.__anext__()
        except StopAsyncIteration:
            break
        except Exception as e:
            # The workflow raises WorkflowRuntimeError("Max iterations of N
            # reached! …") when the cap hits — convert to the standard
            # "say continue" notice instead of failing the whole run (tool
            # side effects have already happened; retrying isn't safe).
            if "max iterations" in str(e).lower():
                hit_max_iterations = True
                logger.info("llamaindex loop: max_iterations (%d) reached for chat %s",
                            max_iters, chat_id)
                break
            raise
        if isinstance(ev, AgentStream):
            thinking = getattr(ev, "thinking_delta", None) or ""
            if thinking:
                if not thinking_open:
                    thinking_open = True
                    chunk = f"<think>{thinking}"
                else:
                    chunk = thinking
                answer_buf.append(chunk)
                if stream:
                    yield ("text", chunk)
            delta = ev.delta or ""
            if delta:
                closer = _close_thinking_if_open(answer_buf, stream)
                if closer and stream:
                    yield ("text", closer)
                answer_buf.append(delta)
                if stream:
                    yield ("text", delta)
        elif isinstance(ev, ToolCall) and not isinstance(ev, ToolCallResult):
            closer = _close_thinking_if_open(answer_buf, stream)
            if closer and stream:
                yield ("text", closer)
            if run_state is not None:
                run_state["tools_executed"] = run_state.get("tools_executed", 0) + 1
            tool_started_at[ev.tool_id] = _time.monotonic()
            try:
                args_preview = _json.dumps(ev.tool_kwargs, default=str)
            except Exception:
                args_preview = str(ev.tool_kwargs)
            if len(args_preview) > 500:
                args_preview = args_preview[:500] + "…"
            if stream:
                yield ("event", {"tool_call_started": {
                    "id": ev.tool_id, "tool": ev.tool_name, "args": args_preview,
                }})
        elif isinstance(ev, ToolCallResult):
            # Tool ran = real progress; reset the spinning detector.
            recent_assistant_texts.clear()
            started = tool_started_at.pop(ev.tool_id, None)
            latency_ms = int((_time.monotonic() - started) * 1000) if started else None
            raw_output_text = str(ev.tool_output) if ev.tool_output is not None else ""
            output_text = agent_shared.truncate_tool_output(raw_output_text)
            harvested_image_urls.extend(agent_shared.harvest_image_urls(output_text))
            status = "error" if output_text.strip().startswith("ERROR:") else "ok"
            try:
                args_preview = _json.dumps(ev.tool_kwargs, default=str)
            except Exception:
                args_preview = str(ev.tool_kwargs)
            if len(args_preview) > 500:
                args_preview = args_preview[:500] + "…"
            output_preview = output_text[:500]
            if len(output_text) > 500:
                output_preview += "…"
            err_preview = output_text[:500] if status == "error" else None
            tool_trace.append({
                "tool": ev.tool_name, "args": args_preview,
                "latency_ms": latency_ms, "status": status, "error": err_preview,
            })
            if stream:
                yield ("event", {"tool_call_completed": {
                    "id": ev.tool_id, "tool": ev.tool_name, "status": status,
                    "latency_ms": latency_ms, "output": output_preview, "error": err_preview,
                }})
        elif isinstance(ev, AgentOutput):
            final_output = ev
            try:
                resp = getattr(final_output, "response", None)
                turn_text = str(getattr(resp, "content", "") or resp).strip() if resp else ""
            except Exception:
                turn_text = ""
            if turn_text:
                recent_assistant_texts.append(turn_text)
                if len(recent_assistant_texts) > 3:
                    recent_assistant_texts.pop(0)
                if agent_shared.looks_repetitive(recent_assistant_texts):
                    logger.warning("llamaindex loop: repetition guard fired for chat %s", chat_id)
                    answer_buf.append("\n\n" + agent_shared.REPETITION_NOTICE)
                    if stream:
                        yield ("text", "\n\n" + agent_shared.REPETITION_NOTICE)
                    break

    closer = _close_thinking_if_open(answer_buf, stream)
    if closer and stream:
        yield ("text", closer)

    answer = "".join(answer_buf).strip()
    if not answer and final_output is not None:
        resp = getattr(final_output, "response", None)
        if resp is not None:
            answer = str(getattr(resp, "content", "") or resp).strip()

    if hit_max_iterations:
        answer = (answer or "").rstrip() + agent_shared.max_turns_notice(max_iters)

    answer = agent_shared.append_unreferenced_image_urls(answer, harvested_image_urls)

    if mcp_pool is not None:
        try:
            await mcp_pool.__aexit__(None, None, None)
        except Exception:
            pass

    # Transcript-aware estimate (question + system prompt + history + tool
    # round-trip), floored by any real usage the final raw response carried
    # (last call only → accuracy "medium"; nothing → "low").
    est_input = agent_shared.estimate_input_tokens(
        prompt_text, system_prompt=augmented or "",
        history=history, tool_trace=tool_trace,
    )
    est_output = tokens_from_string(answer)
    real = agent_shared.usage_from_raw_response(getattr(final_output, "raw", None))
    if real is not None:
        tokens = {
            "input": max(est_input, real[0]),
            "output": max(est_output, real[1]),
            "accuracy": "medium",
        }
    else:
        tokens = {"input": est_input, "output": est_output, "accuracy": "low"}

    yield ("result", {
        "answer": answer,
        "tokens": tokens,
        "tool_trace": tool_trace or None,
        "stop_reason": "max_turns" if hit_max_iterations else None,
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
        "agent_loop": "llamaindex",
    }

    # Container + session below are keyed by this scoped id (bound to the
    # authenticated user + project) so users can't collide on a shared
    # chat_id and reach each other's sandbox. The client already got the raw
    # id via output["id"] above.
    chat_id = agent_shared.sandbox_chat_id(project.props.id, user.id, chat_id)

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

    def _factory(llm_override, run_state):
        return _drive(
            project, db, agent_self,
            prompt_text=prompt_text, system_prompt=(chatModel.system or project.props.system or ""),
            stream=chatModel.stream, chat_id=chat_id, image_url=image_url,
            llm_override=llm_override, run_state=run_state,
        )

    async for kind, payload in agent_shared.drive_with_fallbacks(
        project, _factory, loop_name="llamaindex", output=output,
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
        elif kind == "error":
            e = payload["exception"]
            if isinstance(e, HTTPException):
                err = f"llamaindex loop config error: {e.detail}"
            else:
                err = f"llamaindex loop error: {e}"
            output["answer"] = err
            output["status"] = "error"
            output["error"] = err
            if chatModel.stream:
                if not streamed_any_text:
                    yield "data: " + _json.dumps({"text": err}) + "\n\n"
                yield "data: " + _json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                yield output
            return

    agent_self.check_output_guard(project, user, db, output)

    # Fire-and-forget persist so a Starlette cancel during the final
    # yield doesn't drop the just-completed turn.
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

