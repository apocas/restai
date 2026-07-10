"""Coverage for the token-accounting gap fixes: count_usage, platform-usage rows,
and the guard accounting wiring."""
import types

from restai.database import open_db_wrapper
from restai.models.databasemodels import OutputDatabase


def test_count_usage_prefers_real_then_estimates():
    from restai.limits.accounting import count_usage

    # Provider-reported usage wins.
    resp = types.SimpleNamespace(raw={"usage": {
        "prompt_tokens": 30, "completion_tokens": 9, "total_tokens": 39,
    }})
    assert count_usage(resp, "ignored", "ignored") == (30, 9)

    # No response → tiktoken estimate of the text.
    i, o = count_usage(None, "hello world foo bar", "an answer")
    assert i > 0 and o > 0


def test_log_platform_usage_writes_unbilled_row():
    """Platform System-LLM usage is logged with team_id/api_key_id/project_id NULL
    so it shows in statistics but bills no team."""
    from restai.limits.accounting import log_platform_usage

    db = open_db_wrapper()
    try:
        sys_llm = types.SimpleNamespace(props=types.SimpleNamespace(
            name="sys-test-llm", input_cost=1.0, output_cost=2.0,
        ))
        log_platform_usage(db, "unit_test_feat", sys_llm, "some prompt text here", "some answer")

        row = (
            db.db.query(OutputDatabase)
            .filter(OutputDatabase.question == "(platform:unit_test_feat)")
            .order_by(OutputDatabase.id.desc())
            .first()
        )
        assert row is not None
        assert row.team_id is None
        assert row.project_id is None
        assert row.api_key_id is None
        assert row.llm == "sys-test-llm"
        assert row.input_tokens > 0
        # cleanup
        db.db.delete(row)
        db.db.commit()
    finally:
        db.db.close()


def test_account_guard_logs_against_guard_project(monkeypatch):
    """Guard checks are logged via log_inference against the guard project, with
    the guard call's own token counts."""
    from restai.projects import base

    captured = []
    monkeypatch.setattr(
        "restai.tools.log_inference",
        lambda project, user, output, db: captured.append((project, output)),
    )

    guard = types.SimpleNamespace(project=types.SimpleNamespace(props="guard-proj"))
    result = types.SimpleNamespace(raw_response="OK", input_tokens=5, output_tokens=2)
    user = types.SimpleNamespace(id=1)

    base._account_guard(guard, user, "some question", result, db=None)

    assert len(captured) == 1
    project, output = captured[0]
    assert project.props == "guard-proj"
    assert output["tokens"] == {"input": 5, "output": 2}
    assert output["status"] == "guard"
    assert output["answer"] == "OK"


def test_account_guard_noop_without_guard_project(monkeypatch):
    """No log when the guard project failed to load."""
    from restai.projects import base

    captured = []
    monkeypatch.setattr("restai.tools.log_inference", lambda *a, **k: captured.append(1))
    guard = types.SimpleNamespace(project=None)
    result = types.SimpleNamespace(raw_response="OK", input_tokens=1, output_tokens=1)
    base._account_guard(guard, types.SimpleNamespace(id=1), "q", result, db=None)
    assert captured == []


def test_cost_for_tokens_math():
    import pytest
    from restai.limits.accounting import cost_for_tokens

    c = cost_for_tokens({"input": 1000, "output": 500}, 3.0, 6.0)
    assert c["input"] == pytest.approx(0.003)   # 1000 * 3 / 1e6
    assert c["output"] == pytest.approx(0.003)  # 500 * 6 / 1e6
    assert c["total"] == pytest.approx(0.006)

    # Missing / zero tokens and prices are all safe.
    assert cost_for_tokens(None, 3.0, 6.0) == {"input": 0.0, "output": 0.0, "total": 0.0}
    assert cost_for_tokens({"input": 10, "output": 5}, None, None)["total"] == 0.0


def test_attach_cost_sets_input_output_total(monkeypatch):
    import pytest
    from restai.limits import accounting

    monkeypatch.setattr(
        "restai.models.models.LLMModel.model_validate",
        lambda _row: types.SimpleNamespace(input_cost=3.0, output_cost=6.0),
    )
    db = types.SimpleNamespace(get_llm_by_name=lambda _name: object())
    project = types.SimpleNamespace(props=types.SimpleNamespace(llm="some-llm"))
    out = {"tokens": {"input": 1000, "output": 500}}
    accounting.attach_cost(out, project, db)
    assert set(out["cost"]) == {"input", "output", "total"}
    assert out["cost"]["total"] == pytest.approx(0.006)


def test_attach_cost_idempotent_and_no_llm():
    from restai.limits import accounting

    # Already priced → left untouched (idempotent).
    out = {"tokens": {"input": 10, "output": 5}, "cost": {"input": 1, "output": 2, "total": 3}}
    accounting.attach_cost(
        out,
        types.SimpleNamespace(props=types.SimpleNamespace(llm="x")),
        types.SimpleNamespace(get_llm_by_name=lambda _n: None),
    )
    assert out["cost"] == {"input": 1, "output": 2, "total": 3}

    # No project LLM (e.g. block project) → zero cost, still present.
    out2 = {"tokens": {"input": 10, "output": 5}}
    accounting.attach_cost(
        out2,
        types.SimpleNamespace(props=types.SimpleNamespace(llm=None)),
        types.SimpleNamespace(get_llm_by_name=lambda _n: None),
    )
    assert out2["cost"] == {"input": 0.0, "output": 0.0, "total": 0.0}

    # No tokens key → nothing added.
    out3 = {"answer": "hi"}
    accounting.attach_cost(out3, types.SimpleNamespace(props=types.SimpleNamespace(llm="x")), None)
    assert "cost" not in out3


def test_enrich_final_frame_adds_cost(monkeypatch):
    import json
    from restai import helper

    monkeypatch.setattr(
        helper, "attach_cost",
        lambda output, project, db: output.__setitem__("cost", {"input": 0.1, "output": 0.2, "total": 0.3}),
    )
    project = types.SimpleNamespace(props=types.SimpleNamespace(llm="x"))

    # Final frame (has answer + type) → enriched with cost.
    frame = "data: " + json.dumps({"answer": "hi", "type": "chat", "tokens": {"input": 1, "output": 1}}) + "\n"
    new_frame, parsed = helper._enrich_final_frame(frame, project, db=None)
    assert parsed is not None and parsed["cost"]["total"] == 0.3
    assert '"cost"' in new_frame

    # Text-delta frame (no answer/type) → passes through untouched.
    text_frame = "data: " + json.dumps({"text": "hello"}) + "\n\n"
    nf, p = helper._enrich_final_frame(text_frame, project, db=None)
    assert p is None and nf == text_frame


def test_agent_count_tokens_includes_tool_trace():
    """Multi-step agent turns fold tool round-trip context into the token count."""
    from restai.projects.agent import Agent

    base_out = {"question": "hi", "answer": "done", "tool_trace": None}
    Agent._count_tokens(base_out)
    without = base_out["tokens"]["input"]

    with_trace = {"question": "hi", "answer": "done",
                  "tool_trace": [{"tool": "x", "args": {"a": "b" * 200}, "status": "ok"}]}
    Agent._count_tokens(with_trace)
    assert with_trace["tokens"]["input"] > without  # tool_trace added, never dropped
