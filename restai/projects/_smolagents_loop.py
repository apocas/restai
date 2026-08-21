"""smolagents loop (agent_loop=smolagents) — prefers OpenAIServerModel; LiteLLM fallback."""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from uuid import uuid4

from fastapi import HTTPException
from smolagents import LiteLLMModel, OpenAIServerModel, ToolCallingAgent, Tool
from smolagents.agents import ToolOutput
from smolagents.memory import ActionStep, FinalAnswerStep, PlanningStep
from smolagents.memory import ToolCall as SmolToolCall
from smolagents.models import ChatMessageStreamDelta

from restai.database import DBWrapper
from restai.models.models import ChatModel, LLMModel, User
from restai.project import Project
from restai.projects import agent_shared
from restai.tools import tokens_from_string


logger = logging.getLogger("restai.smolagents_loop")


# Internal params; must not leak to LLM as call arguments.
_INTERNAL_PARAM_NAMES = {"kwargs", "_brain", "_chat_id", "_project_id"}


# JSON-schema → smolagents inputs.type. Accepts:
# "string" | "integer" | "number" | "boolean" | "array" | "object" | "any".
_JSON_TYPE_MAP = {
    "string": "string", "str": "string",
    "integer": "integer", "int": "integer",
    "number": "number", "float": "number",
    "boolean": "boolean", "bool": "boolean",
    "array": "array", "list": "array",
    "object": "object", "dict": "object",
}


def _llama_schema_to_smolagents_inputs(fn_schema: dict) -> dict:
    """Convert llama-index FunctionTool JSON schema → smolagents inputs dict."""
    if not isinstance(fn_schema, dict):
        return {}
    props = fn_schema.get("properties") or {}
    required = set(fn_schema.get("required") or [])
    out: dict[str, dict] = {}
    for name, spec in props.items():
        if name in _INTERNAL_PARAM_NAMES:
            continue
        if not isinstance(spec, dict):
            continue
        raw_t = spec.get("type")
        if isinstance(raw_t, list):
            # smolagents needs a single type; pick first non-null.
            raw_t = next((t for t in raw_t if t and t != "null"), raw_t[0] if raw_t else "string")
        ttype = _JSON_TYPE_MAP.get(str(raw_t or "string").lower(), "string")
        entry = {
            "type": ttype,
            "description": spec.get("description") or name,
        }
        if name not in required:
            entry["nullable"] = True
        out[name] = entry
    return out


def _function_tool_schema(ft) -> dict:
    """Extract JSON schema from a llama-index FunctionTool."""
    try:
        meta = ft.metadata
        if hasattr(meta, "get_parameters_dict"):
            schema = meta.get_parameters_dict()
            if schema:
                return schema
        if hasattr(meta, "fn_schema_str") and meta.fn_schema_str:
            try:
                return _json.loads(meta.fn_schema_str)
            except Exception:
                pass
        if hasattr(meta, "fn_schema") and meta.fn_schema is not None:
            return meta.fn_schema.schema()
    except Exception:
        pass
    return {"type": "object", "properties": {}}


