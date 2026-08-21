"""Feature-parity tests for the external agent loops (claude / llamaindex /
smolagents / openai_agents): the shared ToolRunPolicy (timeout, loop guard,
output cap, threading), the whole-run fallback-LLM driver, the shared token
estimator, and each loop's tool-wrapper integration. No network, no Docker.
"""
import asyncio
import time
import types

from restai.projects import agent_shared
from restai.projects.agent_shared import (
    ToolRunPolicy,
    drive_with_fallbacks,
    estimate_input_tokens,
    execution_deadline,
    fallback_llm_names,
    max_execution_seconds,
    max_time_notice,
    usage_from_raw_response,
)


def run(coro):
    return asyncio.run(coro)


def make_project(tool_timeout=0, fallback_llm=None, llm="main-llm",
                 max_execution_time=0):
    options = types.SimpleNamespace(
        tool_timeout=tool_timeout,
        fallback_llm=fallback_llm,
        tools="",
        max_iterations=5,
        max_execution_time=max_execution_time,
    )
    props = types.SimpleNamespace(id=1, name="proj", llm=llm, options=options)
    return types.SimpleNamespace(props=props)


# ─── ToolRunPolicy ──────────────────────────────────────────────────────

def test_policy_sync_call_runs_in_thread_and_caps_output():
    policy = ToolRunPolicy(timeout=None)
    big = "z" * 50_000
    text, is_error = run(policy.run_async("t", {}, call_sync=lambda: big))
    assert is_error is False
    assert len(text) < len(big)
    assert "truncated" in text


def test_policy_async_timeout_returns_error():
    policy = ToolRunPolicy(timeout=0.05)

    async def hang():
        await asyncio.sleep(5)
        return "late"

    text, is_error = run(policy.run_async("slowtool", {}, call_async=hang))
    assert is_error is True
    assert "timed out" in text
    assert "slowtool" in text


def test_policy_sync_timeout_via_run_async():
    policy = ToolRunPolicy(timeout=0.05)
    text, is_error = run(
        policy.run_async("blocky", {}, call_sync=lambda: time.sleep(2) or "late")
    )
    assert is_error is True
    assert "timed out" in text


def test_policy_exception_becomes_error_string():
    policy = ToolRunPolicy(timeout=None)

    def boom():
        raise RuntimeError("kaput")

    text, is_error = run(policy.run_async("t", {}, call_sync=boom))
    assert is_error is True
    assert text == "ERROR: kaput"


def test_policy_loop_guard_on_third_identical_call():
    policy = ToolRunPolicy(timeout=None)
    args = {"q": "same"}
    results = [
        run(policy.run_async("t", args, call_sync=lambda: "ok"))[0]
        for _ in range(3)
    ]
    assert "loop guard" not in results[0]
    assert "loop guard" not in results[1]
    assert "loop guard" in results[2]
    # Different args never trip it.
    text, _ = run(policy.run_async("t", {"q": "different"}, call_sync=lambda: "ok"))
    assert "loop guard" not in text


def test_policy_run_sync_paths():
    policy = ToolRunPolicy(timeout=0.05)
    text, err = policy.run_sync("s", {}, lambda: "fine")
    assert (text, err) == ("fine", False)

    text, err = policy.run_sync("s", {}, lambda: time.sleep(2) or "late")
    assert err is True
    assert "timed out" in text

    def boom():
        raise ValueError("nope")

    text, err = policy.run_sync("s", {}, boom)
    assert err is True
    assert text == "ERROR: nope"


def test_policy_dict_results_json_encoded():
    policy = ToolRunPolicy(timeout=None)
    text, _ = run(policy.run_async("t", {}, call_sync=lambda: {"a": 1}))
    assert text == '{"a": 1}'


def test_policy_timeout_from_project_options():
    assert ToolRunPolicy(make_project(tool_timeout=120)).timeout == 120.0
    assert ToolRunPolicy(make_project(tool_timeout=0)).timeout is None


def test_policy_sync_calls_run_concurrently():
    policy = ToolRunPolicy(timeout=None)

    def slow():
        time.sleep(0.3)
        return "slept"

    async def both():
        return await asyncio.gather(
            policy.run_async("a", {}, call_sync=slow),
            policy.run_async("b", {}, call_sync=slow),
        )

    start = time.monotonic()
    results = run(both())
    elapsed = time.monotonic() - start
    assert [r[0] for r in results] == ["slept", "slept"]
    assert elapsed < 0.55, f"sync tools did not run in parallel ({elapsed:.2f}s)"


# ─── fallback helpers ───────────────────────────────────────────────────

