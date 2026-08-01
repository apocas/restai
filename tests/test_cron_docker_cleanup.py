"""Unit tests for crons/docker_cleanup.py — idle-detection via the DB
heartbeat, label fallback for orphans, multi-install isolation, and the
in-flight-exec guard. Docker SDK fully faked."""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import restai.config as config

import crons.docker_cleanup as cdc


class FakeContainer:
    def __init__(self, labels, exec_ids=None, created=""):
        self.labels = labels
        self.short_id = "cafe" + labels.get("restai.chat_id", "x")[:6]
        self.attrs = {"ExecIDs": exec_ids or [], "Created": created}
        self.stopped = False
        self.stop_error = None

    def reload(self):
        pass

    def stop(self, timeout=None):
        if self.stop_error:
            raise self.stop_error
        self.stopped = True


def _activity_db(rows):
    db = MagicMock()
    db.db.query.return_value.all.return_value = rows
    return db


def _run(monkeypatch, containers, activity_rows, docker_url="tcp://dockerd:2375",
         timeout=900, instance="me", ping_error=None, exec_running=False):
    monkeypatch.setattr(config, "DOCKER_URL", docker_url, raising=False)
    monkeypatch.setattr(config, "DOCKER_TIMEOUT", timeout, raising=False)

    client = MagicMock()
    client.containers.list.return_value = containers
    client.api.exec_inspect.return_value = {"Running": exec_running}
    if ping_error:
        client.ping.side_effect = ping_error

    with patch.object(cdc, "ensure_settings_table"), \
         patch("docker.DockerClient", return_value=client) as dc, \
         patch.object(cdc, "open_db_wrapper", return_value=_activity_db(activity_rows)), \
         patch("restai.observability.instance.get_instance_id", return_value=instance):
        cdc.main()
    return client, dc


def test_no_docker_url_is_noop(monkeypatch):
    monkeypatch.setattr(config, "DOCKER_URL", "", raising=False)
    with patch.object(cdc, "ensure_settings_table"), \
         patch("docker.DockerClient") as dc:
        cdc.main()
    dc.assert_not_called()


def test_docker_unreachable_logged_not_raised(monkeypatch):
    client, _ = _run(monkeypatch, [], [], ping_error=RuntimeError("conn refused"))
    client.containers.list.assert_not_called()


def test_no_managed_containers(monkeypatch):
    client, _ = _run(monkeypatch, [], [])
    client.containers.list.assert_called_once()


def test_idle_container_stopped_active_kept(monkeypatch):
    idle = FakeContainer({"restai.chat_id": "idlechat"})
    active = FakeContainer({"restai.chat_id": "activechat"})
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(chat_id="idlechat", last_activity=now - timedelta(hours=2)),
        SimpleNamespace(chat_id="activechat", last_activity=now),
    ]
    _run(monkeypatch, [idle, active], rows, timeout=900)
    assert idle.stopped is True
    assert active.stopped is False


def test_naive_heartbeat_treated_as_utc(monkeypatch):
    # SQLite returns naive datetimes; a fresh naive timestamp must read as
    # "just now", not as idle.
    c = FakeContainer({"restai.chat_id": "c1"})
    rows = [SimpleNamespace(chat_id="c1", last_activity=datetime.utcnow())]
    _run(monkeypatch, [c], rows, timeout=900)
    assert c.stopped is False


def test_other_instance_container_untouched(monkeypatch):
    foreign = FakeContainer({
        "restai.chat_id": "c1",
        "restai.observability.instance_id": "someone-else",
    })
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(chat_id="c1", last_activity=now - timedelta(hours=5))]
    _run(monkeypatch, [foreign], rows, instance="me")
    assert foreign.stopped is False


def test_own_instance_container_managed(monkeypatch):
    mine = FakeContainer({
        "restai.chat_id": "c1",
        "restai.observability.instance_id": "me",
    })
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(chat_id="c1", last_activity=now - timedelta(hours=5))]
    _run(monkeypatch, [mine], rows, instance="me")
    assert mine.stopped is True


def test_orphan_falls_back_to_creation_label(monkeypatch):
    old_orphan = FakeContainer({
        "restai.chat_id": "orphan",
        "restai.created_at": str(int(time.time()) - 7200),
    })
    fresh_orphan = FakeContainer({
        "restai.chat_id": "fresh",
        "restai.created_at": str(int(time.time())),
    })
    _run(monkeypatch, [old_orphan, fresh_orphan], [], timeout=900)
    assert old_orphan.stopped is True
    assert fresh_orphan.stopped is False


def test_inflight_exec_blocks_eviction(monkeypatch):
    busy = FakeContainer({"restai.chat_id": "busy"}, exec_ids=["e1"])
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(chat_id="busy", last_activity=now - timedelta(hours=2))]
    _run(monkeypatch, [busy], rows, exec_running=True)
    assert busy.stopped is False


def test_stop_failure_swallowed_and_others_continue(monkeypatch):
    bad = FakeContainer({"restai.chat_id": "bad"})
    bad.stop_error = RuntimeError("docker api 500")
    good = FakeContainer({"restai.chat_id": "good"})
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(chat_id="bad", last_activity=now - timedelta(hours=2)),
        SimpleNamespace(chat_id="good", last_activity=now - timedelta(hours=2)),
    ]
    _run(monkeypatch, [bad, good], rows)  # must not raise
    assert good.stopped is True
