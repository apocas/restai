"""Unit tests for restai/llms/tools/search_knowledge.py — the nested-RAG
builtin. Everything (brain, db, RAG loop, permission check) is faked; asserts
on the returned strings and the log_inference accounting call."""
import asyncio
import json
import types

import pytest

import restai.auth as auth_mod
import restai.database as database_mod
import restai.tools as tools_mod
from restai.llms.tools.search_knowledge import search_knowledge
from restai.projects import rag as rag_mod


def run(coro):
    return asyncio.run(coro)


class FakeDB:
    def __init__(self, agent=None, targets=None):
        self.agent = agent
        self.targets = targets or {}
        self.closed = False
        self.db = types.SimpleNamespace(close=lambda: setattr(self, "closed", True))

    def get_project_by_id(self, pid):
        return self.agent

    def get_project_by_name(self, name):
        return self.targets.get(name)


def _agent(target_name="kb", team_id=5, options=None):
    opts = {"search_knowledge_project": target_name} if options is None else options
    return types.SimpleNamespace(id=1, team_id=team_id, options=json.dumps(opts))


def _target(name="kb", ptype="rag", team_id=5, pid=42):
    return types.SimpleNamespace(id=pid, name=name, type=ptype, team_id=team_id)


class FakeRAG:
    result = None

    def __init__(self, brain):
        pass

    async def chat(self, proj, q, user, db):
        if FakeRAG.result is not None:
            yield FakeRAG.result


@pytest.fixture()
def wired(monkeypatch):
    """Wire the happy path; individual tests then break one link each."""
    db = FakeDB(agent=_agent(), targets={"kb": _target()})
    loaded_project = types.SimpleNamespace(props=types.SimpleNamespace(id=42))
    brain = types.SimpleNamespace(find_project=lambda pid, _db: loaded_project)
    user = types.SimpleNamespace(id=9)
    logged = []

    monkeypatch.setattr(database_mod, "open_db_wrapper", lambda: db)
    monkeypatch.setattr(auth_mod, "user_can_access_project", lambda u, pid, d: True)
    monkeypatch.setattr(rag_mod, "RAG", FakeRAG)
    monkeypatch.setattr(
        tools_mod, "log_inference",
        lambda project, u, output, d: logged.append((project, output)),
    )
    FakeRAG.result = None
    return types.SimpleNamespace(
        db=db, brain=brain, user=user, logged=logged, project=loaded_project)


def _call(wired, query="refund policy"):
    return run(search_knowledge(
        query, _brain=wired.brain, _project_id=1, _user=wired.user))


# ─── plumbing / resolution errors ───────────────────────────────────────

def test_requires_restai_agent_loop_kwargs():
    out = run(search_knowledge("q"))
    assert out.startswith("ERROR: search_knowledge requires the RESTai agent loop")


def test_agent_project_not_found(wired):
    wired.db.agent = None
    assert _call(wired) == "ERROR: project 1 not found."
    assert wired.db.closed is True  # session closed on every path


def test_no_knowledge_project_configured(wired):
    wired.db.agent = _agent(options={})
    out = _call(wired)
    assert out.startswith("ERROR: no knowledge-search project configured")


def test_unparseable_options_treated_as_unconfigured(wired):
    wired.db.agent = types.SimpleNamespace(id=1, team_id=5, options="{broken")
    out = _call(wired)
    assert out.startswith("ERROR: no knowledge-search project configured")


def test_target_missing(wired):
    wired.db.targets = {}
    assert _call(wired) == "ERROR: configured knowledge project 'kb' no longer exists."


def test_target_not_rag(wired):
    wired.db.targets["kb"] = _target(ptype="agent")
    assert _call(wired) == "ERROR: knowledge project 'kb' is not a RAG project."


def test_team_boundary_enforced(wired):
    wired.db.targets["kb"] = _target(team_id=99)
    assert _call(wired) == "ERROR: knowledge project 'kb' is not in this agent's team."

    wired.db.targets["kb"] = _target(team_id=None)
    assert _call(wired) == "ERROR: knowledge project 'kb' is not in this agent's team."


def test_permission_boundary_enforced(wired, monkeypatch):
    monkeypatch.setattr(auth_mod, "user_can_access_project", lambda u, pid, d: False)
    out = _call(wired)
    assert out == "ERROR: you do not have access to the knowledge project 'kb'."


def test_find_project_failure(wired):
    wired.brain.find_project = lambda pid, db: None
    assert _call(wired) == "ERROR: failed to load knowledge project 'kb'."


# ─── results / accounting ───────────────────────────────────────────────

def test_success_formats_answer_sources_and_logs(wired):
    FakeRAG.result = {
        "answer": "  You get a refund.  ",
        "sources": [
            {"score": 0.87, "text": "refund\npolicy text", "source": "faq.md"},
            {"text": "x" * 600, "id": "chunk-2"},
            "a bare string source",
        ],
        "tokens": {"input": 10, "output": 5},
    }
    out = _call(wired)
    assert out.startswith("Knowledge base 'kb':")
    assert "ANSWER:\nYou get a refund." in out
    assert "[1] (0.87) refund policy text — faq.md" in out
    assert "…" in out  # long chunk truncated at 500 chars
    assert "— chunk-2" in out
    assert "[3] a bare string source" in out

    # Nested inference accounted against the target knowledge project.
    assert len(wired.logged) == 1
    project, output = wired.logged[0]
    assert project is wired.project
    assert output["question"] == "refund policy"
    assert output["tokens"] == {"input": 10, "output": 5}


def test_sources_capped_at_eight(wired):
    FakeRAG.result = {
        "answer": "a",
        "sources": [{"text": f"s{i}", "source": f"f{i}"} for i in range(12)],
    }
    out = _call(wired)
    assert "[8]" in out
    assert "[9]" not in out


def test_no_result_from_rag(wired):
    FakeRAG.result = None
    out = _call(wired)
    assert out == "No results found in 'kb' for: refund policy"
    assert wired.logged == []


def test_empty_answer_and_sources(wired):
    FakeRAG.result = {"answer": "   ", "sources": []}
    out = _call(wired)
    assert out == "No results found in 'kb' for: refund policy"
    # Even an empty result is still accounted.
    assert len(wired.logged) == 1


def test_log_inference_failure_swallowed(wired, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("accounting down")
    monkeypatch.setattr(tools_mod, "log_inference", boom)
    FakeRAG.result = {"answer": "fine", "sources": []}
    out = _call(wired)
    assert "ANSWER:\nfine" in out  # user still gets the answer


def test_unexpected_exception_becomes_error_string(wired):
    def explode(pid):
        raise RuntimeError("kaboom")
    wired.db.get_project_by_id = explode
    out = _call(wired)
    assert out == "ERROR: knowledge search failed: kaboom"
    assert wired.db.closed is True
