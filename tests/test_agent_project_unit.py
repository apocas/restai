"""Unit tests for restai/projects/agent.py — the agent project handler.
Fakes for LLM/runtime/session store throughout; no models, no Docker,
no network.
"""
import asyncio
import base64
import json
import types

import pytest
from fastapi import HTTPException

import restai.projects.agent as agent_mod
from restai.agent2 import Agent2UnsupportedLLMError
from restai.agent2.types import (
    AgentEvent,
    AgentSession,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from restai.brain import Brain
from restai.projects.agent import (
    Agent,
    _looks_repetitive,
    _make_project_tool_adapted,
    _wrap_image_error,
)


def run(coro):
    return asyncio.run(coro)


class FakeBrain:
    defaultCensorship = "This question is outside of my scope."
    # Reuse the real implementation — it only touches `output`.
    post_processing_reasoning = Brain.post_processing_reasoning

    def __init__(self):
        self.docker_manager = None
        self.llm_wrapper = None

    def get_tools(self, names):
        return []

    def get_llm(self, name, db):
        return self.llm_wrapper

    def post_processing_counting(self, output):
        output.setdefault("tokens", {"input": 0, "output": 0})


def make_project(**opt_overrides):
    options = dict(
        agent_loop="restai",
        mcp_servers=[],
        auto_plan=False,
        max_iterations=5,
        tools="",
        agent_mode=None,
        guard_output=None,
        guard_mode=None,
    )
    options.update(opt_overrides)
    props = types.SimpleNamespace(
        id=1,
        name="proj",
        llm="llm1",
        system="base system",
        censorship=None,
        guard=None,
        options=types.SimpleNamespace(**options),
    )
    return types.SimpleNamespace(props=props)


def make_chat_model(question="hi", stream=False, chat_id="conv1"):
    return types.SimpleNamespace(
        question=question, stream=stream, id=chat_id,
        image=None, files=None, system=None,
    )


USER = types.SimpleNamespace(id=7, username="alice")


class ScriptedRuntime:
    """run_iter pops one batch of AgentEvents per invocation."""

    def __init__(self, batches):
        self.batches = [list(b) for b in batches]
        self.calls = []
        self.system_prompt = "sys"

    async def run_iter(self, prompt, *, session=None, image=None, stream=False):
        self.calls.append({"prompt": prompt, "image": image, "stream": stream})
        for ev in self.batches.pop(0):
            yield ev


def ev_delta(text):
    return AgentEvent(type="text_delta", data={"text": text})


def ev_assistant(*blocks):
    return AgentEvent(type="assistant",
                      message=Message(role="assistant", content=list(blocks)))


def ev_tool_result(tool_use_id, content):
    return AgentEvent(
        type="tool_result",
        message=Message(role="user",
                        content=[ToolResultBlock(tool_use_id=tool_use_id,
                                                 content=content)]),
    )


def ev_final(text, stop_reason="completed"):
    return AgentEvent(type="final",
                      data={"final_text": text, "stop_reason": stop_reason})


def make_agent():
    return Agent(FakeBrain())


async def drive(agent, runtime, *, prompt="q", session=None, stream=False,
                project=None, output=None):
    session = session if session is not None else AgentSession()
    output = output if output is not None else {"question": prompt}
    events = []
    async for kind, payload in agent._drive_runtime(
        runtime, prompt=prompt, session=session, image_block=None,
        stream=stream, project=project or make_project(), output=output,
    ):
        events.append((kind, payload))
    return events, output


# ─── _looks_repetitive ──────────────────────────────────────────────────

def test_looks_repetitive_true_on_identical_long_turns():
    t = "Let me look at a few more files before answering this question. " * 3
    assert _looks_repetitive([t, t, t]) is True


def test_looks_repetitive_false_under_three_or_short():
    long = "x" * 100
    assert _looks_repetitive([long, long]) is False
    assert _looks_repetitive(["short", "short", "short"]) is False


def test_looks_repetitive_false_when_divergent():
    a = "The alpha result covers many interesting different details here. " * 3
    b = "Beta content goes a completely different direction entirely now. " * 3
    c = "Gamma text about something else altogether, unrelated to both. " * 3
    assert _looks_repetitive([a, b, c]) is False


# ─── _wrap_image_error ──────────────────────────────────────────────────

def test_wrap_image_error_passthrough_without_image():
    err = ValueError("original")
    assert _wrap_image_error(err, has_image=False) is err


def test_wrap_image_error_wraps_with_image():
    wrapped = _wrap_image_error(ValueError("upstream 400"), has_image=True)
    assert isinstance(wrapped, HTTPException)
    assert wrapped.status_code == 400
    assert "vision-capable" in wrapped.detail
    assert "upstream 400" in wrapped.detail


# ─── _make_project_tool_adapted ─────────────────────────────────────────

def _tool_row(name="mytool", parameters='{"type":"object","properties":{}}',
              code="print('hi')", description="does things"):
    return types.SimpleNamespace(name=name, parameters=parameters,
                                 code=code, description=description)


def test_project_tool_runs_in_sandbox_with_declared_args_only():
    calls = []

    class FakeDocker:
        def run_script(self, chat_id, script, stdin_data=""):
            calls.append((chat_id, script, stdin_data))
            return "tool output"

    brain = types.SimpleNamespace(docker_manager=FakeDocker())
    adapted = _make_project_tool_adapted(_tool_row(code="print(args['x'])"), brain)
    assert adapted.name == "mytool"
    assert adapted.description == "does things"
    assert adapted.is_async and adapted.accepts_kwargs

    out = run(adapted.call(
        {"x": 1}, context={"chat_id": "c5", "brain": brain, "user": object()}))
    assert out == "tool output"
    chat_id, script, stdin = calls[0]
    assert chat_id == "c5"
    assert "print(args['x'])" in script
    # framework-injected context keys never reach the sandbox stdin
    assert json.loads(stdin) == {"x": 1}


def test_project_tool_without_docker_errors():
    brain = types.SimpleNamespace(docker_manager=None)
    adapted = _make_project_tool_adapted(_tool_row(), brain)
    out = run(adapted.call({}, context={"brain": brain}))
    assert out == "ERROR: Docker is not configured."


def test_project_tool_invalid_schema_defaults():
    adapted = _make_project_tool_adapted(
        _tool_row(parameters="not json"), types.SimpleNamespace(docker_manager=None))
    assert adapted.input_schema == {"type": "object", "properties": {}, "required": []}


def test_project_tool_dict_schema_passthrough():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    row = _tool_row()
    row.parameters = schema
    adapted = _make_project_tool_adapted(row, None)
    assert adapted.input_schema is schema


# ─── _count_tokens ──────────────────────────────────────────────────────

def test_count_tokens_includes_history_and_system_prompt():
    session = AgentSession(messages=[
        Message(role="user", content=[TextBlock(text="earlier question " * 50)]),
        Message(role="assistant", content=[TextBlock(text="earlier answer " * 50)]),
    ])
    out_small = {"question": "q", "answer": "a"}
    Agent._count_tokens(out_small, "", None)
    baseline = out_small["tokens"]["input"]

    out_full = {"question": "q", "answer": "a"}
    Agent._count_tokens(out_full, "system prompt " * 20, session)
    assert out_full["tokens"]["input"] > baseline
    assert out_full["tokens"]["accuracy"] == "low"
    assert out_full["tokens"]["output"] >= 1


def test_count_tokens_excludes_final_answer_from_input():
    ans = "the final answer text " * 30
    with_ans = {"question": "q", "answer": ans}
    session = AgentSession(messages=[
        Message(role="assistant", content=[TextBlock(text=ans)]),
    ])
    Agent._count_tokens(with_ans, "", session)

    other = {"question": "q", "answer": "different"}
    session2 = AgentSession(messages=[
        Message(role="assistant", content=[TextBlock(text=ans)]),
    ])
    Agent._count_tokens(other, "", session2)
    # When the session text IS the answer it must not count as input.
    assert with_ans["tokens"]["input"] < other["tokens"]["input"]


def test_count_tokens_folds_tool_trace():
    bare = {"question": "q", "answer": "a"}
    Agent._count_tokens(bare, "", None)
    traced = {"question": "q", "answer": "a",
              "tool_trace": [{"tool": "t", "args": "x" * 400}]}
    Agent._count_tokens(traced, "", None)
    assert traced["tokens"]["input"] > bare["tokens"]["input"]


def test_count_tokens_never_raises():
    class Evil:
        def get(self, *a, **kw):
            raise RuntimeError("boom")

        def __getitem__(self, k):
            raise RuntimeError("boom")

        def __setitem__(self, k, v):
            self.__dict__[k] = v

    out = Evil()
    Agent._count_tokens(out, "", None)
    assert out.__dict__["tokens"] == {"input": 0, "output": 0, "accuracy": "low"}


# ─── _drive_runtime ─────────────────────────────────────────────────────

def test_drive_runtime_text_deltas_and_final():
    agent = make_agent()
    runtime = ScriptedRuntime([[ev_delta("Hel"), ev_delta("lo"), ev_final("Hello")]])
    events, output = run(drive(agent, runtime, stream=True))
    assert events == [("text", "Hel"), ("text", "lo")]
    assert output["answer"] == "Hello"
    assert "tool_trace" not in output


def test_drive_runtime_tool_flow_records_trace_and_events():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={"x": 1})),
        ev_tool_result("t1", "42"),
        ev_final("done"),
    ]])
    events, output = run(drive(agent, runtime, stream=True))
    kinds = [k for k, _ in events]
    assert kinds == ["event", "event"]
    started = events[0][1]["tool_call_started"]
    assert started["tool"] == "calc" and started["id"] == "t1"
    completed = events[1][1]["tool_call_completed"]
    assert completed["status"] == "ok"
    assert completed["output"] == "42"
    assert completed["latency_ms"] is not None

    [trace] = output["tool_trace"]
    assert trace["tool"] == "calc"
    assert trace["status"] == "ok"
    assert trace["error"] is None
    steps = output["reasoning"]["steps"]
    assert steps[0]["actions"][0] == {"action": "calc", "input": {"x": 1},
                                      "output": "42"}


