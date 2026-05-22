"""Tests for restai.agent2.compression — token counting, turn boundaries, splitting, truncation."""
import asyncio

from restai.agent2.compression import (
    _approx_char_count,
    compress_session,
    count_session_tokens,
    find_user_turn_boundaries,
    hard_truncate,
    split_for_compression,
)
from restai.agent2.types import (
    AgentSession,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    user_text_message,
)


def _user(text: str) -> Message:
    return user_text_message(text)


def _assistant(text: str) -> Message:
    return Message(role="assistant", content=[TextBlock(text=text)])


def _assistant_tool_use() -> Message:
    return Message(
        role="assistant",
        content=[ToolUseBlock(id="t1", name="search", input={"q": "test"})],
    )


def _user_tool_result() -> Message:
    return Message(
        role="user",
        content=[ToolResultBlock(tool_use_id="t1", content="result")],
    )


def test_count_session_tokens_nonempty():
    msgs = [_user("Hello, how are you?"), _assistant("I am fine, thank you.")]
    tokens = count_session_tokens(msgs)
    assert tokens > 0


def test_count_session_tokens_empty():
    assert count_session_tokens([]) == 0


def test_find_user_turn_boundaries_basic():
    msgs = [
        _user("q1"),           # 0 - turn boundary
        _assistant("a1"),      # 1
        _user("q2"),           # 2 - turn boundary
        _assistant("a2"),      # 3
        _user("q3"),           # 4 - turn boundary
    ]
    boundaries = find_user_turn_boundaries(msgs)
    assert boundaries == [0, 2, 4]


def test_find_user_turn_boundaries_skips_tool_result_user():
    msgs = [
        _user("q1"),           # 0 - turn boundary
        _assistant_tool_use(), # 1
        _user_tool_result(),   # 2 - NOT a turn boundary (contains ToolResultBlock)
        _assistant("a1"),      # 3
        _user("q2"),           # 4 - turn boundary
    ]
    boundaries = find_user_turn_boundaries(msgs)
    assert boundaries == [0, 4]


def test_find_user_turn_boundaries_empty():
    assert find_user_turn_boundaries([]) == []
def test_split_for_compression_enough_turns():
    msgs = [
        _user("q1"), _assistant("a1"),
        _user("q2"), _assistant("a2"),
        _user("q3"), _assistant("a3"),
        _user("q4"), _assistant("a4"),
        _user("q5"), _assistant("a5"),
    ]
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3)
    assert len(to_compress) > 0
    assert len(to_keep) > 0
    # The kept slice should start at the 3rd-from-last turn boundary
    assert to_keep[0].role == "user"
    assert to_compress + to_keep == msgs


def test_split_for_compression_not_enough_turns():
    msgs = [_user("q1"), _assistant("a1")]
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3)
    assert to_compress == []
    assert to_keep == msgs


def test_split_for_compression_budget_aware_keeps_largest_fitting_suffix():
    """When `target_tokens` is supplied (production path from
    `compress_session`), the split should return the LARGEST recent
    suffix that fits the budget — not just the last 3 messages.

    Regression for the "agent forgets everything after /continue" report:
    a 200-message session over a 142.5k budget was previously compressed
    to ~3 messages (wasting 140k tokens of headroom), so the resumed
    agent had no recall of what it had just done across 100 tool calls."""
    # Build a sequence: user + 30 tool round-trips. Each tool_result is
    # 1000-char so token counts stay realistic.
    msgs = [_user("audit the repo")]
    for i in range(30):
        msgs.append(_assistant_tool_use())
        msgs.append(Message(
            role="user",
            content=[ToolResultBlock(tool_use_id="t1", content="x" * 1000)],
        ))
    total = count_session_tokens(msgs)
    # Budget that's about 60% of total — should keep more than just the
    # last 3 messages.
    budget = int(total * 0.6)
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3, target_tokens=budget)
    assert len(to_keep) > 6, (
        f"budget-aware split kept only {len(to_keep)} messages; "
        f"expected many more (budget={budget}, total={total})"
    )
    assert count_session_tokens(to_keep) <= budget
    assert to_compress + to_keep == msgs


