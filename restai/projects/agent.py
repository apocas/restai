"""agent project type — direct LLM chat with optional tool calling.

Built on the agent2 runtime (`restai.agent2`), which is the non-llamaindex
agent loop. Supports built-in tools, MCP servers, multimodal image input,
fallback LLMs, output guards, history compression, ReAct fallback for
tool-callless models, and token-by-token streaming.

Agent projects without any tools configured behave like a plain LLM chat —
the runtime exits after one turn with no extra overhead. Add tools or MCP
servers in the project's Tools tab to turn them into actual agents.
"""
import asyncio
import json
import logging
import re
from uuid import uuid4

from fastapi import HTTPException

from restai.agent2 import (
    Agent2Runtime,
    Agent2UnsupportedLLMError,
    MCPSessionPool,
    adapt_function_tools,
    build_provider_for_llm,
)
from restai.agent2.memory import get_session, save_session
from restai.agent2.tool_adapter import AdaptedTool
from restai.agent2.types import ImageBlock, ToolUseBlock
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.tools import tokens_from_string
from restai import memory_bank


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _is_image_attachment(f) -> bool:
    """True if the attachment should go through the multimodal vision flow."""
    mime = (getattr(f, "mime_type", None) or "").lower()
    if mime.startswith("image/"):
        return True
    name = (getattr(f, "name", "") or "").lower()
    return name.endswith(_IMAGE_EXTS)


def _augment_system_prompt_with_memory_bank(project, db, base_system_prompt: str | None) -> str | None:
    """When the project has memory_bank_enabled, prepend the rendered memory
    bank block to the system prompt. Cheap on the no-bank-yet path: a single
    indexed query that returns zero rows yields an empty string immediately.
    Failures degrade silently — the worst case is the LLM not seeing memory
    on this turn, never a broken request."""
    try:
        if not getattr(project.props.options, "memory_bank_enabled", False):
            return base_system_prompt
        max_tokens = int(getattr(project.props.options, "memory_bank_max_tokens", 2000) or 2000)
        block = memory_bank.render_for_prompt(db, project.props.id, max_tokens)
    except Exception:
        return base_system_prompt
    if not block:
        return base_system_prompt
    if base_system_prompt:
        return f"{block}\n\n{base_system_prompt}"
    return block


def _project_has_terminal(project) -> bool:
    """True iff the project has the `terminal` tool enabled. Only that tool
    (the Docker-sandbox shell) reads files from `/home/user/uploads/` — for
    projects without it, pushing attachments into a container is dead weight
    and can even fail loudly (container creation, tar size limits), so we
    short-circuit the upload entirely."""
    try:
        raw = (getattr(project.props.options, "tools", None) or "")
    except Exception:
        raw = ""
    names = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return "terminal" in names


def _route_attachments(files, chat_id, prompt, brain, existing_image=None, project=None):
    """Route non-image file attachments to the Docker sandbox (or politely
    drop them when `terminal` isn't configured).

    `helper._normalize_image_inputs` canonicalizes the two image-input
    paths before we're called: by the time this function runs, any image
    that arrived in `files[]` has already been promoted to
    `chatModel.image` and removed from `files`. So `files` here should
    only contain non-image attachments. The image branch below is kept as
    a defensive fallback for direct callers that bypass the helper.

    Returns ``(augmented_prompt, image_data_url_or_existing)``. If the
    caller already passed an explicit `image` on the request, it wins
    over anything in `files` (backward-compat with the old `image` field).
    """
    if not files:
        return prompt, existing_image

    images = [f for f in files if _is_image_attachment(f)]
    docs = [f for f in files if not _is_image_attachment(f)]

    image_url = existing_image
    if images and image_url is None:
        primary = images[0]
        mime = primary.mime_type or "image/png"
        image_url = f"data:{mime};base64,{primary.content}"

    if docs and project is not None and _project_has_terminal(project):
        prompt, _ = _upload_files_and_augment_prompt(docs, chat_id, prompt, brain)
    elif docs:
        # File attachments came in but this project can't read them — let
        # the LLM know instead of silently dropping them.
        names = ", ".join(f.name for f in docs[:5])
        if len(docs) > 5:
            names += f", …(+{len(docs) - 5} more)"
        prompt += (
            "\n\n[Attached file(s) ignored: this project has no tool that can "
            f"process them ({names}). Enable the `terminal` tool on the "
            "project to let the agent read uploaded files.]"
        )

    return prompt, image_url


