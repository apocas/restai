"""Unit tests for crons/routines.py — schedule gating, execution-log
rows, webhook emission on failure, and the one-broken-routine-must-not-
block-the-rest contract. chat_main / Brain / DB are mocked."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from restai.models.databasemodels import RoutineExecutionLogDatabase

import crons.routines as cr


def _routine(id=1, name="r", message="do it", schedule_minutes=60,
             last_run=None, project_id=5):
    return SimpleNamespace(
        id=id, name=name, message=message, schedule_minutes=schedule_minutes,
        last_run=last_run, project_id=project_id,
        last_result=None, updated_at=None,
    )


def _db(routines):
    db = MagicMock()
    db.get_all_enabled_routines.return_value = routines
    db.db.add = MagicMock()
    return db


def _project(pid=5, name="proj"):
    proj = MagicMock()
    proj.props.id = pid
    proj.props.name = name
    proj.props.creator = None
    return proj


def _run(routines, brain=None, fire=None, emit=None):
    db = _db(routines)
    brain = brain or MagicMock()
    with patch.object(cr, "ensure_settings_table"), \
         patch.object(cr, "Brain", return_value=brain), \
         patch.object(cr, "open_db_wrapper", return_value=db), \
         patch.object(cr, "_fire_routine", new=fire or AsyncMock(return_value={"answer": "done"})) as f, \
         patch("restai.comms.webhooks.emit_event_for_project_id", new=emit or MagicMock()) as e:
        cr.main()
    return db, brain, f, e


def test_no_routines_is_noop():
    db, brain, fire, _ = _run([])
    fire.assert_not_called()
    brain.find_project.assert_not_called()
    db.db.close.assert_called_once()


def test_recent_routine_not_fired():
    r = _routine(last_run=datetime.now(timezone.utc) - timedelta(minutes=5),
                 schedule_minutes=60)
    db, brain, fire, _ = _run([r])
    fire.assert_not_called()
    brain.find_project.assert_not_called()


def test_elapsed_routine_fires_and_updates_state():
    r = _routine(last_run=datetime.now(timezone.utc) - timedelta(minutes=90),
                 schedule_minutes=60)
    brain = MagicMock()
    brain.find_project.return_value = _project()
    db, brain, fire, _ = _run([r], brain=brain)
    fire.assert_called_once()
    assert r.last_result == "done"
    assert r.last_run > datetime.now(timezone.utc) - timedelta(minutes=1)
    # ok execution-log row written
    logged = [a.args[0] for a in db.db.add.call_args_list
              if isinstance(a.args[0], RoutineExecutionLogDatabase)]
    assert len(logged) == 1
    assert logged[0].status == "ok"
    assert logged[0].result == "done"
    assert logged[0].is_manual is False


def test_never_run_routine_fires():
    r = _routine(last_run=None)
    brain = MagicMock()
    brain.find_project.return_value = _project()
    _, _, fire, _ = _run([r], brain=brain)
    fire.assert_called_once()


def test_naive_last_run_treated_as_utc():
    # Old rows stored naive; must not crash and must still gate correctly.
    r = _routine(last_run=datetime.utcnow() - timedelta(minutes=5),
                 schedule_minutes=60)
    _, brain, fire, _ = _run([r])
    fire.assert_not_called()


def test_missing_project_skipped():
    r = _routine()
    brain = MagicMock()
    brain.find_project.return_value = None
    _, _, fire, _ = _run([r], brain=brain)
    fire.assert_not_called()


def test_failed_routine_records_error_and_emits_webhook():
    r = _routine(name="broken")
    brain = MagicMock()
    brain.find_project.return_value = _project(pid=5)
    fire = AsyncMock(side_effect=RuntimeError("llm exploded"))
    emit = MagicMock()
    db, _, _, emit = _run([r], brain=brain, fire=fire, emit=emit)

    assert r.last_result.startswith("ERROR:")
    assert "llm exploded" in r.last_result
    logged = [a.args[0] for a in db.db.add.call_args_list
              if isinstance(a.args[0], RoutineExecutionLogDatabase)]
    assert len(logged) == 1
    assert logged[0].status == "error"
    assert "llm exploded" in logged[0].result

    emit.assert_called_once()
    args = emit.call_args.args
    assert args[0] == 5
    assert args[1] == "routine_failed"
    assert args[2]["routine_name"] == "broken"


def test_one_broken_routine_does_not_block_the_rest():
    r1 = _routine(id=1, name="broken")
    r2 = _routine(id=2, name="healthy")
    brain = MagicMock()
    brain.find_project.return_value = _project()
    fire = AsyncMock(side_effect=[RuntimeError("boom"), {"answer": "yay"}])
    db, _, fire, _ = _run([r1, r2], brain=brain, fire=fire)
    assert fire.call_count == 2
    assert r1.last_result.startswith("ERROR:")
    assert r2.last_result == "yay"


def test_webhook_failure_swallowed():
    r = _routine()
    brain = MagicMock()
    brain.find_project.return_value = _project()
    fire = AsyncMock(side_effect=RuntimeError("boom"))
    emit = MagicMock(side_effect=RuntimeError("webhook down"))
    _run([r], brain=brain, fire=fire, emit=emit)  # must not raise
    emit.assert_called_once()


def test_execution_log_write_failure_swallowed():
    r = _routine()
    brain = MagicMock()
    brain.find_project.return_value = _project()
    db = _db([r])
    db.db.add.side_effect = RuntimeError("db gone")
    with patch.object(cr, "ensure_settings_table"), \
         patch.object(cr, "Brain", return_value=brain), \
         patch.object(cr, "open_db_wrapper", return_value=db), \
         patch.object(cr, "_fire_routine", new=AsyncMock(return_value={"answer": "ok"})):
        cr.main()  # must not raise
    assert r.last_result == "ok"


# ─── _fire_routine ──────────────────────────────────────────────────────

def test_fire_routine_no_user_returns_none():
    project = _project()
    project.props.creator = 7
    db = MagicMock()
    db.get_user_by_id.return_value = None
    db.get_user_by_username.return_value = None
    result = asyncio.run(cr._fire_routine(MagicMock(), db, _routine(), project))
    assert result is None


def test_fire_routine_runs_chat_and_background_tasks():
    project = _project()
    project.props.creator = 7
    db = MagicMock()
    db.get_user_by_id.return_value = SimpleNamespace(id=7, username="creator")

    ran = []

    async def fake_chat_main(request, brain, proj, q, user, db_, background_tasks):
        background_tasks.add_task(lambda: ran.append("sync"))

        async def _async_task():
            ran.append("async")

        background_tasks.add_task(_async_task)
        background_tasks.add_task(MagicMock(side_effect=RuntimeError("task boom")))
        assert q.question == "do it"
        assert user.username == "creator"
        return {"answer": "A"}

    with patch("restai.helper.chat_main", new=fake_chat_main):
        result = asyncio.run(cr._fire_routine(MagicMock(), db, _routine(), project))

    assert result == {"answer": "A"}
    # Both task kinds executed; the raising one was swallowed.
    assert set(ran) == {"sync", "async"}


def test_fire_routine_falls_back_to_admin():
    project = _project()
    project.props.creator = None
    db = MagicMock()
    db.get_user_by_username.return_value = SimpleNamespace(id=1, username="admin")
    with patch("restai.helper.chat_main", new=AsyncMock(return_value={"answer": "A"})) as cm:
        result = asyncio.run(cr._fire_routine(MagicMock(), db, _routine(), project))
    assert result == {"answer": "A"}
    db.get_user_by_id.assert_not_called()
    assert cm.call_args.args[4].username == "admin"
