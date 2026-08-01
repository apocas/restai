"""Unit tests for the cheap, LLM-free parts of restai/projects/rag.py:
connection-string validation, the vectorstore-unavailable fast path, and
EntityBoostPostprocessor scoring."""
import asyncio
import types

import pytest
from fastapi import HTTPException

from restai.projects.rag import (
    RAG,
    EntityBoostPostprocessor,
    _validate_connection_string,
)


# ─── _validate_connection_string ────────────────────────────────────────

@pytest.mark.parametrize("conn", [
    "postgresql://u:p@host/db",
    "postgresql+psycopg2://u:p@host/db",
    "mysql://u:p@host/db",
    "mysql+pymysql://u:p@host/db",
])
def test_connection_string_allowed(conn):
    _validate_connection_string(conn)  # must not raise


@pytest.mark.parametrize("conn", [
    "sqlite:///anything.db",           # deliberately banned (file-read primitive)
    "sqlite:////etc/passwd",
    "oracle://u:p@host/db",
    "file:///etc/passwd",
    "not-a-url",
])
def test_connection_string_rejected(conn):
    with pytest.raises(HTTPException) as exc:
        _validate_connection_string(conn)
    assert exc.value.status_code == 400


# ─── vectorstore-unavailable fast path ─────────────────────────────────

def test_rag_chat_without_vector_or_connection_yields_notice():
    from restai.models.models import ChatModel

    options = types.SimpleNamespace(connection=None)
    props = types.SimpleNamespace(name="ragproj", options=options)
    project = types.SimpleNamespace(vector=None, props=props)
    rag = RAG(types.SimpleNamespace())

    async def _collect():
        out = []
        async for line in rag.chat(project, ChatModel(question="hi"), None, None):
            out.append(line)
        return out

    lines = asyncio.run(_collect())
    assert len(lines) == 1
    out = lines[0]
    assert "Knowledge base unavailable" in out["answer"]
    assert out["question"] == "hi"
    assert out["sources"] == []
    assert out["tokens"] == {"input": 0, "output": 0}
    assert out["project"] == "ragproj"


# ─── EntityBoostPostprocessor ───────────────────────────────────────────

def _node(source, score):
    return types.SimpleNamespace(
        node=types.SimpleNamespace(metadata={"source": source}),
        score=score,
    )


class _BoomDB:
    """Any attribute access explodes — exercises the swallow-everything path."""
    @property
    def db(self):
        raise RuntimeError("db unavailable")


def test_entity_boost_db_failure_passthrough():
    pp = EntityBoostPostprocessor(brain=None, db=_BoomDB(), project_id=1, query="q")
    nodes = [_node("a", 0.5), _node("b", 0.9)]
    out = pp.postprocess_nodes(list(nodes))
    assert pp._matched_sources == set()
    # No boost applied; scores unchanged.
    assert sorted(n.score for n in out) == [0.5, 0.9]


def test_entity_boost_applies_factor_and_resorts():
    pp = EntityBoostPostprocessor(brain=None, db=None, project_id=1, query="q",
                                  boost_factor=2.0)
    pp._matched_sources = {"matched.pdf"}  # bypass DB lookup
    nodes = [
        _node("other.pdf", 0.8),
        _node("matched.pdf", 0.5),
    ]
    out = pp.postprocess_nodes(nodes)
    # matched 0.5*2.0 = 1.0 outranks 0.8 after resort.
    assert out[0].node.metadata["source"] == "matched.pdf"
    assert out[0].score == 1.0
    assert out[1].score == 0.8


def test_entity_boost_none_score_left_alone():
    pp = EntityBoostPostprocessor(brain=None, db=None, project_id=1, query="q")
    pp._matched_sources = {"m"}
    nodes = [_node("m", None), _node("x", 0.3)]
    out = pp.postprocess_nodes(nodes)
    scores = {n.node.metadata["source"]: n.score for n in out}
    assert scores["m"] is None
    assert scores["x"] == 0.3
    # Sort key treats None as 0 → x first.
    assert out[0].node.metadata["source"] == "x"


def test_entity_boost_empty_match_returns_nodes_unsorted():
    pp = EntityBoostPostprocessor(brain=None, db=None, project_id=1, query="q")
    pp._matched_sources = set()
    nodes = [_node("a", 0.1), _node("b", 0.9)]
    out = pp.postprocess_nodes(nodes)
    assert out is nodes  # untouched passthrough
