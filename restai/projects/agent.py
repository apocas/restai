"""agent project type — direct LLM chat with optional tool calling, on agent2 runtime."""
import asyncio
import contextlib
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
from restai.models.models import ChatModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.projects.agent_shared import (
    augment_system_prompt_with_memory_bank as _augment_system_prompt_with_memory_bank,
    augment_system_prompt_with_memory_search_hint as _augment_system_prompt_with_memory_search_hint,
    prepend_current_time as _prepend_current_time,
    route_attachments as _route_attachments,
    sandbox_chat_id as _sandbox_chat_id,
    spawn_session_save as _spawn_session_save,
)
from restai.tools import tokens_from_string


def _looks_repetitive(texts: list[str], min_chars: int = 60, prefix_ratio: float = 0.6,
                      min_prefix_chars: int = 50) -> bool:
    """Detect classic open-model self-prompting loop: last 3 turns share
    enough common prefix to qualify as rambling without progress.

    Both signals required: shared prefix >= min_prefix_chars (don't trip on
    short openers like "I will check...") AND >= prefix_ratio of shortest
    turn (the repeating part dominates each turn).
    """
    if len(texts) < 3:
        return False
    norms = [(t or "").strip().lower()[:300] for t in texts[-3:]]
    if any(len(n) < min_chars for n in norms):
        return False
    prefix = norms[0]
    for n in norms[1:]:
        i = 0
        cap = min(len(prefix), len(n))
        while i < cap and prefix[i] == n[i]:
            i += 1
        prefix = prefix[:i]
        if len(prefix) < min_prefix_chars:
            return False
    return len(prefix) >= prefix_ratio * min(len(n) for n in norms)