def _wrap_function_tool(ft, *, brain, chat_id, project_id, policy, main_loop=None,
                        inject_context: bool = True) -> Tool:
    """Wrap a llama-index FunctionTool as a smolagents Tool subclass."""
    import inspect

    # `real_fn` is the original callable — for async-built FunctionTools
    # (MCP-adapted tools) `.fn` is llama-index's sync bridge which runs the
    # coroutine on a FRESH event loop, breaking MCP sessions bound to the
    # request's loop.
    inner = getattr(ft, "real_fn", None) or ft.fn
    sig = inspect.signature(inner)
    has_var_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    # inject_context=False for MCP-adapted tools: their **kwargs go verbatim
    # to the remote server, and an injected `_brain` (unserializable) would
    # fail every call.
    accepts_brain = inject_context and ("_brain" in sig.parameters or has_var_kwargs)
    accepts_chat = inject_context and ("_chat_id" in sig.parameters or has_var_kwargs)
    accepts_project = inject_context and ("_project_id" in sig.parameters or has_var_kwargs)
    is_async = inspect.iscoroutinefunction(inner)

    tool_name = ft.metadata.name
    tool_desc = ft.metadata.description or tool_name
    schema = _function_tool_schema(ft)
    inputs_dict = _llama_schema_to_smolagents_inputs(schema)

    # smolagents validates at __init_subclass__ time, so produce one concrete
    # class per FunctionTool (not just instances).
    def _forward(self, **kwargs):
        visible_args = dict(kwargs)
        if accepts_brain and "_brain" not in kwargs:
            kwargs["_brain"] = brain
        if accepts_chat and "_chat_id" not in kwargs:
            kwargs["_chat_id"] = chat_id
        if accepts_project and "_project_id" not in kwargs:
            kwargs["_project_id"] = project_id
        # smolagents drives tools synchronously from its own worker thread;
        # the policy adds tool_timeout, the loop guard, and the output cap.
        # Async fns run on the REQUEST's event loop when we have it (MCP
        # sessions are bound to that loop — a fresh asyncio.run loop breaks
        # them); the main loop is free while the agent blocks in its
        # executor, so run_coroutine_threadsafe can't deadlock here.
        if is_async and main_loop is not None:
            call = lambda: asyncio.run_coroutine_threadsafe(  # noqa: E731
                inner(**kwargs), main_loop,
            ).result()
        elif is_async:
            call = lambda: asyncio.run(inner(**kwargs))  # noqa: E731
        else:
            call = lambda: inner(**kwargs)  # noqa: E731
        text, _err = policy.run_sync(tool_name, visible_args, call)
        return text

    cls = type(
        f"PlatformTool_{tool_name}",
        (Tool,),
        {
            "name": tool_name,
            "description": tool_desc,
            "inputs": inputs_dict,
            "output_type": "string",
            "forward": _forward,
            # smolagents validates forward() param names match `inputs` keys.
            # Our wrapper uses **kwargs so the validator would reject every
            # tool, leaving only `final_answer`. Same escape hatch as
            # smolagents' own LangChainToolWrapper / SpaceToolWrapper.
            "skip_forward_signature_validation": True,
        },
    )
    return cls()


def _wrap_project_tool(row, *, brain, chat_id, policy) -> Tool:
    """ProjectToolDatabase row → smolagents Tool that runs user code in per-chat Docker sandbox."""
    try:
        schema = (
            _json.loads(row.parameters)
            if isinstance(row.parameters, str)
            else (row.parameters or {"type": "object", "properties": {}})
        )
    except (_json.JSONDecodeError, TypeError):
        schema = {"type": "object", "properties": {}}

    tool_code = row.code
    tool_name = row.name
    tool_desc = row.description or tool_name
    inputs_dict = _llama_schema_to_smolagents_inputs(schema)

    def _forward(self, **kwargs):
        if not brain or not getattr(brain, "docker_manager", None):
            return "ERROR: Docker is not configured."
        args_json = _json.dumps(kwargs)
        script = (
            "import json, sys\n"
            "args = json.loads(sys.stdin.readline() or '{}')\n"
            f"{tool_code}"
        )
        text, _err = policy.run_sync(
            tool_name, dict(kwargs),
            lambda: brain.docker_manager.run_script(
                chat_id or "ephemeral", script, stdin_data=args_json,
            ),
        )
        return text

    cls = type(
        f"ProjectTool_{tool_name}",
        (Tool,),
        {
            "name": tool_name,
            "description": tool_desc,
            "inputs": inputs_dict,
            "output_type": "string",
            "forward": _forward,
            "skip_forward_signature_validation": True,
        },
    )
    return cls()


