"""Unit tests for agent2 resilience features: transient-error retries,
the fallback-LLM chain, tool timeouts, threaded sync tools, the identical-
call loop guard, argument validation/coercion, and real usage accounting.
Fake providers and tools throughout; no SDKs, no network.
"""
import asyncio
import time
import types

from restai.agent2.agent import Agent2Runtime
from restai.agent2.providers import ProviderConfig, normalize_usage
from restai.agent2.resilience import backoff_delay, is_retryable_error
from restai.agent2.tool_adapter import (
    AdaptedTool,
    coerce_and_validate_args,
    describe_schema_for_error,
)
from restai.agent2.types import (
    Message,
    TextBlock,
    ToolUseBlock,
)


def run(coro):
    return asyncio.run(coro)


def text_msg(text, usage=None):
    return Message(role="assistant", content=[TextBlock(text=text)], usage=usage)


def tool_msg(*calls, usage=None):
    return Message(
        role="assistant",
        content=[ToolUseBlock(id=i, name=n, input=a) for i, n, a in calls],
        usage=usage,
    )


class TransientError(Exception):
    """Looks like a rate limit to the classifier."""
    status_code = 429


class ServerError(Exception):
    status_code = 503


class FakeProvider:
    """Scripted provider (same contract as test_agent2_runtime_unit)."""

    def __init__(self, turns=None, stream_turns=None):
        self.turns = list(turns or [])
        self.stream_turns = list(stream_turns or [])
        self.complete_calls = []
        self.stream_calls = []

    async def complete(self, *, system_prompt, messages, tools, config):
        self.complete_calls.append({
            "system": system_prompt,
            "messages": list(messages),
            "tools": list(tools),
        })
        item = self.turns.pop(0)
        if callable(item) and not isinstance(item, Message):
            item = item()
        if isinstance(item, Exception):
            raise item
        return item

    async def stream_complete(self, *, system_prompt, messages, tools, config):
        self.stream_calls.append({"tools": list(tools)})
        script = self.stream_turns.pop(0)
        for item in script:
            if isinstance(item, Exception):
                raise item
            yield item


def make_tool(name="echo", fn=None, is_async=False, schema=None):
    return AdaptedTool(
        name=name,
        description=f"{name} tool",
        input_schema=schema or {"type": "object", "properties": {"a": {"type": "string"}}},
        fn=fn or (lambda **kw: f"echo:{kw}"),
        is_async=is_async,
    )


def make_runtime(provider, tools=(), mode=None, max_turns=5, fallbacks=(),
                 tool_timeout=None, retry_attempts=0, llm_name="primary",
                 max_execution_time=None):
    return Agent2Runtime(
        provider=provider,
        config=ProviderConfig(model="fake"),
        tools=list(tools),
        system_prompt="be helpful",
        max_turns=max_turns,
        mode=mode,
        llm_name=llm_name,
        fallbacks=fallbacks,
        tool_timeout=tool_timeout,
        retry_attempts=retry_attempts,
        retry_base_delay=0.001,
        max_execution_time=max_execution_time,
    )


async def collect(runtime, prompt, **kw):
    events = []
    async for ev in runtime.run_iter(prompt, **kw):
        events.append(ev)
    return events


# ─── error classification ───────────────────────────────────────────────

def test_retryable_by_status_code():
    assert is_retryable_error(TransientError("x"))
    assert is_retryable_error(ServerError("x"))

    class Auth(Exception):
        status_code = 401

    class NotFound(Exception):
        status_code = 404

    assert not is_retryable_error(Auth("no"))
    assert not is_retryable_error(NotFound("no"))


def test_retryable_by_class_name():
    class MyRateLimitError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    assert is_retryable_error(MyRateLimitError("hm"))
    assert is_retryable_error(APIConnectionError("hm"))


def test_retryable_by_message_fragment():
    assert is_retryable_error(RuntimeError("upstream said: too many requests"))
    assert is_retryable_error(RuntimeError("connection reset by peer"))
    assert not is_retryable_error(RuntimeError("model exploded mysteriously"))