def test_drive_runtime_error_tool_result_classified():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={})),
        ev_tool_result("t1", "ERROR: division by zero"),
        ev_final("done"),
    ]])
    events, output = run(drive(agent, runtime, stream=True))
    completed = events[1][1]["tool_call_completed"]
    assert completed["status"] == "error"
    assert "division by zero" in completed["error"]
    assert output["tool_trace"][0]["status"] == "error"


def test_drive_runtime_long_args_and_output_previews_truncated():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={"blob": "x" * 900})),
        ev_tool_result("t1", "y" * 900),
        ev_final("done"),
    ]])
    events, output = run(drive(agent, runtime, stream=True))
    assert events[0][1]["tool_call_started"]["args"].endswith("…")
    assert events[1][1]["tool_call_completed"]["output"].endswith("…")
    assert len(output["tool_trace"][0]["args"]) <= 501


def test_drive_runtime_splices_dropped_image_urls():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="draw_image", input={})),
        ev_tool_result("t1", "Here: ![](/image/cache/AB12.png)"),
        ev_final("Image generated!"),
    ]])
    _, output = run(drive(agent, runtime))
    assert output["answer"].startswith("Image generated!")
    assert "![](/image/cache/AB12.png)" in output["answer"]


def test_drive_runtime_image_url_already_present_not_duplicated():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="draw_image", input={})),
        ev_tool_result("t1", "![](/image/cache/AB12.png)"),
        ev_final("See ![](/image/cache/AB12.png)"),
    ]])
    _, output = run(drive(agent, runtime))
    assert output["answer"].count("/image/cache/AB12.png") == 1