def _gather_tools(project: Project, agent_self, db: DBWrapper, chat_id: str, policy,
                  main_loop=None) -> list[Tool]:
    raw_names = {
        t.strip() for t in (project.props.options.tools or "").split(",") if t.strip()
    }
    builtins = agent_self.brain.get_tools(raw_names) if raw_names else []

    tools: list[Tool] = []
    for ft in builtins:
        try:
            tools.append(_wrap_function_tool(
                ft, brain=agent_self.brain, chat_id=chat_id, project_id=project.props.id,
                policy=policy, main_loop=main_loop,
            ))
        except Exception as e:
            logger.warning("Failed to wrap builtin %s: %s", getattr(ft.metadata, "name", "?"), e)

    try:
        for row in db.get_project_tools(project.props.id) or []:
            if not getattr(row, "enabled", True):
                continue
            try:
                tools.append(_wrap_project_tool(row, brain=agent_self.brain, chat_id=chat_id, policy=policy))
            except Exception as e:
                logger.warning("Failed to wrap project tool %s: %s", row.name, e)
    except Exception:
        pass
    return tools


def _build_model(project: Project, db: DBWrapper, llm_override: str | None = None):
    """Resolve project LLM into smolagents Model; direct OpenAIServerModel
    when possible avoids LiteLLM bridge + spurious 'Calling tools: [...]'
    text leakage. LiteLLMModel only for Anthropic / Gemini / Bedrock.
    """
    llm_name = llm_override or project.props.llm
    if not llm_name:
        raise HTTPException(400, detail="agent_loop=smolagents requires an LLM configured on the project.")
    llm_db = db.get_llm_by_name(llm_name)
    if llm_db is None:
        raise HTTPException(400, detail=f"LLM '{llm_name}' not found.")

    options = LLMModel.model_validate(llm_db).options or {}
    api_key = options.get("api_key")
    base_url = options.get("base_url") or options.get("api_base")
    raw_model = options.get("model") or options.get("model_name") or llm_name
    cls = llm_db.class_name

    if cls in {"OpenAI", "OpenAILike", "AzureOpenAI", "vLLM", "Grok"}:
        if cls == "Grok":
            api_base = base_url or "https://api.x.ai/v1"
        elif cls == "AzureOpenAI":
            api_base = base_url
        else:
            api_base = base_url
        return OpenAIServerModel(
            model_id=raw_model, api_base=api_base, api_key=api_key,
        )

    if cls in {"Ollama", "OllamaCloud", "OllamaMultiModal", "OllamaMultiModal2"}:
        # api_key is ignored by local Ollama but OpenAIServerModel requires
        # a non-empty string.
        is_cloud = cls == "OllamaCloud"
        host = base_url or ("https://ollama.com" if is_cloud else "http://localhost:11434")
        api_base_ollama = host.rstrip("/")
        if not api_base_ollama.endswith("/v1"):
            api_base_ollama = api_base_ollama + "/v1"
        return OpenAIServerModel(
            model_id=raw_model,
            api_base=api_base_ollama,
            api_key=api_key or "ollama",
            # Some Ollama models reject vision-style content arrays even for
            # text-only messages — flatten guarantees plain string.
            flatten_messages_as_text=True,
        )

    if cls == "LiteLLM":
        return LiteLLMModel(model_id=raw_model, api_key=api_key, api_base=base_url)

    # Last-resort LiteLLM bridge for non-OpenAI-shape providers.
    if cls == "Anthropic":
        prefixed = raw_model if raw_model.startswith("anthropic/") else f"anthropic/{raw_model}"
        return LiteLLMModel(model_id=prefixed, api_key=api_key, api_base=base_url)
    if cls in {"Gemini", "GeminiMultiModal"}:
        prefixed = raw_model if raw_model.startswith("gemini/") else f"gemini/{raw_model}"
        return LiteLLMModel(model_id=prefixed, api_key=api_key, api_base=base_url)
    if cls == "Bedrock":
        prefixed = raw_model if raw_model.startswith("bedrock/") else f"bedrock/{raw_model}"
        return LiteLLMModel(model_id=prefixed, api_key=api_key, api_base=base_url)

    raise HTTPException(
        400,
        detail=(
            f"agent_loop=smolagents has no mapping for LLM class '{cls}'. "
            f"Switch the project's LLM or pick a different agent_loop."
        ),
    )