def test_context_length_never_retryable():
    class MaybeRateLimited(Exception):
        status_code = 429

    # Veto fragments win even over a retryable status.
    assert not is_retryable_error(
        MaybeRateLimited("input exceeds the maximum context length")
    )
    assert not is_retryable_error(RuntimeError("invalid api key; timeout ignored"))


def test_response_status_code_extraction():
    class Wrapped(Exception):
        def __init__(self):
            super().__init__("boom")
            self.response = types.SimpleNamespace(status_code=503)

    assert is_retryable_error(Wrapped())


def test_backoff_delay_grows_and_caps():
    d0 = backoff_delay(0, base=1.0)
    d3 = backoff_delay(3, base=1.0)
    assert 0.5 <= d0 <= 1.5
    assert d3 > d0
    assert backoff_delay(10, base=1.0, cap=15.0) <= 15.0 * 1.25
    assert backoff_delay(5, base=0) == 0.0


# ─── same-provider retries ──────────────────────────────────────────────

def test_transient_error_retried_then_succeeds():
    provider = FakeProvider(turns=[TransientError("429"), text_msg("recovered")])
    runtime = make_runtime(provider, mode="function_calling", retry_attempts=2)
    events = run(collect(runtime, "hi"))
    assert events[-1].data["stop_reason"] == "completed"
    assert events[-1].data["final_text"] == "recovered"
    assert len(provider.complete_calls) == 2


def test_retries_exhausted_yields_error():
    provider = FakeProvider(
        turns=[TransientError("a"), TransientError("b"), TransientError("c")]
    )
    runtime = make_runtime(provider, mode="function_calling", retry_attempts=2)
    events = run(collect(runtime, "hi"))
    assert events[-1].data["stop_reason"] == "error"
    assert len(provider.complete_calls) == 3  # initial + 2 retries


def test_non_retryable_error_not_retried():
    provider = FakeProvider(turns=[RuntimeError("schema rejected")])
    runtime = make_runtime(provider, mode="function_calling", retry_attempts=3)
    events = run(collect(runtime, "hi"))
    assert events[-1].data["stop_reason"] == "error"
    assert len(provider.complete_calls) == 1


def test_streaming_transient_retry_before_first_delta():
    provider = FakeProvider(
        stream_turns=[[TransientError("429")], ["ok", text_msg("ok")]]
    )
    runtime = make_runtime(provider, mode="function_calling", retry_attempts=1)
    events = run(collect(runtime, "hi", stream=True))
    assert events[-1].data["stop_reason"] == "completed"
    assert [e.type for e in events][:1] == ["text_delta"]
    assert len(provider.stream_calls) == 2


def test_streaming_no_retry_after_delta():
    provider = FakeProvider(
        stream_turns=[["partial", TransientError("429")]]
    )
    runtime = make_runtime(provider, mode="function_calling", retry_attempts=3)
    events = run(collect(runtime, "hi", stream=True))
    assert events[-1].data["stop_reason"] == "error"
    assert len(provider.stream_calls) == 1


# ─── fallback LLM chain ─────────────────────────────────────────────────

def test_fallback_chain_switches_on_persistent_transient_error():
    primary = FakeProvider(turns=[TransientError("down"), TransientError("down")])
    backup = FakeProvider(turns=[text_msg("backup answered")])
    runtime = make_runtime(
        primary,
        tools=[make_tool()],
        retry_attempts=1,
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "hi"))
    assert events[-1].data == {
        "final_text": "backup answered", "stop_reason": "completed",
    }
    assert runtime.active_llm_name == "backup-llm"
    assert len(runtime.fallback_trail) == 1
    assert runtime.fallback_trail[0]["from"] == "primary"
    assert runtime.fallback_trail[0]["to"] == "backup-llm"
    # Transient failure skips the ReAct downgrade: every primary attempt was
    # native (tools passed), never a ReAct call (tools=[]).
    assert all(c["tools"] for c in primary.complete_calls)
    # The backup provider got a fresh native start too.
    assert backup.complete_calls[0]["tools"]


