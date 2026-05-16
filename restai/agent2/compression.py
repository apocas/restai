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
    ImageBlock,
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
# Headroom we reserve for the summary message + a bit of buffer so the
# kept slice + summary together comfortably fit under target_tokens.
# 4000 tokens is enough for a 400+ word summary plus framing overhead.
SUMMARY_RESERVE_TOKENS = 4000
SUMMARY_MARKER = "[Earlier conversation summary]"
CURRENT_QUESTION_MARKER = "[Current question]"

# Per-message and per-block overhead estimates (matches the OpenAI cookbook
# guidance for chat completion token counting).
PER_MESSAGE_OVERHEAD_TOKENS = 4
PER_TOOL_USE_OVERHEAD_TOKENS = 8
PER_TOOL_RESULT_OVERHEAD_TOKENS = 6


# ---------- token counting ----------


PER_IMAGE_BLOCK_TOKENS = 1024  # rough — providers vary widely; conservative


def _count_message_tokens(msg: Message) -> int:
    total = PER_MESSAGE_OVERHEAD_TOKENS
    for block in msg.content:
        if isinstance(block, TextBlock):
            total += _encode_len(block.text or "")
        elif isinstance(block, ImageBlock):
            total += PER_IMAGE_BLOCK_TOKENS
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


def find_safe_split_points(messages: Sequence[Message]) -> list[int]:
    """Indices where the prefix `messages[:i]` is self-contained — i.e.
    cutting at `i` doesn't orphan any assistant `tool_use` from its
    matching `tool_result`. Safe = the message at `i` has no
    `ToolResultBlock` (which would otherwise be the response to the
    assistant tool_use immediately before).

    Includes pure user-text turn boundaries by construction (those
    messages have no tool_result) plus assistant-text-only continuations
    and the start of the list. This widens the set of compressible
    chats — agent sessions with many tool calls inside one user turn
    can now still be summarized."""
    if not messages:
        return []
    points = [0]
    for i in range(1, len(messages)):
        if any(isinstance(b, ToolResultBlock) for b in messages[i].content):
            continue
        points.append(i)
    return points


def split_for_compression(
    messages: Sequence[Message],
    keep_n_turns: int,
    target_tokens: Optional[int] = None,
) -> tuple[list[Message], list[Message]]:
    """Split into (to_compress, to_keep) at a safe split point.

    Two modes:

    **Budget-aware** (`target_tokens` is given) — finds the LARGEST recent
    suffix whose token count fits within `target_tokens` at a safe split
    point. This is what production callers use (`compress_session`) so a
    100-iteration tool run that gets summarized doesn't waste the model's
    context window. Without this, a 142k-token session over a 142.5k
    budget would crater to ~3 messages instead of keeping ~140k tokens
    of recent context.

    **Turn-based** (`target_tokens` is None) — preserves the historic
    semantics for callers/tests that haven't moved to the budget API.
    Prefers user-text turn boundaries (most natural compression cut),
    falling back to safe split points when user turns can't satisfy
    `keep_n_turns`.

    Returns ([], list(messages)) when nothing useful can be compressed.
    ``_prepend_summary_to_first_user`` handles the case where the kept
    slice doesn't start with a user-role message.
    """
    if target_tokens is not None:
        safe = find_safe_split_points(messages)
        if not safe:
            return [], list(messages)
        # Walk oldest-first so the FIRST suffix that fits is the LARGEST.
        for keep_start in safe:
            if count_session_tokens(list(messages[keep_start:])) <= target_tokens:
                if keep_start == 0:
                    return [], list(messages)
                return list(messages[:keep_start]), list(messages[keep_start:])
        # Even the last single message doesn't fit — nothing safe to do here;
        # caller will fall back to hard_truncate.
        return [], list(messages)

    user_turns = find_user_turn_boundaries(messages)
    if len(user_turns) > keep_n_turns:
        keep_start = user_turns[-keep_n_turns]
        return list(messages[:keep_start]), list(messages[keep_start:])

    safe = find_safe_split_points(messages)
    if len(safe) > keep_n_turns:
        keep_start = safe[-keep_n_turns]
        return list(messages[:keep_start]), list(messages[keep_start:])

    return [], list(messages)


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

    # Walk safe split points oldest-first so the FIRST suffix that fits
    # is the LARGEST suffix that fits. Walking newest-first (the bug)
    # always returned the smallest fitting suffix — including just the
    # last single message when the full list was barely over budget,
    # cratering the chat from 142k tokens to ~460 tokens of context.
    boundaries = find_safe_split_points(messages)
    if not boundaries:
        return list(messages)

    for keep_start in boundaries:
        candidate = list(messages[keep_start:])
        if count_session_tokens(candidate) <= target_tokens:
            return candidate

    # Every suffix is over budget — return the smallest one anyway. The
    # provider will surface a clear error and the user can shrink input.
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
            elif isinstance(block, ImageBlock):
                # Force the fast-path to defer to real counting whenever an
                # image is present — image tokens are model-dependent.
                total += PER_IMAGE_BLOCK_TOKENS * 4
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

    # Budget-aware: reserve room for the summary itself + framing, leaving
    # the rest of the budget for as much recent context as fits. The previous
    # fixed `keep_recent_turns=3` slice wasted ~140k of the 190k window on
    # long tool-heavy chats — the agent would resume with almost no memory
    # of what it just did. min() guards against pathological cases where the
    # reserve exceeds the budget.
    keep_budget = max(target_tokens - SUMMARY_RESERVE_TOKENS, target_tokens // 2)
    to_compress, to_keep = split_for_compression(
        session.messages, keep_recent_turns, target_tokens=keep_budget,
    )

    if not to_compress:
        # Budget-aware split found nothing safe to compress (every safe
        # suffix is still too big, or only the full list fits exactly).
        # Hard-truncate as last resort.
        truncated = hard_truncate(list(session.messages), target_tokens, keep_recent_turns)
        if len(truncated) < len(session.messages):
            session.messages = truncated
            logger.info("agent2: compression fallback used hard truncation (%d → %d tokens, %d messages)",
                        current_tokens, count_session_tokens(truncated), len(truncated))
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
    """Prepend the summary so the kept slice starts with a user message.

    Two cases:
    - Kept already starts with a pure user-text message → merge the
      summary into that message (preserves the user's current question).
    - Kept starts with anything else (assistant continuation, tool_use,
      tool_result-bearing user message, or empty) → prepend a fresh
      user-role message carrying the summary. Chat APIs require the first
      message to be role=user, and the previous behavior of mutating an
      INNER user message left an orphan assistant prefix that broke
      alternation for the LLM.
    """
    if not kept:
        return [user_text_message(f"{SUMMARY_MARKER}\n{summary}")]

    first = kept[0]
    if _is_pure_user_message(first):
        original_text = first.content[0].text if first.content else ""
        new_text = (
            f"{SUMMARY_MARKER}\n{summary}\n\n"
            f"{CURRENT_QUESTION_MARKER}\n{original_text}"
        )
        new_msg = Message(role="user", content=[TextBlock(text=new_text)])
        return [new_msg] + list(kept[1:])

    return [user_text_message(f"{SUMMARY_MARKER}\n{summary}")] + list(kept)