def test_drive_runtime_max_turns_appends_notice():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_delta("partial work so far"),
        ev_final("only last turn", stop_reason="max_turns"),
    ]])
    project = make_project(max_iterations=3)
    _, output = run(drive(agent, runtime, stream=True, project=project))
    assert output["answer"].startswith("partial work so far")
    assert "3-iteration tool-call cap" in output["answer"]


def test_drive_runtime_repetition_guard_aborts():
    agent = make_agent()
    rep = "I will check a few more files before I answer the question. " * 3
    runtime = ScriptedRuntime([[
        ev_assistant(TextBlock(text=rep)),
        ev_assistant(TextBlock(text=rep)),
        ev_assistant(TextBlock(text=rep)),
        ev_final("never reached"),
    ]])
    events, output = run(drive(agent, runtime, stream=True))
    assert output["aborted_repetition"] is True
    assert "repetitive output" in output["answer"]
    assert events[-1][0] == "text"
    assert "repetitive output" in events[-1][1]


def test_drive_runtime_tool_call_resets_repetition_buffer():
    agent = make_agent()
    rep = "I will check a few more files before I answer the question. " * 3
    runtime = ScriptedRuntime([[
        ev_assistant(TextBlock(text=rep)),
        ev_assistant(TextBlock(text=rep)),
        # progress! tool call clears the detector
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={})),
        ev_tool_result("t1", "ok"),
        ev_assistant(TextBlock(text=rep)),
        ev_final("real answer"),
    ]])
    _, output = run(drive(agent, runtime))
    assert "aborted_repetition" not in output
    assert output["answer"] == "real answer"


def test_drive_runtime_interrupted_stream_recovers_buffer():
    agent = make_agent()
    runtime = ScriptedRuntime([[ev_delta("what the user "), ev_delta("saw")]])
    _, output = run(drive(agent, runtime, stream=True))
    assert output["answer"] == "what the user saw"