def test_fallback_chain_exhausted_reports_chain():
    primary = FakeProvider(turns=[TransientError("down")])
    backup = FakeProvider(turns=[ServerError("also down")])
    runtime = make_runtime(
        primary,
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "hi"))
    assert events[-1].data["stop_reason"] == "error"
    assert "fallback chain exhausted" in events[-1].data["final_text"]
    assert "primary" in events[-1].data["final_text"]
    assert "backup-llm" in events[-1].data["final_text"]
    assert len(runtime.fallback_trail) == 1


def test_auto_mode_tries_react_then_chain():
    # Non-transient native failure → ReAct on same provider → that fails too
    # → chain advance, with the requested mode restored for the new provider.
    primary = FakeProvider(
        turns=[RuntimeError("tools not supported"), RuntimeError("react broke too")]
    )
    backup = FakeProvider(turns=[text_msg("backup answered")])
    runtime = make_runtime(
        primary,
        tools=[make_tool()],
        mode="auto",
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "hi"))
    assert events[-1].data["final_text"] == "backup answered"
    # Primary call 1 = native (tools), call 2 = react (no tools).
    assert primary.complete_calls[0]["tools"]
    assert primary.complete_calls[1]["tools"] == []
    # Chain switch reset the mode: backup got a native attempt.
    assert backup.complete_calls[0]["tools"]
    assert runtime.mode == "function_calling"


def test_fallback_mid_run_keeps_session_context():
    # Turn 1 succeeds on primary with a tool call; provider dies on turn 2 →
    # backup must see the full transcript including the tool round-trip.
    primary = FakeProvider(turns=[
        tool_msg(("t1", "echo", {"a": "x"})),
        TransientError("down"),
    ])
    backup = FakeProvider(turns=[text_msg("done from backup")])
    runtime = make_runtime(
        primary,
        tools=[make_tool()],
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "go"))
    assert events[-1].data["final_text"] == "done from backup"
    seen = backup.complete_calls[0]["messages"]
    # user prompt + assistant tool_use + tool_result all present
    assert len(seen) >= 3
    assert runtime.fallback_trail[0]["turn"] == 2


def test_streaming_fallback_chain_before_delta():
    primary = FakeProvider(stream_turns=[[ServerError("boom")]])
    backup = FakeProvider(stream_turns=[["he", "llo", text_msg("hello")]])
    runtime = make_runtime(
        primary,
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "hi", stream=True))
    deltas = [e.data["text"] for e in events if e.type == "text_delta"]
    assert deltas == ["he", "llo"]
    assert events[-1].data["stop_reason"] == "completed"
    assert runtime.active_llm_name == "backup-llm"


def test_streaming_no_chain_switch_after_delta():
    primary = FakeProvider(stream_turns=[["partial", ServerError("boom")]])
    backup = FakeProvider(stream_turns=[["never", text_msg("never")]])
    runtime = make_runtime(
        primary,
        fallbacks=[("backup-llm", backup, ProviderConfig(model="fake2"))],
    )
    events = run(collect(runtime, "hi", stream=True))
    assert events[-1].data["stop_reason"] == "error"
    assert runtime.active_llm_name == "primary"
    assert backup.stream_calls == []


# ─── tool timeout + threading ───────────────────────────────────────────

def test_tool_timeout_returns_error_result():
    async def hang(**kw):
        await asyncio.sleep(5)
        return "too late"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "hang", {})),
        text_msg("moving on"),
    ])
    runtime = make_runtime(
        provider, tools=[make_tool("hang", hang, is_async=True)], tool_timeout=0.05,
    )
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "timed out" in block.content
    assert events[-1].data["final_text"] == "moving on"


def test_tool_timeout_disabled_by_default_zero():
    async def quick(**kw):
        await asyncio.sleep(0.01)
        return "fine"

    provider = FakeProvider(turns=[tool_msg(("t1", "q", {})), text_msg("ok")])
    runtime = make_runtime(
        provider, tools=[make_tool("q", quick, is_async=True)], tool_timeout=0,
    )
    events = run(collect(runtime, "go"))
    assert events[1].message.content[0].content == "fine"


