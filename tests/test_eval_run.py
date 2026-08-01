"""Tests for restai/eval.py — eval-run orchestration with faked brain,
faked project answers, and no real deepeval metric calls (eval LLM is left
unset so the 'No LLM available' scoring path is exercised).

Complements tests/test_evals.py, which covers the CRUD endpoints only.
"""
import asyncio
import json
import random
import types

import pytest
from fastapi.testclient import TestClient

from restai.main import app
from restai import eval as eval_mod
from restai.database import open_db_wrapper
from restai.eval import DeepEvalLLM, _build_metric, _get_project_answer, run_evaluation
from restai.models.databasemodels import (
    EvalDatasetDatabase,
    EvalResultDatabase,
    EvalRunDatabase,
    EvalTestCaseDatabase,
)

# Bogus project id — SQLite doesn't enforce FKs here, and brain.find_project
# is faked, so no real project row is needed.
PROJECT_ID = 987000 + random.randint(0, 999)


@pytest.fixture(scope="module")
def client():
    # Entering the TestClient runs the (shared) lifespan once, which
    # guarantees tables + the admin user exist for run_evaluation.
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    wrapper = open_db_wrapper()
    yield wrapper
    wrapper.close()


def _fake_project(ptype="agent", creator=None, llm=None, eval_llm=None):
    options = types.SimpleNamespace(eval_llm=eval_llm)
    props = types.SimpleNamespace(
        id=PROJECT_ID, type=ptype, creator=creator, llm=llm,
        system="orig system", options=options, name="fake",
    )
    return types.SimpleNamespace(props=props)


def _fake_brain(project=None, llm=None):
    return types.SimpleNamespace(
        find_project=lambda pid, db: project,
        get_llm=lambda name, db: llm,
    )


def _fake_app(brain):
    return types.SimpleNamespace(state=types.SimpleNamespace(brain=brain))


def _make_run(db, questions, metrics, expected=None):
    """Create dataset + test cases + run rows; returns run id."""
    dataset = EvalDatasetDatabase(name="ds", project_id=PROJECT_ID)
    db.db.add(dataset)
    db.db.commit()
    for i, q in enumerate(questions):
        exp = (expected or {}).get(i)
        db.db.add(EvalTestCaseDatabase(dataset_id=dataset.id, question=q, expected_answer=exp))
    run = EvalRunDatabase(
        dataset_id=dataset.id,
        project_id=PROJECT_ID,
        status="pending",
        metrics=json.dumps(metrics),
    )
    db.db.add(run)
    db.db.commit()
    return run.id


def _results(db, run_id):
    return (
        db.db.query(EvalResultDatabase)
        .filter(EvalResultDatabase.run_id == run_id)
        .all()
    )


def _refresh_run(db, run_id):
    db.db.expire_all()
    return db.db.query(EvalRunDatabase).filter(EvalRunDatabase.id == run_id).first()


# ─── DeepEvalLLM wrapper ────────────────────────────────────────────────

def test_deepeval_llm_wrapper():
    class _FakeLLM:
        def complete(self, prompt):
            return types.SimpleNamespace(text=f"echo:{prompt}")

    wrapped = DeepEvalLLM(model=_FakeLLM())
    assert wrapped.generate("hi") == "echo:hi"
    assert wrapped.get_model_name() == "Custom LLamaindex LLM"
    assert wrapped.load_model() is wrapped._llm


def test_deepeval_llm_a_generate():
    class _FakeAsyncLLM:
        async def complete(self, prompt):
            return types.SimpleNamespace(text=f"async:{prompt}")

    wrapped = DeepEvalLLM(model=_FakeAsyncLLM())
    assert asyncio.run(wrapped.a_generate("q")) == "async:q"


# ─── _build_metric ──────────────────────────────────────────────────────

def test_build_metric_unknown_raises():
    class _FakeLLM:
        def complete(self, prompt):
            return types.SimpleNamespace(text="x")

    llm = DeepEvalLLM(model=_FakeLLM())
    with pytest.raises(ValueError):
        _build_metric("nonsense_metric", llm)


