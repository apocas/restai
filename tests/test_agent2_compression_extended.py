"""Extended tests for restai/agent2/compression.py — token counting details,
summary extraction/rendering, the summarizer call, and the full
compress_session paths with a faked provider. No network."""
import asyncio


from restai.agent2 import compression as comp
from restai.agent2.compression import (
    CURRENT_QUESTION_MARKER,
    PER_IMAGE_BLOCK_TOKENS,
    PER_MESSAGE_OVERHEAD_TOKENS,
    SUMMARY_MARKER,
    _build_summary_user_prompt,
    _call_summarizer,
    _count_message_tokens,
    _extract_prior_summary,
    _prepend_summary_to_first_user,
    _render_messages_as_text,
    compress_session,
    count_session_tokens,
    find_safe_split_points,
    hard_truncate,
    truncate_text_to_token_budget,
)
from restai.agent2.providers import ProviderConfig
from restai.agent2.types import (
    AgentSession,
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    user_text_message,
)


def _user(text):
    return user_text_message(text)


def _assistant(text):
    return Message(role="assistant", content=[TextBlock(text=text)])


def _tool_result(content, is_error=False):
    return Message(role="user", content=[
        ToolResultBlock(tool_use_id="t1", content=content, is_error=is_error)
    ])


class _FakeProvider:
    """Provider stub for _call_summarizer / compress_session."""

    def __init__(self, summary="a compact summary", fail=False):
        self.summary = summary
        self.fail = fail
        self.calls = []

    async def complete(self, *, system_prompt, messages, tools, config):
        self.calls.append({
            "system_prompt": system_prompt,
            "messages": messages,
            "tools": tools,
            "config": config,
        })
        if self.fail:
            raise RuntimeError("provider down")
        return Message(role="assistant", content=[TextBlock(text=self.summary)])


# ─── truncate_text_to_token_budget ─────────────────────────────────────

def test_truncate_text_budget_short_passthrough():
    assert truncate_text_to_token_budget("short", 100) == "short"


def test_truncate_text_budget_nonpositive_passthrough():
    assert truncate_text_to_token_budget("anything", 0) == "anything"
    assert truncate_text_to_token_budget("", 10) == ""


def test_truncate_text_budget_truncates_and_marks():
    text = "z" * 500
    out = truncate_text_to_token_budget(text, 50)
    assert len(out) < len(text)
    assert "truncated" in out
    assert "context window" in out


# ─── token counting ─────────────────────────────────────────────────────

def test_count_message_tokens_text_includes_overhead():
    msg = _user("abcd")
    tokens = _count_message_tokens(msg)
    assert tokens > PER_MESSAGE_OVERHEAD_TOKENS


def test_count_message_tokens_image_flat_cost():
    msg = Message(role="user", content=[ImageBlock(data="QUJD", mime_type="image/png")])
    assert _count_message_tokens(msg) == PER_MESSAGE_OVERHEAD_TOKENS + PER_IMAGE_BLOCK_TOKENS


def test_count_message_tokens_tool_blocks():
    msg = Message(role="assistant", content=[
        ToolUseBlock(id="i", name="tool_name", input={"key": "value"}),
    ])
    tokens = _count_message_tokens(msg)
    assert tokens > PER_MESSAGE_OVERHEAD_TOKENS + comp.PER_TOOL_USE_OVERHEAD_TOKENS

    res = _tool_result("some tool output")
    assert _count_message_tokens(res) > PER_MESSAGE_OVERHEAD_TOKENS


def test_count_message_tokens_unjsonable_tool_input():
    msg = Message(role="assistant", content=[
        ToolUseBlock(id="i", name="t", input={"bad": object()}),
    ])
    # Falls back to str() — must not raise.
    assert _count_message_tokens(msg) > 0


def test_count_session_tokens_sums():
    msgs = [_user("aa"), _assistant("bb")]
    assert count_session_tokens(msgs) == sum(_count_message_tokens(m) for m in msgs)


# ─── find_safe_split_points ─────────────────────────────────────────────

