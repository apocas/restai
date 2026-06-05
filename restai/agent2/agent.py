"""The agent2 ReAct-style run loop. No llamaindex imports."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Literal, Optional, Sequence, Union
from uuid import uuid4

from .compression import compress_session, truncate_text_to_token_budget
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

            # Mutates session.messages in place; no-op when under the threshold.
            await self._maybe_compress_session(session)

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

    async def _run_turn_with_fallback(self, session: AgentSession, turn: int) -> Message:
        """Run one turn; in auto mode, swap native→ReAct on first-turn failure."""
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

    async def _stream_turn_with_fallback(
        self, session: AgentSession, turn: int
    ) -> AsyncIterator[Union[str, Message]]:
        """Streaming variant; native→ReAct fallback only before any delta is emitted."""
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
            # Native → ReAct (only on turn 1, only in auto mode).
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
            raise

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
            )
        except Exception as e:
            logger.warning(
                "agent2: session compression failed (%s); proceeding uncompressed", e
            )

    @property
    def _active_provider(self) -> Provider:
        return self.provider

    @property
    def _active_config(self) -> ProviderConfig:
        return self.config

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
        return self._build_react_message(parsed)

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
    def _build_react_message(parsed: ReactParseResult) -> Message:
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
            return Message(role="assistant", content=blocks)

        if parsed.kind == "final":
            return Message(
                role="assistant", content=[TextBlock(text=(parsed.final_text or "").strip())]
            )

        # kind == "text" — model didn't follow the format; treat as final answer
        return Message(role="assistant", content=[TextBlock(text=parsed.final_text or "")])

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
                "project_id": getattr(self, "_project_id", None),
                "user": getattr(self, "_user", None),
            }
            result_text = await tool.call(args, context=context)
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

        return ToolResultBlock(tool_use_id=tool_call.id, content=result_text)