def _make_project_tool_adapted(tool_row, brain) -> AdaptedTool:
    """Adapt a ProjectToolDatabase row — code runs in the Docker sandbox."""
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
    """Wrap provider errors with a clearer message when an image is likely the cause."""
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

    async def _run_planner(
        self, project, prompt: str, db: DBWrapper
    ) -> list[str] | None:
        """One-shot LLM call that returns 2-6 subtask names or None to skip planning."""
        llm_wrapper = self.brain.get_llm(project.props.llm, db)
        if llm_wrapper is None or not hasattr(llm_wrapper, "llm"):
            return None

        # Per-step budget shown to the planner so it can size the plan:
        # total work-loops = len(plan) * max_iterations.
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

        # Strip <think>…</think> (Qwen3, deepseek-r1) + fenced markdown wrappers.
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
        """Run multi-step plan: each subtask is its own bounded _drive_runtime
        call against a SHARED session, then a synthesis turn produces the
        final answer. Yields pre-formatted SSE strings.
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
                    "When you're done with this step, write a brief one-paragraph summary of what you found/did and stop. "
                    "Note: the plan above was just created for THIS conversation — don't waste a `memory_search` call trying to look up the plan itself. "
                    "(Other `memory_search` calls — user preferences, project facts, past work on the same topic — are fine when they help the step.)"
                )
            else:
                # Re-state plan + completed-step summaries inline so the model
                # never hunts through session history (or worse, runs
                # memory_search) for context.
                done_recap = "\n".join(
                    f"  {i+1}. {s['name']} — {(s.get('result') or '').strip()[:300]}"
                    for i, s in enumerate(output["step_summaries"])
                )
                step_prompt = (
                    f"User's overall request:\n\n{original_prompt}\n\n"
                    f"Plan ({len(plan)} steps):\n"
                    + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan))
                    + f"\n\nCompleted so far:\n{done_recap}\n\n"
                    f"**Now do step {idx+1}/{len(plan)}: {step_name}**\n"
                    "Focus only on this step. When done, write a brief summary and stop. "
                    "The request, plan, and prior step results are all in THIS message — don't waste a `memory_search` call looking for them. "
                    "(Other `memory_search` calls for the actual step work — user preferences, project facts, past work on the same topic — are fine.)"
                )

            step_output: dict = {}
            async for kind, payload in self._drive_runtime(
                runtime,
                prompt=step_prompt,
                session=session,
                image_block=image_block if idx == 0 else None,
                stream=stream,
                project=project,
                output=step_output,
            ):
                if stream:
                    if kind == "text":
                        yield "data: " + json.dumps({"text": payload}) + "\n\n"
                    else:
                        yield "data: " + json.dumps(payload) + "\n\n"

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

            # Repetition guard fired inside the step — abort the whole
            # plan (don't run remaining steps, skip synthesis). The
            # step's warning message becomes the final answer.
            if step_output.get("aborted_repetition"):
                output["aborted_repetition"] = True
                output["answer"] = step_text
                output["reasoning"] = {"steps": aggregated_reasoning_steps}
                if aggregated_tool_trace:
                    output["tool_trace"] = aggregated_tool_trace
                return

        # Final synthesis: index = len(plan) so UI renders as virtual extra
        # step at the bottom of the checklist.
        if stream:
            yield "data: " + json.dumps(
                {"step_start": {"index": len(plan), "name": "Synthesize final answer"}}
            ) + "\n\n"

        steps_recap = "\n\n".join(
            f"### Step {i+1}/{len(plan)}: {s['name']}\n{(s.get('result') or '').strip()}"
            for i, s in enumerate(output["step_summaries"])
        )
        synth_prompt = (
            f"User's original request:\n\n{original_prompt}\n\n"
            f"Findings from each step:\n\n{steps_recap}\n\n"
            "All planned steps are done. Write a complete, well-structured final answer "
            "to the user's original request, drawing on the findings above. "
            "Don't ask clarifying questions and don't recap the plan — just give the answer. "
            "The request and per-step findings are all in THIS message — don't waste a `memory_search` call looking for them. "
            "(If a memory lookup genuinely improves the synthesis — user preferences, related past work — go ahead.)"
        )
        final_output: dict = {}
        async for kind, payload in self._drive_runtime(
            runtime,
            prompt=synth_prompt,
            session=session,
            image_block=None,
            stream=stream,
            project=project,
            output=final_output,
        ):
            if stream:
                if kind == "text":
                    yield "data: " + json.dumps({"text": payload}) + "\n\n"
                else:
                    yield "data: " + json.dumps(payload) + "\n\n"

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
        """tiktoken-based token estimate."""
        try:
            output["tokens"] = {
                "input": tokens_from_string(output.get("question") or ""),
                "output": tokens_from_string(output.get("answer") or ""),
                "accuracy": "low",
            }
        except Exception:
            output["tokens"] = {"input": 0, "output": 0, "accuracy": "low"}

    def _finalize_reasoning(self, output: dict, reasoning_buf: list, steps: list) -> None:
        """Build reasoning dict; post_processing_reasoning strips <think> tags from answer."""
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
        """Drive the runtime's event loop; yield text deltas + mutate output dict."""
        import re as _re

        steps: list = []
        reasoning_buf: list = []
        # Pair tool calls with their results for the reasoning panel.
        pending_tool_calls: dict = {}
        # Per-call timing + structured trace, keyed by tool_use_id so latency
        # = tool_result_ts - tool_use_ts. Flushed to output["tool_trace"]; log
        # viewer renders as a timeline.
        import time as _time
        tool_call_started_at: dict = {}
        tool_trace: list = []
        # Capture draw_image URLs from tool results — appended to final answer
        # if the LLM doesn't echo them (some models summarize tool results
        # instead of quoting and would silently swallow the image link).
        image_urls: list[str] = []
        _image_url_re = _re.compile(
            r"!\[[^\]]*\]\((https?://[^)\s]+/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+|/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+)\)"
        )

        # Repetition guard: when the model gets stuck self-prompting ("Let me
        # look at a few more files: …" repeated for dozens of turns without
        # invoking a tool), abort cleanly instead of burning max_iterations.
        recent_assistant_texts: list[str] = []

        # Mirror every text_delta. The "final" event is canonical for
        # output["answer"], but if the runtime is interrupted (timeout, abort,
        # upstream EOS without final_text) we'd otherwise lose everything the
        # user already saw streaming — including thinking content. Falling
        # back to this buffer lets _finalize_reasoning still extract <think>
        # blocks so persisted messages keep the thoughts the user watched.
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
                    yield ("text", delta)

            elif event.type == "assistant":
                msg = event.message
                if msg:
                    try:
                        turn_text = msg.text_content() or ""
                    except Exception:
                        turn_text = ""
                    # Tool call = real progress; reset the spinning
                    # detector. Only consecutive PURE-TEXT turns count
                    # toward the rolling buffer.
                    if any(isinstance(b, ToolUseBlock) for b in (msg.content or [])):
                        recent_assistant_texts.clear()
                    elif turn_text.strip():
                        recent_assistant_texts.append(turn_text)
                        if len(recent_assistant_texts) > 3:
                            recent_assistant_texts.pop(0)
                        if _looks_repetitive(recent_assistant_texts):
                            warning_msg = (
                                "(stopped — model produced repetitive output across "
                                "the last 3 turns without making progress. Try rephrasing "
                                "the request, breaking it into smaller steps, or switching "
                                "to a more capable model.)"
                            )
                            logging.warning(
                                "agent _drive_runtime aborted: detected repetitive "
                                "output across last 3 assistant turns"
                            )
                            output["answer"] = warning_msg
                            # Plan-loop / chat() see this flag and abort the
                            # entire run instead of moving on to the next step.
                            output["aborted_repetition"] = True
                            if stream:
                                yield ("text", "\n\n" + warning_msg)
                            return
                    for block in msg.content:
                        if isinstance(block, ToolUseBlock):
                            pending_tool_calls[block.id] = block
                            tool_call_started_at[block.id] = _time.monotonic()
                            try:
                                args_preview = json.dumps(block.input, default=str)
                            except Exception:
                                args_preview = str(block.input)
                            if len(args_preview) > 500:
                                args_preview = args_preview[:500] + "…"
                            yield ("event", {
                                "tool_call_started": {
                                    "id": block.id,
                                    "tool": block.name,
                                    "args": args_preview,
                                }
                            })

            elif event.type == "tool_result":
                msg = event.message
                if msg:
                    for block in msg.content:
                        tool_use_id = getattr(block, "tool_use_id", None)
                        tool_call = pending_tool_calls.pop(tool_use_id, None)
                        content = getattr(block, "content", "") or ""
                        if tool_call is not None:
                            self._record_step(steps, reasoning_buf, tool_call, content)
                            # Per-tool trace row. Status is best-effort: our
                            # builtins return `"ERROR: ..."` / `"OK: ..."` so
                            # a prefix check works without wrapping every tool.
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
                            output_preview = str(content)[:500]
                            if len(str(content)) > 500:
                                output_preview = output_preview + "…"
                            yield ("event", {
                                "tool_call_completed": {
                                    "id": tool_use_id,
                                    "tool": tool_call.name,
                                    "status": status,
                                    "latency_ms": latency_ms,
                                    "output": output_preview,
                                    "error": err_preview,
                                }
                            })
                            # Capture image-cache URLs to guarantee they reach the user.
                            for m in _image_url_re.finditer(content):
                                url = m.group(1)
                                if url not in image_urls:
                                    image_urls.append(url)

                # /artifacts/ injection: drain the per-chat artifact tray and
                # append bytes as a synthetic user message before the next
                # turn. Images become ImageBlocks (only multimodal block both
                # Anthropic and OpenAI-compat serialize uniformly today);
                # other types fall back to text mention. Best-effort — never
                # let an artifact-injection bug kill the chat.
                try:
                    from restai.agent2 import artifacts as _artifacts
                    chat_id_now = getattr(runtime, "_chat_id", None) or ""
                    pending = _artifacts.consume(chat_id_now)
                except Exception:
                    pending = []
                if pending:
                    try:
                        from restai.agent2.types import (
                            ImageBlock as _ImgBlk,
                            TextBlock as _TxtBlk,
                            Message as _Msg,
                        )
                        import base64 as _b64
                        blocks: list = []
                        intro_lines = ["[artifacts] Files saved to /artifacts/:"]
                        for a in pending:
                            mime = a.get("mime") or "application/octet-stream"
                            name = a.get("name") or "file"
                            size = a.get("size") or 0
                            data = a.get("bytes")
                            kb = max(1, size // 1024)
                            if a.get("truncated") or not data:
                                intro_lines.append(
                                    f"  - {name} ({mime}, {kb} KB) — too large to attach, only mentioned"
                                )
                                continue
                            if mime.startswith("image/"):
                                intro_lines.append(f"  - {name} ({mime}, {kb} KB) — attached below as image")
                                try:
                                    data_url = f"data:{mime};base64,{_b64.b64encode(data).decode('ascii')}"
                                    blocks.append(_ImgBlk.from_data_url(data_url))
                                except Exception:
                                    intro_lines.append(f"    (attach failed; treating as text mention)")
                            else:
                                intro_lines.append(f"  - {name} ({mime}, {kb} KB)")
                        # Lead with text manifest for explicit image context.
                        msg_blocks = [_TxtBlk(text="\n".join(intro_lines))] + blocks
                        try:
                            session.messages.append(_Msg(role="user", content=msg_blocks))
                        except Exception:
                            pass
                    except Exception:
                        logging.exception("Failed to inject /artifacts/ into next turn")

            elif event.type == "final":
                output["answer"] = event.data.get("final_text", "") or ""
                # Capture stop_reason for post-loop max-turns handling — we
                # used to overwrite answer with the fallback string here,
                # clobbering any thinking the model streamed before the cap.
                output["_stop_reason"] = event.data.get("stop_reason")

        # Belt-and-braces: splice back any draw_image URL the LLM dropped on
        # its way to the final answer (some models summarize "Image
        # generated!" instead of echoing the markdown link).
        if image_urls:
            answer = output.get("answer") or ""
            missing = [u for u in image_urls if u not in answer]
            if missing:
                appendix = "\n\n" + "\n\n".join(f"![]({u})" for u in missing)
                output["answer"] = (answer + appendix).strip()

        stop_reason = output.pop("_stop_reason", None)

        # Recover what the user saw streaming. Two cases:
        #  (a) Runtime exited without a `final` event (interrupted, EOS,
        #      timeout) → output["answer"] empty.
        #  (b) max_turns hit: final_text is ONLY the last turn's text but the
        #      buffer holds every turn including earlier <think> blocks —
        #      without this, multi-turn thoughts get silently dropped.
        buffer_text = "".join(streamed_text_buf)
        if buffer_text and (not (output.get("answer") or "") or stop_reason == "max_turns"):
            output["answer"] = buffer_text

        # Append (don't overwrite) the max_turns notice so partial work
        # (thinking + tool output) remains visible.
        if stop_reason == "max_turns":
            cap = getattr(project.props.options, "max_iterations", None) or "max"
            notice = (
                f"\n\n_⚠ Reached the {cap}-iteration tool-call cap before producing a final answer. "
                f"Reply **\"continue\"** (or give a more focused next step) and I'll keep working from here._"
            )
            current = (output.get("answer") or "").rstrip()
            output["answer"] = (current + notice).lstrip()

        self._finalize_reasoning(output, reasoning_buf, steps)

        # Capture <think> blocks from EARLIER turns too. final_text only
        # carries the last turn so thoughts from turns 1..N-1 would be
        # invisible to post_processing_reasoning. Pull from the streamed
        # buffer, dedupe against already-recorded thoughts, prepend so the
        # panel reads thoughts → tools → final in chronological order.
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
                    existing["steps"] = new_steps + existing["steps"]
                    joined_new = "\n\n".join(new_thoughts)
                    existing["output"] = (
                        joined_new + ("\n\n" + existing.get("output", "") if existing.get("output") else "")
                    )

        # Fallback notice only when we genuinely have nothing — no answer
        # AND no captured thoughts. Without the thoughts check, a model that
        # produced lots of thinking but got interrupted before the final
        # answer would have its bubble body clobbered by the fallback.
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

        # Empty list → omit so we don't bloat the DB with "[]" rows.
        if tool_trace:
            output["tool_trace"] = tool_trace

    async def chat(
        self,
        project: Project,
        chatModel: ChatModel,
        user: User,
        db: DBWrapper,
    ):
        loop = (getattr(project.props.options, "agent_loop", None) or "restai").lower()
        if loop == "claude":
            from restai.projects import _claude_sdk_loop
            async for chunk in _claude_sdk_loop.chat(self, project, chatModel, user, db):
                yield chunk
            return
        if loop == "llamaindex":
            from restai.projects import _llamaindex_loop
            async for chunk in _llamaindex_loop.chat(self, project, chatModel, user, db):
                yield chunk
            return
        if loop == "smolagents":
            from restai.projects import _smolagents_loop
            async for chunk in _smolagents_loop.chat(self, project, chatModel, user, db):
                yield chunk
            return
        if loop == "openai_agents":
            from restai.projects import _openai_agents_loop
            async for chunk in _openai_agents_loop.chat(self, project, chatModel, user, db):
                yield chunk
            return

        chat_id = chatModel.id or str(uuid4())
        # Sandbox container + agent session are keyed by this scoped id, NOT the
        # raw client chat id — so one user can't collide on another user's
        # chat_id and reach their container/files/history. The client still
        # gets the raw chat_id back as the conversation id.
        sandbox_id = _sandbox_chat_id(project.props.id, user.id, chat_id)

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
            mcp_servers = project.props.options.mcp_servers or []
            async with contextlib.AsyncExitStack() as _mcp_stack:
                mcp_tools = []
                if mcp_servers:
                    mcp_pool = await _mcp_stack.enter_async_context(MCPSessionPool())
                    try:
                        mcp_tools = await mcp_pool.connect_servers(mcp_servers)
                    except Exception:
                        mcp_tools = []

                try:
                    base_system = chatModel.system or project.props.system
                    sys_prompt = _augment_system_prompt_with_memory_bank(
                        project, db, base_system,
                    )
                    sys_prompt = _augment_system_prompt_with_memory_search_hint(
                        project, sys_prompt,
                    )
                    sys_prompt = _prepend_current_time(sys_prompt)
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

                runtime._chat_id = sandbox_id
                runtime._brain = self.brain
                runtime._project_id = project.props.id
                session = await get_session(self.brain, sandbox_id)

                prompt_text, image_url = _route_attachments(
                    getattr(chatModel, "files", None), sandbox_id, chatModel.question, self.brain,
                    existing_image=chatModel.image, project=project,
                )
                image_block = ImageBlock.from_data_url(image_url) if image_url else None

                use_plan = (
                    bool(getattr(project.props.options, "auto_plan", False))
                    and not getattr(session, "messages", None)
                )
                plan = None
                if use_plan:
                    plan = await self._run_planner(project, prompt_text, db)

                saved_session = False
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
                        async for kind, payload in self._drive_runtime(
                            runtime,
                            prompt=prompt_text,
                            session=session,
                            image_block=image_block,
                            stream=chatModel.stream,
                            project=project,
                            output=output,
                        ):
                            if chatModel.stream:
                                if kind == "text":
                                    streamed_any_text = True
                                    yield "data: " + json.dumps({"text": payload}) + "\n\n"
                                else:
                                    yield "data: " + json.dumps(payload) + "\n\n"

                    await save_session(self.brain, sandbox_id, session)
                    saved_session = True
                    self._count_tokens(output)
                    self.check_output_guard(project, user, db, output)

                    if chatModel.stream:
                        # Emit final answer only when streaming didn't already
                        # deliver it (e.g. fell back to ReAct mid-run).
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
                finally:
                    if not saved_session:
                        _spawn_session_save(self.brain, sandbox_id, session)
        except BaseException as e:
            # CancelledError MUST always propagate — the user pressed Stop
            # (or Starlette is tearing down), and swallowing it would let
            # the agent keep running tool calls + LLM requests in the
            # background. Per anyio convention, never absorb cancellation.
            import asyncio as _asyncio
            if isinstance(e, _asyncio.CancelledError):
                raise
            # Catches ExceptionGroup from MCP session-pool cleanup failures
            # to prevent "No response returned" crashes.
            if "answer" not in output:
                logging.warning("Agent chat failed during post-response cleanup: %s", e)
                output["answer"] = project.props.censorship or "An error occurred processing your request."

        # Non-streaming yield MUST be outside the `async with MCPSessionPool()`
        # block. When the caller does `async for line in gen: return line`,
        # the generator is abandoned after the first yield. If that yield
        # happens inside the async-with, the pool's __aexit__ runs in a
        # GC/finalizer task → "exit cancel scope in different task" →
        # corrupted HTTP response.
        if chatModel.stream:
            if "answer" in output and not streamed_any_text:
                yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
        else:
            if "answer" not in output:
                output["answer"] = project.props.censorship or "No response generated."
            yield output