def test_find_safe_split_points_skips_tool_results():
    msgs = [_user("q"), _assistant("a"), _tool_result("r"), _user("q2")]
    points = find_safe_split_points(msgs)
    assert 0 in points and 1 in points and 3 in points
    assert 2 not in points


def test_find_safe_split_points_empty():
    assert find_safe_split_points([]) == []


# ─── _extract_prior_summary ─────────────────────────────────────────────

def test_extract_prior_summary_none_cases():
    assert _extract_prior_summary([]) == (None, [])
    msgs = [_assistant("hello")]
    assert _extract_prior_summary(msgs) == (None, msgs)
    msgs = [_user("no marker here")]
    assert _extract_prior_summary(msgs) == (None, msgs)


def test_extract_prior_summary_with_current_question():
    text = f"{SUMMARY_MARKER}\nold facts\n\n{CURRENT_QUESTION_MARKER}\nwhat now?"
    msgs = [_user(text), _assistant("...")]
    summary, rest = _extract_prior_summary(msgs)
    assert summary == "old facts"
    assert rest is msgs  # list itself untouched


def test_extract_prior_summary_without_current_question():
    msgs = [_user(f"{SUMMARY_MARKER}\njust the summary")]
    summary, _ = _extract_prior_summary(msgs)
    assert summary == "just the summary"


# ─── _render_messages_as_text ───────────────────────────────────────────

def test_render_messages_transcript():
    msgs = [
        _user("question?"),
        Message(role="assistant", content=[
            TextBlock(text="let me check"),
            ToolUseBlock(id="i", name="lookup", input={"q": "x"}),
        ]),
        _tool_result("the result"),
        _tool_result("bad thing", is_error=True),
    ]
    out = _render_messages_as_text(msgs)
    assert "USER: question?" in out
    assert "ASSISTANT: let me check" in out
    assert "ASSISTANT used tool 'lookup'" in out
    assert '{"q": "x"}' in out
    assert "TOOL RESULT: the result" in out
    assert "TOOL ERROR: bad thing" in out


def test_render_messages_skips_summary_marker():
    msgs = [_user(f"{SUMMARY_MARKER}\nold"), _user("real question")]
    out = _render_messages_as_text(msgs)
    assert SUMMARY_MARKER not in out
    assert "real question" in out


# ─── _build_summary_user_prompt / _call_summarizer ─────────────────────

def test_build_summary_user_prompt_with_prior():
    out = _build_summary_user_prompt("HISTORY", "PRIOR")
    assert "[Existing summary of even earlier turns]" in out
    assert "PRIOR" in out
    assert "HISTORY" in out


def test_build_summary_user_prompt_without_prior():
    out = _build_summary_user_prompt("HISTORY", None)
    assert "[Existing summary" not in out
    assert "HISTORY" in out


def test_call_summarizer_success_caps_output_tokens():
    provider = _FakeProvider(summary="  the summary  ")
    cfg = ProviderConfig(model="m", max_output_tokens=8192)
    out = asyncio.run(_call_summarizer(provider, cfg, "history", None))
    assert out == "the summary"
    call = provider.calls[0]
    assert call["tools"] == []
    assert call["config"].max_output_tokens == 1024


def test_call_summarizer_empty_text_returns_none():
    provider = _FakeProvider(summary="   ")
    out = asyncio.run(_call_summarizer(provider, ProviderConfig(model="m"), "h", None))
    assert out is None


def test_call_summarizer_provider_failure_returns_none():
    provider = _FakeProvider(fail=True)
    out = asyncio.run(_call_summarizer(provider, ProviderConfig(model="m"), "h", None))
    assert out is None


# ─── hard_truncate edge cases ───────────────────────────────────────────

def test_hard_truncate_empty():
    assert hard_truncate([], 100, 3) == []


def test_hard_truncate_all_over_budget_returns_smallest_suffix():
    msgs = [_user("x" * 500), _user("y" * 500), _user("z" * 500)]
    out = hard_truncate(msgs, 10, 3)
    assert len(out) == 1
    assert out[0].content[0].text.startswith("z")


# ─── _prepend_summary_to_first_user ─────────────────────────────────────

