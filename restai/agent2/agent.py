"""The agent2 ReAct-style run loop. No llamaindex imports."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Literal, Optional, Sequence, Union
from uuid import uuid4

from .compression import compress_session, truncate_text_to_token_budget
from .providers import (
    Provider,
    ProviderConfig,
)
from .react_prompt import (
    ReactParseResult,
    build_react_system_prompt,
    parse_react_response,
)
from .resilience import backoff_delay, is_retryable_error
from .tool_adapter import (
    AdaptedTool,
    coerce_and_validate_args,
    describe_schema_for_error,
)
from .types import (
    AgentEvent,
    AgentSession,
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    user_text_message,
)

logger = logging.getLogger(__name__)


class Agent2Error(Exception):
    pass


AgentMode = Literal["auto", "function_calling", "react"]


class Agent2Runtime:
    """Standalone (non-llamaindex) agent loop; one instance per run."""

    def __init__(
        self,
        *,
        provider: Provider,
        config: ProviderConfig,
        tools: Sequence[AdaptedTool],
        system_prompt: Optional[str] = None,
        max_turns: int = 12,
        mode: Optional[AgentMode] = None,
        llm_name: str = "",
        fallbacks: Sequence[tuple[str, Provider, ProviderConfig]] = (),
        tool_timeout: Optional[float] = 300.0,
        retry_attempts: int = 2,
        retry_base_delay: float = 1.0,
        max_execution_time: Optional[float] = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.tools = list(tools)
        self._tools_by_name: dict[str, AdaptedTool] = {t.name: t for t in self.tools}
        self._builtin_tool_names: set[str] = set(self._tools_by_name.keys())
        self.system_prompt = system_prompt or ""
        self.max_turns = max(1, int(max_turns))
        # "auto" starts in function_calling and may switch on first-turn error.
        self.mode: AgentMode = (
            "function_calling" if (mode or "auto") == "auto" else (mode or "auto")
        )
        self._auto_fallback_allowed: bool = (mode or "auto") == "auto"
        # Remembered so a provider-chain switch can give the NEW provider a
        # fresh start (its own native→ReAct chance, original requested mode).
        self._initial_mode: AgentMode = self.mode
        self._initial_auto_allowed: bool = self._auto_fallback_allowed

        # Provider chain: primary + fallback LLMs. Session messages are
        # provider-neutral, so on a persistent primary failure the run
        # continues on the next provider with full conversation context.
        self._provider_chain: list[tuple[str, Provider, ProviderConfig]] = [
            (llm_name or "", provider, config),
            *[(n, p, c) for (n, p, c) in fallbacks],
        ]
        self._chain_idx = 0
        # Audit of chain switches this run: [{"from", "to", "turn", "error"}].
        self.fallback_trail: list[dict] = []

        # Per-tool-call wall-clock cap (seconds); None/0 disables.
        self.tool_timeout: Optional[float] = (
            float(tool_timeout) if tool_timeout else None
        )
        # Whole-run wall-clock deadline, set at construction so a planned
        # multi-step request (several run_iter calls on one runtime) shares
        # ONE budget. Checked at turn boundaries only — a run wraps up with
        # partial results instead of dying mid-stream.
        self._deadline: Optional[float] = (
            time.monotonic() + float(max_execution_time)
            if max_execution_time else None
        )
        # Same-provider retries per turn for transient errors (429/5xx/…).
        self.retry_attempts = max(0, int(retry_attempts))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        # Transient retries actually performed this run (observability —
        # persisted on the log row so flaky providers are visible).
        self.retry_count = 0

        # Real token usage accumulated across every LLM turn this run.
        # usage_turns counts turns that reported usage; llm_turns counts all —
        # equal means the totals are complete (accuracy "high").
        self.usage_input = 0
        self.usage_output = 0
        self.usage_turns = 0
        self.llm_turns = 0

        # (tool, canonical-args) → call count, for the identical-call loop
        # guard. Per-runtime, so planned multi-step runs share the counter.
        self._call_counts: dict[tuple[str, str], int] = {}

    async def run_iter(
        self,
        prompt: str,
        *,
        session: Optional[AgentSession] = None,
        image: Optional[ImageBlock] = None,
        stream: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        if session is None:
            session = AgentSession()

        if image is not None:
            session.messages.append(
                Message(role="user", content=[TextBlock(text=prompt), image])
            )
        else:
            session.messages.append(user_text_message(prompt))

        last_assistant_text = ""
        for turn in range(1, self.max_turns + 1):
            session.turn_count = turn

            # Wall-clock cap: stop cleanly at the turn boundary. Everything
            # already produced (streamed text, tool results in the session)
            # is preserved; the project layer appends the "say continue"
            # notice, and the persisted session lets the next turn resume.
            if self._deadline is not None and time.monotonic() >= self._deadline:
                yield AgentEvent(
                    type="final",
                    turn=turn,
                    data={
                        "final_text": last_assistant_text,
                        "stop_reason": "max_time",
                    },
                )
                return

            # Mutates session.messages in place; no-op when under the threshold.
            await self._maybe_compress_session(session)

            turn_started = time.monotonic()
            try:
                if stream and self.mode != "react":
                    assistant_message = None
                    async for chunk in self._stream_turn_with_fallback(session, turn):
                        if isinstance(chunk, str):
                            yield AgentEvent(type="text_delta", turn=turn, data={"text": chunk})
                        else:
                            assistant_message = chunk
                            break
                    if assistant_message is None:
                        raise RuntimeError("stream_complete did not yield a final Message")
                else:
                    assistant_message = await self._run_turn_with_fallback(session, turn)
            except Exception as e:
                logger.exception("agent2 provider call failed on turn %d", turn)
                error_text = f"Provider error: {e}"
                if self.fallback_trail:
                    tried = " → ".join(
                        [self.fallback_trail[0]["from"] or "primary"]
                        + [t["to"] or "fallback" for t in self.fallback_trail]
                    )
                    error_text += f" (fallback chain exhausted: {tried})"
                yield AgentEvent(
                    type="final",
                    turn=turn,
                    data={
                        "final_text": error_text,
                        "stop_reason": "error",
                    },
                )
                return

            session.messages.append(assistant_message)
            self._accumulate_usage(assistant_message)
            text_now = assistant_message.text_content()
            if text_now:
                last_assistant_text = text_now
            # Turn wall time (retries/backoff/fallback switches included) +
            # the model that served it — feeds the persisted trace timeline.
            yield AgentEvent(
                type="assistant",
                message=assistant_message,
                turn=turn,
                data={
                    "turn_latency_ms": int((time.monotonic() - turn_started) * 1000),
                    "llm": self.active_llm_name or None,
                },
            )

            tool_calls = [
                b for b in assistant_message.content if isinstance(b, ToolUseBlock)
            ]
            if not tool_calls:
                yield AgentEvent(
                    type="final",
                    message=assistant_message,
                    turn=turn,
                    data={
                        "final_text": last_assistant_text,
                        "stop_reason": "completed",
                    },
                )
                return

            # Execute the turn's tool calls in parallel — the LLM decided they
            # were independent by emitting them as a batch. Yield order matches
            # call order so the streaming protocol stays deterministic.
            results = await asyncio.gather(
                *(self._execute_tool_call(tc) for tc in tool_calls)
            )
            for result_block, tc in zip(results, tool_calls):
                tool_msg = Message(role="user", content=[result_block])
                session.messages.append(tool_msg)
                yield AgentEvent(type="tool_result", message=tool_msg, turn=turn)

                # Hot-add newly created tools so they're usable this conversation.
                if tc.name == "create_tool" and not result_block.is_error and "created successfully" in result_block.content:
                    self._reload_project_tools()

        yield AgentEvent(
            type="final",
            turn=session.turn_count,
            data={
                "final_text": last_assistant_text,
                "stop_reason": "max_turns",
            },
        )

    def _deadline_passed(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline

    async def _retrying(self, thunk) -> Message:
        """Run `thunk` with same-provider retries on transient errors.
        Retries (and their backoff sleeps) stop once the run's wall-clock
        deadline has passed — no point burning budget the turn check will
        reject anyway."""
        attempt = 0
        while True:
            try:
                return await thunk()
            except Exception as e:
                if (
                    attempt >= self.retry_attempts
                    or not is_retryable_error(e)
                    or self._deadline_passed()
                ):
                    raise
                delay = backoff_delay(attempt, base=self.retry_base_delay)
                attempt += 1
                self.retry_count += 1
                logger.warning(
                    "agent2: transient provider error on '%s' (%s); "
                    "retry %d/%d in %.1fs",
                    self.active_llm_name or "primary",
                    e, attempt, self.retry_attempts, delay,
                )
                await asyncio.sleep(delay)

    def _advance_provider_chain(self, err: Exception, turn: int) -> bool:
        """Switch to the next fallback LLM; True if one was available.

        The new provider gets a fresh start: the originally requested mode is
        restored (a native→ReAct downgrade on the dead provider shouldn't
        condemn a tool-calling-capable fallback to ReAct).
        """
        if self._chain_idx + 1 >= len(self._provider_chain):
            return False
        if self._deadline_passed():
            logger.warning(
                "agent2: not switching to a fallback LLM — the run's "
                "wall-clock deadline has already passed",
            )
            return False
        previous = self.active_llm_name
        self._chain_idx += 1
        self.mode = self._initial_mode
        self._auto_fallback_allowed = self._initial_auto_allowed
        self.fallback_trail.append({
            "from": previous,
            "to": self.active_llm_name,
            "turn": turn,
            "error": str(err)[:300],
        })
        logger.warning(
            "agent2: switching to fallback LLM '%s' after '%s' failed: %s",
            self.active_llm_name, previous, err,
        )
        return True

    async def _run_turn_with_fallback(self, session: AgentSession, turn: int) -> Message:
        """Run one turn with the full resilience ladder: transient retries on
        the active provider → native→ReAct swap (auto mode, turn 1,
        non-transient errors only) → next LLM in the fallback chain."""
        while True:
            try:
                if self.mode == "react":
                    return await self._retrying(lambda: self._react_turn(session))
                try:
                    return await self._retrying(lambda: self._native_turn(session))
                except Exception as native_err:
                    # ReAct downgrade only helps when the provider rejected
                    # the native tools array; a provider that is down/rate-
                    # limited fails ReAct identically — let the chain handle it.
                    if (
                        self._auto_fallback_allowed
                        and turn == 1
                        and not is_retryable_error(native_err)
                    ):
                        logger.info(
                            "agent2: native function calling failed (%s); "
                            "falling back to ReAct mode",
                            native_err,
                        )
                        self.mode = "react"
                        self._auto_fallback_allowed = False
                        return await self._retrying(lambda: self._react_turn(session))
                    raise
            except Exception as provider_err:
                if not self._advance_provider_chain(provider_err, turn):
                    raise

    async def _stream_turn_with_fallback(
        self, session: AgentSession, turn: int
    ) -> AsyncIterator[Union[str, Message]]:
        """Streaming variant of the resilience ladder. Retries, the ReAct
        swap, and chain switches are only possible before the first text
        delta reaches the client — after that, restarting would duplicate
        already-streamed output, so errors propagate."""
        attempt = 0
        while True:
            emitted_any = False
            try:
                async for chunk in self._active_provider.stream_complete(
                    system_prompt=self.system_prompt,
                    messages=session.messages,
                    tools=self.tools,
                    config=self._active_config,
                ):
                    if isinstance(chunk, str):
                        emitted_any = True
                    yield chunk
                return
            except Exception as primary_err:
                if emitted_any:
                    raise
                if (
                    is_retryable_error(primary_err)
                    and attempt < self.retry_attempts
                    and not self._deadline_passed()
                ):
                    delay = backoff_delay(attempt, base=self.retry_base_delay)
                    attempt += 1
                    self.retry_count += 1
                    logger.warning(
                        "agent2: transient streaming error on '%s' (%s); "
                        "retry %d/%d in %.1fs",
                        self.active_llm_name or "primary",
                        primary_err, attempt, self.retry_attempts, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Native → ReAct (only on turn 1, only in auto mode, only for
                # non-transient errors). ReAct is non-streaming — we just
                # yield its result as a single final Message (no text deltas).
                if (
                    self._auto_fallback_allowed
                    and turn == 1
                    and self.mode != "react"
                    and not is_retryable_error(primary_err)
                ):
                    logger.info(
                        "agent2: streaming native call failed (%s); "
                        "falling back to ReAct mode (non-streaming)",
                        primary_err,
                    )
                    self.mode = "react"
                    self._auto_fallback_allowed = False
                    try:
                        msg = await self._retrying(lambda: self._react_turn(session))
                    except Exception as react_err:
                        if self._advance_provider_chain(react_err, turn):
                            attempt = 0
                            continue
                        raise
                    yield msg
                    return
                if self._advance_provider_chain(primary_err, turn):
                    attempt = 0
                    continue
                raise

    def _absorb_side_usage(self, usage: dict) -> None:
        """Fold non-turn LLM spend (e.g. the compression summarizer) into the
        run totals. Turn counters stay untouched so `usage_complete` still
        reflects whether every *turn* reported usage."""
        try:
            self.usage_input += int(usage.get("input") or 0)
            self.usage_output += int(usage.get("output") or 0)
        except (TypeError, ValueError, AttributeError):
            pass

    async def _maybe_compress_session(self, session: AgentSession) -> None:
        """Sliding-window + summary compression when over context window. No-op if window unknown."""
        cw = self._active_config.context_window
        if not cw:
            return
        try:
            await compress_session(
                session,
                provider=self._active_provider,
                config=self._active_config,
                context_window=cw,
                usage_sink=self._absorb_side_usage,
            )
        except Exception as e:
            logger.warning(
                "agent2: session compression failed (%s); proceeding uncompressed", e
            )

    @property
    def _active_provider(self) -> Provider:
        return self._provider_chain[self._chain_idx][1]

    @property
    def _active_config(self) -> ProviderConfig:
        return self._provider_chain[self._chain_idx][2]

    @property
    def active_llm_name(self) -> str:
        """Display name of the LLM currently serving turns (empty if unset)."""
        return self._provider_chain[self._chain_idx][0]

    def _accumulate_usage(self, message: Message) -> None:
        """Fold one assistant turn's real provider usage into the run totals."""
        self.llm_turns += 1
        usage = getattr(message, "usage", None)
        if not isinstance(usage, dict):
            return
        try:
            in_tokens = int(usage.get("input") or 0)
            out_tokens = int(usage.get("output") or 0)
        except (TypeError, ValueError):
            return
        if in_tokens <= 0 and out_tokens <= 0:
            return
        self.usage_input += in_tokens
        self.usage_output += out_tokens
        self.usage_turns += 1

    @property
    def usage_complete(self) -> bool:
        """True when every LLM turn this run reported real usage (billing-
        accurate totals; summing per-call input matches what providers bill)."""
        return self.llm_turns > 0 and self.usage_turns == self.llm_turns

    async def _native_turn(self, session: AgentSession) -> Message:
        """Native function calling — provider sees the tools array."""
        return await self._active_provider.complete(
            system_prompt=self.system_prompt,
            messages=session.messages,
            tools=self.tools,
            config=self._active_config,
        )

    async def _react_turn(self, session: AgentSession) -> Message:
        """Text-based ReAct prompting; tools described in system prompt, none passed to provider."""
        react_system = build_react_system_prompt(self.system_prompt, self.tools)
        text_messages = self._react_messages(session.messages)
        response_msg = await self._active_provider.complete(
            system_prompt=react_system,
            messages=text_messages,
            tools=[],  # IMPORTANT: never pass tools in react mode
            config=self._active_config,
        )
        parsed = parse_react_response(response_msg.text_content())
        return self._build_react_message(parsed, usage=getattr(response_msg, "usage", None))

    @staticmethod
    def _react_messages(messages: Sequence[Message]) -> list[Message]:
        """Rewrite ToolUse/ToolResult blocks to plain text on the way to the LLM.

        Original blocks stay in session.messages so the project layer's
        reasoning recorder still works.
        """
        rewritten: list[Message] = []
        for msg in messages:
            new_blocks: list = []
            for block in msg.content:
                if isinstance(block, TextBlock):
                    new_blocks.append(block)
                elif isinstance(block, ImageBlock):
                    # ReAct fallback is text-only; the model can't see the image.
                    new_blocks.append(TextBlock(text="[image attachment — not available in ReAct mode]"))
                elif isinstance(block, ToolUseBlock):
                    try:
                        args_json = json.dumps(block.input or {})
                    except Exception:
                        args_json = str(block.input or {})
                    new_blocks.append(
                        TextBlock(
                            text=f"Action: {block.name}\nAction Input: {args_json}"
                        )
                    )
                elif isinstance(block, ToolResultBlock):
                    prefix = "Observation"
                    if block.is_error:
                        prefix = "Observation (error)"
                    new_blocks.append(
                        TextBlock(text=f"{prefix}: {block.content or ''}")
                    )
            if new_blocks:
                rewritten.append(Message(role=msg.role, content=new_blocks))
        return rewritten

    @staticmethod
    def _build_react_message(
        parsed: ReactParseResult, usage: Optional[dict] = None
    ) -> Message:
        """Synthesize an assistant Message indistinguishable from a native turn's output."""
        if parsed.kind == "action" and parsed.action_name:
            blocks: list = []
            if parsed.thought:
                blocks.append(TextBlock(text=f"Thought: {parsed.thought}"))
            blocks.append(
                ToolUseBlock(
                    id=f"react_{uuid4().hex}",
                    name=parsed.action_name,
                    input=parsed.action_input or {},
                )
            )
            return Message(role="assistant", content=blocks, usage=usage)

        if parsed.kind == "final":
            return Message(
                role="assistant",
                content=[TextBlock(text=(parsed.final_text or "").strip())],
                usage=usage,
            )

        # kind == "text" — model didn't follow the format; treat as final answer
        return Message(
            role="assistant",
            content=[TextBlock(text=parsed.final_text or "")],
            usage=usage,
        )

    def _reload_project_tools(self):
        """Reload project-created tools from DB and add new ones to the runtime."""
        project_id = getattr(self, "_project_id", None)
        brain = getattr(self, "_brain", None)
        if not project_id or not brain:
            return
        try:
            from restai.database import DBWrapper as _DBW
            from restai.projects.agent import _make_project_tool_adapted
            _db = _DBW()
            try:
                for pt in _db.get_project_tools(project_id):
                    if pt.name not in self._tools_by_name:
                        adapted = _make_project_tool_adapted(pt, brain)
                        self.tools.append(adapted)
                        self._tools_by_name[adapted.name] = adapted
            finally:
                _db.db.close()
        except Exception as e:
            logger.warning("Failed to reload project tools: %s", e)

    def _loop_guard_note(self, name: str, args: dict) -> str:
        """Count identical (tool, args) calls this run; from the 3rd repeat on,
        return a nudge to append to the result. The call still executes —
        stateful tools (terminal, browser) may legitimately repeat — but the
        note breaks the classic stuck-model pattern of re-issuing the same
        call for dozens of turns."""
        try:
            canonical = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            canonical = str(args)
        key = (name, canonical)
        count = self._call_counts.get(key, 0) + 1
        self._call_counts[key] = count
        if count < 3:
            return ""
        return (
            f"\n\n[loop guard: this exact tool call has now run {count} times "
            "this request. If the result isn't changing, adjust the arguments "
            "or approach — or produce your final answer with what you have.]"
        )

    async def _execute_tool_call(self, tool_call: ToolUseBlock) -> ToolResultBlock:
        tool = self._tools_by_name.get(tool_call.name)
        if tool is None:
            available = ", ".join(sorted(self._tools_by_name.keys())[:40])
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=(
                    f"Error: No such tool available: {tool_call.name}. "
                    f"Available tools: {available or '(none)'}"
                ),
                is_error=True,
            )

        args = tool_call.input or {}
        if not isinstance(args, dict):
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Error: tool input must be an object, got {type(args).__name__}",
                is_error=True,
            )

        # Validate + coerce against the tool's schema so a fixable slip
        # ("5" for an integer) succeeds and a real mismatch comes back as a
        # crisp, self-correctable message instead of a deep TypeError.
        args, problems = coerce_and_validate_args(tool.input_schema, args)
        if problems:
            schema_hint = describe_schema_for_error(tool.input_schema)
            content = (
                f"Error: invalid arguments for tool '{tool_call.name}': "
                + "; ".join(problems)
            )
            if schema_hint:
                content += f". Expected parameters: {schema_hint}"
            return ToolResultBlock(
                tool_use_id=tool_call.id, content=content, is_error=True,
            )

        guard_note = self._loop_guard_note(tool_call.name, args)

        try:
            context = {
                "chat_id": getattr(self, "_chat_id", None),
                "brain": getattr(self, "_brain", None),
                "project_id": getattr(self, "_project_id", None),
                "user": getattr(self, "_user", None),
            }
            call_coro = tool.call(args, context=context)
            if self.tool_timeout:
                result_text = await asyncio.wait_for(
                    call_coro, timeout=self.tool_timeout
                )
            else:
                result_text = await call_coro
        except asyncio.TimeoutError:
            logger.warning(
                "agent2 tool '%s' timed out after %.0fs",
                tool_call.name, self.tool_timeout or 0,
            )
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=(
                    f"ERROR: tool '{tool_call.name}' timed out after "
                    f"{int(self.tool_timeout or 0)}s. The operation may still "
                    "finish in the background. Try a smaller input, a quicker "
                    "check, or a different approach."
                ),
                is_error=True,
            )
        except Exception as e:
            logger.exception("agent2 tool '%s' raised", tool_call.name)
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Error calling tool ({tool_call.name}): {e}",
                is_error=True,
            )

        # Cap a single tool result so it can't dominate — or overflow — the
        # model's context window. Scales with the window: a tiny local model
        # (e.g. a 4k-token model) gets a small cap, big models keep a generous
        # one (≈ the legacy 20k-char limit). Without this, one giant tool
        # result exceeds the whole window and compression — which summarizes /
        # drops WHOLE messages — can never bring the session under budget.
        cw = getattr(getattr(self, "_active_config", None), "context_window", None)
        if cw and cw > 0:
            result_text = truncate_text_to_token_budget(
                result_text, max(512, min(6000, cw // 4)),
            )
        elif len(result_text) > 20_000:
            omitted = len(result_text) - 20_000
            result_text = result_text[:20_000] + f"\n\n[... truncated {omitted} characters ...]"

        if guard_note:
            result_text = (result_text or "") + guard_note

        return ToolResultBlock(tool_use_id=tool_call.id, content=result_text)