def test_drive_runtime_extracts_thoughts_from_stream_buffer():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_delta("<think>early pondering</think>"),
        ev_delta("visible answer"),
        ev_final("visible answer"),
    ]])
    _, output = run(drive(agent, runtime, stream=True))
    assert output["answer"] == "visible answer"
    thoughts = [
        a["output"]
        for s in output["reasoning"]["steps"]
        for a in s["actions"] if a["action"] == "reasoning"
    ]
    assert thoughts == ["early pondering"]


def test_drive_runtime_fallback_when_tools_but_no_answer():
    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={})),
        ev_tool_result("t1", "data"),
        # runtime dies before final; nothing streamed
    ]])
    _, output = run(drive(agent, runtime))
    assert "didn't produce a final answer" in output["answer"]


def test_drive_runtime_fallback_uses_censorship():
    agent = make_agent()
    project = make_project()
    project.props.censorship = "custom censored"
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="calc", input={})),
        ev_tool_result("t1", "data"),
    ]])
    _, output = run(drive(agent, runtime, project=project))
    assert output["answer"] == "custom censored"


def test_drive_runtime_injects_artifacts_into_session():
    from restai.agent2 import artifacts

    agent = make_agent()
    runtime = ScriptedRuntime([[
        ev_assistant(ToolUseBlock(id="t1", name="terminal", input={})),
        ev_tool_result("t1", "saved files"),
        ev_final("done"),
    ]])
    runtime._chat_id = "art_chat_1"
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    artifacts.stage("art_chat_1", [
        {"name": "plot.png", "mime": "image/png", "size": len(png),
         "bytes": png, "truncated": False},
        {"name": "huge.bin", "mime": "application/zip", "size": 999999,
         "bytes": None, "truncated": True},
    ])
    session = AgentSession()
    _, output = run(drive(agent, runtime, session=session))
    injected = session.messages[-1]
    assert injected.role == "user"
    manifest = injected.content[0].text
    assert "plot.png" in manifest and "attached below as image" in manifest
    assert "huge.bin" in manifest and "too large to attach" in manifest
    from restai.agent2.types import ImageBlock
    assert any(isinstance(b, ImageBlock) for b in injected.content)
    # tray drained
    assert artifacts.consume("art_chat_1") == []


# ─── _run_planner ───────────────────────────────────────────────────────

class FakeLLM:
    def __init__(self, text):
        self._text = text

    def complete(self, prompt):
        if isinstance(self._text, Exception):
            raise self._text
        return types.SimpleNamespace(text=self._text)


def _agent_with_planner(text):
    agent = make_agent()
    agent.brain.llm_wrapper = types.SimpleNamespace(llm=FakeLLM(text))
    return agent


def test_planner_valid_plan():
    agent = _agent_with_planner('{"plan": ["Step one", "Step two", "Step three"]}')
    plan = run(agent._run_planner(make_project(), "do complex things", None))
    assert plan == ["Step one", "Step two", "Step three"]


def test_planner_null_plan():
    agent = _agent_with_planner('{"plan": null}')
    assert run(agent._run_planner(make_project(), "hi", None)) is None


def test_planner_strips_think_and_fences():
    agent = _agent_with_planner(
        '<think>reasoning</think>```json\n{"plan": ["A step", "B step"]}\n```')
    plan = run(agent._run_planner(make_project(), "q", None))
    assert plan == ["A step", "B step"]


def test_planner_extracts_json_from_prose():
    agent = _agent_with_planner(
        'Sure! Here is the plan: {"plan": ["First", "Second"]} hope that helps')
    assert run(agent._run_planner(make_project(), "q", None)) == ["First", "Second"]


def test_planner_invalid_json_skips():
    agent = _agent_with_planner("total garbage")
    assert run(agent._run_planner(make_project(), "q", None)) is None


def test_planner_wrong_lengths_skip():
    agent = _agent_with_planner('{"plan": ["only one"]}')
    assert run(agent._run_planner(make_project(), "q", None)) is None
    agent = _agent_with_planner(json.dumps({"plan": [f"s{i}" for i in range(7)]}))
    assert run(agent._run_planner(make_project(), "q", None)) is None


def test_planner_non_list_plan_skips():
    agent = _agent_with_planner('{"plan": "not a list"}')
    assert run(agent._run_planner(make_project(), "q", None)) is None


def test_planner_llm_failure_skips():
    agent = _agent_with_planner(RuntimeError("llm down"))
    assert run(agent._run_planner(make_project(), "q", None)) is None


def test_planner_no_llm_wrapper_skips():
    agent = make_agent()  # llm_wrapper None
    assert run(agent._run_planner(make_project(), "q", None)) is None