def test_sync_tools_run_in_parallel_threads():
    def slow_sync(**kw):
        time.sleep(0.3)
        return "slept"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "s1", {}), ("t2", "s2", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(
        provider,
        tools=[make_tool("s1", slow_sync), make_tool("s2", slow_sync)],
    )
    start = time.monotonic()
    events = run(collect(runtime, "go"))
    elapsed = time.monotonic() - start
    results = [e.message.content[0].content for e in events if e.type == "tool_result"]
    assert results == ["slept", "slept"]
    # Serial execution would need >= 0.6s; threading keeps it near 0.3s.
    assert elapsed < 0.55, f"sync tools did not run in parallel ({elapsed:.2f}s)"


def test_sync_tool_timeout_applies():
    def blocking(**kw):
        time.sleep(1.0)
        return "late"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "blocky", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(
        provider, tools=[make_tool("blocky", blocking)], tool_timeout=0.05,
    )
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "timed out" in block.content


# ─── wall-clock execution cap ───────────────────────────────────────────

def test_max_execution_time_stops_at_turn_boundary():
    async def slow_tool(**kw):
        await asyncio.sleep(0.1)
        return "done"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "slow", {})),
        text_msg("should never be asked"),
    ])
    runtime = make_runtime(
        provider, tools=[make_tool("slow", slow_tool, is_async=True)],
        max_execution_time=0.05,
    )
    events = run(collect(runtime, "go"))
    assert events[-1].type == "final"
    assert events[-1].data["stop_reason"] == "max_time"
    # Turn 1 ran (tool executed); turn 2 was never started.
    assert len(provider.complete_calls) == 1
    kinds = [e.type for e in events]
    assert "tool_result" in kinds


def test_max_execution_time_unset_never_trips():
    provider = FakeProvider(turns=[text_msg("fine")])
    runtime = make_runtime(provider)
    events = run(collect(runtime, "go"))
    assert events[-1].data["stop_reason"] == "completed"


# ─── loop guard ─────────────────────────────────────────────────────────

def test_identical_call_loop_guard_annotates_third_repeat():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {"a": "x"})),
        tool_msg(("t2", "echo", {"a": "x"})),
        tool_msg(("t3", "echo", {"a": "x"})),
        text_msg("done"),
    ])
    runtime = make_runtime(provider, tools=[make_tool()], max_turns=5)
    events = run(collect(runtime, "go"))
    results = [e.message.content[0].content for e in events if e.type == "tool_result"]
    assert "loop guard" not in results[0]
    assert "loop guard" not in results[1]
    assert "loop guard" in results[2]
    assert "3 times" in results[2]


def test_different_args_do_not_trip_loop_guard():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {"a": "x"})),
        tool_msg(("t2", "echo", {"a": "y"})),
        tool_msg(("t3", "echo", {"a": "z"})),
        text_msg("done"),
    ])
    runtime = make_runtime(provider, tools=[make_tool()], max_turns=5)
    events = run(collect(runtime, "go"))
    results = [e.message.content[0].content for e in events if e.type == "tool_result"]
    assert all("loop guard" not in r for r in results)


# ─── argument validation & coercion ─────────────────────────────────────

def test_missing_required_arg_is_crisp_error():
    called = []

    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
    }
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(
        provider,
        tools=[make_tool("echo", lambda **kw: called.append(kw) or "ran", schema=schema)],
    )
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "missing required parameter 'a'" in block.content
    assert "Expected parameters" in block.content
    assert called == []


def test_string_number_coerced_to_int():
    seen = {}

    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
    }
    provider = FakeProvider(turns=[
        tool_msg(("t1", "calc", {"n": "5"})),
        text_msg("ok"),
    ])

    def calc(n=None, **kw):
        seen["n"] = n
        return str(n * 2)

    runtime = make_runtime(provider, tools=[make_tool("calc", calc, schema=schema)])
    events = run(collect(runtime, "go"))
    assert seen["n"] == 5
    assert events[1].message.content[0].content == "10"


