"""Re-embed phase machine — the data-safety behaviour, driven against fakes.

These are the tests that matter most in this feature: every case here is one
where getting it wrong destroys a knowledge base that cannot be rebuilt from
source, because ingest deletes its files.

No live vector backend, embedding provider or database is involved.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from restai import reembed


# ----------------------------------------------------------------- fakes

class FakeVector:
    """Minimal VectorBase stand-in over a list of `{id, text, metadata}`.

    `reported_count` is settable independently of the contents so a backend
    that disagrees with itself — the outage signature — can be reproduced.
    """

    def __init__(self, nodes=None, reported_count=None, fail_on_read=False):
        self.nodes = list(nodes or [])
        self._reported = reported_count
        self.fail_on_read = fail_on_read
        self.reset_calls = 0
        self.inserted = []
        self.index = SimpleNamespace(insert_nodes=self._insert_nodes)

    def _insert_nodes(self, nodes):
        self.inserted.extend(nodes)

    def info(self):
        return len(self.nodes) if self._reported is None else self._reported

    def list_all_nodes(self, limit=1000, offset=0):
        if self.fail_on_read:
            raise RuntimeError("vector store unreachable")
        return self.nodes[offset:offset + limit]

    def reset(self, brain):
        self.reset_calls += 1
        self.nodes = []


class FakeJob:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.project_id = kw.get("project_id", 7)
        self.user_id = None
        self.from_embeddings = kw.get("from_embeddings", "old-model")
        self.to_embeddings = kw.get("to_embeddings", "new-model")
        self.status = kw.get("status", "processing")
        self.phase = kw.get("phase")
        self.error_message = None
        self.snapshot_path = kw.get("snapshot_path")
        self.chunks_total = kw.get("chunks_total", 0)
        self.chunks_done = kw.get("chunks_done", 0)
        self.tokens_embedded = 0
        self.cost = 0.0
        self.completed_at = None


class FakeSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeDB:
    def __init__(self):
        self.db = FakeSession()
        self.stamped = None

    def get_project_by_id(self, pid):
        return SimpleNamespace(embeddings_indexed=None)


class FakeBrain:
    def __init__(self, project, embedding_props=None):
        self._project = project
        self._embedding = SimpleNamespace(
            props=embedding_props or SimpleNamespace(name="new-model", input_cost=0.0),
        )

    def find_project(self, pid, db):
        return self._project

    def get_embedding(self, name, db):
        return self._embedding


def _project(vector):
    return SimpleNamespace(
        vector=vector,
        props=SimpleNamespace(
            id=7, type="rag", team_id=None, embeddings="old-model",
            vectorstore="chroma",
        ),
    )


def _nodes(n, **extra_meta):
    return [
        {"id": f"n{i}", "text": f"chunk text {i}",
         "metadata": {"source": "doc.pdf", "keywords": "alpha, beta", **extra_meta}}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    """Point snapshots at tmp_path; leave real llama-index `TextNode` alone.

    Stubbing `llama_index.core.schema` in `sys.modules` was tempting but would
    shadow a real dependency for anything else importing it in the same
    process, and building actual `TextNode`s is the more honest test anyway.
    """
    monkeypatch.setattr(reembed, "snapshot_dir", lambda: str(tmp_path))
    monkeypatch.setattr(reembed, "stamp_indexed_embedding", lambda project, db: None)
    yield


def _run(job, vector, monkeypatch, embedding_props=None):
    project = _project(vector)
    brain = FakeBrain(project, embedding_props)
    db = FakeDB()

    monkeypatch.setattr(
        "restai.limits.accounting.log_embedding_usage",
        lambda db, project, props, tokens, label, user_id=None: tokens * 0.001,
    )
    monkeypatch.setattr("restai.tools.tokens_from_string", lambda s: max(1, len(s) // 4))
    monkeypatch.setattr(
        "restai.vectordb.tools.find_vector_db",
        lambda p: (lambda brain_, project_, embedding_: vector),
    )
    reembed.run_job(job, brain, db)
    return project


# ------------------------------------------------------------ happy path

def test_full_migration_preserves_every_chunk_and_its_metadata(monkeypatch, tmp_path):
    """Re-embedding must be lossless. `list_all_chunks` projects out everything
    but `source`, which is why the engine reads through `list_all_nodes`."""
    vector = FakeVector(_nodes(5))
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    _run(job, vector, monkeypatch)

    assert job.chunks_done == 5
    assert job.chunks_total == 5
    assert vector.reset_calls == 1
    assert len(vector.inserted) == 5
    assert [n.text for n in vector.inserted] == [f"chunk text {i}" for i in range(5)]
    # `keywords` survives — dropping it would silently degrade retrieval.
    assert all(n.metadata["keywords"] == "alpha, beta" for n in vector.inserted)
    assert all(n.metadata["source"] == "doc.pdf" for n in vector.inserted)


def test_llama_index_internal_metadata_is_not_carried_over(monkeypatch, tmp_path):
    """`_node_content` and friends describe the node being replaced; keeping
    them would attach stale bookkeeping to the new one."""
    vector = FakeVector(_nodes(2, _node_content="{...}", ref_doc_id="abc", doc_id="abc"))
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    _run(job, vector, monkeypatch)

    for node in vector.inserted:
        assert "_node_content" not in node.metadata
        assert "ref_doc_id" not in node.metadata
        assert "doc_id" not in node.metadata
        assert node.metadata["source"] == "doc.pdf"


def test_cost_is_accumulated_on_the_job(monkeypatch, tmp_path):
    vector = FakeVector(_nodes(3))
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    _run(job, vector, monkeypatch)

    assert job.tokens_embedded > 0
    assert job.cost > 0


# ------------------------------------------------- the safety-critical cases

def test_count_mismatch_aborts_without_resetting(monkeypatch, tmp_path):
    """THE test. Weaviate and Pinecone both return partial results on error,
    so a short read is indistinguishable from a small store — and the next
    step destroys the store."""
    vector = FakeVector(_nodes(3), reported_count=100)
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    with pytest.raises(reembed.ReembedError) as exc:
        _run(job, vector, monkeypatch)

    assert "3" in str(exc.value) and "100" in str(exc.value)
    assert vector.reset_calls == 0
    assert len(vector.nodes) == 3  # untouched


def test_empty_read_aborts_without_resetting(monkeypatch, tmp_path):
    """`info()` returns 0 from the except branch on two backends, so an
    apparent zero must never be treated as 'nothing to lose'."""
    vector = FakeVector([], reported_count=0)
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    with pytest.raises(reembed.ReembedError):
        _run(job, vector, monkeypatch)

    assert vector.reset_calls == 0


def test_read_failure_propagates_and_does_not_reset(monkeypatch, tmp_path):
    vector = FakeVector(_nodes(4), fail_on_read=True)
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    with pytest.raises(Exception):
        _run(job, vector, monkeypatch)

    assert vector.reset_calls == 0
    assert len(vector.nodes) == 4


def test_missing_vector_store_aborts(monkeypatch, tmp_path):
    project = _project(None)
    brain = FakeBrain(project)
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))

    with pytest.raises(reembed.ReembedError) as exc:
        reembed.run_job(job, brain, FakeDB())

    assert "unavailable" in str(exc.value).lower()


def test_snapshot_is_never_overwritten(tmp_path):
    """A resumed job must reuse its snapshot. Overwriting one is
    unrecoverable, so the writer refuses outright rather than trusting
    callers to gate correctly."""
    path = tmp_path / "job1.jsonl"
    path.write_text('{"id":"n0","text":"original","metadata":{}}\n')

    with pytest.raises(reembed.ReembedError) as exc:
        reembed._write_snapshot(FakeVector(_nodes(2)), str(path))

    assert "overwrite" in str(exc.value).lower()
    assert "original" in path.read_text()


# --------------------------------------------------------------- resume

def test_resume_from_rebuilding_skips_snapshot_and_reset(monkeypatch, tmp_path):
    """A job interrupted mid-rebuild must continue from `chunks_done`. Redoing
    the reset would wipe the chunks already written."""
    path = tmp_path / "job1.jsonl"
    path.write_text("".join(
        json.dumps({"id": f"n{i}", "text": f"chunk text {i}", "metadata": {"source": "d.pdf"}}) + "\n"
        for i in range(5)
    ))
    vector = FakeVector([])  # store already reset by the previous run
    job = FakeJob(
        phase=reembed.PHASE_REBUILD, snapshot_path=str(path),
        chunks_total=5, chunks_done=2,
    )

    _run(job, vector, monkeypatch)

    assert vector.reset_calls == 0
    # Only the remaining three are re-embedded — no double billing.
    assert [n.text for n in vector.inserted] == ["chunk text 2", "chunk text 3", "chunk text 4"]
    assert job.chunks_done == 5


def test_resume_from_resetting_does_not_resnapshot(monkeypatch, tmp_path):
    """`resetting` means the store may already be empty. Re-snapshotting there
    would capture the emptied store and destroy the real backup."""
    path = tmp_path / "job1.jsonl"
    path.write_text("".join(
        json.dumps({"id": f"n{i}", "text": f"chunk text {i}", "metadata": {}}) + "\n"
        for i in range(4)
    ))
    vector = FakeVector([])  # emptied by the reset that ran before the crash
    job = FakeJob(
        phase=reembed.PHASE_RESET, snapshot_path=str(path),
        chunks_total=4, chunks_done=0,
    )

    _run(job, vector, monkeypatch)

    # The snapshot survived and every chunk came back.
    assert path.exists()
    assert len(vector.inserted) == 4
    assert job.chunks_done == 4


def test_resume_without_snapshot_fails_loudly(monkeypatch, tmp_path):
    """Silently 'succeeding' here would leave an empty knowledge base looking
    migrated, which is worse than an error row."""
    vector = FakeVector([])
    job = FakeJob(
        phase=reembed.PHASE_REBUILD,
        snapshot_path=str(tmp_path / "gone.jsonl"),
        chunks_total=10, chunks_done=4,
    )

    with pytest.raises(reembed.ReembedError) as exc:
        _run(job, vector, monkeypatch)

    assert "snapshot" in str(exc.value).lower()


# ------------------------------------------------------------ finish_job

def test_snapshot_deleted_only_on_success(tmp_path):
    path = tmp_path / "job1.jsonl"
    path.write_text("{}\n")
    job = FakeJob(snapshot_path=str(path))
    db = FakeDB()

    reembed.finish_job(job, db, error="boom")
    assert job.status == "error"
    assert path.exists(), "the snapshot is the surviving copy — keep it on failure"

    job.status = "processing"
    reembed.finish_job(job, db, error=None)
    assert job.status == "done"
    assert not path.exists()


def test_finish_job_truncates_long_errors(tmp_path):
    job = FakeJob(snapshot_path=str(tmp_path / "job1.jsonl"))
    reembed.finish_job(job, FakeDB(), error="x" * 9000)
    assert len(job.error_message) <= 4000


# ------------------------------------------------------------- estimate

def test_estimate_samples_rather_than_scanning(monkeypatch):
    """The estimate is served synchronously to a dialog, so it must not read
    the whole store."""
    vector = FakeVector(_nodes(10_000))
    calls = []
    real = vector.list_all_nodes

    def counting(limit=1000, offset=0):
        calls.append(limit)
        return real(limit=limit, offset=offset)

    vector.list_all_nodes = counting
    monkeypatch.setattr("restai.tools.tokens_from_string", lambda s: 10)

    db = FakeDB()
    db.get_embedding_by_name = lambda n: SimpleNamespace(dimension=768)
    out = reembed.estimate_reembed(
        _project(vector), SimpleNamespace(dimension=768, input_cost=1.0), db,
    )

    assert out["chunks"] == 10_000
    assert calls == [reembed.ESTIMATE_SAMPLE]
    assert out["tokens"] == 100_000
    assert out["cost"] == pytest.approx(0.1)
    assert out["compatible"] is True


def test_estimate_reports_incompatible_pinecone_dimension_change(monkeypatch):
    vector = FakeVector(_nodes(5))
    monkeypatch.setattr("restai.tools.tokens_from_string", lambda s: 4)
    project = _project(vector)
    project.props.vectorstore = "pinecone"

    db = FakeDB()
    db.get_embedding_by_name = lambda n: SimpleNamespace(dimension=768)
    out = reembed.estimate_reembed(
        project, SimpleNamespace(dimension=1536, input_cost=0.0), db,
    )

    assert out["compatible"] is False
    assert out["dimension_change"] is True


# ------------------------------------------------------ orphan snapshots

def test_purge_removes_only_unreferenced_snapshots(monkeypatch, tmp_path):
    keep = tmp_path / "job1.jsonl"
    drop = tmp_path / "job2.jsonl"
    keep.write_text("{}\n")
    drop.write_text("{}\n")

    class _Q:
        def filter(self, *a, **kw):
            return [SimpleNamespace(snapshot_path=str(keep))]

    db = FakeDB()
    db.db.query = lambda *a, **kw: _Q()

    reembed.purge_orphan_snapshots(db)

    assert keep.exists()
    assert not drop.exists()


def test_purge_keeps_snapshots_of_failed_jobs(monkeypatch, tmp_path):
    """A job that failed after the reset holds the only surviving copy of that
    knowledge base. Purging it because the job is no longer 'open' would undo
    the whole point of keeping it on failure."""
    captured = {}

    class _Q:
        def filter(self, criterion, *a, **kw):
            captured["criterion"] = str(criterion)
            return []

    db = FakeDB()
    db.db.query = lambda *a, **kw: _Q()

    reembed.purge_orphan_snapshots(db)

    # Retention is keyed on "not finished", not on "still running".
    assert "status" in captured["criterion"]
    assert "!=" in captured["criterion"] or "IS NOT" in captured["criterion"].upper()
