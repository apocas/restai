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


# ---------- count_session_tokens ----------


def test_count_session_tokens_nonempty():
    msgs = [_user("Hello, how are you?"), _assistant("I am fine, thank you.")]
    tokens = count_session_tokens(msgs)
    assert tokens > 0


def test_count_session_tokens_empty():
    assert count_session_tokens([]) == 0


# ---------- find_user_turn_boundaries ----------


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


# ---------- split_for_compression ----------


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


def test_split_for_compression_exact_keep_n():
    msgs = [
        _user("q1"), _assistant("a1"),
        _user("q2"), _assistant("a2"),
        _user("q3"), _assistant("a3"),
    ]
    to_compress, to_keep = split_for_compression(msgs, keep_n_turns=3)
    # 3 turns, keep_n=3 → not enough to compress (need strictly more)
    assert to_compress == []
    assert to_keep == msgs


# ---------- hard_truncate ----------


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


# ---------- _approx_char_count ----------


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


# ---------- compress_session ----------


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