def test_build_metric_known_names():
    class _FakeLLM:
        def complete(self, prompt):
            return types.SimpleNamespace(text="x")

    llm = DeepEvalLLM(model=_FakeLLM())
    assert _build_metric("answer_relevancy", llm) is not None
    assert _build_metric("faithfulness", llm) is not None
    assert _build_metric("correctness", llm) is not None


# ─── _get_project_answer ────────────────────────────────────────────────

def test_get_project_answer_unknown_type():
    project = _fake_project(ptype="weird")
    answer, sources, latency = asyncio.run(
        _get_project_answer(project, "q", None, None, None)
    )
    assert (answer, sources, latency) == ("", [], 0)


def test_get_project_answer_agent_happy_path(monkeypatch):
    import restai.projects.agent as agent_module

    class _FakeAgent:
        def __init__(self, brain):
            pass

        async def chat(self, project, q, user, db):
            yield {
                "answer": "the answer",
                "sources": [{"text": "src1"}, "src2", {"nope": 1}],
            }

    monkeypatch.setattr(agent_module, "Agent", _FakeAgent)
    project = _fake_project(ptype="agent")
    answer, sources, latency = asyncio.run(
        _get_project_answer(project, "q", None, None, None)
    )
    assert answer == "the answer"
    assert sources == ["src1", "src2"]
    assert latency >= 0


def test_get_project_answer_handler_error_returns_error_string(monkeypatch):
    import restai.projects.agent as agent_module

    class _BoomAgent:
        def __init__(self, brain):
            pass

        async def chat(self, project, q, user, db):
            raise RuntimeError("llm exploded")
            yield  # pragma: no cover

    monkeypatch.setattr(agent_module, "Agent", _BoomAgent)
    project = _fake_project(ptype="agent")
    answer, sources, _ = asyncio.run(
        _get_project_answer(project, "q", None, None, None)
    )
    assert answer.startswith("Error:")
    assert "llm exploded" in answer
    assert sources == []


# ─── run_evaluation orchestration ───────────────────────────────────────

def test_run_evaluation_missing_run_is_noop(client):
    brain = _fake_brain()
    asyncio.run(run_evaluation(99999999, _fake_app(brain)))  # must not raise


def test_run_evaluation_no_test_cases_completes_empty(client, db):
    dataset = EvalDatasetDatabase(name="empty-ds", project_id=PROJECT_ID)
    db.db.add(dataset)
    db.db.commit()
    run = EvalRunDatabase(
        dataset_id=dataset.id, project_id=PROJECT_ID,
        status="pending", metrics=json.dumps(["answer_relevancy"]),
    )
    db.db.add(run)
    db.db.commit()
    run_id = run.id

    asyncio.run(run_evaluation(run_id, _fake_app(_fake_brain())))

    row = _refresh_run(db, run_id)
    assert row.status == "completed"
    assert json.loads(row.summary) == {}
    assert row.completed_at is not None


def test_run_evaluation_project_not_found_fails(client, db):
    run_id = _make_run(db, ["q1"], ["answer_relevancy"])
    brain = _fake_brain(project=None)

    asyncio.run(run_evaluation(run_id, _fake_app(brain)))

    row = _refresh_run(db, run_id)
    assert row.status == "failed"
    assert "not found" in row.error