# ─── _chat_planned_stream ───────────────────────────────────────────────

def _frames(sse_lines):
    out = []
    for line in sse_lines:
        assert line.startswith("data: ")
        out.append(json.loads(line[len("data: "):].strip()))
    return out


def test_planned_stream_runs_steps_and_synthesis():
    agent = make_agent()
    runtime = ScriptedRuntime([
        [ev_final("step one findings")],
        [ev_final("step two findings")],
        [ev_final("the grand synthesis")],
    ])
    output = {}
    lines = []

    async def go():
        async for line in agent._chat_planned_stream(
            project=make_project(),
            original_prompt="big request",
            plan=["Investigate", "Summarize"],
            session=AgentSession(),
            runtime=runtime,
            image_block=None,
            stream=True,
            output=output,
        ):
            lines.append(line)

    run(go())
    frames = _frames(lines)
    assert frames[0] == {"plan": ["Investigate", "Summarize"]}
    starts = [f["step_start"] for f in frames if "step_start" in f]
    assert [s["name"] for s in starts] == ["Investigate", "Summarize",
                                          "Synthesize final answer"]
    dones = [f["step_done"] for f in frames if "step_done" in f]
    assert dones[-1]["summary"] == "synthesis complete"

    assert output["answer"] == "the grand synthesis"
    assert output["plan"] == ["Investigate", "Summarize"]
    assert [s["result"] for s in output["step_summaries"]] == [
        "step one findings", "step two findings"]
    # step 1 prompt carries the request + plan; step 2 carries the recap
    assert "big request" in runtime.calls[0]["prompt"]
    assert "step 1/2" in runtime.calls[0]["prompt"]
    assert "step one findings" in runtime.calls[1]["prompt"]
    assert "step one findings" in runtime.calls[2]["prompt"]


def test_planned_stream_aborts_plan_on_repetition():
    agent = make_agent()
    rep = "I keep saying exactly the same words over and over again here. " * 3
    runtime = ScriptedRuntime([
        [ev_assistant(TextBlock(text=rep)),
         ev_assistant(TextBlock(text=rep)),
         ev_assistant(TextBlock(text=rep))],
        # remaining batches must never be pulled
        [ev_final("should not run")],
        [ev_final("no synthesis either")],
    ])
    output = {}

    async def go():
        async for _ in agent._chat_planned_stream(
            project=make_project(), original_prompt="req",
            plan=["A", "B"], session=AgentSession(), runtime=runtime,
            image_block=None, stream=False, output=output,
        ):
            pass

    run(go())
    assert output["aborted_repetition"] is True
    assert "repetitive output" in output["answer"]
    assert len(runtime.calls) == 1  # plan aborted after step 1


# ─── chat() full flow ───────────────────────────────────────────────────

@pytest.fixture
def chat_env(monkeypatch):
    """Patch session store + prompt augmentation for isolated chat() runs."""
    saved = {}

    async def fake_get_session(brain, chat_id):
        return AgentSession()

    async def fake_save_session(brain, chat_id, session):
        saved["chat_id"] = chat_id

    monkeypatch.setattr(agent_mod, "get_session", fake_get_session)
    monkeypatch.setattr(agent_mod, "save_session", fake_save_session)
    monkeypatch.setattr(agent_mod, "_augment_system_prompt_with_memory_bank",
                        lambda project, db, base: base)
    monkeypatch.setattr(agent_mod, "_augment_system_prompt_with_memory_search_hint",
                        lambda project, base: base)
    monkeypatch.setattr(agent_mod, "_prepend_current_time", lambda base: base)
    return saved


def _wire_runtime(monkeypatch, runtime):
    built = {}

    def fake_build(self, project, db, system_prompt, extra_tools=None):
        built["system_prompt"] = system_prompt
        built["extra_tools"] = extra_tools
        if isinstance(runtime, Exception):
            raise runtime
        return runtime

    monkeypatch.setattr(Agent, "_build_runtime", fake_build)
    return built


def collect_chat(agent, project, chat_model):
    async def go():
        chunks = []
        async for chunk in agent.chat(project, chat_model, USER, None):
            chunks.append(chunk)
        return chunks

    return run(go())


def test_chat_non_streaming_returns_single_output(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("the answer")]])
    _wire_runtime(monkeypatch, runtime)
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert len(chunks) == 1
    out = chunks[0]
    assert out["answer"] == "the answer"
    assert out["type"] == "agent"
    assert out["id"] == "conv1"
    assert out["tokens"]["accuracy"] == "low"
    # session was persisted under the scoped sandbox id, not the raw chat id
    assert chat_env["chat_id"].startswith("sbx_")


