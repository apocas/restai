"""Unit tests for crons/memory_index.py — project selection, embedding
resolution/swap handling, cursor advancement past failing rows, and the
per-project crash isolation in the tick loop."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import crons.memory_index as cmi


def _proj(id=1, name="p", embeddings="emb1", **opts):
    return SimpleNamespace(id=id, name=name, embeddings=embeddings,
                           options=json.dumps(opts) if opts else None)


def _row(id, question="q", answer="a", chat_id="c1", date=None):
    return SimpleNamespace(id=id, question=question, answer=answer,
                           chat_id=chat_id, date=date)


# ─── _embed_text ────────────────────────────────────────────────────────

def test_embed_text_success():
    emb = MagicMock()
    emb.embedding.get_text_embedding.return_value = (0.1, 0.2)
    assert cmi._embed_text(emb, "hello") == [0.1, 0.2]


def test_embed_text_empty_vector_is_none():
    emb = MagicMock()
    emb.embedding.get_text_embedding.return_value = []
    assert cmi._embed_text(emb, "hello") is None


def test_embed_text_failure_is_none():
    emb = MagicMock()
    emb.embedding.get_text_embedding.side_effect = RuntimeError("provider down")
    assert cmi._embed_text(emb, "hello") is None


# ─── _list_search_enabled_projects ──────────────────────────────────────

def test_list_search_enabled_projects_filters_options():
    rows = [
        _proj(id=1, memory_search_enabled=True),
        _proj(id=2, memory_search_enabled=False),
        _proj(id=3),  # no options at all
        SimpleNamespace(id=4, name="broken", embeddings="", options="{not json"),
        _proj(id=5, memory_search_enabled=True),
    ]
    db = MagicMock()
    db.db.query.return_value.filter.return_value.all.return_value = rows
    enabled = [p.id for p in cmi._list_search_enabled_projects(db)]
    assert enabled == [1, 5]


# ─── _process_project ───────────────────────────────────────────────────

def _db_with_rows(rows):
    db = MagicMock()
    db.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
    return db


def test_process_project_without_embedding_name_skips():
    brain = MagicMock()
    with patch.object(cmi, "open_db_wrapper") as odw:
        assert cmi._process_project(brain, _proj(embeddings="  ")) == (0, 0)
    odw.assert_not_called()


def test_process_project_unresolvable_embedding_skips():
    brain = MagicMock()
    brain.get_embedding.return_value = None
    db = _db_with_rows([])
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        assert cmi._process_project(brain, _proj()) == (0, 0)
    ms.set_indexed_embedding_model.assert_not_called()
    db.db.close.assert_called_once()


def test_process_project_embedding_swap_resets_collection():
    brain = MagicMock()
    brain.get_embedding.return_value = MagicMock()
    db = _db_with_rows([])
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        ms.get_indexed_embedding_model.return_value = "old-model"
        ms.get_last_indexed_id.return_value = 0
        cmi._process_project(brain, _proj(embeddings="new-model"))
    ms.reset_collection.assert_called_once_with(1)
    ms.set_indexed_embedding_model.assert_called_once_with(1, "new-model")


def test_process_project_same_embedding_no_reset():
    brain = MagicMock()
    brain.get_embedding.return_value = MagicMock()
    db = _db_with_rows([])
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        ms.get_indexed_embedding_model.return_value = "emb1"
        ms.get_last_indexed_id.return_value = 0
        cmi._process_project(brain, _proj(embeddings="emb1"))
    ms.reset_collection.assert_not_called()


def test_process_project_indexes_rows_and_advances_cursor():
    emb = MagicMock()
    emb.embedding.get_text_embedding.return_value = [0.5]
    brain = MagicMock()
    brain.get_embedding.return_value = emb

    rows = [
        _row(10, question="hi", answer="yo"),
        _row(11, question="", answer=""),  # empty — skipped, cursor still moves
        _row(12, question="q2", answer="a2"),
    ]
    db = _db_with_rows(rows)
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        ms.get_indexed_embedding_model.return_value = None
        ms.get_last_indexed_id.return_value = 9
        indexed, scanned = cmi._process_project(brain, _proj())

    assert (indexed, scanned) == (2, 3)
    assert ms.index_turn.call_count == 2
    first = ms.index_turn.call_args_list[0].kwargs
    assert first["project_id"] == 1
    assert first["output_id"] == 10
    assert first["question"] == "hi"
    assert first["embedding"] == [0.5]
    ms.set_last_indexed_id.assert_called_once_with(1, 12)


def test_process_project_embed_failures_skip_but_cursor_advances():
    emb = MagicMock()
    emb.embedding.get_text_embedding.side_effect = RuntimeError("no provider")
    brain = MagicMock()
    brain.get_embedding.return_value = emb
    rows = [_row(21), _row(22)]
    db = _db_with_rows(rows)
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        ms.get_indexed_embedding_model.return_value = None
        ms.get_last_indexed_id.return_value = 0
        indexed, scanned = cmi._process_project(brain, _proj())
    assert (indexed, scanned) == (0, 2)
    ms.index_turn.assert_not_called()
    # Cursor advanced anyway so failing rows are not rescanned forever.
    ms.set_last_indexed_id.assert_called_once_with(1, 22)


def test_process_project_index_turn_failure_isolated():
    emb = MagicMock()
    emb.embedding.get_text_embedding.return_value = [0.5]
    brain = MagicMock()
    brain.get_embedding.return_value = emb
    rows = [_row(31), _row(32)]
    db = _db_with_rows(rows)
    with patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "memory_search") as ms:
        ms.get_indexed_embedding_model.return_value = None
        ms.get_last_indexed_id.return_value = 0
        ms.index_turn.side_effect = [RuntimeError("chroma hiccup"), None]
        indexed, scanned = cmi._process_project(brain, _proj())
    assert (indexed, scanned) == (1, 2)
    ms.set_last_indexed_id.assert_called_once_with(1, 32)


# ─── _run (tick loop) ───────────────────────────────────────────────────

def _run_tick(projects, process=None):
    db = MagicMock()
    db.db.query.return_value.filter.return_value.all.return_value = projects
    with patch.object(cmi, "ensure_settings_table"), \
         patch.object(cmi, "Brain"), \
         patch.object(cmi, "open_db_wrapper", return_value=db), \
         patch.object(cmi, "_process_project", new=process or MagicMock(return_value=(1, 1))) as pp:
        cmi._run()
    return pp


def test_run_skips_projects_without_embedding():
    projects = [
        _proj(id=1, embeddings="", memory_search_enabled=True),
        _proj(id=2, embeddings="emb", memory_search_enabled=True),
    ]
    pp = _run_tick(projects)
    pp.assert_called_once()
    assert pp.call_args.args[1].id == 2


def test_run_project_crash_does_not_block_rest():
    projects = [
        _proj(id=1, memory_search_enabled=True),
        _proj(id=2, memory_search_enabled=True),
    ]
    process = MagicMock(side_effect=[RuntimeError("boom"), (3, 5)])
    pp = _run_tick(projects, process=process)
    assert pp.call_count == 2


def test_run_respects_max_projects_per_tick(monkeypatch):
    monkeypatch.setattr(cmi, "MAX_PROJECTS_PER_TICK", 1)
    projects = [
        _proj(id=1, memory_search_enabled=True),
        _proj(id=2, memory_search_enabled=True),
    ]
    pp = _run_tick(projects)
    pp.assert_called_once()
    assert pp.call_args.args[1].id == 1
