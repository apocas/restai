"""Sliding-window + summary compression for agent2 chat sessions.

Algorithm: identify the last N user-initiated turns; summarize everything
before via the same provider (tools=[]); prepend summary to the first kept
user message ("[Earlier conversation summary] … [Current question] …").
Recursive (prior summary is re-fed to next summarization). Summary call
failures fall back to hard truncation respecting turn boundaries.
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

# Bind once; tiktoken's get_encoding has an internal cache but the lookup
# still costs ~80ns per call — this keeps count_session_tokens tight.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def _encode_len(text: str) -> int:
    return len(_ENCODING.encode(text or ""))


DEFAULT_CONTEXT_RATIO = 0.75
DEFAULT_KEEP_RECENT_TURNS = 3
# Headroom for the summary message + framing so kept slice + summary fit
# under target_tokens. 4000 tokens covers a 400+ word summary plus framing.
SUMMARY_RESERVE_TOKENS = 4000
SUMMARY_MARKER = "[Earlier conversation summary]"
CURRENT_QUESTION_MARKER = "[Current question]"

# Per-message/block overhead estimates per OpenAI cookbook guidance.
PER_MESSAGE_OVERHEAD_TOKENS = 4
PER_TOOL_USE_OVERHEAD_TOKENS = 8
PER_TOOL_RESULT_OVERHEAD_TOKENS = 6


PER_IMAGE_BLOCK_TOKENS = 1024  # conservative — providers vary widely


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


def _is_pure_user_message(msg: Message) -> bool:
    """Turn-starting message: user role with only TextBlocks (no ToolResultBlocks).

    Guarantees slicing never splits a tool_use / tool_result pair.
    """
    if msg.role != "user":
        return False
    if not msg.content:
        return False
    return all(isinstance(b, TextBlock) for b in msg.content)


def find_user_turn_boundaries(messages: Sequence[Message]) -> list[int]:
    return [i for i, m in enumerate(messages) if _is_pure_user_message(m)]


def find_safe_split_points(messages: Sequence[Message]) -> list[int]:
    """Indices where `messages[:i]` is self-contained — i.e. cutting at `i`
    doesn't orphan an assistant `tool_use` from its matching `tool_result`.

    Widens compressible set vs. user-turn-only boundaries so chats with many
    tool calls inside one user turn can still be summarized.
    """
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

    Budget-aware (target_tokens given): finds the LARGEST recent suffix
    fitting target_tokens at a safe split. Without this, a 142k-token
    session over a 142.5k budget cratered to ~3 messages instead of
    keeping ~140k tokens of recent context.

    Turn-based (target_tokens=None): historic semantics — prefer user-text
    turn boundaries, falling back to safe split points.
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
        # Even the last single message doesn't fit — caller falls back to hard_truncate.
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


def _extract_prior_summary(
    messages: list[Message],
) -> tuple[Optional[str], list[Message]]:
    """If first message starts with SUMMARY_MARKER, extract summary; return (summary, rest)."""
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

    # Trailing "[Current question]" was the previous user prompt — leave it in
    # the message list by extracting only the summary portion here.
    body = text[len(SUMMARY_MARKER):].lstrip("\n")
    cq_idx = body.find(CURRENT_QUESTION_MARKER)
    if cq_idx >= 0:
        summary_text = body[:cq_idx].strip()
    else:
        summary_text = body.strip()
    return summary_text or None, messages


def _render_messages_as_text(messages: Sequence[Message]) -> str:
    """Plain-text transcript for the summarizer; skips prior SUMMARY_MARKER lines."""
    lines: list[str] = []
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                text = block.text or ""
                if text.startswith(SUMMARY_MARKER):
                    # Caller passes this as prior_summary.
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
    """Summarize via the agent's own provider (tools=[], capped max_output)."""
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


