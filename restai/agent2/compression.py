"""Sliding-window + summary compression for agent2 chat sessions.

When `session.messages` would exceed the LLM's context window, we:

1. Identify the last N "user-initiated" turns (a turn starts at a user message
   that contains only TextBlocks — never in the middle of a tool_use/tool_result
   pair).
2. Compress everything before that boundary into a single summary, generated
   by the same provider with `tools=[]`.
3. Prepend the summary to the first kept user message so the LLM sees:
   `[Earlier conversation summary] ...\\n\\n[Current question] ...`
4. Recursive: subsequent compressions detect any prior summary at the start
   of the to-compress slice and feed it back to the summarizer as context.
5. Failure mode: if the summary call fails, fall back to hard truncation by
   token budget while preserving turn boundaries.

This module is pure functions; only `_call_summarizer` performs I/O. Designed
to be called from `Agent2Runtime.run_iter` once per turn.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

import tiktoken

from .types import (
    AgentSession,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    user_text_message,
)

logger = logging.getLogger(__name__)

# Cache the tiktoken encoder once at module import. tiktoken's get_encoding
# has its own internal cache but the lookup still costs ~80ns per call;
# binding it here makes count_session_tokens a tight loop.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _encode_len(text: str) -> int:
    return len(_ENCODING.encode(text or ""))


DEFAULT_CONTEXT_RATIO = 0.75
DEFAULT_KEEP_RECENT_TURNS = 3
SUMMARY_MARKER = "[Earlier conversation summary]"
CURRENT_QUESTION_MARKER = "[Current question]"

# Per-message and per-block overhead estimates (matches the OpenAI cookbook
# guidance for chat completion token counting).
PER_MESSAGE_OVERHEAD_TOKENS = 4
PER_TOOL_USE_OVERHEAD_TOKENS = 8
PER_TOOL_RESULT_OVERHEAD_TOKENS = 6


# ---------- token counting ----------


def _count_message_tokens(msg: Message) -> int:
    total = PER_MESSAGE_OVERHEAD_TOKENS
    for block in msg.content:
        if isinstance(block, TextBlock):
            total += _encode_len(block.text or "")
        elif isinstance(block, ToolUseBlock):
            total += PER_TOOL_USE_OVERHEAD_TOKENS
            total += _encode_len(block.name or "")
            try:
                args_text = json.dumps(block.input or {})
            except Exception:
                args_text = str(block.input or {})
            total += _encode_len(args_text)
        elif isinstance(block, ToolResultBlock):
            total += PER_TOOL_RESULT_OVERHEAD_TOKENS
            total += _encode_len(block.content or "")
    return total


def count_session_tokens(messages: Sequence[Message]) -> int:
    """Approximate total tokens for a message list."""
    return sum(_count_message_tokens(m) for m in messages)


# ---------- turn boundaries ----------


def _is_pure_user_message(msg: Message) -> bool:
    """A message that starts a 'turn' — user role with only TextBlocks
    (no ToolResultBlocks). This guarantees we never split a tool_use /
    tool_result pair when slicing the history."""
    if msg.role != "user":
        return False
    if not msg.content:
        return False
    return all(isinstance(b, TextBlock) for b in msg.content)


def find_user_turn_boundaries(messages: Sequence[Message]) -> list[int]:
    """Indices of messages that mark the start of a conversational turn."""
    return [i for i, m in enumerate(messages) if _is_pure_user_message(m)]


def split_for_compression(
    messages: Sequence[Message], keep_n_turns: int
) -> tuple[list[Message], list[Message]]:
    """Split into (to_compress, to_keep) at the Nth-from-last turn boundary.

    Returns ([], list(messages)) if there aren't enough turns to compress.
    """
    boundaries = find_user_turn_boundaries(messages)
    if len(boundaries) <= keep_n_turns:
        return [], list(messages)
    keep_start = boundaries[-keep_n_turns]
    return list(messages[:keep_start]), list(messages[keep_start:])


# ---------- prior summary extraction ----------


def _extract_prior_summary(
    messages: list[Message],
) -> tuple[Optional[str], list[Message]]:
    """If the first message is a user message whose first TextBlock starts with
    SUMMARY_MARKER, extract the summary text and return (summary, rest).
    Otherwise return (None, messages)."""
    if not messages:
        return None, messages
    first = messages[0]
    if first.role != "user" or not first.content:
        return None, messages
    block = first.content[0]
    if not isinstance(block, TextBlock):
        return None, messages
    text = block.text or ""
    if not text.startswith(SUMMARY_MARKER):
        return None, messages

    # Strip the marker and any trailing "[Current question]" section. The
    # current-question section, if present, was the user's actual prompt that
    # got prepended on the previous compression — leave it in place by NOT
    # consuming it from the message list. We only extract the summary text.
    body = text[len(SUMMARY_MARKER):].lstrip("\n")
    cq_idx = body.find(CURRENT_QUESTION_MARKER)
    if cq_idx >= 0:
        summary_text = body[:cq_idx].strip()
    else:
        summary_text = body.strip()
    return summary_text or None, messages


# ---------- history rendering for the summarizer ----------


def _render_messages_as_text(messages: Sequence[Message]) -> str:
    """Walk the message list and produce a plain-text transcript the
    summarizer can read. Strips the summary marker from any prior summary so
    the summarizer doesn't double-include it (we pass that as a separate
    `prior_summary` argument)."""
    lines: list[str] = []
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                text = block.text or ""
                if text.startswith(SUMMARY_MARKER):
                    # Skip — caller passes this as prior_summary
                    continue
                role = "USER" if msg.role == "user" else "ASSISTANT"
                lines.append(f"{role}: {text}")
            elif isinstance(block, ToolUseBlock):
                try:
                    args = json.dumps(block.input or {})
                except Exception:
                    args = str(block.input or {})
                lines.append(f"ASSISTANT used tool '{block.name}' with input: {args}")
            elif isinstance(block, ToolResultBlock):
                tag = "TOOL ERROR" if block.is_error else "TOOL RESULT"
                lines.append(f"{tag}: {block.content or ''}")
    return "\n".join(lines)


# ---------- summarizer call ----------


_SUMMARY_SYSTEM_PROMPT = (
    "You are a conversation memory compressor. Your only job is to produce a "
    "concise running summary of a conversation between a user and an AI "
    "assistant so the assistant can continue the chat with limited context."
)


def _build_summary_user_prompt(history_text: str, prior_summary: Optional[str]) -> str:
    parts: list[str] = [
        "Summarize the following conversation. Preserve key facts, decisions, "
        "names, numbers, file paths, identifiers, and any incomplete tasks. "
        "Be concise — aim for 200-400 words. Output ONLY the summary text.",
    ]
    if prior_summary:
        parts.append("\n[Existing summary of even earlier turns]")
        parts.append(prior_summary)
    parts.append("\n[Conversation to summarize]")
    parts.append(history_text)
    return "\n".join(parts)


async def _call_summarizer(
    provider,
    config,
    history_text: str,
    prior_summary: Optional[str],
) -> Optional[str]:
    """Ask the provider to summarize the conversation. Returns the summary
    text, or None on failure.

    Reuses the agent's own provider so we don't need a separate summarizer
    LLM. The call is made with `tools=[]` so the model can't accidentally
    invoke functions during summarization, and with a capped
    `max_output_tokens` so the summary can't bloat unbounded.
    """
    from dataclasses import replace as dc_replace

    try:
        summary_config = dc_replace(
            config,
            max_output_tokens=min(config.max_output_tokens or 1024, 1024),
        )
    except Exception:
        summary_config = config

    try:
        prompt = _build_summary_user_prompt(history_text, prior_summary)
        response = await provider.complete(
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
            messages=[user_text_message(prompt)],
            tools=[],
            config=summary_config,
        )
        text = response.text_content().strip()
        return text or None
    except Exception as e:
        logger.warning("agent2: summarizer call failed (%s)", e)
        return None


# ---------- main entry points ----------


def hard_truncate(
    messages: list[Message], target_tokens: int, keep_n_turns: int
) -> list[Message]:
    """Drop oldest messages until total tokens fall under target_tokens.

    Truncation respects turn boundaries — we always slice at a user-turn-start
    so we never produce a dangling tool_result. If even keeping the last
    `keep_n_turns` turns is over budget, we keep slicing forward until we fit
    or until only the very last turn remains.
    """
    if not messages:
        return messages

    # Walk turn boundaries from newest to oldest, keeping the largest suffix
    # that fits in the budget. Always keep at least the last turn.
    boundaries = find_user_turn_boundaries(messages)
    if not boundaries:
        # No clean turn boundary at all — return as-is and hope for the best
        return list(messages)

    # Try suffixes starting from each boundary, newest-first
    for n in range(min(keep_n_turns, len(boundaries)), 0, -1):
        candidate = list(messages[boundaries[-n]:])
        if count_session_tokens(candidate) <= target_tokens:
            return candidate

    # Even the most recent single turn is over budget — return it anyway,
    # the provider will surface a clear error and the user can shrink their
    # input.
    return list(messages[boundaries[-1]:])


def _approx_char_count(messages: Sequence[Message]) -> int:
    """Sum of raw character lengths across all blocks. ~3-4 chars/token in
    practice, used as a cheap pre-check before paying for tokenization."""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += len(block.text or "")
            elif isinstance(block, ToolResultBlock):
                total += len(block.content or "")
            else:  # ToolUseBlock
                total += 32  # rough envelope estimate
    return total


async def compress_session(
    session: AgentSession,
    *,
    provider,
    config,
    context_window: int,
    ratio: float = DEFAULT_CONTEXT_RATIO,
    keep_recent_turns: int = DEFAULT_KEEP_RECENT_TURNS,
) -> bool:
    """If session.messages exceed (context_window * ratio) tokens, compress
    them in-place and return True. Otherwise return False.

    See module docstring for the algorithm.
    """
    if not context_window or context_window <= 0:
        return False

    target_tokens = int(context_window * ratio)

    # Cheap pre-check: if even a generous chars-per-token ratio (3) puts us
    # under the budget, skip the real tokenization. This makes the no-op path
    # microseconds instead of milliseconds for chats with chunky tool results.
    if _approx_char_count(session.messages) < target_tokens * 3:
        return False

    current_tokens = count_session_tokens(session.messages)
    if current_tokens <= target_tokens:
        return False

    logger.info(
        "agent2: compressing session — %d tokens > %d budget (%d-token window, ratio %.2f)",
        current_tokens, target_tokens, context_window, ratio,
    )

    to_compress, to_keep = split_for_compression(session.messages, keep_recent_turns)

    if not to_compress:
        # Not enough turns to do a sliding-window split — fall back to hard truncation.
        truncated = hard_truncate(list(session.messages), target_tokens, keep_recent_turns)
        if len(truncated) < len(session.messages):
            session.messages = truncated
            logger.info("agent2: compression fallback used hard truncation (%d → %d messages)",
                        current_tokens, count_session_tokens(truncated))
            return True
        return False

    # Detect any prior summary embedded in the to-compress slice
    prior_summary, to_compress = _extract_prior_summary(to_compress)

    history_text = _render_messages_as_text(to_compress)
    summary = await _call_summarizer(provider, config, history_text, prior_summary)

    if not summary:
        # Summarizer failed — fall back to hard truncation
        logger.warning("agent2: summarizer returned no text; falling back to hard truncation")
        truncated = hard_truncate(list(session.messages), target_tokens, keep_recent_turns)
        if len(truncated) < len(session.messages):
            session.messages = truncated
            return True
        return False

    # Prepend the summary to the first kept user message (if any)
    new_messages = _prepend_summary_to_first_user(to_keep, summary)
    session.messages = new_messages

    after_tokens = count_session_tokens(session.messages)
    logger.info(
        "agent2: compression complete — %d → %d tokens (%d-message summary)",
        current_tokens, after_tokens, len(summary.split()),
    )

    # If we're STILL over budget after summarization (giant tool result in the
    # kept window, etc.), apply hard truncation as a final pass.
    if after_tokens > target_tokens:
        logger.info("agent2: still over budget after summary; applying hard truncation")
        session.messages = hard_truncate(session.messages, target_tokens, keep_recent_turns)

    return True


def _prepend_summary_to_first_user(
    kept: list[Message], summary: str
) -> list[Message]:
    """Insert the summary into the first kept user message (or as a new
    leading message if there's no user message at the start)."""
    if not kept:
        return [user_text_message(f"{SUMMARY_MARKER}\n{summary}")]

    # Find the first pure user message in the kept list
    for i, msg in enumerate(kept):
        if _is_pure_user_message(msg):
            original_text = msg.content[0].text if msg.content else ""
            new_text = (
                f"{SUMMARY_MARKER}\n{summary}\n\n"
                f"{CURRENT_QUESTION_MARKER}\n{original_text}"
            )
            new_msg = Message(role="user", content=[TextBlock(text=new_text)])
            return list(kept[:i]) + [new_msg] + list(kept[i + 1:])

    # No clean user message in the kept slice — fall back to inserting one
    return [user_text_message(f"{SUMMARY_MARKER}\n{summary}")] + list(kept)