def test_fallback_llm_names_parses_and_dedupes():
    project = make_project(fallback_llm=" backup, main-llm, backup, other ")
    assert fallback_llm_names(project) == ["backup", "other"]
    assert fallback_llm_names(make_project(fallback_llm=None)) == []


def _scripted_factory(scripts):
    """scripts[i] = list of items for attempt i: (kind, payload) tuples,
    ("tool", None) markers (increment run_state, not yielded), or Exceptions
    raised at that point."""
    calls: list = []
    states: list = []

    def factory(llm_override, run_state):
        script = scripts[len(calls)]
        calls.append(llm_override)
        states.append(run_state)

        async def gen():
            for item in script:
                if isinstance(item, Exception):
                    raise item
                kind, payload = item
                if kind == "tool":
                    run_state["tools_executed"] += 1
                    continue
                yield kind, payload

        return gen()

    factory.calls = calls
    factory.states = states
    return factory


def _result(answer="ok"):
    return ("result", {"answer": answer, "tokens": {"input": 1, "output": 1},
                       "tool_trace": None, "stop_reason": None})


def test_drive_with_fallbacks_passthrough_on_success():
    project = make_project(fallback_llm="backup")
    factory = _scripted_factory([[("text", "hi"), _result()]])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    assert [k for k, _ in events] == ["text", "result"]
    assert factory.calls == [None]
    assert "llm_used" not in output


async def _collect(agen):
    out = []
    async for item in agen:
        out.append(item)
    return out


def test_drive_with_fallbacks_switches_before_any_output():
    project = make_project(fallback_llm="backup")
    factory = _scripted_factory([
        [RuntimeError("provider down")],
        [_result("saved by backup")],
    ])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))

    assert factory.calls == [None, "backup"]
    kinds = [k for k, _ in events]
    assert kinds == ["event", "result"]
    assert events[0][1] == {"llm_fallback": {"from": "main-llm", "to": "backup"}}
    # Switch row merged into the retried run's tool trace.
    trace = events[1][1]["tool_trace"]
    assert trace[0]["tool"] == "llm_fallback"
    assert "backup" in trace[0]["args"]
    assert output["llm_used"] == "backup"
    assert output["llm_fallbacks"][0]["from"] == "main-llm"
    assert "provider down" in output["llm_fallbacks"][0]["error"]


def test_drive_with_fallbacks_no_retry_after_streamed_text():
    project = make_project(fallback_llm="backup")
    boom = RuntimeError("mid-stream death")
    factory = _scripted_factory([
        [("text", "partial"), boom],
        [_result("never")],
    ])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    assert factory.calls == [None]
    assert events[-1][0] == "error"
    assert events[-1][1]["exception"] is boom
    assert "llm_used" not in output


def test_drive_with_fallbacks_no_retry_after_tool_side_effect():
    project = make_project(fallback_llm="backup")
    boom = RuntimeError("died after tool ran")
    factory = _scripted_factory([
        [("tool", None), boom],
        [_result("never")],
    ])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    assert factory.calls == [None]
    assert events[-1][0] == "error"


def test_drive_with_fallbacks_chain_exhausted():
    project = make_project(fallback_llm="backup")
    final = RuntimeError("backup also down")
    factory = _scripted_factory([
        [RuntimeError("primary down")],
        [final],
    ])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    assert factory.calls == [None, "backup"]
    assert events[-1][0] == "error"
    assert events[-1][1]["exception"] is final
    # The attempted switch is still recorded for observability.
    assert output["llm_fallbacks"][0]["to"] == "backup"


def test_drive_with_fallbacks_incompatible_fallback_skips_to_next():
    from fastapi import HTTPException

    project = make_project(fallback_llm="wrong-class, good-one")
    factory = _scripted_factory([
        [RuntimeError("primary down")],
        [HTTPException(400, detail="requires an OpenAI-class LLM")],
        [_result("third time lucky")],
    ])
    output = {}
    events = run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    assert factory.calls == [None, "wrong-class", "good-one"]
    assert events[-1][0] == "result"
    assert output["llm_used"] == "good-one"
    assert len(output["llm_fallbacks"]) == 2
    assert "OpenAI-class" in output["llm_fallbacks"][1]["error"]


def test_drive_with_fallbacks_shares_one_deadline_across_attempts():
    project = make_project(fallback_llm="backup", max_execution_time=600)
    factory = _scripted_factory([
        [RuntimeError("primary down")],
        [_result("ok")],
    ])
    output = {}
    run(_collect(drive_with_fallbacks(project, factory, loop_name="x", output=output)))
    deadlines = [s.get("deadline") for s in factory.states]
    assert len(deadlines) == 2
    assert deadlines[0] is not None
    # The fallback attempt inherits the SAME deadline — no budget reset.
    assert deadlines[0] == deadlines[1]

    # Unlimited project → no deadline handed to attempts.
    factory2 = _scripted_factory([[_result("ok")]])
    run(_collect(drive_with_fallbacks(
        make_project(max_execution_time=0), factory2, loop_name="x", output={},
    )))
    assert factory2.states[0].get("deadline") is None


