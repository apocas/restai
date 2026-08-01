"""Unit tests for crons/bulk_ingest.py — queue claiming, error paths
(missing staged file, missing/non-RAG project), classic-method success
path, and tempfile cleanup. Loaders/vectordb/Brain are mocked."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import crons.bulk_ingest as cbi


def _job(id=7, project_id=3, file_path="/nonexistent/file.txt",
         filename="report.txt", method="auto", splitter=None, chunks=None):
    return SimpleNamespace(
        id=id, project_id=project_id, file_path=file_path, filename=filename,
        method=method, splitter=splitter, chunks=chunks,
        status="queued", started_at=None, completed_at=None,
        error_message=None, documents_count=None, chunks_count=None,
    )


def _claim_db(job):
    """DB session that returns `job` from the claim query."""
    db = MagicMock()
    db.db.query.return_value.filter.return_value.order_by.return_value.first.return_value = job
    return db


def _finalize_db(job_row):
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = job_row
    return db


def _fresh_row():
    return SimpleNamespace(status=None, completed_at=None, documents_count=None,
                           chunks_count=None, error_message=None)


def _run_main(job, brain, extra_patches=()):
    """One job in the queue, then empty. Returns the finalize row."""
    final_row = _fresh_row()
    sessions = [_claim_db(job), _finalize_db(final_row), _claim_db(None)]
    with ExitStack() as stack:
        stack.enter_context(patch("restai.settings.ensure_settings_table"))
        stack.enter_context(patch("restai.database.open_db_wrapper", side_effect=sessions))
        stack.enter_context(patch("restai.brain.Brain", return_value=brain))
        for p in extra_patches:
            stack.enter_context(p)
        cbi.main()
    return final_row


def test_empty_queue_is_noop():
    brain = MagicMock()
    db = _claim_db(None)
    with patch("restai.settings.ensure_settings_table"), \
         patch("restai.database.open_db_wrapper", return_value=db), \
         patch("restai.brain.Brain", return_value=brain):
        cbi.main()
    brain.find_project.assert_not_called()


def test_missing_staged_file_errors_job():
    job = _job(file_path="/definitely/not/there.txt")
    brain = MagicMock()
    row = _run_main(job, brain)
    # Claimed → processing
    assert job.status == "processing"
    assert job.started_at is not None
    # Finalized → error with reason
    assert row.status == "error"
    assert "staged file missing" in row.error_message
    assert row.completed_at is not None
    # Never got as far as resolving the project.
    brain.find_project.assert_not_called()


def test_project_not_found_errors_job(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("content")
    job = _job(file_path=str(staged))
    brain = MagicMock()
    brain.find_project.return_value = None
    row = _run_main(job, brain)
    assert row.status == "error"
    assert "not found" in row.error_message
    # Staged file removed even on failure.
    assert not staged.exists()


def test_non_rag_project_rejected(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("content")
    job = _job(file_path=str(staged))
    project = MagicMock()
    project.props.type = "agent"
    brain = MagicMock()
    brain.find_project.return_value = project
    row = _run_main(job, brain)
    assert row.status == "error"
    assert "not RAG" in row.error_message
    assert not staged.exists()


def test_classic_method_success(tmp_path):
    staged = tmp_path / "report.txt"
    staged.write_text("hello world")
    job = _job(file_path=str(staged), filename="münchen report.txt", method="classic")

    project = MagicMock()
    project.props.type = "rag"
    brain = MagicMock()
    brain.find_project.return_value = project

    doc1 = SimpleNamespace(metadata={"filename": "junk"})
    doc2 = SimpleNamespace(metadata={})
    loader = MagicMock()
    loader.load_data.return_value = [doc1, doc2]

    row = _run_main(job, brain, extra_patches=(
        patch("restai.vectordb.tools.find_file_loader", return_value=loader),
        patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d),
        patch("restai.vectordb.tools.index_documents_classic", return_value=4),
    ))

    assert row.status == "done"
    assert row.documents_count == 2
    assert row.chunks_count == 4
    assert row.error_message is None
    project.vector.save.assert_called_once()
    # Source name is unidecoded, filename metadata key stripped.
    assert doc1.metadata == {"source": "munchen report.txt"}
    assert doc2.metadata == {"source": "munchen report.txt"}
    assert not staged.exists()


def test_no_extractable_content_errors_job(tmp_path):
    staged = tmp_path / "empty.txt"
    staged.write_text("")
    job = _job(file_path=str(staged), method="classic", filename="empty.txt")

    project = MagicMock()
    project.props.type = "rag"
    brain = MagicMock()
    brain.find_project.return_value = project

    loader = MagicMock()
    loader.load_data.return_value = []

    row = _run_main(job, brain, extra_patches=(
        patch("restai.vectordb.tools.find_file_loader", return_value=loader),
    ))
    assert row.status == "error"
    assert "No content" in row.error_message
    assert not staged.exists()


def test_drains_multiple_jobs():
    """Two queued jobs both get claimed and finalized in one run."""
    job1 = _job(id=1, file_path="/gone1.txt")
    job2 = _job(id=2, file_path="/gone2.txt")
    row1 = _fresh_row()
    row2 = _fresh_row()
    sessions = [
        _claim_db(job1), _finalize_db(row1),
        _claim_db(job2), _finalize_db(row2),
        _claim_db(None),
    ]
    brain = MagicMock()
    with patch("restai.settings.ensure_settings_table"), \
         patch("restai.database.open_db_wrapper", side_effect=sessions), \
         patch("restai.brain.Brain", return_value=brain):
        cbi.main()
    assert row1.status == "error"
    assert row2.status == "error"