def test_split_for_compression_tool_heavy_single_user_turn():
    """One user turn followed by many assistant tool_use → user tool_result
    pairs — the agent2 chat shape that originally deadlocked compression
    (only 1 user-text boundary, can't satisfy keep_n_turns=3). The safe
    split point fallback should kick in and let us still compress the
    older tool round-trips."""
    msgs = [_user("do stuff")]
    for _ in range(10):
        msgs.append(_assistant_tool_use())
        msgs.append(_user_tool_result())
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3)
    assert len(to_compress) > 0, "tool-heavy session must still be compressible"
    assert to_compress + to_keep == msgs


def test_split_for_compression_exact_keep_n_uses_safe_fallback():
    """3 turns, keep_n=3 — user-text turns alone can't beat keep_n, so we
    fall back to safe split points. Without this fallback, plain-text
    chats with exactly keep_n turns would crater via hard_truncate when
    they hit the budget (see the 142k→460 token bug)."""
    msgs = [
        _user("q1"), _assistant("a1"),
        _user("q2"), _assistant("a2"),
        _user("q3"), _assistant("a3"),
    ]
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3)
    # All 6 indices are safe split points (no tool_result blocks).
    # safe[-3] = index 3 = _assistant("a2"), so kept starts there.
    assert len(to_compress) == 3
    assert len(to_keep) == 3
    assert to_compress + to_keep == msgs


def test_hard_truncate_drops_oldest():
    msgs = [
        _user("A" * 1000), _assistant("B" * 1000),
        _user("C" * 1000), _assistant("D" * 1000),
        _user("short"), _assistant("reply"),
    ]
    total_before = count_session_tokens(msgs)
    # Set a budget well below the total but enough for the last turn
    budget = count_session_tokens([_user("short"), _assistant("reply")]) + 50
    truncated = hard_truncate(msgs, budget, keep_n_turns=1)
    assert len(truncated) < len(msgs)
    total_after = count_session_tokens(truncated)
    assert total_after <= budget


def test_hard_truncate_empty():
    assert hard_truncate([], 100, 3) == []


def test_hard_truncate_returns_largest_fitting_suffix():
    """Regression for the 142k → 460 token bug. When the full list is
    just barely over budget, hard_truncate must return the LARGEST
    suffix that fits, not the smallest. The bug was walking safe split
    points newest-first, which returned the smallest fitting suffix —
    a chat with 142k tokens and a 142.5k budget collapsed to 2 messages
    (460 tokens) instead of trimming the few overshoot tokens.
    """
    # Stuff each message with enough text so dropping ONE turn from the
    # front is the smallest cut that fits — exposes the bug clearly.
    msgs = [
        _user("A" * 4000), _assistant("B" * 4000),
        _user("C" * 4000), _assistant("D" * 4000),
        _user("E" * 4000), _assistant("F" * 4000),
    ]
    total = count_session_tokens(msgs)
    last_turn_tokens = count_session_tokens(msgs[-2:])
    # Budget that fits everything except the first turn but is MUCH
    # bigger than just the last turn — the bug returned just the last
    # turn here.
    budget = count_session_tokens(msgs[2:])
    truncated = hard_truncate(msgs, budget, keep_n_turns=3)
    assert len(truncated) > 2, (
        f"hard_truncate cratered to {len(truncated)} messages; "
        f"expected >2 (largest fitting suffix). "
        f"total={total} budget={budget} last_turn={last_turn_tokens}"
    )
    assert count_session_tokens(truncated) <= budget


def test_approx_char_count_text():
    msgs = [_user("hello"), _assistant("world")]
    count = _approx_char_count(msgs)
    assert count >= len("hello") + len("world")


def test_approx_char_count_tool_result():
    msg = Message(
        role="user",
        content=[ToolResultBlock(tool_use_id="t1", content="result text")],
    )
    count = _approx_char_count([msg])
    assert count >= len("result text")


def test_compress_session_returns_false_no_context_window():
    session = AgentSession(messages=[_user("hello")])
    result = asyncio.run(
        compress_session(
            session,
            provider=None,
            config=None,
            context_window=None,
        )
    )
    assert result is False


def test_compress_session_returns_false_zero_context_window():
    session = AgentSession(messages=[_user("hello")])
    result = asyncio.run(
        compress_session(
            session,
            provider=None,
            config=None,
            context_window=0,
        )
    )
    assert result is False


def test_compress_session_returns_false_under_budget():
    session = AgentSession(messages=[_user("hello"), _assistant("hi")])
    result = asyncio.run(
        compress_session(
            session,
            provider=None,
            config=None,
            context_window=100000,
        )
    )
    assert result is False