def test_run_evaluation_full_run_without_eval_llm(client, db, monkeypatch):
    """Two test cases, three metrics, no judge LLM configured.

    - answer_relevancy / faithfulness score 0.0 with 'No LLM available'
    - correctness on the case WITHOUT expected answer records the explicit
      'No expected answer' failure row
    """
    run_id = _make_run(
        db,
        ["q with expected", "q without expected"],
        ["answer_relevancy", "faithfulness", "correctness"],
        expected={0: "the truth"},
    )

    async def fake_answer(project, question, brain, user, db_):
        return f"answer to {question}", ["ctx chunk"], 7

    monkeypatch.setattr(eval_mod, "_get_project_answer", fake_answer)
    project = _fake_project()
    brain = _fake_brain(project=project)

    asyncio.run(run_evaluation(run_id, _fake_app(brain)))

    row = _refresh_run(db, run_id)
    assert row.status == "completed"

    results = _results(db, run_id)
    assert len(results) == 6  # 3 metrics x 2 cases
    by_metric = {}
    for r in results:
        by_metric.setdefault(r.metric_name, []).append(r)
    assert set(by_metric) == {"answer_relevancy", "faithfulness", "correctness"}

    for r in by_metric["answer_relevancy"] + by_metric["faithfulness"]:
        assert r.score == 0.0
        assert r.reason == "No LLM available for evaluation"
        assert r.passed is False
        assert r.latency_ms == 7
        assert r.actual_answer.startswith("answer to ")

    correctness_reasons = sorted(r.reason for r in by_metric["correctness"])
    assert any("No expected answer" in reason for reason in correctness_reasons)
    assert any("No LLM available" in reason for reason in correctness_reasons)

    # Retrieval context persisted for the metrics that used it.
    assert any(
        r.retrieval_context and json.loads(r.retrieval_context) == ["ctx chunk"]
        for r in by_metric["answer_relevancy"]
    )

    summary = json.loads(row.summary)
    assert summary == {"answer_relevancy": 0.0, "faithfulness": 0.0, "correctness": 0.0}


def test_run_evaluation_faithfulness_skipped_without_context(client, db, monkeypatch):
    run_id = _make_run(db, ["q1"], ["faithfulness"])

    async def fake_answer(project, question, brain, user, db_):
        return "bare answer", [], 3  # no sources, no tc context

    monkeypatch.setattr(eval_mod, "_get_project_answer", fake_answer)
    brain = _fake_brain(project=_fake_project())

    asyncio.run(run_evaluation(run_id, _fake_app(brain)))

    row = _refresh_run(db, run_id)
    assert row.status == "completed"
    assert _results(db, run_id) == []
    assert json.loads(row.summary) == {}


def test_run_evaluation_timeout_records_error_answer(client, db, monkeypatch):
    run_id = _make_run(db, ["slow question"], ["answer_relevancy"])

    async def hanging_answer(project, question, brain, user, db_):
        await asyncio.sleep(5)
        return "never", [], 0

    monkeypatch.setattr(eval_mod, "_get_project_answer", hanging_answer)
    monkeypatch.setattr(eval_mod, "ANSWER_TIMEOUT_SECONDS", 0.05)
    brain = _fake_brain(project=_fake_project())

    asyncio.run(run_evaluation(run_id, _fake_app(brain)))

    row = _refresh_run(db, run_id)
    assert row.status == "completed"
    results = _results(db, run_id)
    assert len(results) == 1
    assert "timed out" in results[0].actual_answer


def test_run_evaluation_uses_prompt_version_override(client, db, monkeypatch):
    """A pinned prompt_version_id belonging to the project swaps the system prompt."""
    from restai.models.databasemodels import PromptVersionDatabase

    pv = PromptVersionDatabase(
        project_id=PROJECT_ID, version=1, system_prompt="pinned prompt",
    )
    db.db.add(pv)
    db.db.commit()

    run_id = _make_run(db, ["q"], ["answer_relevancy"])
    run = db.db.query(EvalRunDatabase).filter(EvalRunDatabase.id == run_id).first()
    run.prompt_version_id = pv.id
    db.db.commit()

    seen = {}

    async def fake_answer(project, question, brain, user, db_):
        seen["system"] = project.props.system
        return "a", [], 1

    monkeypatch.setattr(eval_mod, "_get_project_answer", fake_answer)
    project = _fake_project()
    brain = _fake_brain(project=project)

    asyncio.run(run_evaluation(run_id, _fake_app(brain)))

    assert seen["system"] == "pinned prompt"
    assert _refresh_run(db, run_id).status == "completed"