# ─── wall-clock execution cap helpers ───────────────────────────────────

def test_max_execution_seconds_getter():
    assert max_execution_seconds(make_project(max_execution_time=0)) is None
    assert max_execution_seconds(make_project(max_execution_time=120)) == 120.0
    # Missing attribute (older stored options) → unlimited, never raises.
    bare = types.SimpleNamespace(props=types.SimpleNamespace(
        options=types.SimpleNamespace()))
    assert max_execution_seconds(bare) is None


def test_execution_deadline_is_future_monotonic():
    assert execution_deadline(make_project(max_execution_time=0)) is None
    deadline = execution_deadline(make_project(max_execution_time=300))
    assert deadline is not None
    assert deadline > time.monotonic() + 250


def test_max_time_notice_text():
    notice = max_time_notice(90)
    assert "90s execution-time cap" in notice
    assert "continue" in notice


# ─── shared token estimator + usage extraction ──────────────────────────

def test_estimate_input_tokens_folds_everything():
    history = [types.SimpleNamespace(content="earlier turn " * 50)]
    base = estimate_input_tokens("question")
    full = estimate_input_tokens(
        "question", system_prompt="sys " * 100, history=history,
        tool_trace=[{"tool": "t", "args": "{}"}],
    )
    assert full > base > 0


def test_usage_from_raw_response_shapes():
    assert usage_from_raw_response({"usage": {"prompt_tokens": 10, "completion_tokens": 3}}) == (10, 3)
    obj = types.SimpleNamespace(usage=types.SimpleNamespace(input_tokens=7, output_tokens=2))
    assert usage_from_raw_response(obj) == (7, 2)
    assert usage_from_raw_response(None) is None
    assert usage_from_raw_response({"usage": {}}) is None


# ─── per-loop wrapper integration ───────────────────────────────────────

def _li_function_tool(fn, name="mytool"):
    from llama_index.core.tools import FunctionTool
    return FunctionTool.from_defaults(fn=fn, name=name, description="d")


def test_llamaindex_bound_tool_threads_caps_and_injects_context():
    from restai.projects._llamaindex_loop import _bind_request_kwargs

    seen = {}

    def terminal(command: str, **kwargs):
        seen.update(kwargs)
        seen["command"] = command
        return "out " * 20_000

    ft = _li_function_tool(terminal, "terminal")
    policy = ToolRunPolicy(timeout=None)
    bound = _bind_request_kwargs(
        ft, brain="BRAIN", chat_id="c1", project_id=9, policy=policy,
    )
    # The bound wrapper is async; llama-index exposes a sync-bridged `.fn`.
    out = bound.fn(command="ls")
    assert seen["command"] == "ls"
    assert seen["_brain"] == "BRAIN"
    assert seen["_chat_id"] == "c1"
    assert "truncated" in out


def test_llamaindex_bound_tool_timeout():
    from restai.projects._llamaindex_loop import _bind_request_kwargs

    def sleepy(**kwargs):
        time.sleep(2)
        return "late"

    ft = _li_function_tool(sleepy, "sleepy")
    bound = _bind_request_kwargs(
        ft, brain=None, chat_id="c", project_id=1,
        policy=ToolRunPolicy(timeout=0.05),
    )
    out = bound.fn()
    assert "timed out" in out


def test_llamaindex_adapted_mcp_wrapper_preserves_schema_and_caps():
    from restai.agent2.tool_adapter import AdaptedTool
    from restai.projects._llamaindex_loop import _wrap_adapted_with_policy

    async def mcp_fn(**kwargs):
        return "y" * 50_000

    adapted = AdaptedTool(
        name="mcp_tool", description="d",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}},
                      "required": ["q"]},
        fn=mcp_fn, is_async=True,
    )
    li_ft = agent_shared.adapted_to_function_tool(adapted)
    wrapped = _wrap_adapted_with_policy(li_ft, ToolRunPolicy(timeout=None))
    assert wrapped.metadata.name == "mcp_tool"
    assert wrapped.metadata.fn_schema is not None
    out = wrapped.fn(q="hi")
    assert "truncated" in out


