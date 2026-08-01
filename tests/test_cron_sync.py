"""Unit tests for crons/sync.py — per-source sync_interval/last_sync
gating, up-front stamping, webhook emission on success/failure, and the
one-broken-source-must-not-block-the-rest contract."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import crons.sync as csync


def _proj_row(id=1, name="proj", **opts):
    return SimpleNamespace(id=id, name=name, options=json.dumps(opts) if opts else None)


def _db(rows):
    db = MagicMock()
    db.db.query.return_value.all.return_value = rows
    # _update_last_sync goes through the same query mock.
    db.db.query.return_value.filter.return_value.first.return_value = rows[0] if rows else None
    return db


def _rag_project():
    project = MagicMock()
    project.props.type = "rag"
    return project


def _run_main(rows, brain=None, sync_source=None, emit=None):
    db = _db(rows)
    brain = brain or MagicMock()
    with patch.object(csync, "ensure_settings_table"), \
         patch.object(csync, "Brain", return_value=brain), \
         patch.object(csync, "open_db_wrapper", return_value=db), \
         patch("restai.integrations.sync._sync_source", new=sync_source or MagicMock()) as ss, \
         patch("restai.comms.webhooks.emit_event_for_project_id", new=emit or MagicMock()) as em:
        csync.main()
    return db, ss, em


def test_projects_without_sync_config_skipped():
    rows = [
        _proj_row(id=1),  # no options
        _proj_row(id=2, sync_enabled=True),  # enabled but no sources
        _proj_row(id=3, sync_enabled=False,
                  sync_sources=[{"type": "url", "name": "a", "url": "http://x.example/"}]),
    ]
    brain = MagicMock()
    _, ss, _ = _run_main(rows, brain=brain)
    ss.assert_not_called()
    brain.find_project.assert_not_called()


def test_recent_source_not_resynced():
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    rows = [_proj_row(
        sync_enabled=True,
        sync_sources=[{
            "type": "url", "name": "a", "url": "http://x.example/",
            "sync_interval": 60, "last_sync": fresh,
        }],
    )]
    brain = MagicMock()
    _, ss, _ = _run_main(rows, brain=brain)
    ss.assert_not_called()
    brain.find_project.assert_not_called()


def test_stale_source_synced_and_stamped():
    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{
            "type": "url", "name": "a", "url": "http://x.example/",
            "sync_interval": 60, "last_sync": stale,
        }],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    emit = MagicMock()
    _, ss, emit = _run_main([row], brain=brain, emit=emit)

    ss.assert_called_once()
    src = ss.call_args.args[1]
    assert src.name == "a"
    assert src.url == "http://x.example/"
    # last_sync re-stamped (up-front claim + post-success).
    new_last = json.loads(row.options)["sync_sources"][0]["last_sync"]
    assert new_last != stale
    assert datetime.fromisoformat(new_last) > datetime.now(timezone.utc) - timedelta(minutes=1)
    # Success webhook.
    emit.assert_called_once()
    assert emit.call_args.args[1] == "sync_completed"
    assert emit.call_args.args[2]["status"] == "ok"


def test_never_synced_source_fires():
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{"type": "url", "name": "a", "url": "http://x.example/"}],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    _, ss, _ = _run_main([row], brain=brain)
    ss.assert_called_once()


def test_garbage_last_sync_does_not_crash_and_fires():
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{"type": "url", "name": "a", "url": "http://x.example/",
                       "last_sync": "not-a-date"}],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    _, ss, _ = _run_main([row], brain=brain)
    ss.assert_called_once()


def test_non_rag_project_never_synced():
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{"type": "url", "name": "a", "url": "http://x.example/"}],
    )
    project = MagicMock()
    project.props.type = "agent"
    brain = MagicMock()
    brain.find_project.return_value = project
    _, ss, _ = _run_main([row], brain=brain)
    ss.assert_not_called()


def test_failed_source_emits_error_webhook_and_next_source_still_runs():
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[
            {"type": "url", "name": "broken", "url": "http://x.example/"},
            {"type": "url", "name": "healthy", "url": "http://y.example/"},
        ],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    ss = MagicMock(side_effect=[RuntimeError("selenium died"), None])
    emit = MagicMock()
    _, ss, emit = _run_main([row], brain=brain, sync_source=ss, emit=emit)

    assert ss.call_count == 2
    statuses = [c.args[2]["status"] for c in emit.call_args_list]
    assert statuses == ["error", "ok"]
    assert emit.call_args_list[0].args[2]["error"] == "selenium died"


def test_webhook_failure_swallowed():
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{"type": "url", "name": "a", "url": "http://x.example/"}],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    emit = MagicMock(side_effect=RuntimeError("webhook target down"))
    _, ss, _ = _run_main([row], brain=brain, emit=emit)  # must not raise
    ss.assert_called_once()


def test_encrypted_source_fields_decrypted_before_sync():
    from restai.utils.crypto import encrypt_field
    row = _proj_row(
        sync_enabled=True,
        sync_sources=[{
            "type": "s3", "name": "bucket", "s3_bucket": "b",
            "s3_secret_key": encrypt_field("plain-secret"),
        }],
    )
    brain = MagicMock()
    brain.find_project.return_value = _rag_project()
    _, ss, _ = _run_main([row], brain=brain)
    src = ss.call_args.args[1]
    assert src.s3_secret_key == "plain-secret"


def test_update_last_sync_out_of_range_index_is_noop():
    row = _proj_row(sync_enabled=True, sync_sources=[{"type": "url", "name": "a"}])
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = row
    csync._update_last_sync(db, 1, 5)
    assert "last_sync" not in json.loads(row.options)["sync_sources"][0]
    db.db.commit.assert_not_called()


def test_update_last_sync_missing_project_is_noop():
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = None
    csync._update_last_sync(db, 1, 0)
    db.db.commit.assert_not_called()