def test_uncoercible_type_is_error():
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
    }
    provider = FakeProvider(turns=[
        tool_msg(("t1", "calc", {"n": "not-a-number"})),
        text_msg("ok"),
    ])
    runtime = make_runtime(
        provider, tools=[make_tool("calc", schema=schema)],
    )
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "expected integer" in block.content


def test_coerce_and_validate_args_unit():
    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string"},
            "i": {"type": "integer"},
            "f": {"type": "number"},
            "b": {"type": "boolean"},
            "arr": {"type": "array"},
            "obj": {"type": "object"},
            "nullable": {"type": ["string", "null"]},
        },
        "required": ["s"],
    }
    args = {
        "s": 42,
        "i": "7",
        "f": "2.5",
        "b": "true",
        "arr": '["x", "y"]',
        "obj": '{"k": 1}',
        "nullable": None,
        "extra": "left alone",
    }
    coerced, problems = coerce_and_validate_args(schema, args)
    assert problems == []
    assert coerced["s"] == "42"
    assert coerced["i"] == 7
    assert coerced["f"] == 2.5
    assert coerced["b"] is True
    assert coerced["arr"] == ["x", "y"]
    assert coerced["obj"] == {"k": 1}
    assert coerced["nullable"] is None
    assert coerced["extra"] == "left alone"


def test_coerce_handles_weird_schemas():
    # Non-dict schema, anyOf-style property, missing type — all lenient.
    assert coerce_and_validate_args(None, {"a": 1}) == ({"a": 1}, [])
    schema = {"type": "object", "properties": {"x": {"anyOf": [{"type": "string"}]}}}
    coerced, problems = coerce_and_validate_args(schema, {"x": 5})
    assert problems == []
    assert coerced["x"] == 5


def test_describe_schema_for_error_compact():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["a"],
    }
    desc = describe_schema_for_error(schema)
    assert "a: string (required)" in desc
    assert "n: integer" in desc


# ─── real usage accounting ──────────────────────────────────────────────

def test_usage_accumulates_across_turns():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {}), usage={"input": 100, "output": 20}),
        text_msg("done", usage={"input": 150, "output": 30}),
    ])
    runtime = make_runtime(provider, tools=[make_tool()])
    run(collect(runtime, "go"))
    assert runtime.usage_input == 250
    assert runtime.usage_output == 50
    assert runtime.usage_turns == 2
    assert runtime.llm_turns == 2
    assert runtime.usage_complete is True


def test_usage_partial_marks_incomplete():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {}), usage={"input": 100, "output": 20}),
        text_msg("done"),  # no usage this turn
    ])
    runtime = make_runtime(provider, tools=[make_tool()])
    run(collect(runtime, "go"))
    assert runtime.usage_turns == 1
    assert runtime.llm_turns == 2
    assert runtime.usage_complete is False


def test_react_turn_preserves_usage():
    provider = FakeProvider(turns=[
        text_msg("Final Answer: hi", usage={"input": 42, "output": 7}),
    ])
    runtime = make_runtime(provider, mode="react")
    run(collect(runtime, "go"))
    assert runtime.usage_input == 42
    assert runtime.usage_output == 7
    assert runtime.usage_complete is True


def test_normalize_usage():
    assert normalize_usage(10, 5) == {"input": 10, "output": 5}
    assert normalize_usage("10", "5") == {"input": 10, "output": 5}
    assert normalize_usage(None, None) is None
    assert normalize_usage(0, 0) is None
    assert normalize_usage("x", 5) is None


def test_count_tokens_prefers_complete_real_usage():
    from restai.projects.agent import Agent

    output = {"question": "q" * 400, "answer": "a" * 400}
    runtime = types.SimpleNamespace(
        usage_input=123, usage_output=45, usage_complete=True,
    )
    Agent._count_tokens(output, system_prompt="sys", session=None, runtime=runtime)
    assert output["tokens"] == {"input": 123, "output": 45, "accuracy": "high"}