async def _drive(project, db, agent_self, *, prompt_text: str, system_prompt: str,
                 stream: bool, chat_id: str, image_url: str | None = None,
                 llm_override: str | None = None, run_state: dict | None = None):
    """Async generator yielding (kind, payload) tuples; same protocol as other loops."""
    from restai.agent2.mcp_client import MCPSessionPool

    model = _build_model(project, db, llm_override)
    policy = agent_shared.ToolRunPolicy(project)
    main_loop = asyncio.get_running_loop()
    tools = _gather_tools(project, agent_self, db, chat_id, policy, main_loop=main_loop)

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
                        policy=policy, main_loop=main_loop, inject_context=False,
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

    history = agent_shared.load_chat_history(agent_self.brain, chat_id)
    history_block = agent_shared.chat_history_as_text(history)
    if history_block:
        augmented = f"{augmented}\n\n{history_block}" if augmented else history_block

    max_steps = int(getattr(project.props.options, "max_iterations", 20) or 20)

    agent = ToolCallingAgent(
        tools=tools,
        model=model,
        instructions=augmented or None,
        max_steps=max_steps,
        stream_outputs=stream,
    )

    tool_started_at: dict[str, float] = {}
    harvested_image_urls: list[str] = []
    recent_assistant_texts: list[str] = []
    hit_max_steps = False
    tool_args_cache: dict[str, str] = {}
    tool_trace: list[dict] = []
    answer_buf: list[str] = []
    final_answer = None
    input_tokens = 0
    output_tokens = 0
    # Each step is: model streams text (reasoning) → ToolCall (often
    # `final_answer` carrying the actual response). Wrap reasoning deltas in
    # <think>…</think> with open/close so the whole stream collapses into
    # one thought per step.
    thinking_open = False

    def _close_thinking_if_open():
        nonlocal thinking_open
        if not thinking_open:
            return None
        thinking_open = False
        closer = "</think>"
        answer_buf.append(closer)
        return closer

    def _scrub_think_tags(text: str) -> str:
        """Strip model-emitted <think> markers (Qwen3 / DeepSeek-R1 style).

        Without scrubbing we get nested <think><think>…</think>…</think> and
        brain.py's non-greedy regex matches the inner pair — leaving a
        dangling </think> and the rest of the text in the answer column.
        Bracket form preserves visual reading in the Thoughts panel without
        breaking our wrapping markers.
        """
        if not text:
            return text
        return text.replace("<think>", "[think]").replace("</think>", "[/think]")

    # MultiStepAgent.run takes images=[PIL.Image, ...] natively.
    pil_images = []
    decoded = agent_shared.parse_data_url(image_url) if image_url else None
    if decoded is not None:
        try:
            from io import BytesIO
            from PIL import Image as _PILImage
            _mime, raw = decoded
            pil_images.append(_PILImage.open(BytesIO(raw)))
        except Exception as e:
            logger.warning("smolagents loop: failed to decode attached image: %s", e)

    loop = asyncio.get_running_loop()
    # ToolCallingAgent.run(stream=True) returns a SYNC generator that blocks
    # per step on LLM calls. Wrap in a thread so we don't stall the event
    # loop and other SSE writes can flush.
    sync_gen = await loop.run_in_executor(
        None, lambda: agent.run(
            task=prompt_text, stream=True, max_steps=max_steps,
            images=pil_images or None,
        ),
    )

    def _next():
        try:
            return next(sync_gen)
        except StopIteration:
            return _SENTINEL

    max_exec = agent_shared.max_execution_seconds(project)
    # drive_with_fallbacks hands every attempt the SAME request-wide deadline
    # so a fallback retry can't reset the wall-clock budget.
    deadline = run_state.get("deadline") if run_state else None
    if deadline is None and max_exec:
        deadline = _time.monotonic() + max_exec
    hit_max_time = False

    gen_exhausted = False
    while True:
        # Wall-clock cap: stop before pulling the next step. Gated on
        # final_answer: once the model produced its answer, the remaining
        # events are cheap bookkeeping (final-step usage, FinalAnswerStep) —
        # draining them keeps accounting complete and avoids bolting the
        # "stopped early" notice onto a finished run.
        if (final_answer is None and deadline is not None
                and _time.monotonic() >= deadline):
            hit_max_time = True
            logger.info("smolagents loop: max_execution_time (%ds) reached for chat %s",
                        int(max_exec), chat_id)
            break
        ev = await loop.run_in_executor(None, _next)
        if ev is _SENTINEL:
            gen_exhausted = True
            break
        if isinstance(ev, ChatMessageStreamDelta):
            delta = _scrub_think_tags(ev.content or "")
            if delta:
                if not thinking_open:
                    thinking_open = True
                    chunk = f"<think>{delta}"
                else:
                    chunk = delta
                answer_buf.append(chunk)
                if stream:
                    yield ("text", chunk)
        elif isinstance(ev, SmolToolCall):
            # Close any thinking block so the buffer stays well-formed.
            closer = _close_thinking_if_open()
            if closer and stream:
                yield ("text", closer)
            # `final_answer` is a virtual tool — its `answer` kwarg IS the
            # response. Suppress from tool panel; pull text into final answer.
            if ev.name == "final_answer":
                ans = (ev.arguments or {}).get("answer")
                if ans:
                    final_answer = str(ans)
                continue
            if run_state is not None:
                run_state["tools_executed"] = run_state.get("tools_executed", 0) + 1
            tool_id = getattr(ev, "id", None) or f"call_{len(tool_trace)}"
            tool_started_at[tool_id] = _time.monotonic()
            try:
                args_preview = _json.dumps(ev.arguments, default=str)
            except Exception:
                args_preview = str(ev.arguments)
            if len(args_preview) > 500:
                args_preview = args_preview[:500] + "…"
            tool_args_cache[tool_id] = args_preview
            if stream:
                yield ("event", {"tool_call_started": {
                    "id": tool_id, "tool": ev.name, "args": args_preview,
                }})
        elif isinstance(ev, ToolOutput):
            tool_name = getattr(ev.tool_call, "name", "unknown")
            # Skip synthetic final_answer so its bookkeeping doesn't pollute
            # the tool trace.
            if tool_name == "final_answer":
                if final_answer is None and ev.output is not None:
                    final_answer = str(ev.output)
                continue
            # Tool ran = real progress; reset the spinning detector.
            recent_assistant_texts.clear()
            tool_id = getattr(ev, "id", None) or f"call_{len(tool_trace)}"
            started = tool_started_at.pop(tool_id, None)
            latency_ms = int((_time.monotonic() - started) * 1000) if started else None
            raw_observation = ev.observation or (str(ev.output) if ev.output is not None else "")
            observation = agent_shared.truncate_tool_output(raw_observation)
            harvested_image_urls.extend(agent_shared.harvest_image_urls(observation))
            status = "error" if observation.strip().startswith("ERROR:") else "ok"
            args_preview = tool_args_cache.pop(tool_id, "")
            output_preview = observation[:500]
            if len(observation) > 500:
                output_preview += "…"
            err_preview = observation[:500] if status == "error" else None
            tool_trace.append({
                "tool": tool_name, "args": args_preview,
                "latency_ms": latency_ms, "status": status, "error": err_preview,
            })
            if stream:
                yield ("event", {"tool_call_completed": {
                    "id": tool_id, "tool": tool_name, "status": status,
                    "latency_ms": latency_ms, "output": output_preview, "error": err_preview,
                }})
        elif isinstance(ev, ActionStep):
            usage = getattr(ev, "token_usage", None)
            if usage is not None:
                input_tokens += getattr(usage, "input_tokens", 0) or 0
                output_tokens += getattr(usage, "output_tokens", 0) or 0
            try:
                turn_text = str(getattr(ev, "model_output", None) or "").strip()
            except Exception:
                turn_text = ""
            if turn_text:
                recent_assistant_texts.append(turn_text)
                if len(recent_assistant_texts) > 3:
                    recent_assistant_texts.pop(0)
                if agent_shared.looks_repetitive(recent_assistant_texts):
                    logger.warning("smolagents loop: repetition guard fired for chat %s", chat_id)
                    answer_buf.append("\n\n" + agent_shared.REPETITION_NOTICE)
                    if stream:
                        yield ("text", "\n\n" + agent_shared.REPETITION_NOTICE)
                    final_answer = (final_answer or "") + "\n\n" + agent_shared.REPETITION_NOTICE
                    break
            if getattr(ev, "error", None) is not None and "AgentMaxStepsError" in type(ev.error).__name__:
                hit_max_steps = True
        elif isinstance(ev, PlanningStep):
            usage = getattr(ev, "token_usage", None)
            if usage is not None:
                input_tokens += getattr(usage, "input_tokens", 0) or 0
                output_tokens += getattr(usage, "output_tokens", 0) or 0
        elif isinstance(ev, FinalAnswerStep):
            final_answer = ev.output

    # Close an unexhausted generator explicitly IN A WORKER THREAD (fire and
    # forget). Leaving it to GC would run gen.close() on the event loop
    # thread — and when the generator is suspended inside smolagents'
    # parallel-tool ThreadPoolExecutor with-block, close blocks until every
    # in-flight tool thread finishes (indefinitely with tool_timeout=0),
    # which would freeze the whole event loop. Not awaited: a blocked close
    # must not hold this request's capped response hostage either.
    if not gen_exhausted:
        def _close_gen():
            try:
                sync_gen.close()
            except Exception:
                pass
        close_future = loop.run_in_executor(None, _close_gen)
        close_future.add_done_callback(lambda f: f.exception())

    # Close any trailing thinking block.
    closer = _close_thinking_if_open()
    if closer and stream:
        yield ("text", closer)

    # `answer_buf` holds reasoning wrapped in <think>…</think> for
    # post_processing_reasoning to lift into the Thoughts panel. Actual
    # answer comes from final_answer tool call's `answer` kwarg (or
    # FinalAnswerStep.output as fallback).
    reasoning_block = "".join(answer_buf).strip()
    if final_answer is not None:
        answer = reasoning_block + ("\n\n" if reasoning_block else "") + str(final_answer).strip()
    else:
        answer = reasoning_block

    if (hit_max_steps and not hit_max_time
            and not (final_answer or "").strip().endswith(agent_shared.REPETITION_NOTICE.strip())):
        answer = (answer or "").rstrip() + agent_shared.max_turns_notice(max_steps)

    if hit_max_time:
        answer = (answer or "").rstrip() + agent_shared.max_time_notice(max_exec)

    answer = agent_shared.append_unreferenced_image_urls(answer, harvested_image_urls)

    if mcp_pool is not None:
        try:
            await mcp_pool.__aexit__(None, None, None)
        except Exception:
            pass

    # Real per-step usage accumulated from ActionStep/PlanningStep token_usage
    # (accuracy "high"); estimate fallback mirrors the other loops (system
    # prompt already carries the rendered history + memory injections).
    if input_tokens or output_tokens:
        tokens = {"input": input_tokens, "output": output_tokens, "accuracy": "high"}
    else:
        tokens = {
            "input": agent_shared.estimate_input_tokens(
                prompt_text, system_prompt=augmented or "", tool_trace=tool_trace,
            ),
            "output": tokens_from_string(answer),
            "accuracy": "low",
        }

    yield ("result", {
        "answer": answer,
        "tokens": tokens,
        "tool_trace": tool_trace or None,
        "stop_reason": (
            "max_time" if hit_max_time
            else ("max_turns" if hit_max_steps else None)
        ),
    })


_SENTINEL = object()


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
        "agent_loop": "smolagents",
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
        project, _factory, loop_name="smolagents", output=output,
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
            if payload.get("stop_reason"):
                output["stop_reason"] = payload["stop_reason"]
        elif kind == "error":
            e = payload["exception"]
            if isinstance(e, HTTPException):
                err = f"smolagents loop config error: {e.detail}"
            else:
                err = f"smolagents loop error: {e}"
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