def test_claude_sdk_tool_wrapper_caps_and_flags_errors():
    from restai.projects._claude_sdk_tools import _wrap_function_tool

    def big(**kwargs):
        return "x" * 50_000

    sdk_tool = _wrap_function_tool(
        _li_function_tool(big, "big"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
    )
    resp = run(sdk_tool.handler({}))
    assert "isError" not in resp
    assert "truncated" in resp["content"][0]["text"]

    def boom(**kwargs):
        raise RuntimeError("dead")

    sdk_tool = _wrap_function_tool(
        _li_function_tool(boom, "boom"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
    )
    resp = run(sdk_tool.handler({}))
    assert resp["isError"] is True
    assert "ERROR: dead" in resp["content"][0]["text"]


def test_claude_sdk_tool_wrapper_timeout():
    from restai.projects._claude_sdk_tools import _wrap_function_tool

    def sleepy(**kwargs):
        time.sleep(2)
        return "late"

    sdk_tool = _wrap_function_tool(
        _li_function_tool(sleepy, "sleepy"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=0.05),
    )
    resp = run(sdk_tool.handler({}))
    assert resp["isError"] is True
    assert "timed out" in resp["content"][0]["text"]


def test_openai_agents_tool_wrapper_caps_and_times_out():
    from restai.projects._openai_agents_loop import _wrap_function_tool

    def big(**kwargs):
        return "x" * 50_000

    ft = _wrap_function_tool(
        _li_function_tool(big, "big"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
    )
    out = run(ft.on_invoke_tool(None, "{}"))
    assert "truncated" in out

    def sleepy(**kwargs):
        time.sleep(2)
        return "late"

    ft = _wrap_function_tool(
        _li_function_tool(sleepy, "sleepy"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=0.05),
    )
    out = run(ft.on_invoke_tool(None, "{}"))
    assert "timed out" in out


def test_smolagents_tool_wrapper_caps_and_times_out():
    from restai.projects._smolagents_loop import _wrap_function_tool

    def big(**kwargs):
        return "x" * 50_000

    tool = _wrap_function_tool(
        _li_function_tool(big, "big"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
    )
    out = tool.forward()
    assert "truncated" in out

    def sleepy(**kwargs):
        time.sleep(2)
        return "late"

    tool = _wrap_function_tool(
        _li_function_tool(sleepy, "sleepy"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=0.05),
    )
    out = tool.forward()
    assert "timed out" in out


def test_openai_agents_async_tool_stays_on_calling_loop():
    from restai.projects._openai_agents_loop import _wrap_function_tool

    seen = {}

    async def mcp_fn(**kwargs):
        seen["loop"] = asyncio.get_running_loop()
        seen["kwargs"] = dict(kwargs)
        return "same-loop"

    ft = _wrap_function_tool(
        _li_function_tool(mcp_fn, "mcp"),
        brain="BRAIN", chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
        inject_context=False,
    )

    async def scenario():
        out = await ft.on_invoke_tool(None, '{"q": "x"}')
        assert out == "same-loop"
        # MCP sessions are bound to the request loop — the coroutine must run
        # there, not on a throwaway loop from llama-index's sync bridge.
        assert seen["loop"] is asyncio.get_running_loop()
        # MCP kwargs go verbatim to the server — context must NOT be injected.
        assert seen["kwargs"] == {"q": "x"}

    run(scenario())


def test_smolagents_async_tool_dispatches_to_main_loop():
    from restai.projects._smolagents_loop import _wrap_function_tool

    seen = {}

    async def mcp_fn(**kwargs):
        seen["loop"] = asyncio.get_running_loop()
        seen["kwargs"] = dict(kwargs)
        return "on-main"

    async def scenario():
        main = asyncio.get_running_loop()
        tool = _wrap_function_tool(
            _li_function_tool(mcp_fn, "mcp"),
            brain="BRAIN", chat_id="c", project_id=1,
            policy=ToolRunPolicy(timeout=None), main_loop=main,
            inject_context=False,
        )
        # smolagents calls forward() from its worker thread.
        out = await asyncio.to_thread(lambda: tool.forward(q="x"))
        assert out == "on-main"
        assert seen["loop"] is main
        assert seen["kwargs"] == {"q": "x"}

    run(scenario())


def test_smolagents_async_tool_bridged_and_guarded():
    from restai.projects._smolagents_loop import _wrap_function_tool

    async def async_tool(**kwargs):
        return "async-ok"

    tool = _wrap_function_tool(
        _li_function_tool(async_tool, "async_tool"),
        brain=None, chat_id="c", project_id=1, policy=ToolRunPolicy(timeout=None),
    )
    outs = [tool.forward(q="same") for _ in range(3)]
    assert outs[0].startswith("async-ok")
    assert "loop guard" in outs[2]
