"""The agent2 ReAct-style run loop. No llamaindex imports."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Literal, Optional, Sequence, Union
from uuid import uuid4

from .compression import compress_session
from .providers import (
    Agent2ProviderError,
    Agent2UnsupportedLLMError,
    Provider,
    ProviderConfig,
)
from .react_prompt import (
    ReactParseResult,
    build_react_system_prompt,
    parse_react_response,
)
from .tool_adapter import AdaptedTool
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
    """A standalone (non-llamaindex) agent loop.

    Construct one per run with the resolved provider, tools, system prompt,
    and turn budget. Then call `run_iter()` to drive the loop and consume
    `AgentEvent`s.
    """

    def __init__(
        self,
        *,
        provider: Provider,
        config: ProviderConfig,
        tools: Sequence[AdaptedTool],
        system_prompt: Optional[str] = None,
        max_turns: int = 12,
        mode: Optional[AgentMode] = None,
        fallback_provider: Optional[Provider] = None,
        fallback_config: Optional[ProviderConfig] = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.tools = list(tools)
        self._tools_by_name: dict[str, AdaptedTool] = {t.name: t for t in self.tools}
        self.system_prompt = system_prompt or ""
        self.max_turns = max(1, int(max_turns))
        # "auto" starts in function_calling and may switch on first-turn error.
        self.mode: AgentMode = (
            "function_calling" if (mode or "auto") == "auto" else (mode or "auto")
        )
        self._auto_fallback_allowed: bool = (mode or "auto") == "auto"
        # Fallback LLM (project.props.options.fallback_llm). Used to retry the
        # current turn if the primary provider raises. Independent of the
        # native↔react auto-fallback above.
        self._fallback_provider: Optional[Provider] = fallback_provider
        self._fallback_config: Optional[ProviderConfig] = fallback_config
        self._fallback_active: bool = False

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

            # Compress history if it's about to exceed the model's context
            # window. Mutates session.messages in place; safe to call every
            # turn — it's a no-op when we're under the threshold.
            await self._maybe_compress_session(session)

            try:
                if stream and self.mode != "react":
                    # Streaming path: yield text_delta events as deltas arrive,
                    # then return the assembled Message.
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
                yield AgentEvent(
                    type="final",
                    turn=turn,
                    data={
                        "final_text": f"Provider error: {e}",
                        "stop_reason": "error",
                    },
                )
                return

            session.messages.append(assistant_message)
            text_now = assistant_message.text_content()
            if text_now:
                last_assistant_text = text_now
            yield AgentEvent(type="assistant", message=assistant_message, turn=turn)

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

            # Execute all tool calls from this turn in parallel — the LLM
            # already decided they're independent by emitting them as a batch.
            # Results are still appended (and yielded) in the original call
            # order so the streaming protocol stays deterministic.
            results = await asyncio.gather(
                *(self._execute_tool_call(tc) for tc in tool_calls)
            )
            for result_block in results:
                tool_msg = Message(role="user", content=[result_block])
                session.messages.append(tool_msg)
                yield AgentEvent(type="tool_result", message=tool_msg, turn=turn)

        # Hit the turn budget without producing a tool-free response
        yield AgentEvent(
            type="final",
            turn=session.turn_count,
            data={
                "final_text": last_assistant_text,
                "stop_reason": "max_turns",
            },
        )

    # ---------- per-turn helpers ----------

    async def _run_turn_with_fallback(self, session: AgentSession, turn: int) -> Message:
        """Run one turn through the active mode, with two layers of fallback:

        1. **Native → ReAct** (intra-provider): if the user picked auto mode and
           the first-turn native call fails, swap to text-based ReAct.
        2. **Primary → fallback LLM** (cross-provider): if the call fails on
           any turn AND a `fallback_llm` is configured, swap to the fallback
           provider for the rest of the run.

        Both layers can fire on the same turn (native fails → ReAct fails →
        fallback provider). After fallback activation, the runtime stays on the
        fallback for all subsequent turns of this run.
        """
        try:
            if self.mode == "react":
                return await self._react_turn(session)
            try:
                return await self._native_turn(session)
            except Exception as native_err:
                if self._auto_fallback_allowed and turn == 1:
                    logger.info(
                        "agent2: native function calling failed (%s); "
                        "falling back to ReAct mode",
                        native_err,
                    )
                    self.mode = "react"
                    self._auto_fallback_allowed = False
                    return await self._react_turn(session)
                raise
        except Exception as primary_err:
            if self._fallback_provider is not None and not self._fallback_active:
                logger.warning(
                    "agent2: primary LLM failed on turn %d (%s); "
                    "switching to fallback LLM for remainder of run",
                    turn, primary_err,
                )
                self._fallback_active = True
                # Retry the SAME turn against the fallback provider
                if self.mode == "react":
                    return await self._react_turn(session)
                return await self._native_turn(session)
            raise

    async def _stream_turn_with_fallback(
        self, session: AgentSession, turn: int
    ) -> AsyncIterator[Union[str, Message]]:
        """Streaming variant of `_run_turn_with_fallback`.

        Yields text deltas as `str`, then the final `Message`. Fallback only
        kicks in if the primary stream fails BEFORE any delta has been
        emitted — once we've started streaming to the user we can't un-emit,
        so mid-stream errors propagate.
        """
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
            # Layer 1: native → ReAct (only on turn 1, only in auto mode).
            # ReAct is non-streaming — we just yield its result as a single
            # final Message (no text deltas).
            if self._auto_fallback_allowed and turn == 1 and self.mode != "react":
                logger.info(
                    "agent2: streaming native call failed (%s); "
                    "falling back to ReAct mode (non-streaming)",
                    primary_err,
                )
                self.mode = "react"
                self._auto_fallback_allowed = False
                msg = await self._react_turn(session)
                yield msg
                return
            # Layer 2: primary LLM → fallback LLM
            if self._fallback_provider is not None and not self._fallback_active:
                logger.warning(
                    "agent2: primary streaming LLM failed on turn %d (%s); "
                    "switching to fallback LLM (streaming)",
                    turn, primary_err,
                )
                self._fallback_active = True
                async for chunk in self._active_provider.stream_complete(
                    system_prompt=self.system_prompt,
                    messages=session.messages,
                    tools=self.tools,
                    config=self._active_config,
                ):
                    yield chunk
                return
            raise

    async def _maybe_compress_session(self, session: AgentSession) -> None:
        """Run sliding-window + summary compression on the session if it's
        over the context window. No-op when context_window is unknown."""
        cw = self._active_config.context_window
        if not cw:
            return
        try:
            await compress_session(
                session,
                provider=self._active_provider,
                config=self._active_config,
                context_window=cw,
            )
        except Exception as e:
            logger.warning(
                "agent2: session compression failed (%s); proceeding uncompressed", e
            )

    @property
    def _active_provider(self) -> Provider:
        return self._fallback_provider if self._fallback_active else self.provider

    @property
    def _active_config(self) -> ProviderConfig:
        return self._fallback_config if self._fallback_active else self.config

    async def _native_turn(self, session: AgentSession) -> Message:
        """Run one turn using native function calling. Provider sees the real
        tools array; tool calls come back as structured ToolUseBlocks."""
        return await self._active_provider.complete(
            system_prompt=self.system_prompt,
            messages=session.messages,
            tools=self.tools,
            config=self._active_config,
        )

    async def _react_turn(self, session: AgentSession) -> Message:
        """Run one turn using text-based ReAct prompting. The provider does NOT
        see a tools array — instead, the system prompt describes the tools and
        the LLM emits Action/Action Input text that we parse out."""
        react_system = build_react_system_prompt(self.system_prompt, self.tools)
        text_messages = self._react_messages(session.messages)
        response_msg = await self._active_provider.complete(
            system_prompt=react_system,
            messages=text_messages,
            tools=[],  # IMPORTANT: never pass tools in react mode
            config=self._active_config,
        )
        parsed = parse_react_response(response_msg.text_content())
        return self._build_react_message(parsed)

    @staticmethod
    def _react_messages(messages: Sequence[Message]) -> list[Message]:
        """Walk the session and rewrite any ToolUseBlock / ToolResultBlock into
        plain text the model can read in ReAct format. The runtime keeps the
        original blocks in `session.messages` so the project layer's reasoning
        recorder still works — we only do the rewriting on the way to the LLM.
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
    def _build_react_message(parsed: ReactParseResult) -> Message:
        """Convert a parsed ReAct response into a synthetic assistant Message
        the rest of the loop can treat identically to a native one."""
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
            return Message(role="assistant", content=blocks)

        if parsed.kind == "final":
            return Message(
                role="assistant", content=[TextBlock(text=(parsed.final_text or "").strip())]
            )

        # kind == "text" — model didn't follow the format; treat as final answer
        return Message(role="assistant", content=[TextBlock(text=parsed.final_text or "")])

    async def _execute_tool_call(self, tool_call: ToolUseBlock) -> ToolResultBlock:
        tool = self._tools_by_name.get(tool_call.name)
        if tool is None:
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Error: No such tool available: {tool_call.name}",
                is_error=True,
            )

        args = tool_call.input or {}
        if not isinstance(args, dict):
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Error: tool input must be an object, got {type(args).__name__}",
                is_error=True,
            )

        try:
            context = {
                "chat_id": getattr(self, "_chat_id", None),
                "brain": getattr(self, "_brain", None),
            }
            result_text = await tool.call(args, context=context)
        except Exception as e:
            logger.exception("agent2 tool '%s' raised", tool_call.name)
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Error calling tool ({tool_call.name}): {e}",
                is_error=True,
            )

        # Truncate very long tool outputs to avoid blowing the context window
        if len(result_text) > 20_000:
            omitted = len(result_text) - 20_000
            result_text = result_text[:20_000] + f"\n\n[... truncated {omitted} characters ...]"

        return ToolResultBlock(tool_use_id=tool_call.id, content=result_text)
