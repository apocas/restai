"""Unit tests for restai/comms/telegram.py — HTTP wrappers and the
legacy TelegramPoller. All requests are mocked; nothing hits Telegram."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

import restai.comms.telegram as tg


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


# ─── validate_token ─────────────────────────────────────────────────────

def test_validate_token_ok():
    with patch("restai.comms.telegram.requests.get", return_value=_resp({"ok": True, "result": {"id": 9, "username": "bot"}})) as g:
        result = tg.validate_token("tok")
    assert result == {"id": 9, "username": "bot"}
    assert "bottok/getMe" in g.call_args.args[0]


def test_validate_token_rejected():
    with patch("restai.comms.telegram.requests.get", return_value=_resp({"ok": False, "description": "Unauthorized"})):
        with pytest.raises(ValueError):
            tg.validate_token("bad")


# ─── send_message ───────────────────────────────────────────────────────

def test_send_message_single_chunk():
    with patch("restai.comms.telegram.requests.post", return_value=_resp({"ok": True})) as p:
        tg.send_message("tok", 42, "hello")
    assert p.call_count == 1
    assert p.call_args.kwargs["json"] == {"chat_id": 42, "text": "hello"}


def test_send_message_chunks_long_text():
    text = "x" * 5000
    with patch("restai.comms.telegram.requests.post", return_value=_resp({"ok": True})) as p:
        tg.send_message("tok", 42, text)
    assert p.call_count == 2
    sent = [c.kwargs["json"]["text"] for c in p.call_args_list]
    assert len(sent[0]) == 4096
    assert len(sent[1]) == 904
    assert "".join(sent) == text


def test_send_typing_action_swallows_errors():
    with patch("restai.comms.telegram.requests.post", side_effect=RuntimeError("net down")):
        tg.send_typing_action("tok", 42)  # must not raise


# ─── delete_webhook ─────────────────────────────────────────────────────

def test_delete_webhook_ok():
    with patch("restai.comms.telegram.requests.post", return_value=_resp({"ok": True})):
        assert tg.delete_webhook("tok") == (True, None)


def test_delete_webhook_api_refusal():
    with patch("restai.comms.telegram.requests.post", return_value=_resp({"ok": False, "description": "nope"})):
        assert tg.delete_webhook("tok") == (False, "nope")


def test_delete_webhook_exception():
    with patch("restai.comms.telegram.requests.post", side_effect=RuntimeError("boom")):
        ok, err = tg.delete_webhook("tok")
    assert ok is False
    assert err == "RuntimeError: boom"


# ─── get_updates ────────────────────────────────────────────────────────

def test_get_updates_success():
    updates = [{"update_id": 1}]
    with patch("restai.comms.telegram.requests.get", return_value=_resp({"ok": True, "result": updates})):
        assert tg.get_updates("tok") == (updates, None)


def test_get_updates_api_rejection_carries_code_and_description():
    payload = {"ok": False, "error_code": 409, "description": "Conflict: terminated by other getUpdates request"}
    with patch("restai.comms.telegram.requests.get", return_value=_resp(payload)):
        result, err = tg.get_updates("tok")
    assert result is None
    assert "409" in err and "Conflict" in err


def test_get_updates_timeout_is_normal():
    with patch("restai.comms.telegram.requests.get", side_effect=requests.exceptions.Timeout()):
        assert tg.get_updates("tok") == ([], None)


def test_get_updates_http_error_extracts_description():
    response = MagicMock()
    response.status_code = 404
    response.json.return_value = {"description": "Not Found"}
    exc = requests.exceptions.HTTPError(response=response)
    with patch("restai.comms.telegram.requests.get", side_effect=exc):
        result, err = tg.get_updates("tok")
    assert result is None
    assert err == "HTTP 404: Not Found"


def test_get_updates_generic_exception():
    with patch("restai.comms.telegram.requests.get", side_effect=ValueError("weird")):
        result, err = tg.get_updates("tok")
    assert result is None
    assert err == "ValueError: weird"


# ─── TelegramPoller._handle_update ──────────────────────────────────────

def _poller():
    return tg.TelegramPoller(project_id=1, token="tok", app=None)


def test_handle_update_ignores_non_message():
    p = _poller()
    with patch("restai.comms.telegram.send_typing_action") as typing:
        p._handle_update({"edited_message": {"text": "x"}})
        p._handle_update({"message": {"chat": {"id": 5}}})  # no text
        p._handle_update({"message": {"text": "hi", "chat": {}}})  # no chat id
    typing.assert_not_called()


def test_handle_update_sends_answer():
    p = _poller()
    p._process_message = AsyncMock(return_value="the answer")
    with patch("restai.comms.telegram.send_typing_action") as typing, \
         patch("restai.comms.telegram.send_message") as send:
        p._handle_update({"message": {"text": "hi", "chat": {"id": 42}}})
    typing.assert_called_once_with("tok", 42)
    send.assert_called_once_with("tok", 42, "the answer")


def test_handle_update_empty_answer_not_sent():
    p = _poller()
    p._process_message = AsyncMock(return_value=None)
    with patch("restai.comms.telegram.send_typing_action"), \
         patch("restai.comms.telegram.send_message") as send:
        p._handle_update({"message": {"text": "hi", "chat": {"id": 42}}})
    send.assert_not_called()


def test_handle_update_error_sends_apology():
    p = _poller()
    p._process_message = AsyncMock(side_effect=RuntimeError("agent died"))
    with patch("restai.comms.telegram.send_typing_action"), \
         patch("restai.comms.telegram.send_message") as send:
        p._handle_update({"message": {"text": "hi", "chat": {"id": 42}}})
    assert send.call_count == 1
    assert "error occurred" in send.call_args.args[2]


def test_handle_update_apology_failure_swallowed():
    p = _poller()
    p._process_message = AsyncMock(side_effect=RuntimeError("agent died"))
    with patch("restai.comms.telegram.send_typing_action"), \
         patch("restai.comms.telegram.send_message", side_effect=RuntimeError("net")):
        p._handle_update({"message": {"text": "hi", "chat": {"id": 42}}})  # must not raise


# ─── TelegramPoller._poll_loop ──────────────────────────────────────────

class _FakeEvent:
    def __init__(self):
        self._set = False

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def wait(self, timeout=None):
        pass


def test_poll_loop_stops_after_ten_consecutive_errors():
    p = _poller()
    p._stop_event = _FakeEvent()
    with patch("restai.comms.telegram.get_updates", return_value=(None, "err")) as g:
        p._poll_loop()
    assert g.call_count == 10


def test_poll_loop_advances_offset_and_dispatches():
    p = _poller()
    p._stop_event = _FakeEvent()
    p._handle_update = MagicMock()
    calls = []

    def fake_get_updates(token, offset=0, timeout=30):
        calls.append(offset)
        if len(calls) == 1:
            return [{"update_id": 7, "message": {}}], None
        p._stop_event.set()
        return [], None

    with patch("restai.comms.telegram.get_updates", side_effect=fake_get_updates):
        p._poll_loop()

    assert calls[0] == 0
    assert calls[1] == 8  # update_id + 1
    p._handle_update.assert_called_once_with({"update_id": 7, "message": {}})


# ─── TelegramPoller._process_message ────────────────────────────────────

def _app_with_brain(brain):
    return SimpleNamespace(state=SimpleNamespace(brain=brain))


def test_process_message_project_not_found():
    brain = MagicMock()
    brain.find_project.return_value = None
    p = tg.TelegramPoller(1, "tok", _app_with_brain(brain))
    with patch("restai.database.open_db_wrapper", return_value=MagicMock()):
        assert asyncio.run(p._process_message("hi", 42)) is None


def test_process_message_returns_answer_from_dict():
    brain = MagicMock()
    brain.find_project.return_value = MagicMock()
    p = tg.TelegramPoller(1, "tok", _app_with_brain(brain))
    with patch("restai.database.open_db_wrapper", return_value=MagicMock()), \
         patch("restai.helper.chat_main", new=AsyncMock(return_value={"answer": "yo"})):
        assert asyncio.run(p._process_message("hi", 42)) == "yo"


def test_process_message_parses_response_body():
    brain = MagicMock()
    brain.find_project.return_value = MagicMock()
    p = tg.TelegramPoller(1, "tok", _app_with_brain(brain))
    fake_response = SimpleNamespace(body=json.dumps({"answer": "from body"}).encode())
    with patch("restai.database.open_db_wrapper", return_value=MagicMock()), \
         patch("restai.helper.chat_main", new=AsyncMock(return_value=fake_response)):
        assert asyncio.run(p._process_message("hi", 42)) == "from body"


# ─── poller registry ────────────────────────────────────────────────────

def test_poller_registry_lifecycle():
    with patch.object(tg.TelegramPoller, "start") as start, \
         patch.object(tg.TelegramPoller, "stop") as stop:
        tg.start_poller(1, "tokA", None)
        assert 1 in tg._pollers
        first = tg._pollers[1]

        # Restart replaces and stops the old poller.
        tg.start_poller(1, "tokB", None)
        assert tg._pollers[1] is not first
        assert stop.call_count == 1
        assert start.call_count == 2

        tg.start_poller(2, "tokC", None)
        tg.stop_poller(1)
        assert 1 not in tg._pollers
        tg.stop_poller(999)  # unknown id is a no-op

        tg.stop_all_pollers()
        assert tg._pollers == {}