def _upload_files_and_augment_prompt(files, chat_id, prompt, brain):
    """Push user-attached files into the agent's sandbox container and return
    the original prompt augmented with a manifest the LLM can see.

    Returns ``(prompt, warning_or_none)``. When Docker isn't configured we
    skip the upload and append a note so the LLM knows the files weren't
    available.
    """
    if not files:
        return prompt, None

    docker = getattr(brain, "docker_manager", None)
    if docker is None:
        note = "\n\n[The user attached files but the agent sandbox (Docker) isn't configured on this RESTai instance, so the files cannot be processed.]"
        return prompt + note, "no_docker"

    import base64
    decoded: list[tuple[str, bytes]] = []
    for f in files:
        try:
            raw = base64.b64decode(f.content, validate=False)
        except Exception:
            continue
        if raw:
            decoded.append((f.name, raw))

    if not decoded:
        return prompt, None

    try:
        manifest = docker.put_files(chat_id or "ephemeral", decoded)
    except Exception as e:
        return prompt + f"\n\n[File upload to sandbox failed: {e}]", "upload_failed"

    if not manifest:
        return prompt, None

    lines = ["", "[Files attached by the user (available in /home/user/uploads/ — use the terminal tool to inspect them):]"]
    for entry in manifest:
        lines.append(f"  - {entry['path']}  ({entry['size']} bytes)")
    return prompt + "\n" + "\n".join(lines), None


def _make_project_tool_adapted(tool_row, brain) -> AdaptedTool:
    """Create an AdaptedTool from a ProjectToolDatabase row.
    The tool runs code in the Docker sandbox."""
    import json as _json

    try:
        schema = _json.loads(tool_row.parameters) if isinstance(tool_row.parameters, str) else tool_row.parameters
    except (_json.JSONDecodeError, TypeError):
        schema = {"type": "object", "properties": {}, "required": []}

    tool_code = tool_row.code
    tool_name = tool_row.name

    async def _run_project_tool(**kwargs):
        _brain = kwargs.pop("_brain", brain)
        _chat_id = kwargs.pop("_chat_id", None)
        kwargs.pop("_project_id", None)
        if not _brain or not getattr(_brain, "docker_manager", None):
            return "ERROR: Docker is not configured."
        args_json = _json.dumps(kwargs)
        script = f"import json, sys\nargs = json.loads(sys.stdin.readline() or '{{}}')\n{tool_code}"
        return _brain.docker_manager.run_script(_chat_id or "ephemeral", script, stdin_data=args_json)

    return AdaptedTool(
        name=tool_name,
        description=tool_row.description or tool_name,
        input_schema=schema,
        fn=_run_project_tool,
        is_async=True,
        accepts_kwargs=True,
    )


def _wrap_image_error(err: Exception, has_image: bool) -> Exception:
    """Wrap an LLM provider error with a clearer message when an image was
    likely the cause (the model doesn't support vision)."""
    if not has_image:
        return err
    return HTTPException(
        status_code=400,
        detail=(
            "This LLM rejected the request, likely because it does not support "
            "image input. Try a vision-capable model (e.g. OllamaMultiModal, "
            "gpt-4o, claude-3+, gemini-2.0-flash) or remove the image. "
            f"Original error: {err}"
        ),
    )