def test_prepend_summary_empty_kept():
    out = _prepend_summary_to_first_user([], "S")
    assert len(out) == 1
    assert out[0].role == "user"
    assert out[0].content[0].text == f"{SUMMARY_MARKER}\nS"


def test_prepend_summary_merges_into_pure_user_first():
    kept = [_user("current question"), _assistant("...")]
    out = _prepend_summary_to_first_user(kept, "S")
    assert len(out) == 2
    text = out[0].content[0].text
    assert text.startswith(SUMMARY_MARKER)
    assert CURRENT_QUESTION_MARKER in text
    assert text.endswith("current question")


def test_prepend_summary_assistant_first_gets_fresh_user():
    kept = [_assistant("orphan"), _user("q")]
    out = _prepend_summary_to_first_user(kept, "S")
    assert len(out) == 3
    assert out[0].role == "user"
    assert out[0].content[0].text.startswith(SUMMARY_MARKER)
    assert out[1].content[0].text == "orphan"


# ─── compress_session end-to-end paths ─────────────────────────────────

def _big_session(n_msgs=6, chars=300):
    msgs = []
    for i in range(n_msgs - 1):
        if i % 2 == 0:
            msgs.append(_user(f"question {i} " + "q" * chars))
        else:
            msgs.append(_assistant(f"answer {i} " + "a" * chars))
    msgs.append(_user("final tiny question"))
    return AgentSession(messages=msgs)


def test_compress_session_noop_without_context_window():
    session = _big_session()
    before = list(session.messages)
    assert asyncio.run(compress_session(
        session, provider=_FakeProvider(), config=ProviderConfig(model="m"),
        context_window=0,
    )) is False
    assert session.messages == before


def test_compress_session_noop_under_budget():
    session = AgentSession(messages=[_user("small")])
    assert asyncio.run(compress_session(
        session, provider=_FakeProvider(), config=ProviderConfig(model="m"),
        context_window=100000,
    )) is False


def test_compress_session_summarizes_and_prepends_marker():
    session = _big_session()
    provider = _FakeProvider(summary="what happened earlier")
    changed = asyncio.run(compress_session(
        session, provider=provider, config=ProviderConfig(model="m"),
        context_window=200,  # target 150; keep_budget max(150-4000, 75)=75
    ))
    assert changed is True
    assert len(provider.calls) == 1
    first_text = session.messages[0].content[0].text
    assert first_text.startswith(SUMMARY_MARKER)
    assert "what happened earlier" in first_text
    # Kept slice + summary now fits the budget.
    assert count_session_tokens(session.messages) <= 150


def test_compress_session_summarizer_failure_hard_truncates():
    session = _big_session()
    before_count = len(session.messages)
    provider = _FakeProvider(fail=True)
    changed = asyncio.run(compress_session(
        session, provider=provider, config=ProviderConfig(model="m"),
        context_window=200,
    ))
    assert changed is True
    assert len(session.messages) < before_count
    assert count_session_tokens(session.messages) <= 150
    # No summary marker — pure truncation.
    assert not session.messages[0].content[0].text.startswith(SUMMARY_MARKER)


def test_compress_session_recursive_prior_summary_forwarded():
    """A prior summary in message 0 is extracted and fed to the summarizer."""
    msgs = [_user(f"{SUMMARY_MARKER}\nprevious summary\n\n{CURRENT_QUESTION_MARKER}\nold q " + "x" * 300)]
    for i in range(4):
        msgs.append(_assistant(f"a{i} " + "a" * 300))
        msgs.append(_user(f"q{i} " + "q" * 300))
    msgs.append(_user("tiny tail"))
    session = AgentSession(messages=msgs)
    provider = _FakeProvider(summary="new merged summary")
    changed = asyncio.run(compress_session(
        session, provider=provider, config=ProviderConfig(model="m"),
        context_window=200,
    ))
    assert changed is True
    prompt = provider.calls[0]["messages"][0].content[0].text
    assert "previous summary" in prompt  # prior summary forwarded
    assert SUMMARY_MARKER in session.messages[0].content[0].text
