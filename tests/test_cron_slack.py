"""Unit tests for crons/slack.py — cron-driven Slack poller.

slack_sdk WebClient is faked; no network. DB wrapper and Brain mocked.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from slack_sdk.errors import SlackApiError

import crons.slack as cs


def _project(id=1, name="proj", **opts):
    return SimpleNamespace(id=id, name=name, options=json.dumps(opts))


def _db(projects):
    db = MagicMock()
    db.db.query.return_value.all.return_value = projects
    return db


def _slack_error(msg="invalid_auth"):
    return SlackApiError(msg, response={"ok": False, "error": msg})


# ─── _get_bot_conversations ─────────────────────────────────────────────

def test_get_bot_conversations_paginates_and_filters():
    client = MagicMock()
    client.conversations_list.side_effect = [
        {
            "channels": [
                {"id": "C1", "is_member": True},
                {"id": "C2", "is_member": False},
                {"id": "D1", "is_im": True},
            ],
            "response_metadata": {"next_cursor": "cur2"},
        },
        {
            "channels": [{"id": "C3", "is_member": True}],
            "response_metadata": {"next_cursor": ""},
        },
    ]
    assert cs._get_bot_conversations(client) == ["C1", "D1", "C3"]
    # Second page requested with the cursor from the first.
    assert client.conversations_list.call_args_list[1].kwargs["cursor"] == "cur2"


# ─── _update_slack_ts ───────────────────────────────────────────────────

def test_update_slack_ts_writes_option():
    proj_row = SimpleNamespace(options=json.dumps({"slack_bot_token": "x"}))
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = proj_row
    cs._update_slack_ts(db, 1, "123.456")
    opts = json.loads(proj_row.options)
    assert opts["slack_last_ts"] == "123.456"
    assert opts["slack_bot_token"] == "x"  # other keys preserved
    db.db.commit.assert_called_once()


def test_update_slack_ts_missing_project_is_noop():
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = None
    cs._update_slack_ts(db, 1, "123.456")
    db.db.commit.assert_not_called()


# ─── main ───────────────────────────────────────────────────────────────

def _run_main(projects, client, process=None):
    db = _db(projects)
    # _update_slack_ts also goes through db.db.query(...).filter(...).first()
    db.db.query.return_value.filter.return_value.first.return_value = projects[0] if projects else None
    with patch.object(cs, "ensure_settings_table"), \
         patch.object(cs, "Brain"), \
         patch.object(cs, "open_db_wrapper", return_value=db), \
         patch("slack_sdk.WebClient", return_value=client), \
         patch.object(cs, "_process_message", new=process or AsyncMock(return_value="reply")) as pm:
        cs.main()
    return db, pm


def test_project_without_token_skipped():
    client = MagicMock()
    _run_main([_project()], client)
    client.auth_test.assert_not_called()


def test_auth_failure_skips_project():
    client = MagicMock()
    client.auth_test.side_effect = _slack_error()
    _run_main([_project(slack_bot_token="xoxb-1")], client)
    client.conversations_list.assert_not_called()


def test_conversations_list_failure_skips_project():
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.side_effect = _slack_error("missing_scope")
    _run_main([_project(slack_bot_token="xoxb-1")], client)
    client.conversations_history.assert_not_called()


def test_message_filtering_and_reply_threading():
    proj = _project(slack_bot_token="xoxb-1", slack_last_ts="100")
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.return_value = {
        "channels": [{"id": "D1", "is_im": True}],
        "response_metadata": {"next_cursor": ""},
    }
    client.conversations_history.return_value = {
        "messages": [
            {"user": "BOT", "text": "own message", "ts": "105"},
            {"user": "U1", "bot_id": "B99", "text": "other bot", "ts": "104"},
            {"user": "U1", "subtype": "channel_join", "text": "joined", "ts": "103"},
            {"user": "U1", "text": "   ", "ts": "102"},
            {"user": "U1", "text": "hello there", "ts": "101.5"},
        ]
    }
    db, pm = _run_main([proj], client)

    # Only the one real human message was processed.
    pm.assert_called_once()
    assert pm.call_args.args[3] == "hello there"

    client.chat_postMessage.assert_called_once_with(
        channel="D1", text="reply", thread_ts="101.5",
    )
    # History fetched from the stored high-water mark.
    assert client.conversations_history.call_args.kwargs["oldest"] == "100"
    # High-water mark advanced past the bot's own newest ts is NOT counted;
    # newest processed-eligible ts is what gets stored.
    opts = json.loads(proj.options)
    assert opts["slack_last_ts"] == "101.5"


def test_existing_thread_ts_reused():
    proj = _project(slack_bot_token="xoxb-1", slack_last_ts="0")
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.return_value = {
        "channels": [{"id": "C1", "is_member": True}],
        "response_metadata": {"next_cursor": ""},
    }
    client.conversations_history.return_value = {
        "messages": [{"user": "U1", "text": "in thread", "ts": "50.2", "thread_ts": "49.0"}]
    }
    _run_main([proj], client)
    assert client.chat_postMessage.call_args.kwargs["thread_ts"] == "49.0"


def test_unreadable_channel_skipped_but_others_processed():
    proj = _project(slack_bot_token="xoxb-1", slack_last_ts="0")
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.return_value = {
        "channels": [
            {"id": "C_PRIVATE", "is_member": True},
            {"id": "C_OK", "is_member": True},
        ],
        "response_metadata": {"next_cursor": ""},
    }
    client.conversations_history.side_effect = [
        _slack_error("not_in_channel"),
        {"messages": [{"user": "U1", "text": "hi", "ts": "10"}]},
    ]
    db, pm = _run_main([proj], client)
    pm.assert_called_once()
    client.chat_postMessage.assert_called_once()


def test_processing_error_does_not_block_other_messages():
    proj = _project(slack_bot_token="xoxb-1", slack_last_ts="0")
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.return_value = {
        "channels": [{"id": "D1", "is_im": True}],
        "response_metadata": {"next_cursor": ""},
    }
    client.conversations_history.return_value = {
        "messages": [
            {"user": "U1", "text": "second", "ts": "20"},
            {"user": "U1", "text": "first", "ts": "10"},
        ]
    }
    process = AsyncMock(side_effect=[RuntimeError("boom"), "ok"])
    db, pm = _run_main([proj], client, process=process)
    assert pm.call_count == 2
    client.chat_postMessage.assert_called_once()
    # High-water mark still advanced (no infinite reprocessing loop).
    assert json.loads(proj.options)["slack_last_ts"] == "20"


def test_slack_sdk_missing_aborts_cleanly(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "slack_sdk", None)  # forces ImportError
    db = _db([])
    with patch.object(cs, "ensure_settings_table"), \
         patch.object(cs, "Brain"), \
         patch.object(cs, "open_db_wrapper", return_value=db):
        cs.main()  # must not raise
    db.db.query.assert_not_called()


def test_main_crash_is_caught_and_db_closed():
    db = MagicMock()
    db.db.query.side_effect = RuntimeError("db exploded")
    with patch.object(cs, "ensure_settings_table"), \
         patch.object(cs, "Brain"), \
         patch.object(cs, "open_db_wrapper", return_value=db):
        cs.main()  # must not raise
    db.db.close.assert_called_once()


# ─── _process_message ───────────────────────────────────────────────────

def test_process_message_project_not_found():
    import asyncio
    brain = MagicMock()
    brain.find_project.return_value = None
    assert asyncio.run(cs._process_message(brain, MagicMock(), 1, "hi", "D1")) is None


def _project_owned_by(creator_id):
    project = MagicMock()
    project.props.creator = creator_id
    return project


def test_process_message_no_resolvable_creator():
    """Fail closed rather than escalating the turn to the platform admin."""
    import asyncio
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(None)
    db = MagicMock()
    assert asyncio.run(cs._process_message(brain, db, 1, "hi", "D1")) is None


def test_process_message_returns_answer_and_runs_background_tasks():
    import asyncio
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(7)
    db = MagicMock()
    db.get_user_by_id.return_value = SimpleNamespace(id=7, username="owner")

    ran = []

    async def fake_chat_main(request, brain_, project, q, user, db_, background_tasks):
        assert q.id == "slack_D1"  # per-channel conversation memory
        assert request.app.state.brain is brain
        assert user.username == "owner"  # project creator, not "admin"
        background_tasks.add_task(lambda: ran.append("sync"))

        async def _async_task():
            ran.append("async")

        background_tasks.add_task(_async_task)
        background_tasks.add_task(MagicMock(side_effect=RuntimeError("task boom")))
        return {"answer": "hi there"}

    with patch("restai.helper.chat_main", new=fake_chat_main):
        result = asyncio.run(cs._process_message(brain, db, 1, "hi", "D1"))
    assert result == "hi there"
    assert set(ran) == {"sync", "async"}


def test_process_message_non_dict_result_is_none():
    import asyncio
    brain = MagicMock()
    brain.find_project.return_value = _project_owned_by(7)
    db = MagicMock()
    db.get_user_by_id.return_value = SimpleNamespace(id=7, username="owner")
    with patch("restai.helper.chat_main", new=AsyncMock(return_value="raw string")):
        assert asyncio.run(cs._process_message(brain, db, 1, "hi", "D1")) is None


def test_empty_answer_not_posted():
    proj = _project(slack_bot_token="xoxb-1", slack_last_ts="0")
    client = MagicMock()
    client.auth_test.return_value = {"user_id": "BOT"}
    client.conversations_list.return_value = {
        "channels": [{"id": "D1", "is_im": True}],
        "response_metadata": {"next_cursor": ""},
    }
    client.conversations_history.return_value = {
        "messages": [{"user": "U1", "text": "hi", "ts": "10"}]
    }
    _run_main([proj], client, process=AsyncMock(return_value=None))
    client.chat_postMessage.assert_not_called()
