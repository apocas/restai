"""Unit tests for crons/browser_cleanup.py — enable/config gating, DB
heartbeat idle detection, label fallback, instance isolation, in-flight
exec guard. Docker SDK fully faked."""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import restai.config as config

import crons.browser_cleanup as cbc


class FakeContainer:
    def __init__(self, labels, exec_ids=None):
        self.labels = labels
        self.short_id = "beef" + labels.get("restai.browser_chat_id", "x")[:6]
        self.attrs = {"ExecIDs": exec_ids or []}
        self.stopped = False
        self.stop_error = None

    def reload(self):
        pass

    def stop(self, timeout=None):
        if self.stop_error:
            raise self.stop_error
        self.stopped = True


def _run(monkeypatch, containers, activity_rows, enabled=True,
         docker_url="tcp://dockerd:2375", timeout=900, instance="me",
         exec_running=False):
    monkeypatch.setattr(config, "BROWSER_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "DOCKER_URL", docker_url, raising=False)
    monkeypatch.setattr(config, "BROWSER_TIMEOUT", timeout, raising=False)

    client = MagicMock()
    client.containers.list.return_value = containers
    client.api.exec_inspect.return_value = {"Running": exec_running}

    db = MagicMock()
    db.db.query.return_value.all.return_value = activity_rows

    with patch.object(cbc, "ensure_settings_table"), \
         patch("docker.DockerClient", return_value=client) as dc, \
         patch.object(cbc, "open_db_wrapper", return_value=db), \
         patch("restai.observability.instance.get_instance_id", return_value=instance):
        cbc.main()
    return client, dc


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(config, "BROWSER_ENABLED", False, raising=False)
    with patch.object(cbc, "ensure_settings_table"), \
         patch("docker.DockerClient") as dc:
        cbc.main()
    dc.assert_not_called()


def test_enabled_without_docker_url_is_noop(monkeypatch):
    monkeypatch.setattr(config, "BROWSER_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "DOCKER_URL", "  ", raising=False)
    with patch.object(cbc, "ensure_settings_table"), \
         patch("docker.DockerClient") as dc:
        cbc.main()
    dc.assert_not_called()


def test_no_containers(monkeypatch):
    client, _ = _run(monkeypatch, [], [])
    client.containers.list.assert_called_once()


def test_idle_browser_container_stopped_active_kept(monkeypatch):
    idle = FakeContainer({"restai.browser_chat_id": "idle"})
    active = FakeContainer({"restai.browser_chat_id": "active"})
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(chat_id="idle", last_activity=now - timedelta(hours=1)),
        SimpleNamespace(chat_id="active", last_activity=now),
    ]
    _run(monkeypatch, [idle, active], rows, timeout=900)
    assert idle.stopped is True
    assert active.stopped is False


def test_naive_heartbeat_treated_as_utc(monkeypatch):
    c = FakeContainer({"restai.browser_chat_id": "c1"})
    rows = [SimpleNamespace(chat_id="c1", last_activity=datetime.utcnow())]
    _run(monkeypatch, [c], rows)
    assert c.stopped is False


def test_other_instance_untouched(monkeypatch):
    foreign = FakeContainer({
        "restai.browser_chat_id": "c1",
        "restai.observability.instance_id": "other-install",
    })
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(chat_id="c1", last_activity=now - timedelta(hours=9))]
    _run(monkeypatch, [foreign], rows, instance="me")
    assert foreign.stopped is False


def test_orphan_label_fallback(monkeypatch):
    old = FakeContainer({
        "restai.browser_chat_id": "old",
        "restai.created_at": str(int(time.time()) - 7200),
    })
    # No created_at label and no heartbeat → idle computes to 0 → kept.
    unknown = FakeContainer({"restai.browser_chat_id": "unknown"})
    _run(monkeypatch, [old, unknown], [], timeout=900)
    assert old.stopped is True
    assert unknown.stopped is False


def test_inflight_exec_blocks_eviction(monkeypatch):
    busy = FakeContainer({"restai.browser_chat_id": "busy"}, exec_ids=["e1"])
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(chat_id="busy", last_activity=now - timedelta(hours=2))]
    _run(monkeypatch, [busy], rows, exec_running=True)
    assert busy.stopped is False


def test_stop_failure_swallowed_and_others_continue(monkeypatch):
    bad = FakeContainer({"restai.browser_chat_id": "bad"})
    bad.stop_error = RuntimeError("api 500")
    good = FakeContainer({"restai.browser_chat_id": "good"})
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(chat_id="bad", last_activity=now - timedelta(hours=2)),
        SimpleNamespace(chat_id="good", last_activity=now - timedelta(hours=2)),
    ]
    _run(monkeypatch, [bad, good], rows)  # must not raise
    assert good.stopped is True