def test_chat_streaming_emits_sse_protocol(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_delta("He"), ev_delta("y"), ev_final("Hey")]])
    _wire_runtime(monkeypatch, runtime)
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=True))
    assert chunks[0] == 'data: {"text": "He"}\n\n'
    assert chunks[1] == 'data: {"text": "y"}\n\n'
    final = json.loads(chunks[2][len("data: "):])
    assert final["answer"] == "Hey"
    assert chunks[3] == "event: close\n\n"
    # runtime got stream=True
    assert runtime.calls[0]["stream"] is True


def test_chat_streaming_no_deltas_emits_final_text(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("quiet answer")]])
    _wire_runtime(monkeypatch, runtime)
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=True))
    assert chunks[0] == 'data: {"text": "quiet answer"}\n\n'
    assert chunks[-1] == "event: close\n\n"


def test_chat_unsupported_llm_streams_error(chat_env, monkeypatch):
    _wire_runtime(monkeypatch, Agent2UnsupportedLLMError("provider not supported"))
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=True))
    assert chunks[0] == 'data: {"text": "provider not supported"}\n\n'
    final = json.loads(chunks[1][len("data: "):])
    assert final["answer"] == "provider not supported"
    assert chunks[2] == "event: close\n\n"


def test_chat_unsupported_llm_non_streaming(chat_env, monkeypatch):
    _wire_runtime(monkeypatch, Agent2UnsupportedLLMError("nope"))
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert out["answer"] == "nope"


def test_chat_runtime_failure_yields_error_answer(chat_env, monkeypatch):
    class ExplodingRuntime(ScriptedRuntime):
        async def run_iter(self, prompt, *, session=None, image=None, stream=False):
            raise RuntimeError("provider blew up")
            yield  # pragma: no cover

    _wire_runtime(monkeypatch, ExplodingRuntime([]))
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert "Agent failed: provider blew up" in out["answer"]


def test_chat_runtime_failure_uses_censorship(chat_env, monkeypatch):
    class ExplodingRuntime(ScriptedRuntime):
        async def run_iter(self, prompt, *, session=None, image=None, stream=False):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    _wire_runtime(monkeypatch, ExplodingRuntime([]))
    project = make_project()
    project.props.censorship = "not allowed"
    agent = make_agent()
    [out] = collect_chat(agent, project, make_chat_model(stream=False))
    assert out["answer"] == "not allowed"


def test_chat_input_guard_block_short_circuits(chat_env, monkeypatch):
    def fake_guard(self, project, question, user, db, output):
        output["answer"] = "blocked by guard"
        output["guard"] = True
        return True

    monkeypatch.setattr(Agent, "check_input_guard", fake_guard)

    def never_build(self, *a, **kw):
        raise AssertionError("runtime must not be built when guard blocks")

    monkeypatch.setattr(Agent, "_build_runtime", never_build)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert out["answer"] == "blocked by guard"
    assert out["guard"] is True


def test_chat_input_guard_block_streaming(chat_env, monkeypatch):
    def fake_guard(self, project, question, user, db, output):
        output["answer"] = "blocked"
        return True

    monkeypatch.setattr(Agent, "check_input_guard", fake_guard)
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=True))
    assert chunks[0] == 'data: {"text": "blocked"}\n\n'
    assert chunks[-1] == "event: close\n\n"


def test_chat_output_guard_invoked(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("raw answer")]])
    _wire_runtime(monkeypatch, runtime)
    checked = {}

    def fake_output_guard(self, project, user, db, output):
        checked["answer"] = output.get("answer")
        output["answer"] = "guarded answer"

    monkeypatch.setattr(Agent, "check_output_guard", fake_output_guard)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert checked["answer"] == "raw answer"
    assert out["answer"] == "guarded answer"


def test_chat_mcp_tools_passed_to_runtime(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("ok")]])
    built = _wire_runtime(monkeypatch, runtime)
    fake_tools = ["mcp-tool-sentinel"]

    class FakePool:
        entered = 0
        exited = 0

        async def __aenter__(self):
            FakePool.entered += 1
            return self

        async def __aexit__(self, *a):
            FakePool.exited += 1

        async def connect_servers(self, servers):
            assert servers == ["srv1"]
            return fake_tools

    monkeypatch.setattr(agent_mod, "MCPSessionPool", FakePool)
    agent = make_agent()
    project = make_project(mcp_servers=["srv1"])
    [out] = collect_chat(agent, project, make_chat_model(stream=False))
    assert out["answer"] == "ok"
    assert built["extra_tools"] == fake_tools
    assert FakePool.entered == 1 and FakePool.exited == 1