class Agent(ProjectBase):

    # ---------------- Plan-and-execute (auto_plan) ----------------

    async def _run_planner(
        self, project, prompt: str, db: DBWrapper
    ) -> list[str] | None:
        """One-shot LLM call that decides if `prompt` should be split into
        subtasks. Returns a list of 2-6 short subtask names if multi-step,
        or None to skip planning. Failures fall back to None (no plan)
        so a planner glitch never breaks the chat.
        """
        llm_wrapper = self.brain.get_llm(project.props.llm, db)
        if llm_wrapper is None or not hasattr(llm_wrapper, "llm"):
            return None

        # Per-step iteration budget shown to the planner so it can size
        # the plan: total work-loops will be len(plan) * max_iterations.
        cap = int(getattr(project.props.options, "max_iterations", 10) or 10)
        planner_prompt = (
            "You are a task planner. Decide if the user's request needs multiple distinct steps.\n\n"
            "Respond with STRICT JSON, one of:\n"
            '  {"plan": ["short step name 1", "short step name 2", ...]}  (2-6 steps)\n'
            '  {"plan": null}\n\n'
            "Plan when the request requires multiple coherent phases of work — e.g. "
            '"clone repo and audit security" → {"plan": ["Clone the repo", "Map the codebase", '
            '"Audit auth and input validation", "Audit secrets handling", "Compile final report"]}.\n\n'
            "Do NOT plan for simple questions, lookups, single-tool calls, or chit-chat — return "
            '{"plan": null}. Each step gets up to '
            f"{cap} tool-call iterations on its own, so prefer a smaller plan over a longer one. "
            "Step names must be short and action-oriented.\n\n"
            f"User request:\n{prompt}\n\nJSON:"
        )

        try:
            result = await asyncio.to_thread(llm_wrapper.llm.complete, planner_prompt)
            text = (result.text if hasattr(result, "text") else str(result)).strip()
        except Exception as e:
            logging.warning("Planner LLM call failed (skipping plan): %s", e)
            return None

        # Strip <think>…</think> blocks (Qwen3, deepseek-r1, …) and any
        # fenced markdown wrappers before parsing JSON.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        # Some models emit prose around the JSON; grab the first {…} block.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)

        try:
            data = json.loads(text)
        except Exception as e:
            logging.warning("Planner output wasn't valid JSON (skipping plan): %s | %r", e, text[:200])
            return None

        plan = data.get("plan")
        if not isinstance(plan, list):
            return None
        plan = [s.strip() for s in plan if isinstance(s, str) and s.strip()]
        if not (2 <= len(plan) <= 6):
            return None
        return plan

    async def _chat_planned_stream(
        self,
        project: Project,
        original_prompt: str,
        plan: list[str],
        session,
        runtime,
        image_block,
        stream: bool,
        output: dict,
    ):
        """Run a multi-step plan: each subtask is its own bounded
        `_drive_runtime` invocation against a SHARED session, then a
        synthesis turn produces the final answer. Yields fully-formatted
        SSE strings (the caller just passes them through to the wire).

        Aggregates reasoning steps, tool traces, and a per-step summary
        log into `output` so the frontend can render the checklist + the
        usual thoughts/tools panels.
        """
        output["plan"] = plan
        output["step_summaries"] = []
        aggregated_reasoning_steps: list = []
        aggregated_tool_trace: list = []

        if stream:
            yield "data: " + json.dumps({"plan": plan}) + "\n\n"

        for idx, step_name in enumerate(plan):
            if stream:
                yield "data: " + json.dumps(
                    {"step_start": {"index": idx, "name": step_name}}
                ) + "\n\n"

            if idx == 0:
                step_prompt = (
                    f"Here is the user's overall request:\n\n{original_prompt}\n\n"
                    f"We'll tackle it as a {len(plan)}-step plan:\n"
                    + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan))
                    + f"\n\n**Now do step 1/{len(plan)}: {step_name}**\n"
                    "Focus only on this step. Use as many tool calls as needed. "
                    "When you're done with this step, write a brief one-paragraph summary of what you found/did and stop."
                )
            else:
                step_prompt = (
                    f"**Now do step {idx+1}/{len(plan)}: {step_name}**\n"
                    "Focus only on this step. When done, write a brief summary and stop."
                )

            step_output: dict = {}
            async for delta in self._drive_runtime(
                runtime,
                prompt=step_prompt,
                session=session,
                image_block=image_block if idx == 0 else None,
                stream=stream,
                project=project,
                output=step_output,
            ):
                if stream:
                    yield "data: " + json.dumps({"text": delta}) + "\n\n"

            step_text = (step_output.get("answer") or "").strip()
            output["step_summaries"].append({"name": step_name, "result": step_text[:1000]})
            aggregated_reasoning_steps.extend(
                (step_output.get("reasoning") or {}).get("steps") or []
            )
            aggregated_tool_trace.extend(step_output.get("tool_trace") or [])

            if stream:
                yield "data: " + json.dumps(
                    {"step_done": {"index": idx, "summary": step_text[:300]}}
                ) + "\n\n"

        # Final synthesis: index = len(plan) so the UI shows it as a
        # virtual extra step at the bottom of the checklist.
        if stream:
            yield "data: " + json.dumps(
                {"step_start": {"index": len(plan), "name": "Synthesize final answer"}}
            ) + "\n\n"

        synth_prompt = (
            "All planned steps are done. Write a complete, well-structured final answer "
            "to the user's original request, drawing on everything you found across the steps. "
            "Don't ask clarifying questions and don't recap the plan — just give the answer."
        )
        final_output: dict = {}
        async for delta in self._drive_runtime(
            runtime,
            prompt=synth_prompt,
            session=session,
            image_block=None,
            stream=stream,
            project=project,
            output=final_output,
        ):
            if stream:
                yield "data: " + json.dumps({"text": delta}) + "\n\n"

        if stream:
            yield "data: " + json.dumps(
                {"step_done": {"index": len(plan), "summary": "synthesis complete"}}
            ) + "\n\n"

        output["answer"] = final_output.get("answer") or ""
        final_steps = (final_output.get("reasoning") or {}).get("steps") or []
        output["reasoning"] = {
            "output": "\n\n".join(
                a.get("output", "")
                for s in (aggregated_reasoning_steps + final_steps)
                for a in (s.get("actions") or [])
            ),
            "steps": aggregated_reasoning_steps + final_steps,
        }
        merged_trace = aggregated_tool_trace + (final_output.get("tool_trace") or [])
        if merged_trace:
            output["tool_trace"] = merged_trace

    def _build_runtime(
        self,
        project: Project,
        db: DBWrapper,
        system_prompt: str | None,
        extra_tools: list | None = None,
    ) -> Agent2Runtime:
        llm_db = db.get_llm_by_name(project.props.llm)
        if llm_db is None:
            raise ValueError(f"LLM '{project.props.llm}' not found")

        provider, prov_config = build_provider_for_llm(llm_db)

        raw_tool_names = set(
            t.strip() for t in (project.props.options.tools or "").split(",") if t.strip()
        )
        raw_tools = self.brain.get_tools(raw_tool_names) if raw_tool_names else []
        adapted = adapt_function_tools(raw_tools)
        if extra_tools:
            adapted.extend(extra_tools)

        # Load agent-created project tools from DB
        from restai.database import DBWrapper as _DBW
        _db = _DBW()
        try:
            project_tools = _db.get_project_tools(project.props.id)
            for pt in project_tools:
                if pt.enabled:
                    adapted.append(_make_project_tool_adapted(pt, self.brain))
        finally:
            _db.db.close()

        return Agent2Runtime(
            provider=provider,
            config=prov_config,
            tools=adapted,
            system_prompt=system_prompt or "",
            max_turns=project.props.options.max_iterations,
            mode=project.props.options.agent_mode or "auto",
        )

    @staticmethod
    def _record_step(steps: list, reasoning_buf: list, tool_call: ToolUseBlock, tool_output: str):
        reasoning_buf.append("Action: " + tool_call.name)
        reasoning_buf.append("Action Input: " + json.dumps(tool_call.input))
        reasoning_buf.append("Action Output: " + tool_output)
        steps.append({
            "actions": [{
                "action": tool_call.name,
                "input": tool_call.input,
                "output": tool_output,
            }],
            "output": "",
        })

    @staticmethod
    def _count_tokens(output: dict) -> None:
        """Lightweight tiktoken-based token estimate."""
        try:
            output["tokens"] = {
                "input": tokens_from_string(output.get("question") or ""),
                "output": tokens_from_string(output.get("answer") or ""),
                "accuracy": "low",
            }
        except Exception:
            output["tokens"] = {"input": 0, "output": 0, "accuracy": "low"}

    def _finalize_reasoning(self, output: dict, reasoning_buf: list, steps: list) -> None:
        """Build the reasoning dict from tool steps if any, then let
        `post_processing_reasoning` extract `<think>...</think>` blocks from
        the answer if no tool reasoning was recorded. Strips think tags from
        the answer either way."""
        if steps:
            output["reasoning"] = {"output": "\n".join(reasoning_buf), "steps": steps}
        self.brain.post_processing_reasoning(output)

    async def _drive_runtime(
        self,
        runtime,
        *,
        prompt: str,
        session,
        image_block,
        stream: bool,
        project: Project,
        output: dict,
    ):
        """Drive the runtime's event loop, yield text deltas as `str`, mutate
        `output["answer"]` and `output["reasoning"]` along the way. Used by
        both `chat()` and `question()` to share the (otherwise identical)
        per-event handling."""
        import re as _re

        steps: list = []
        reasoning_buf: list = []
        # Pair tool calls with their results so the reasoning panel renders correctly
        pending_tool_calls: dict = {}
        # Per-call timing + structured trace. Keyed by tool_use_id so we
        # can compute latency = tool_result_ts - tool_use_ts. Flushed
        # into `output["tool_trace"]` when we finalize — the log viewer
        # renders this as a timeline.
        import time as _time
        tool_call_started_at: dict = {}
        tool_trace: list = []
        # `draw_image` tool URLs collected from tool results — appended to the
        # final answer if the LLM didn't echo them (some models summarize tool
        # results instead of quoting them, which would silently swallow the
        # image link).
        image_urls: list[str] = []
        _image_url_re = _re.compile(
            r"!\[[^\]]*\]\((https?://[^)\s]+/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+|/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+)\)"
        )

        # Mirror every text_delta into a local buffer. The "final" event
        # is the canonical source for output["answer"], but if the
        # runtime is interrupted (timeout, abort, upstream EOS without
        # final_text) we'd otherwise lose everything the user already
        # saw streaming — including thinking content. Falling back to
        # the streamed buffer lets `_finalize_reasoning` still extract
        # `<think>…</think>` blocks so the persisted message keeps the
        # thoughts the user watched in the live panel.
        streamed_text_buf: list[str] = []

        async for event in runtime.run_iter(
            prompt,
            session=session,
            image=image_block,
            stream=stream,
        ):
            if event.type == "text_delta":
                delta = event.data.get("text", "")
                if delta:
                    streamed_text_buf.append(delta)
                    yield delta

            elif event.type == "assistant":
                msg = event.message
                if msg:
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            pending_tool_calls[block.id] = block
                            tool_call_started_at[block.id] = _time.monotonic()

            elif event.type == "tool_result":
                msg = event.message
                if msg:
                    for block in msg.content:
                        tool_use_id = getattr(block, "tool_use_id", None)
                        tool_call = pending_tool_calls.pop(tool_use_id, None)
                        content = getattr(block, "content", "") or ""
                        if tool_call is not None:
                            self._record_step(steps, reasoning_buf, tool_call, content)
                            # Per-tool trace row. Latency comes from the
                            # assistant → tool_result gap. Status is
                            # best-effort: the convention across our
                            # builtin tools is to return `"ERROR: ..."`
                            # or `"OK: ..."`, so a prefix check is good
                            # enough without wrapping every tool.
                            started = tool_call_started_at.pop(tool_use_id, None)
                            latency_ms = (
                                int((_time.monotonic() - started) * 1000) if started is not None else None
                            )
                            status = "error" if str(content).strip().startswith("ERROR:") else "ok"
                            try:
                                input_preview = json.dumps(tool_call.input, default=str)
                            except Exception:
                                input_preview = str(tool_call.input)
                            if len(input_preview) > 500:
                                input_preview = input_preview[:500] + "…"
                            err_preview = None
                            if status == "error":
                                err_preview = str(content)[:500]
                            tool_trace.append({
                                "tool": tool_call.name,
                                "args": input_preview,
                                "latency_ms": latency_ms,
                                "status": status,
                                "error": err_preview,
                            })
                            # Capture every image-cache URL the tool emitted so
                            # we can guarantee it ends up in front of the user.
                            for m in _image_url_re.finditer(content):
                                url = m.group(1)
                                if url not in image_urls:
                                    image_urls.append(url)

            elif event.type == "final":
                output["answer"] = event.data.get("final_text", "") or ""
                # Capture stop_reason for the post-loop max-turns
                # handling — we used to overwrite answer with the
                # fallback string here, which clobbered any thinking
                # the model had streamed before hitting the cap.
                output["_stop_reason"] = event.data.get("stop_reason")

        # If the LLM dropped a draw_image URL on its way to writing the final
        # answer, splice it back in. Most models echo the markdown verbatim
        # when instructed; this is the belt-and-braces safety net for the
        # ones that summarize ("Image generated!") without the link.
        if image_urls:
            answer = output.get("answer") or ""
            missing = [u for u in image_urls if u not in answer]
            if missing:
                appendix = "\n\n" + "\n\n".join(f"![]({u})" for u in missing)
                output["answer"] = (answer + appendix).strip()

        stop_reason = output.pop("_stop_reason", None)

        # Recover everything the user saw streaming. Two distinct cases:
        #   (a) Runtime exited without a `final` event (interrupted,
        #       upstream EOS, timeout) → output["answer"] is empty.
        #   (b) Runtime hit max_turns. `final_text` is set to ONLY the
        #       LAST turn's text, but the buffer has every turn's text
        #       including earlier `<think>…</think>` blocks. Without
        #       this, multi-turn thoughts get silently dropped.
        # `_finalize_reasoning` then extracts the `<think>` blocks into
        # reasoning.steps via post_processing_reasoning.
        buffer_text = "".join(streamed_text_buf)
        if buffer_text and (not (output.get("answer") or "") or stop_reason == "max_turns"):
            output["answer"] = buffer_text

        # If the runtime hit max_turns, surface a notice so the user
        # knows why the agent stopped and can ask to continue. Append
        # rather than overwrite — partial work (thinking + tool output)
        # the model produced should remain visible.
        if stop_reason == "max_turns":
            cap = getattr(project.props.options, "max_iterations", None) or "max"
            notice = (
                f"\n\n_⚠ Reached the {cap}-iteration tool-call cap before producing a final answer. "
                f"Reply **\"continue\"** (or give a more focused next step) and I'll keep working from here._"
            )
            current = (output.get("answer") or "").rstrip()
            output["answer"] = (current + notice).lstrip()

        self._finalize_reasoning(output, reasoning_buf, steps)

        # Capture thoughts from EARLIER turns too. The runtime's
        # `final_text` only carries the last turn's text, so any
        # `<think>…</think>` blocks emitted in turns 1..N-1 would be
        # invisible to post_processing_reasoning. We pull them out of
        # the streamed buffer (which has every delta the user saw),
        # dedupe against thoughts already recorded, and prepend them
        # to reasoning.steps so the panel shows the full chain in
        # chronological order.
        if buffer_text:
            think_re = _re.compile(r"<think>(.*?)</think>", _re.DOTALL)
            buffer_thoughts = [m.group(1).strip() for m in think_re.finditer(buffer_text)]
            buffer_thoughts = [t for t in buffer_thoughts if t]
            if buffer_thoughts:
                existing = output.setdefault("reasoning", {"output": "", "steps": []})
                if not isinstance(existing.get("steps"), list):
                    existing["steps"] = []
                already = {
                    a.get("output", "")
                    for s in existing["steps"]
                    for a in (s.get("actions") or [])
                    if a.get("action") == "reasoning"
                }
                new_thoughts = [t for t in buffer_thoughts if t not in already]
                if new_thoughts:
                    new_steps = [
                        {"actions": [{"output": t, "action": "reasoning"}], "output": t}
                        for t in new_thoughts
                    ]
                    # Prepend so timeline reads thoughts → tools → final.
                    existing["steps"] = new_steps + existing["steps"]
                    joined_new = "\n\n".join(new_thoughts)
                    existing["output"] = (
                        joined_new + ("\n\n" + existing.get("output", "") if existing.get("output") else "")
                    )

        # Only fire the "didn't produce a final answer" notice when we
        # genuinely have nothing — no answer text AND no captured
        # thoughts. Without this guard, a model that produced lots of
        # thinking but got interrupted before the final answer would
        # see its thoughts persisted into reasoning yet have the bubble
        # body clobbered by the fallback string.
        reasoning_steps_now = (output.get("reasoning") or {}).get("steps") or []
        has_thoughts = any(
            (a.get("action") == "reasoning")
            for s in reasoning_steps_now
            for a in (s.get("actions") or [])
        )
        if not (output.get("answer") or "").strip() and steps and not has_thoughts:
            output["answer"] = (
                project.props.censorship
                or "The model used tools but didn't produce a final answer. "
                   "Check the tool-call panel for what was retrieved, then try rephrasing."
            )

        # Hand the tool trace off to log_inference via the output dict.
        # Empty list → None so we don't bloat the DB with "[]" rows.
        if tool_trace:
            output["tool_trace"] = tool_trace

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        chat_id = chatModel.id or str(uuid4())

        output = {
            "question": chatModel.question,
            "type": "agent",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat_id,
        }

        if self.check_input_guard(project, chatModel.question, user, db, output):
            if chatModel.stream:
                yield "data: " + json.dumps({"text": output.get("answer", "")}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                yield output
            return

        streamed_any_text = False
        try:
            async with MCPSessionPool() as mcp_pool:
                try:
                    mcp_tools = await mcp_pool.connect_servers(
                        project.props.options.mcp_servers or []
                    )
                except Exception:
                    mcp_tools = []

                try:
                    sys_prompt = _augment_system_prompt_with_memory_bank(
                        project, db, project.props.system,
                    )
                    runtime = self._build_runtime(
                        project, db, sys_prompt, extra_tools=mcp_tools
                    )
                except Agent2UnsupportedLLMError as e:
                    err_msg = str(e)
                    if chatModel.stream:
                        yield "data: " + json.dumps({"text": err_msg}) + "\n\n"
                        output["answer"] = err_msg
                        yield "data: " + json.dumps(output) + "\n"
                        yield "event: close\n\n"
                    else:
                        output["answer"] = err_msg
                        yield output
                    return

                runtime._chat_id = chat_id
                runtime._brain = self.brain
                runtime._project_id = project.props.id
                session = await get_session(self.brain, chat_id)

                prompt_text, image_url = _route_attachments(
                    getattr(chatModel, "files", None), chat_id, chatModel.question, self.brain,
                    existing_image=chatModel.image, project=project,
                )
                image_block = ImageBlock.from_data_url(image_url) if image_url else None

                # Plan-and-execute (opt-in). Only kicks in on the first
                # turn of a fresh session — follow-up messages run as
                # normal single-loop chat so the user can refine without
                # paying the planner cost again.
                use_plan = (
                    bool(getattr(project.props.options, "auto_plan", False))
                    and not getattr(session, "messages", None)
                )
                plan = None
                if use_plan:
                    plan = await self._run_planner(project, prompt_text, db)

                try:
                    if plan:
                        async for sse_line in self._chat_planned_stream(
                            project=project,
                            original_prompt=prompt_text,
                            plan=plan,
                            session=session,
                            runtime=runtime,
                            image_block=image_block,
                            stream=chatModel.stream,
                            output=output,
                        ):
                            streamed_any_text = True
                            yield sse_line
                    else:
                        async for delta in self._drive_runtime(
                            runtime,
                            prompt=prompt_text,
                            session=session,
                            image_block=image_block,
                            stream=chatModel.stream,
                            project=project,
                            output=output,
                        ):
                            streamed_any_text = True
                            yield "data: " + json.dumps({"text": delta}) + "\n\n"

                    await save_session(self.brain, chat_id, session)
                    self._count_tokens(output)
                    self.check_output_guard(project, user, db, output)

                    if chatModel.stream:
                        # Emit the final answer text only if streaming didn't
                        # already deliver it (e.g. fell back to ReAct mid-run).
                        if not streamed_any_text and output.get("answer"):
                            yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                        yield "data: " + json.dumps(output) + "\n"
                        yield "event: close\n\n"

                except Exception as e:
                    wrapped = _wrap_image_error(e, bool(chatModel.image))
                    err_msg = project.props.censorship or f"Agent failed: {wrapped}"
                    output["answer"] = err_msg
                    self._count_tokens(output)
                    if chatModel.stream:
                        yield "data: " + json.dumps({"text": err_msg}) + "\n\n"
                        yield "data: " + json.dumps(output) + "\n"
                        yield "event: close\n\n"
                        streamed_any_text = True
        except BaseException as e:
            # Catch ExceptionGroup from MCP session pool cleanup failures
            # to prevent "No response returned" crashes
            if "answer" not in output:
                logging.warning("Agent chat failed during MCP cleanup: %s", e)
                output["answer"] = project.props.censorship or "An error occurred processing your request."

        # Non-streaming yield MUST be outside the `async with MCPSessionPool()`
        # block. When the caller does `async for line in gen: return line`, the
        # generator is abandoned after the first yield. If that yield happens
        # inside the async-with, the pool's __aexit__ runs in a GC/finalizer
        # task → "exit cancel scope in different task" → corrupted HTTP response.
        if chatModel.stream:
            # If streaming failed before emitting anything, emit the error as SSE
            if "answer" in output and not streamed_any_text:
                yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
        else:
            if "answer" not in output:
                output["answer"] = project.props.censorship or "No response generated."
            yield output

    async def question(
        self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper
    ):
        output = {
            "question": questionModel.question,
            "type": "agent",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }

        if self.check_input_guard(project, questionModel.question, user, db, output):
            if questionModel.stream:
                yield "data: " + json.dumps({"text": output.get("answer", "")}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                yield output
            return

        system_prompt = questionModel.system or project.props.system
        system_prompt = _augment_system_prompt_with_memory_bank(project, db, system_prompt)

        async with MCPSessionPool() as mcp_pool:
            try:
                mcp_tools = await mcp_pool.connect_servers(
                    project.props.options.mcp_servers or []
                )
            except Exception:
                mcp_tools = []

            try:
                runtime = self._build_runtime(
                    project, db, system_prompt, extra_tools=mcp_tools
                )
            except Agent2UnsupportedLLMError as e:
                output["answer"] = str(e)
                if questionModel.stream:
                    yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    yield output
                return

            runtime._brain = self.brain
            runtime._project_id = project.props.id
            streamed_any_text = False

            # Ephemeral chat id so file uploads still land in a sandbox the
            # terminal tool can read from inside this same invocation.
            eph_chat = f"q_{uuid4().hex[:12]}"
            runtime._chat_id = eph_chat
            prompt_text, image_url = _route_attachments(
                getattr(questionModel, "files", None), eph_chat, questionModel.question, self.brain,
                existing_image=questionModel.image, project=project,
            )
            image_block = ImageBlock.from_data_url(image_url) if image_url else None

            try:
                async for delta in self._drive_runtime(
                    runtime,
                    prompt=prompt_text,
                    session=None,
                    image_block=image_block,
                    stream=questionModel.stream,
                    project=project,
                    output=output,
                ):
                    streamed_any_text = True
                    yield "data: " + json.dumps({"text": delta}) + "\n\n"

                self._count_tokens(output)
                self.check_output_guard(project, user, db, output)
            except Exception as e:
                wrapped = _wrap_image_error(e, bool(questionModel.image))
                err_msg = project.props.censorship or f"Agent failed: {wrapped}"
                output["answer"] = err_msg
                self._count_tokens(output)
                if questionModel.stream:
                    yield "data: " + json.dumps({"text": err_msg}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                    return

        if questionModel.stream:
            if not streamed_any_text and output.get("answer"):
                yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
