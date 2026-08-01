"""Unit tests for restai/agent2/agent.py — the Agent2Runtime loop.
Fake providers and tools throughout; no SDKs, no network.
"""
import asyncio
import types

import pytest

import restai.agent2.agent as agent_mod
from restai.agent2.agent import Agent2Runtime
from restai.agent2.providers import ProviderConfig
from restai.agent2.react_prompt import ReactParseResult
from restai.agent2.tool_adapter import AdaptedTool
from restai.agent2.types import (
    AgentSession,
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


def run(coro):
    return asyncio.run(coro)


def text_msg(text):
    return Message(role="assistant", content=[TextBlock(text=text)])


def tool_msg(*calls):
    return Message(
        role="assistant",
        content=[ToolUseBlock(id=i, name=n, input=a) for i, n, a in calls],
    )


class FakeProvider:
    """Scripted provider: each complete() pops the next item (Message,
    Exception, or callable producing either). stream items are lists whose
    entries are str deltas / Message / Exception."""

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


def make_tool(name="echo", fn=None, is_async=False):
    return AdaptedTool(
        name=name,
        description=f"{name} tool",
        input_schema={"type": "object", "properties": {"a": {"type": "string"}}},
        fn=fn or (lambda **kw: f"echo:{kw}"),
        is_async=is_async,
    )


def make_runtime(provider, tools=(), mode=None, max_turns=5, context_window=None):
    return Agent2Runtime(
        provider=provider,
        config=ProviderConfig(model="fake", context_window=context_window),
        tools=list(tools),
        system_prompt="be helpful",
        max_turns=max_turns,
        mode=mode,
    )


async def collect(runtime, prompt, **kw):
    events = []
    async for ev in runtime.run_iter(prompt, **kw):
        events.append(ev)
    return events


# ─── basic loop ─────────────────────────────────────────────────────────

def test_plain_text_answer_completes():
    provider = FakeProvider(turns=[text_msg("hello there")])
    runtime = make_runtime(provider)
    events = run(collect(runtime, "hi"))
    assert [e.type for e in events] == ["assistant", "final"]
    assert events[-1].data == {"final_text": "hello there", "stop_reason": "completed"}


def test_session_accumulates_messages():
    provider = FakeProvider(turns=[text_msg("answer")])
    runtime = make_runtime(provider)
    session = AgentSession()
    run(collect(runtime, "question", session=session))
    assert [m.role for m in session.messages] == ["user", "assistant"]
    assert session.messages[0].text_content() == "question"
    assert session.turn_count == 1


def test_image_attaches_to_first_user_message():
    provider = FakeProvider(turns=[text_msg("saw it")])
    runtime = make_runtime(provider)
    session = AgentSession()
    img = ImageBlock(data="aGk=", mime_type="image/png")
    run(collect(runtime, "look", session=session, image=img))
    first = session.messages[0]
    assert isinstance(first.content[0], TextBlock)
    assert first.content[1] is img


def test_tool_call_roundtrip():
    seen = {}

    def fn(**kw):
        seen.update(kw)
        return "42"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {"a": "b"})),
        text_msg("done: 42"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo", fn)])
    session = AgentSession()
    events = run(collect(runtime, "compute", session=session))
    assert [e.type for e in events] == ["assistant", "tool_result", "assistant", "final"]
    result_block = events[1].message.content[0]
    assert isinstance(result_block, ToolResultBlock)
    assert result_block.content == "42"
    assert result_block.tool_use_id == "t1"
    assert seen["a"] == "b"
    assert events[-1].data["final_text"] == "done: 42"


def test_parallel_tool_calls_yield_in_call_order():
    async def slow(**kw):
        await asyncio.sleep(0.02)
        return "slow"

    provider = FakeProvider(turns=[
        tool_msg(("t1", "slowtool", {}), ("t2", "fasttool", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(provider, tools=[
        make_tool("slowtool", slow, is_async=True),
        make_tool("fasttool", lambda **kw: "fast"),
    ])
    events = run(collect(runtime, "go"))
    results = [e for e in events if e.type == "tool_result"]
    assert [r.message.content[0].tool_use_id for r in results] == ["t1", "t2"]
    assert [r.message.content[0].content for r in results] == ["slow", "fast"]


def test_unknown_tool_returns_error_block():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "ghost", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")])
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "No such tool available: ghost" in block.content


def test_non_dict_tool_input_rejected():
    provider = FakeProvider(turns=[
        Message(role="assistant",
                content=[ToolUseBlock(id="t1", name="echo", input="not-a-dict")]),
        text_msg("ok"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")])
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "tool input must be an object" in block.content


def test_tool_exception_becomes_error_result():
    def boom(**kw):
        raise RuntimeError("tool exploded")

    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {})),
        text_msg("ok"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo", boom)])
    events = run(collect(runtime, "go"))
    block = events[1].message.content[0]
    assert block.is_error is True
    assert "Error calling tool (echo): tool exploded" in block.content


def test_tool_context_injection():
    provider = FakeProvider(turns=[tool_msg(("t1", "ctx", {})), text_msg("ok")])
    captured = {}

    async def check(args, context=None):
        captured.update(context or {})
        return "seen"

    tool = make_tool("ctx")
    tool.call = check
    runtime = make_runtime(provider, tools=[tool])
    runtime._chat_id = "chatX"
    runtime._project_id = 42
    run(collect(runtime, "go"))
    assert captured["chat_id"] == "chatX"
    assert captured["project_id"] == 42


# ─── result truncation ──────────────────────────────────────────────────

def test_tool_result_truncated_to_context_window():
    huge = "word " * 30_000

    provider = FakeProvider(turns=[tool_msg(("t1", "echo", {})), text_msg("ok")])
    runtime = make_runtime(
        provider, tools=[make_tool("echo", lambda **kw: huge)], context_window=4000
    )
    events = run(collect(runtime, "go"))
    content = events[1].message.content[0].content
    assert len(content) < len(huge)


def test_tool_result_char_cap_without_context_window():
    huge = "z" * 25_000
    provider = FakeProvider(turns=[tool_msg(("t1", "echo", {})), text_msg("ok")])
    runtime = make_runtime(provider, tools=[make_tool("echo", lambda **kw: huge)])
    events = run(collect(runtime, "go"))
    content = events[1].message.content[0].content
    assert content.startswith("z" * 100)
    assert "[... truncated 5000 characters ...]" in content


# ─── iteration cap ──────────────────────────────────────────────────────

def test_max_turns_reached():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {})),
        tool_msg(("t2", "echo", {})),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")], max_turns=2)
    events = run(collect(runtime, "loop forever"))
    assert events[-1].type == "final"
    assert events[-1].data["stop_reason"] == "max_turns"


def test_max_turns_floor_is_one():
    runtime = make_runtime(FakeProvider(turns=[text_msg("x")]), max_turns=0)
    assert runtime.max_turns == 1


def test_final_text_is_last_assistant_text():
    provider = FakeProvider(turns=[
        Message(role="assistant", content=[
            TextBlock(text="thinking about it"),
            ToolUseBlock(id="t1", name="echo", input={}),
        ]),
        tool_msg(("t2", "echo", {})),  # no text this turn
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")], max_turns=2)
    events = run(collect(runtime, "go"))
    assert events[-1].data["final_text"] == "thinking about it"


# ─── provider errors & auto fallback ────────────────────────────────────

def test_provider_error_yields_final_error_event():
    provider = FakeProvider(turns=[RuntimeError("api down")])
    runtime = make_runtime(provider, mode="function_calling")
    events = run(collect(runtime, "hi"))
    assert len(events) == 1
    assert events[0].type == "final"
    assert events[0].data["stop_reason"] == "error"
    assert "api down" in events[0].data["final_text"]


def test_auto_mode_falls_back_to_react_on_first_turn():
    provider = FakeProvider(turns=[
        RuntimeError("no native tools"),
        text_msg("Thought: simple\nFinal Answer: react says hi"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")], mode="auto")
    events = run(collect(runtime, "hi"))
    assert runtime.mode == "react"
    assert events[-1].data == {"final_text": "react says hi", "stop_reason": "completed"}
    # ReAct turn must not pass tools to the provider
    assert provider.complete_calls[1]["tools"] == []
    # …but the tool descriptions land in the system prompt instead.
    assert "echo" in provider.complete_calls[1]["system"]


def test_no_fallback_after_turn_one():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {})),
        RuntimeError("flaked on turn 2"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")], mode="auto")
    events = run(collect(runtime, "hi"))
    assert events[-1].data["stop_reason"] == "error"
    assert runtime.mode == "function_calling"


def test_explicit_mode_never_falls_back():
    provider = FakeProvider(turns=[RuntimeError("nope")])
    runtime = make_runtime(provider, mode="function_calling")
    events = run(collect(runtime, "hi"))
    assert events[0].data["stop_reason"] == "error"
    assert provider.turns == []  # only one call attempted


# ─── react mode ─────────────────────────────────────────────────────────

def test_react_action_executes_tool():
    provider = FakeProvider(turns=[
        text_msg('Thought: need tool\nAction: echo\nAction Input: {"a": "x"}'),
        text_msg("Final Answer: all done"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")], mode="react")
    session = AgentSession()
    events = run(collect(runtime, "go", session=session))
    kinds = [e.type for e in events]
    assert kinds == ["assistant", "tool_result", "assistant", "final"]
    tub = [b for b in events[0].message.content if isinstance(b, ToolUseBlock)]
    assert tub[0].name == "echo"
    assert tub[0].input == {"a": "x"}
    assert tub[0].id.startswith("react_")
    assert events[-1].data["final_text"] == "all done"
    # Second provider call must see prior tool blocks rewritten to text.
    for msg in provider.complete_calls[1]["messages"]:
        assert all(isinstance(b, TextBlock) for b in msg.content)
    joined = "\n".join(
        b.text for m in provider.complete_calls[1]["messages"] for b in m.content
    )
    assert "Action: echo" in joined
    assert "Observation:" in joined


def test_react_unformatted_response_is_final():
    provider = FakeProvider(turns=[text_msg("just a plain answer")])
    runtime = make_runtime(provider, tools=[make_tool("echo")], mode="react")
    events = run(collect(runtime, "go"))
    assert events[-1].data["final_text"] == "just a plain answer"


def test_react_messages_rewrites_image_and_error_result():
    msgs = [
        Message(role="user", content=[
            TextBlock(text="hi"),
            ImageBlock(data="x", mime_type="image/png"),
        ]),
        Message(role="user", content=[
            ToolResultBlock(tool_use_id="t", content="bad", is_error=True),
        ]),
    ]
    rewritten = Agent2Runtime._react_messages(msgs)
    texts = [b.text for m in rewritten for b in m.content]
    assert any("not available in ReAct mode" in t for t in texts)
    assert any(t.startswith("Observation (error): bad") for t in texts)


def test_build_react_message_variants():
    action = Agent2Runtime._build_react_message(
        ReactParseResult(kind="action", thought="th", action_name="t",
                         action_input={"k": 1})
    )
    assert action.content[0].text == "Thought: th"
    assert isinstance(action.content[1], ToolUseBlock)

    final = Agent2Runtime._build_react_message(
        ReactParseResult(kind="final", final_text="  done  ")
    )
    assert final.text_content() == "done"

    text = Agent2Runtime._build_react_message(
        ReactParseResult(kind="text", final_text="raw")
    )
    assert text.text_content() == "raw"


# ─── streaming ──────────────────────────────────────────────────────────

def test_streaming_text_deltas_then_final():
    provider = FakeProvider(stream_turns=[["hel", "lo", text_msg("hello")]])
    runtime = make_runtime(provider)
    events = run(collect(runtime, "hi", stream=True))
    assert [e.type for e in events] == ["text_delta", "text_delta", "assistant", "final"]
    assert events[0].data["text"] == "hel"
    assert events[-1].data["final_text"] == "hello"


def test_streaming_tool_call_then_final():
    provider = FakeProvider(stream_turns=[
        [tool_msg(("t1", "echo", {}))],
        ["ok", text_msg("ok")],
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")])
    events = run(collect(runtime, "go", stream=True))
    kinds = [e.type for e in events]
    assert kinds == ["assistant", "tool_result", "text_delta", "assistant", "final"]


def test_streaming_fallback_to_react_before_any_delta():
    provider = FakeProvider(
        stream_turns=[[RuntimeError("stream unsupported")]],
        turns=[text_msg("Final Answer: fell back")],
    )
    runtime = make_runtime(provider, mode="auto")
    events = run(collect(runtime, "hi", stream=True))
    assert runtime.mode == "react"
    assert [e.type for e in events] == ["assistant", "final"]
    assert events[-1].data["final_text"] == "fell back"


def test_streaming_error_after_delta_is_final_error():
    provider = FakeProvider(
        stream_turns=[["partial", RuntimeError("mid-stream death")]]
    )
    runtime = make_runtime(provider, mode="auto")
    events = run(collect(runtime, "hi", stream=True))
    assert events[0].type == "text_delta"
    assert events[-1].type == "final"
    assert events[-1].data["stop_reason"] == "error"


def test_streaming_without_final_message_errors():
    provider = FakeProvider(stream_turns=[["only", "deltas"]])
    runtime = make_runtime(provider, mode="auto")
    events = run(collect(runtime, "hi", stream=True))
    assert events[-1].data["stop_reason"] == "error"
    assert "stream_complete did not yield a final Message" in events[-1].data["final_text"]


def test_streaming_react_mode_uses_non_streaming_turn():
    provider = FakeProvider(turns=[text_msg("Final Answer: no deltas")])
    runtime = make_runtime(provider, mode="react")
    events = run(collect(runtime, "hi", stream=True))
    assert [e.type for e in events] == ["assistant", "final"]


# ─── compression hookup ─────────────────────────────────────────────────

def test_compression_called_with_context_window(monkeypatch):
    calls = []

    async def fake_compress(session, *, provider, config, context_window):
        calls.append(context_window)

    monkeypatch.setattr(agent_mod, "compress_session", fake_compress)
    provider = FakeProvider(turns=[text_msg("ok")])
    runtime = make_runtime(provider, context_window=8000)
    run(collect(runtime, "hi"))
    assert calls == [8000]


def test_compression_skipped_without_window(monkeypatch):
    async def fake_compress(*a, **kw):
        raise AssertionError("must not be called")

    monkeypatch.setattr(agent_mod, "compress_session", fake_compress)
    provider = FakeProvider(turns=[text_msg("ok")])
    runtime = make_runtime(provider, context_window=None)
    run(collect(runtime, "hi"))


def test_compression_failure_is_non_fatal(monkeypatch):
    async def fake_compress(*a, **kw):
        raise RuntimeError("compression broke")

    monkeypatch.setattr(agent_mod, "compress_session", fake_compress)
    provider = FakeProvider(turns=[text_msg("survived")])
    runtime = make_runtime(provider, context_window=100)
    events = run(collect(runtime, "hi"))
    assert events[-1].data["final_text"] == "survived"


# ─── create_tool hot reload ─────────────────────────────────────────────

def test_create_tool_success_triggers_reload():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "create_tool", {})),
        text_msg("ok"),
    ])
    tool = make_tool("create_tool", lambda **kw: "Tool 'x' created successfully")
    runtime = make_runtime(provider, tools=[tool])
    reloads = []
    runtime._reload_project_tools = lambda: reloads.append(1)
    run(collect(runtime, "make a tool"))
    assert reloads == [1]


def test_create_tool_failure_does_not_reload():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "create_tool", {})),
        text_msg("ok"),
    ])
    tool = make_tool("create_tool", lambda **kw: "ERROR: nope")
    runtime = make_runtime(provider, tools=[tool])
    reloads = []
    runtime._reload_project_tools = lambda: reloads.append(1)
    run(collect(runtime, "make a tool"))
    assert reloads == []


def test_reload_project_tools_noop_without_context():
    runtime = make_runtime(FakeProvider())
    runtime._reload_project_tools()  # no _project_id/_brain → silent no-op


def test_reload_project_tools_adds_new_tools(monkeypatch):
    import restai.database as rdb

    row = types.SimpleNamespace(
        name="fresh_tool", description="d",
        parameters='{"type":"object","properties":{},"required":[]}',
        code="print('x')", enabled=True,
    )

    class FakeDBW:
        def __init__(self):
            self.db = types.SimpleNamespace(close=lambda: None)

        def get_project_tools(self, project_id):
            return [row]

    monkeypatch.setattr(rdb, "DBWrapper", FakeDBW)
    runtime = make_runtime(FakeProvider(), tools=[make_tool("existing")])
    runtime._project_id = 1
    runtime._brain = types.SimpleNamespace(docker_manager=None)
    runtime._reload_project_tools()
    assert "fresh_tool" in runtime._tools_by_name
    # idempotent — second reload doesn't duplicate
    n = len(runtime.tools)
    runtime._reload_project_tools()
    assert len(runtime.tools) == n


# ─── cancellation ───────────────────────────────────────────────────────

def test_cancellation_propagates_out_of_tool_call():
    async def hang(**kw):
        await asyncio.sleep(30)

    provider = FakeProvider(turns=[tool_msg(("t1", "hang", {}))])
    runtime = make_runtime(provider, tools=[make_tool("hang", hang, is_async=True)])

    async def scenario():
        task = asyncio.ensure_future(collect(runtime, "go"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())


def test_generator_close_midway_is_clean():
    provider = FakeProvider(turns=[
        tool_msg(("t1", "echo", {})),
        text_msg("never reached"),
    ])
    runtime = make_runtime(provider, tools=[make_tool("echo")])

    async def scenario():
        gen = runtime.run_iter("go")
        first = await gen.__anext__()
        assert first.type == "assistant"
        await gen.aclose()  # must not raise

    run(scenario())