def test_chat_mcp_connect_failure_degrades_to_no_tools(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("ok")]])
    built = _wire_runtime(monkeypatch, runtime)

    class FakePool:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def connect_servers(self, servers):
            raise RuntimeError("all servers down")

    monkeypatch.setattr(agent_mod, "MCPSessionPool", FakePool)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(mcp_servers=["srv1"]),
                         make_chat_model(stream=False))
    assert out["answer"] == "ok"
    assert built["extra_tools"] == []


def test_chat_auto_plan_uses_planner(chat_env, monkeypatch):
    runtime = ScriptedRuntime([
        [ev_final("s1 done")],
        [ev_final("s2 done")],
        [ev_final("synthesized")],
    ])
    _wire_runtime(monkeypatch, runtime)

    async def fake_planner(self, project, prompt, db):
        return ["First", "Second"]

    monkeypatch.setattr(Agent, "_run_planner", fake_planner)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(auto_plan=True),
                         make_chat_model(stream=False))
    assert out["answer"] == "synthesized"
    assert out["plan"] == ["First", "Second"]
    assert len(runtime.calls) == 3


def test_chat_auto_plan_skipped_when_planner_declines(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("plain answer")]])
    _wire_runtime(monkeypatch, runtime)

    async def fake_planner(self, project, prompt, db):
        return None

    monkeypatch.setattr(Agent, "_run_planner", fake_planner)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(auto_plan=True),
                         make_chat_model(stream=False))
    assert out["answer"] == "plain answer"
    assert len(runtime.calls) == 1


def test_chat_generates_chat_id_when_missing(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("hi")]])
    _wire_runtime(monkeypatch, runtime)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(chat_id=None))
    assert out["id"]  # generated uuid
    assert out["id"] != "conv1"


@pytest.mark.parametrize("loop_name,module_attr", [
    ("claude", "_claude_sdk_loop"),
    ("llamaindex", "_llamaindex_loop"),
    ("smolagents", "_smolagents_loop"),
    ("openai_agents", "_openai_agents_loop"),
])
def test_chat_delegates_to_other_loops(monkeypatch, loop_name, module_attr):
    seen = {}

    async def fake_loop_chat(agent_self, project, chat_model, user, db):
        seen["loop"] = loop_name
        yield {"answer": f"from {loop_name} loop"}

    fake_module = types.SimpleNamespace(chat=fake_loop_chat)
    import restai.projects as projects_pkg
    monkeypatch.setattr(projects_pkg, module_attr, fake_module, raising=False)

    agent = make_agent()
    [out] = collect_chat(agent, make_project(agent_loop=loop_name),
                         make_chat_model())
    assert out == {"answer": f"from {loop_name} loop"}
    assert seen["loop"] == loop_name


def test_chat_streaming_runtime_failure_emits_error_frames(chat_env, monkeypatch):
    class ExplodingRuntime(ScriptedRuntime):
        async def run_iter(self, prompt, *, session=None, image=None, stream=False):
            raise RuntimeError("mid-flight failure")
            yield  # pragma: no cover

    _wire_runtime(monkeypatch, ExplodingRuntime([]))
    agent = make_agent()
    chunks = collect_chat(agent, make_project(), make_chat_model(stream=True))
    assert "mid-flight failure" in chunks[0]
    final = json.loads(chunks[1][len("data: "):])
    assert "Agent failed" in final["answer"]
    assert chunks[2] == "event: close\n\n"


def test_chat_setup_failure_caught_by_outer_handler(chat_env, monkeypatch):
    """A failure before _drive_runtime (e.g. session load) must degrade to a
    generic error answer instead of crashing the response."""
    runtime = ScriptedRuntime([[ev_final("never")]])
    _wire_runtime(monkeypatch, runtime)

    async def broken_get_session(brain, chat_id):
        raise RuntimeError("redis on fire")

    monkeypatch.setattr(agent_mod, "get_session", broken_get_session)
    agent = make_agent()
    [out] = collect_chat(agent, make_project(), make_chat_model(stream=False))
    assert out["answer"] == "An error occurred processing your request."


def test_chat_cancellation_propagates(chat_env, monkeypatch):
    runtime = ScriptedRuntime([[ev_final("never")]])
    _wire_runtime(monkeypatch, runtime)

    async def cancelled_get_session(brain, chat_id):
        raise asyncio.CancelledError()

    monkeypatch.setattr(agent_mod, "get_session", cancelled_get_session)
    agent = make_agent()

    async def go():
        with pytest.raises(asyncio.CancelledError):
            async for _ in agent.chat(make_project(), make_chat_model(), USER, None):
                pass

    run(go())