def hard_truncate(
    messages: list[Message], target_tokens: int, keep_n_turns: int
) -> list[Message]:
    """Drop oldest messages at safe split points until under target_tokens."""
    if not messages:
        return messages

    # Walk oldest-first so the FIRST fitting suffix is the LARGEST. Walking
    # newest-first (prior bug) returned the smallest fitting suffix — once
    # cratered a 142k-token chat to ~460 tokens of context when barely over
    # budget.
    boundaries = find_safe_split_points(messages)
    if not boundaries:
        return list(messages)

    for keep_start in boundaries:
        candidate = list(messages[keep_start:])
        if count_session_tokens(candidate) <= target_tokens:
            return candidate

    # Every suffix over budget — return the smallest. Provider will surface
    # a clear error and the user can shrink input.
    return list(messages[boundaries[-1]:])


def _approx_char_count(messages: Sequence[Message]) -> int:
    """Cheap chars-summed pre-check before paying for tokenization."""
    total = 0
    for msg in messages:
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += len(block.text or "")
            elif isinstance(block, ToolResultBlock):
                total += len(block.content or "")
            elif isinstance(block, ImageBlock):
                # Force fast-path to defer to real counting when images present
                # (image token cost is model-dependent).
                total += PER_IMAGE_BLOCK_TOKENS * 4
            else:  # ToolUseBlock
                total += 32
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
    """Compress session.messages in-place when over (context_window * ratio)."""
    if not context_window or context_window <= 0:
        return False

    target_tokens = int(context_window * ratio)

    # Cheap pre-check: a generous chars/token=3 ratio under budget skips
    # tokenization — no-op path becomes microseconds for chunky tool results.
    if _approx_char_count(session.messages) < target_tokens * 3:
        return False

    current_tokens = count_session_tokens(session.messages)
    if current_tokens <= target_tokens:
        return False

    logger.info(
        "agent2: compressing session — %d tokens > %d budget (%d-token window, ratio %.2f)",
        current_tokens, target_tokens, context_window, ratio,
    )

    # Budget-aware split: reserve summary+framing headroom, keep as much recent
    # context as fits. Previous fixed keep_recent_turns=3 slice wasted ~140k of
    # a 190k window on long tool-heavy chats — agent resumed with almost no
    # memory of what it just did. max() guards against reserve > budget.
    keep_budget = max(target_tokens - SUMMARY_RESERVE_TOKENS, target_tokens // 2)
    to_compress, to_keep = split_for_compression(
        session.messages, keep_recent_turns, target_tokens=keep_budget,
    )

    if not to_compress:
        # Nothing safe to compress (every safe suffix still too big, or only
        # full list fits exactly). Hard-truncate as last resort.
        truncated = hard_truncate(list(session.messages), target_tokens, keep_recent_turns)
        if len(truncated) < len(session.messages):
            session.messages = truncated
            logger.info("agent2: compression fallback used hard truncation (%d → %d tokens, %d messages)",
                        current_tokens, count_session_tokens(truncated), len(truncated))
            return True
        return False

    prior_summary, to_compress = _extract_prior_summary(to_compress)

    history_text = _render_messages_as_text(to_compress)
    summary = await _call_summarizer(provider, config, history_text, prior_summary)

    if not summary:
        logger.warning("agent2: summarizer returned no text; falling back to hard truncation")
        truncated = hard_truncate(list(session.messages), target_tokens, keep_recent_turns)
        if len(truncated) < len(session.messages):
            session.messages = truncated
            return True
        return False

    new_messages = _prepend_summary_to_first_user(to_keep, summary)
    session.messages = new_messages

    after_tokens = count_session_tokens(session.messages)
    logger.info(
        "agent2: compression complete — %d → %d tokens (%d-message summary)",
        current_tokens, after_tokens, len(summary.split()),
    )

    # Still over budget (e.g. giant tool result in kept window) → final hard
    # truncation pass.
    if after_tokens > target_tokens:
        logger.info("agent2: still over budget after summary; applying hard truncation")
        session.messages = hard_truncate(session.messages, target_tokens, keep_recent_turns)

    return True


def _prepend_summary_to_first_user(
    kept: list[Message], summary: str
) -> list[Message]:
    """Prepend the summary so the kept slice starts with a user message.

    If kept starts with a pure user-text message, merge summary into it to
    preserve the user's current question. Otherwise prepend a fresh user
    message — chat APIs require role=user first, and mutating an INNER user
    message would leave an orphan assistant prefix that breaks alternation.
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