def test_count_tokens_partial_usage_floors_estimate():
    from restai.projects.agent import Agent

    output = {"question": "short q", "answer": "short a"}
    runtime = types.SimpleNamespace(
        usage_input=10_000, usage_output=2_000, usage_complete=False,
    )
    Agent._count_tokens(output, system_prompt="", session=None, runtime=runtime)
    assert output["tokens"]["input"] >= 10_000
    assert output["tokens"]["output"] >= 2_000
    assert output["tokens"]["accuracy"] == "medium"


def test_count_tokens_without_runtime_estimates_low():
    from restai.projects.agent import Agent

    output = {"question": "hello there", "answer": "hi"}
    Agent._count_tokens(output, system_prompt="", session=None, runtime=None)
    assert output["tokens"]["accuracy"] == "low"
    assert output["tokens"]["input"] > 0


def test_absorb_side_usage_adds_without_turn_counters():
    runtime = make_runtime(FakeProvider())
    runtime._absorb_side_usage({"input": 55, "output": 9})
    assert runtime.usage_input == 55
    assert runtime.usage_output == 9
    assert runtime.usage_turns == 0
    assert runtime.llm_turns == 0
    # Garbage input never raises.
    runtime._absorb_side_usage({"input": "x"})
    runtime._absorb_side_usage(None)
    assert runtime.usage_input == 55


def test_compression_summarizer_usage_reaches_sink():
    from restai.agent2.compression import SUMMARY_MARKER, compress_session
    from restai.agent2.types import AgentSession, user_text_message

    class SummarizerProvider:
        def __init__(self):
            self.calls = 0

        async def complete(self, *, system_prompt, messages, tools, config):
            self.calls += 1
            return Message(
                role="assistant",
                content=[TextBlock(text="condensed summary")],
                usage={"input": 321, "output": 44},
            )

    # Sized so the recent suffix fits the keep budget (~150 tokens for a
    # 400-token window) while the older prefix goes to the summarizer.
    session = AgentSession()
    for i in range(4):
        session.messages.append(user_text_message(f"question {i} " + "word " * 100))
        session.messages.append(
            Message(role="assistant", content=[TextBlock(text="answer " + "word " * 100)])
        )

    provider = SummarizerProvider()
    sink_calls = []
    compressed = asyncio.run(compress_session(
        session,
        provider=provider,
        config=ProviderConfig(model="fake", max_output_tokens=1024),
        context_window=400,
        usage_sink=sink_calls.append,
    ))
    assert compressed is True
    assert provider.calls == 1
    assert sink_calls == [{"input": 321, "output": 44}]
    assert session.messages[0].content[0].text.startswith(SUMMARY_MARKER)


# ─── project-layer fallback plumbing ────────────────────────────────────

def test_resolve_fallback_chain_skips_unknown_and_broken():
    from restai.projects.agent import Agent

    options = types.SimpleNamespace(fallback_llm="missing, broken, ")
    project = types.SimpleNamespace(
        props=types.SimpleNamespace(id=1, llm="main", options=options)
    )

    class StubDB:
        def get_llm_by_name(self, name):
            if name == "broken":
                # Row that build_provider_for_llm cannot validate.
                return object()
            return None

    chain = Agent._resolve_fallback_chain(project, StubDB())
    assert chain == []


def test_record_fallbacks_sets_llm_used_only_on_switch():
    from restai.projects.agent import Agent

    project = types.SimpleNamespace(props=types.SimpleNamespace(llm="main"))
    output = {}
    Agent._record_fallbacks(output, types.SimpleNamespace(fallback_trail=[]), project)
    assert "llm_used" not in output

    runtime = types.SimpleNamespace(
        fallback_trail=[{"from": "main", "to": "backup", "turn": 2, "error": "x"}],
        active_llm_name="backup",
    )
    Agent._record_fallbacks(output, runtime, project)
    assert output["llm_used"] == "backup"
    assert output["llm_fallbacks"][0]["to"] == "backup"
