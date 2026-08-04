"""Unit tests for crons/telegram.py — the cron-driven Telegram poller.

Everything network/DB/Brain-shaped is mocked; CronLogger writes (if the
table exists) go to the local sqlite test DB, which is fine.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import crons.telegram as ct


def _project(id=1, name="proj", **opts):
    return SimpleNamespace(id=id, name=name, options=json.dumps(opts))


def _db(projects):
    db = MagicMock()
    db.db.query.return_value.all.return_value = projects
    return db


def _run_main(projects, get_updates=None, **extra):
    """Run ct.main() with the standard patch stack. Returns dict of mocks."""
    mocks = {}
    db = _db(projects)
    with patch.object(ct, "ensure_settings_table"), \
         patch.object(ct, "Brain") as brain_cls, \
         patch.object(ct, "open_db_wrapper", return_value=db), \
         patch.object(ct, "get_updates", side_effect=get_updates or [([], None)]) as gu, \
         patch.object(ct, "delete_webhook", return_value=(True, None)) as dw, \
         patch.object(ct, "send_message") as sm, \
         patch.object(ct, "send_typing") as st, \
         patch.object(ct, "_process_message", new=extra.get("process", AsyncMock(return_value="answer"))) as pm:
        ct.main()
    mocks.update(dict(db=db, brain_cls=brain_cls, get_updates=gu,
                      delete_webhook=dw, send_message=sm, send_typing=st,
                      process=pm))
    return mocks


def test_project_without_token_skipped():
    m = _run_main([_project()])
    m["get_updates"].assert_not_called()
    m["db"].db.close.assert_called_once()


def test_chatid_shortcut_always_answered():
    updates = [{"update_id": 5, "message": {"text": "/chatid", "chat": {"id": 42}, "from": {"username": "u"}}}]
    m = _run_main(
        [_project(telegram_token="tok", telegram_allowed_chat_ids="999")],
        get_updates=[(updates, None), ([], None)],
    )
    m["send_message"].assert_called_once_with("tok", 42, "Chat ID: 42")
    m["process"].assert_not_called()
    # Ack call advances the offset past the processed update.
    ack = m["get_updates"].call_args_list[1]
    assert ack.kwargs.get("offset") == 6


def test_myid_alias_and_send_failure_swallowed():
    updates = [{"update_id": 1, "message": {"text": "/MyID", "chat": {"id": 7}, "from": {}}}]
    db = _db([_project(telegram_token="tok")])
    with patch.object(ct, "ensure_settings_table"), \
         patch.object(ct, "Brain"), \
         patch.object(ct, "open_db_wrapper", return_value=db), \
         patch.object(ct, "get_updates", side_effect=[(updates, None), ([], None)]), \
         patch.object(ct, "send_message", side_effect=RuntimeError("net")) as sm, \
         patch.object(ct, "send_typing"), \
         patch.object(ct, "_process_message", new=AsyncMock()) as pm:
        ct.main()  # must not raise
    sm.assert_called_once()
    pm.assert_not_called()


def test_allowlist_rejects_unlisted_chat():
    updates = [{"update_id": 1, "message": {"text": "hi", "chat": {"id": 42}, "from": {"id": 1}}}]
    m = _run_main(
        # Tolerant parsing: whitespace, semicolons, trailing commas, junk.
        [_project(telegram_token="tok", telegram_allowed_chat_ids=" 10, 20; junk,,30, ")],
        get_updates=[(updates, None), ([], None)],
    )
    m["process"].assert_not_called()
    assert m["send_message"].call_count == 1
    assert "not authorized" in m["send_message"].call_args.args[2]
    assert "42" in m["send_message"].call_args.args[2]


def test_allowed_chat_processed_and_answer_sent():
    updates = [{"update_id": 9, "message": {"text": "hello", "chat": {"id": 42}, "from": {"username": "bob"}}}]
    m = _run_main(
        [_project(telegram_token="tok", telegram_allowed_chat_ids="42")],
        get_updates=[(updates, None), ([], None)],
    )
    m["send_typing"].assert_called_once_with("tok", 42)
    m["process"].assert_called_once()
    m["send_message"].assert_called_once_with("tok", 42, "answer")


def test_empty_allowlist_is_open_to_all():
    updates = [{"update_id": 1, "message": {"text": "hi", "chat": {"id": 12345}, "from": {}}}]
    m = _run_main(
        [_project(telegram_token="tok")],
        get_updates=[(updates, None), ([], None)],
    )
    m["process"].assert_called_once()
    m["send_message"].assert_called_once_with("tok", 12345, "answer")


def test_non_message_and_textless_updates_skipped_but_acked():
    updates = [
        {"update_id": 1, "edited_message": {"text": "x"}},
        {"update_id": 2, "message": {"chat": {"id": 5}}},  # no text
        {"update_id": 3, "message": {"text": "hi", "chat": {}}},  # no chat id
    ]
    m = _run_main([_project(telegram_token="tok")], get_updates=[(updates, None), ([], None)])
    m["process"].assert_not_called()
    m["send_message"].assert_not_called()
    ack = m["get_updates"].call_args_list[1]
    assert ack.kwargs.get("offset") == 4


def test_conflict_with_webhook_self_heals():
    err = "Telegram API rejected getUpdates (409): Conflict: can't use getUpdates method while webhook is active"
    m = _run_main([_project(telegram_token="tok")], get_updates=[(None, err)])
    m["delete_webhook"].assert_called_once_with("tok")
    m["send_message"].assert_not_called()


def test_conflict_webhook_clear_failure_logged_not_raised():
    err = "HTTP 409: Conflict: webhook is active"
    db = _db([_project(telegram_token="tok")])
    with patch.object(ct, "ensure_settings_table"), \
         patch.object(ct, "Brain"), \
         patch.object(ct, "open_db_wrapper", return_value=db), \
         patch.object(ct, "get_updates", return_value=(None, err)), \
         patch.object(ct, "delete_webhook", return_value=(False, "still there")) as dw, \
         patch.object(ct, "send_message"):
        ct.main()  # must not raise
    dw.assert_called_once()


def test_conflict_without_webhook_does_not_touch_webhook():
    err = "Telegram API rejected getUpdates (409): Conflict: terminated by other getUpdates request"
    m = _run_main([_project(telegram_token="tok")], get_updates=[(None, err)])
    m["delete_webhook"].assert_not_called()


def test_generic_api_error_skips_project():
    m = _run_main(
        [
            _project(id=1, telegram_token="badtok"),
            _project(id=2, name="p2", telegram_token="goodtok"),
        ],
        get_updates=[(None, "HTTP 401: Unauthorized"), ([], None)],
    )
    # Second project still polled after the first errored.
    assert m["get_updates"].call_count == 2
    m["delete_webhook"].assert_not_called()


def test_processing_error_does_not_block_other_updates():
    updates = [
        {"update_id": 1, "message": {"text": "boom", "chat": {"id": 1}, "from": {}}},
        {"update_id": 2, "message": {"text": "ok", "chat": {"id": 2}, "from": {}}},
    ]
    process = AsyncMock(side_effect=[RuntimeError("agent exploded"), "fine"])
    m = _run_main(
        [_project(telegram_token="tok")],
        get_updates=[(updates, None), ([], None)],
        process=process,
    )
    assert process.call_count == 2
    m["send_message"].assert_called_once_with("tok", 2, "fine")


# ─── _process_message ───────────────────────────────────────────────────

def test_process_message_project_not_found():
    brain = MagicMock()
    brain.find_project.return_value = None
    assert asyncio.run(ct._process_message(brain, MagicMock(), 1, "hi", 42)) is None


def _project_owned_by(creator_id):
    project = MagicMock()
    project.props.creator = creator_id
    return project


def test_process_message_no_resolvable_creator():
    """Fail closed: without a creator the turn is skipped, never escalated to
    the platform admin (which would void the Call Project tenancy check)."""
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(None)
    db = MagicMock()
    assert asyncio.run(ct._process_message(brain, db, 1, "hi", 42)) is None


def test_process_message_runs_as_project_creator():
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(7)
    db = MagicMock()
    db.get_user_by_id.return_value = SimpleNamespace(id=7, username="owner")
    chat_main = AsyncMock(return_value={"answer": "42 is the answer"})
    with patch("restai.helper.chat_main", new=chat_main):
        result = asyncio.run(ct._process_message(brain, db, 1, "hi", 42))
    assert result == "42 is the answer"
    db.get_user_by_id.assert_called_once_with(7)
    # The principal is the project's creator, not "admin".
    assert chat_main.call_args.args[4].username == "owner"
    # Conversation id keeps each Telegram chat separate across ticks.
    chat_model = chat_main.call_args.args[3]
    assert chat_model.id == "telegram_42"


def test_process_message_unexpected_result_type():
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(7)
    db = MagicMock()
    db.get_user_by_id.return_value = SimpleNamespace(id=7, username="owner")
    with patch("restai.helper.chat_main", new=AsyncMock(return_value="just a string")):
        assert asyncio.run(ct._process_message(brain, db, 1, "hi", 42)) is None


def test_send_typing_swallows_errors():
    with patch("requests.post", side_effect=RuntimeError("down")):
        ct.send_typing("tok", 42)  # must not raise