def test_chat_auto_plan_streaming_frames(chat_env, monkeypatch):
    runtime = ScriptedRuntime([
        [ev_delta("working"), ev_final("s1")],
        [ev_final("final synthesis")],
    ])
    _wire_runtime(monkeypatch, runtime)

    async def fake_planner(self, project, prompt, db):
        return ["Only step", "Second step"]

    monkeypatch.setattr(Agent, "_run_planner", fake_planner)
    # two steps + synthesis need three batches
    runtime.batches.insert(1, [ev_final("s2")])
    agent = make_agent()
    chunks = collect_chat(agent, make_project(auto_plan=True),
                          make_chat_model(stream=True))
    payloads = [json.loads(c[len("data: "):]) for c in chunks
                if c.startswith("data: ")]
    assert payloads[0] == {"plan": ["Only step", "Second step"]}
    assert any("step_start" in p for p in payloads)
    assert any(p.get("text") == "working" for p in payloads)
    assert any("step_done" in p for p in payloads)
    assert chunks[-1] == "event: close\n\n"
    final = [p for p in payloads if "answer" in p][-1]
    assert final["answer"] == "final synthesis"


# ─── _build_runtime ─────────────────────────────────────────────────────

def test_build_runtime_wires_provider_tools_and_options(monkeypatch):
    import restai.database as rdb

    llm_row = types.SimpleNamespace(name="llm1")
    fake_db = types.SimpleNamespace(get_llm_by_name=lambda name: llm_row)
    provider = object()
    config = types.SimpleNamespace(context_window=None)
    monkeypatch.setattr(agent_mod, "build_provider_for_llm",
                        lambda row: (provider, config))
    monkeypatch.setattr(agent_mod, "adapt_function_tools", lambda raw: [])

    enabled_row = types.SimpleNamespace(
        name="ptool", description="d",
        parameters='{"type":"object","properties":{}}', code="pass", enabled=True)
    disabled_row = types.SimpleNamespace(
        name="off", description="d",
        parameters='{"type":"object","properties":{}}', code="pass", enabled=False)

    class FakeDBW:
        def __init__(self):
            self.db = types.SimpleNamespace(close=lambda: None)

        def get_project_tools(self, project_id):
            assert project_id == 1
            return [enabled_row, disabled_row]

    monkeypatch.setattr(rdb, "DBWrapper", FakeDBW)
    agent = make_agent()
    extra = agent_mod.AdaptedTool(name="mcp_extra", description="", input_schema={},
                                  fn=lambda **kw: "x")
    project = make_project(max_iterations=9, agent_mode="react")
    runtime = agent._build_runtime(project, fake_db, "sys prompt",
                                   extra_tools=[extra])
    assert runtime.provider is provider
    assert runtime.system_prompt == "sys prompt"
    assert runtime.max_turns == 9
    assert runtime.mode == "react"
    names = {t.name for t in runtime.tools}
    assert names == {"mcp_extra", "ptool"}  # disabled project tool excluded


def test_build_runtime_unknown_llm_raises(monkeypatch):
    fake_db = types.SimpleNamespace(get_llm_by_name=lambda name: None)
    agent = make_agent()
    with pytest.raises(ValueError, match="LLM 'llm1' not found"):
        agent._build_runtime(make_project(), fake_db, None)


# ─── planned stream: deltas + trace merge ──────────────────────────────

def test_planned_stream_streams_deltas_and_merges_traces():
    agent = make_agent()
    runtime = ScriptedRuntime([
        [ev_delta("step-one-delta"),
         ev_assistant(ToolUseBlock(id="t1", name="search", input={})),
         ev_tool_result("t1", "found it"),
         ev_final("s1 result")],
        [ev_delta("synth-delta"), ev_final("synth result")],
    ])
    output = {}
    lines = []

    async def go():
        async for line in agent._chat_planned_stream(
            project=make_project(), original_prompt="req",
            plan=["A", "B"], session=AgentSession(), runtime=runtime,
            image_block=None, stream=True, output=output,
        ):
            lines.append(line)

    # plan has 2 steps → need 3 batches; add the middle one
    runtime.batches.insert(1, [ev_final("s2 result")])
    run(go())
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    assert any(p.get("text") == "step-one-delta" for p in payloads)
    assert any(p.get("text") == "synth-delta" for p in payloads)
    assert any("tool_call_started" in p for p in payloads)
    assert [t["tool"] for t in output["tool_trace"]] == ["search"]
    assert output["answer"] == "synth result"
