"""Unit tests for restai/browser/runtime.py plus the browser tool gating
helpers in restai/llms/tools/_browser_common.py. Mocked docker client and
mocked requests to the in-container micro-server; no network, no daemon.
"""
import io
import json
import tarfile
import types

import pytest
import requests as real_requests

import restai.browser.runtime as rt
import restai.config as cfg
from restai.llms.tools._browser_common import (
    _browser_allow_eval,
    _browser_ctx,
    _check_allowed_domain,
    _parse_allowed_domains,
)


# ─── fakes ──────────────────────────────────────────────────────────────

class ExecResult:
    def __init__(self, exit_code=0, output=b""):
        self.exit_code = exit_code
        self.output = output


class FakeContainer:
    def __init__(self, host_port=43210, status="running", cid="beadfeed"):
        self.status = status
        self.id = cid
        self.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "7000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(host_port)}]
                }
            }
        }
        self.exec_calls = []
        self.exec_script = {}
        self.put_archives = []
        self.put_archive_ok = True
        self.stopped = False
        self.reloaded = False

    def reload(self):
        self.reloaded = True

    def exec_run(self, cmd, **kw):
        self.exec_calls.append((cmd, kw))
        shell = cmd[2] if (isinstance(cmd, list) and len(cmd) >= 3) else ""
        for needle, result in self.exec_script.items():
            if needle in shell:
                return result() if callable(result) else result
        return ExecResult()

    def put_archive(self, path, data):
        self.put_archives.append((path, data))
        return self.put_archive_ok

    def stop(self, timeout=None):
        self.stopped = True


class FakeContainers:
    def __init__(self, existing=None, run_result=None):
        self.existing = list(existing or [])
        self.run_result = run_result
        self.run_calls = []
        self.list_raises = False

    def list(self, filters=None, limit=None):
        if self.list_raises:
            raise RuntimeError("daemon down")
        return self.existing

    def run(self, image, **kw):
        self.run_calls.append((image, kw))
        return self.run_result or FakeContainer()


class FakeClient:
    def __init__(self, containers):
        self.containers = containers


@pytest.fixture
def browser_env(monkeypatch):
    monkeypatch.setattr(cfg, "BROWSER_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://fake:2375", raising=False)
    client = FakeClient(FakeContainers())
    monkeypatch.setattr(rt, "_client", client)
    monkeypatch.setattr(rt, "_client_url", "tcp://fake:2375")
    # storage-state: force in-process fallback + fresh dict
    monkeypatch.setattr(cfg, "build_redis_url", lambda: None)
    monkeypatch.setattr(rt, "_storage_local", {})
    monkeypatch.setattr(rt, "_storage_redis_client", None)
    monkeypatch.setattr(rt, "_storage_redis_url", None)
    # DB activity noop
    import restai.database as rdb
    fake_db = types.SimpleNamespace(
        db=types.SimpleNamespace(close=lambda: None),
        upsert_browser_activity=lambda *a: None,
        delete_browser_activity=lambda *a: None,
    )
    monkeypatch.setattr(rdb, "open_db_wrapper", lambda: fake_db)
    return client


# ─── is_enabled ─────────────────────────────────────────────────────────

def test_is_enabled_requires_flag(monkeypatch):
    monkeypatch.setattr(cfg, "BROWSER_ENABLED", False, raising=False)
    assert rt.is_enabled() is False


def test_is_enabled_requires_docker_url(monkeypatch):
    monkeypatch.setattr(cfg, "BROWSER_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "DOCKER_URL", "", raising=False)
    assert rt.is_enabled() is False


def test_is_enabled_true(browser_env):
    assert rt.is_enabled() is True


def test_get_client_none_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "BROWSER_ENABLED", False, raising=False)
    assert rt._get_client() is None


# ─── port discovery ─────────────────────────────────────────────────────

def test_discover_port_localhost_binding():
    assert rt._discover_port(FakeContainer(host_port=45678)) == 45678


def test_discover_port_all_interfaces():
    c = FakeContainer()
    c.attrs["NetworkSettings"]["Ports"]["7000/tcp"] = [
        {"HostIp": "0.0.0.0", "HostPort": "999"}
    ]
    assert rt._discover_port(c) == 999


def test_discover_port_no_binding():
    c = FakeContainer()
    c.attrs["NetworkSettings"]["Ports"]["7000/tcp"] = None
    assert rt._discover_port(c) is None


def test_discover_port_missing_attrs():
    c = FakeContainer()
    c.attrs = {}
    assert rt._discover_port(c) is None


def test_discover_port_foreign_ip_skipped():
    c = FakeContainer()
    c.attrs["NetworkSettings"]["Ports"]["7000/tcp"] = [
        {"HostIp": "10.0.0.5", "HostPort": "999"}
    ]
    assert rt._discover_port(c) is None


# ─── playwright version pin ─────────────────────────────────────────────

def test_parse_playwright_version_ms_image():
    assert rt._parse_playwright_version(
        "mcr.microsoft.com/playwright/python:v1.48.0-jammy") == "1.48.0"


def test_parse_playwright_version_no_tag():
    assert rt._parse_playwright_version("someimage") is None


def test_parse_playwright_version_non_numeric():
    assert rt._parse_playwright_version("img:latest") is None


def test_parse_playwright_version_two_part():
    assert rt._parse_playwright_version("img:v1.48") == "1.48"


# ─── storage state (in-process fallback) ────────────────────────────────

def test_storage_state_local_roundtrip(browser_env):
    state = {"cookies": [{"name": "session", "value": "abc"}]}
    rt.save_storage_state(7, "example.com", state)
    assert rt.load_storage_state(7, "example.com") == state
    assert rt.load_storage_state(7, "other.com") is None
    assert rt.load_storage_state(8, "example.com") is None


def test_storage_state_redis_path(browser_env, monkeypatch):
    store = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value
            store["_ttl"] = ex

    monkeypatch.setattr(rt, "_redis", lambda: FakeRedis())
    rt.save_storage_state(1, "d.com", {"k": 1})
    assert store["_ttl"] == rt._STORAGE_STATE_TTL
    assert rt.load_storage_state(1, "d.com") == {"k": 1}
    assert rt._storage_local == {}  # never hit the fallback


def test_storage_state_redis_failure_falls_back(browser_env, monkeypatch):
    class BrokenRedis:
        def get(self, key):
            raise RuntimeError("redis down")

        def set(self, key, value, ex=None):
            raise RuntimeError("redis down")

    monkeypatch.setattr(rt, "_redis", lambda: BrokenRedis())
    rt.save_storage_state(1, "d.com", {"k": 2})
    assert rt.load_storage_state(1, "d.com") == {"k": 2}  # local fallback


def test_redis_helper_none_without_url(browser_env):
    assert rt._redis() is None


# ─── container resolution / creation ────────────────────────────────────

def test_resolve_container_running(browser_env):
    c = FakeContainer()
    browser_env.containers.existing = [c]
    assert rt._resolve_container("chat1") is c


def test_resolve_container_non_running_or_error(browser_env):
    browser_env.containers.existing = [FakeContainer(status="exited")]
    assert rt._resolve_container("chat1") is None
    browser_env.containers.list_raises = True
    assert rt._resolve_container("chat1") is None
    assert rt._resolve_container("") is None


def test_get_or_create_reuses_running_container(browser_env):
    c = FakeContainer(host_port=5555)
    browser_env.containers.existing = [c]
    container, port = rt._get_or_create("chat1")
    assert container is c
    assert port == 5555
    assert browser_env.containers.run_calls == []


def test_create_container_full_path(browser_env, monkeypatch):
    calls = []
    monkeypatch.setattr(rt, "_install_micro_server", lambda c: calls.append("install"))
    monkeypatch.setattr(rt, "_ensure_playwright_pkg", lambda c, i: calls.append("pkg"))
    monkeypatch.setattr(rt, "_start_micro_server", lambda c: calls.append("start"))
    monkeypatch.setattr(rt, "_wait_healthy", lambda p: calls.append(("health", p)))

    fake = FakeContainer(host_port=7777)
    browser_env.containers.run_result = fake
    container, port = rt._create_container("chatZ")
    assert container is fake
    assert port == 7777
    assert fake.reloaded is True
    assert calls == ["install", "pkg", "start", ("health", 7777)]
    image, kw = browser_env.containers.run_calls[0]
    assert kw["labels"]["restai.browser_chat_id"] == "chatZ"
    assert kw["shm_size"] == "512m"
    assert kw["ports"] == {"7000/tcp": ("127.0.0.1", None)}


def test_create_container_no_published_port_stops_and_raises(browser_env, monkeypatch):
    fake = FakeContainer()
    fake.attrs = {}  # port discovery fails
    browser_env.containers.run_result = fake
    with pytest.raises(RuntimeError, match="did not publish a host port"):
        rt._create_container("chatZ")
    assert fake.stopped is True


def test_create_container_unconfigured(monkeypatch):
    monkeypatch.setattr(cfg, "BROWSER_ENABLED", False, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        rt._create_container("x")


# ─── micro-server install / pip pin / health ────────────────────────────

def test_install_micro_server_puts_tar(browser_env):
    c = FakeContainer()
    rt._install_micro_server(c)
    path, data = c.put_archives[0]
    assert path == "/opt"
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        names = tar.getnames()
        assert names == ["restai_browser/micro_server.py"]
        payload = tar.extractfile(names[0]).read()
    assert b"Browser micro-server" in payload


def test_install_micro_server_failure_raises(browser_env):
    c = FakeContainer()
    c.put_archive_ok = False
    with pytest.raises(RuntimeError, match="put_archive"):
        rt._install_micro_server(c)


def test_ensure_playwright_pkg_already_installed(browser_env):
    c = FakeContainer()
    c.exec_script["import playwright"] = ExecResult(exit_code=0)
    rt._ensure_playwright_pkg(c, "img:v1.48.0")
    assert len(c.exec_calls) == 1  # probe only, no pip


def test_ensure_playwright_pkg_installs_pinned(browser_env):
    c = FakeContainer()
    c.exec_script["import playwright"] = ExecResult(exit_code=1)
    c.exec_script["pip install"] = ExecResult(exit_code=0)
    rt._ensure_playwright_pkg(c, "mcr.microsoft.com/playwright/python:v1.48.0-jammy")
    pip_cmd = c.exec_calls[1][0][2]
    assert "playwright==1.48.0" in pip_cmd
    assert "--break-system-packages" in pip_cmd


def test_ensure_playwright_pkg_retries_without_break_flag(browser_env):
    c = FakeContainer()
    results = iter([ExecResult(exit_code=1),   # probe
                    ExecResult(exit_code=1),   # pip --break-system-packages
                    ExecResult(exit_code=0)])  # plain pip
    c.exec_run = lambda cmd, **kw: next(results)
    rt._ensure_playwright_pkg(c, "img:v1.48.0")


def test_ensure_playwright_pkg_both_fail_raises(browser_env):
    c = FakeContainer()
    results = iter([ExecResult(exit_code=1),
                    ExecResult(exit_code=1),
                    ExecResult(exit_code=1, output=b"no network")])
    c.exec_run = lambda cmd, **kw: next(results)
    with pytest.raises(RuntimeError, match="no network"):
        rt._ensure_playwright_pkg(c, "img:v1.48.0")


def test_wait_healthy_success(browser_env, monkeypatch):
    monkeypatch.setattr(
        rt.requests, "get",
        lambda url, timeout=None: types.SimpleNamespace(status_code=200),
    )
    rt._wait_healthy(1234)  # returns without raising


def test_wait_healthy_timeout(browser_env, monkeypatch):
    monkeypatch.setattr(rt, "_HEALTH_TIMEOUT", 0.4)

    def refuse(url, timeout=None):
        raise real_requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(rt.requests, "get", refuse)
    with pytest.raises(RuntimeError, match="health check timed out"):
        rt._wait_healthy(1234)


# ─── chat lock / remove ─────────────────────────────────────────────────

def test_chat_lock_reused_per_chat(browser_env, monkeypatch):
    monkeypatch.setattr(rt, "_chat_locks", {})
    lock1 = rt._chat_lock("a")
    assert rt._chat_lock("a") is lock1
    assert rt._chat_lock("b") is not lock1


def test_remove_container_idempotent(browser_env):
    rt.remove_container("nope")  # nothing exists — no raise
    c = FakeContainer()
    browser_env.containers.existing = [c]
    rt.remove_container("chat1")
    assert c.stopped is True


def test_remove_container_stop_failure_swallowed(browser_env):
    c = FakeContainer()

    def boom(timeout=None):
        raise RuntimeError("kaput")

    c.stop = boom
    browser_env.containers.existing = [c]
    rt.remove_container("chat1")  # must not raise


# ─── call() — micro-server round trip ───────────────────────────────────

class FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text or json.dumps(self._payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _wire_call(monkeypatch, container=None, port=9999):
    container = container or FakeContainer(host_port=port)
    created = []

    def fake_get_or_create(chat_id):
        created.append(chat_id)
        return container, port

    monkeypatch.setattr(rt, "_get_or_create", fake_get_or_create)
    monkeypatch.setattr(rt, "_touch_db_activity", lambda *a: None)
    return created


def test_call_posts_json_and_returns_dict(browser_env, monkeypatch):
    created = _wire_call(monkeypatch, port=4321)
    posts = []

    def fake_post(url, json=None, timeout=None):
        posts.append((url, json, timeout))
        return FakeResp(payload={"url": "https://x", "title": "T"})

    monkeypatch.setattr(rt.requests, "post", fake_post)
    out = rt.call("chat1", "/goto", {"url": "https://x"})
    assert out == {"url": "https://x", "title": "T"}
    assert posts[0][0] == "http://127.0.0.1:4321/goto"
    assert posts[0][1] == {"url": "https://x"}
    assert created == ["chat1"]


def test_call_defaults_ephemeral_and_empty_payload(browser_env, monkeypatch):
    created = _wire_call(monkeypatch)
    monkeypatch.setattr(
        rt.requests, "post", lambda url, json=None, timeout=None: FakeResp()
    )
    rt.call("", "/health")
    assert created == ["ephemeral"]


def test_call_error_status_raises_with_detail(browser_env, monkeypatch):
    _wire_call(monkeypatch)
    monkeypatch.setattr(
        rt.requests, "post",
        lambda url, json=None, timeout=None: FakeResp(
            status_code=500, payload={"error": "no such element"}),
    )
    with pytest.raises(RuntimeError, match="no such element"):
        rt.call("chat1", "/click", {"selector": "#x"})


def test_call_error_status_non_json_uses_text(browser_env, monkeypatch):
    _wire_call(monkeypatch)
    resp = FakeResp(status_code=502, payload=ValueError("not json"), text="bad gateway")
    monkeypatch.setattr(rt.requests, "post", lambda *a, **k: resp)
    with pytest.raises(RuntimeError, match="bad gateway"):
        rt.call("chat1", "/content")


def test_call_retries_once_after_connection_error(browser_env, monkeypatch):
    created = _wire_call(monkeypatch)
    removed = []
    monkeypatch.setattr(rt, "remove_container", lambda cid: removed.append(cid))
    attempts = []

    def flaky_post(url, json=None, timeout=None):
        attempts.append(url)
        if len(attempts) == 1:
            raise real_requests.exceptions.ConnectionError("died")
        return FakeResp(payload={"recovered": True})

    monkeypatch.setattr(rt.requests, "post", flaky_post)
    out = rt.call("chat1", "/goto", {"url": "https://x"})
    assert out == {"recovered": True}
    assert removed == ["chat1"]
    assert created == ["chat1", "chat1"]  # dropped + recreated


# ─── client rebuild / redis client plumbing ─────────────────────────────

def test_get_client_rebuilds_on_url_change(browser_env, monkeypatch):
    built = {}

    class FakeSdkClient:
        def __init__(self, base_url=None):
            built["url"] = base_url

    monkeypatch.setattr(
        rt, "_docker_sdk", types.SimpleNamespace(DockerClient=FakeSdkClient)
    )
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://elsewhere:2375", raising=False)
    client = rt._get_client()
    assert isinstance(client, FakeSdkClient)
    assert built["url"] == "tcp://elsewhere:2375"


def test_get_client_connect_failure_returns_none(browser_env, monkeypatch):
    def boom(base_url=None):
        raise RuntimeError("no daemon")

    monkeypatch.setattr(
        rt, "_docker_sdk", types.SimpleNamespace(DockerClient=boom)
    )
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://dead:1", raising=False)
    assert rt._get_client() is None


def test_redis_builds_client_from_url(browser_env, monkeypatch):
    import sys
    created = {}

    class FakeRedisClient:
        def close(self):
            created["closed"] = True

    fake_redis_mod = types.SimpleNamespace(
        Redis=types.SimpleNamespace(
            from_url=lambda url: created.setdefault("client", FakeRedisClient())
        )
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)
    monkeypatch.setattr(cfg, "build_redis_url", lambda: "redis://h:6379/0")
    client = rt._redis()
    assert client is created["client"]
    # cached on second call
    assert rt._redis() is client
    # url gone → cached client closed and cleared
    monkeypatch.setattr(cfg, "build_redis_url", lambda: None)
    assert rt._redis() is None
    assert created.get("closed") is True


def test_redis_build_failure_falls_back(browser_env, monkeypatch):
    import sys

    def explode(url):
        raise RuntimeError("bad url")

    fake_redis_mod = types.SimpleNamespace(
        Redis=types.SimpleNamespace(from_url=explode)
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)
    monkeypatch.setattr(cfg, "build_redis_url", lambda: "redis://bad")
    assert rt._redis() is None


# ─── micro-server start + get_or_create fallthrough ────────────────────

def test_start_micro_server_detached(browser_env):
    c = FakeContainer()
    rt._start_micro_server(c)
    cmd, kw = c.exec_calls[0]
    assert "micro_server.py" in cmd[2]
    assert kw["detach"] is True


def test_get_or_create_recreates_when_port_lost(browser_env, monkeypatch):
    stale = FakeContainer()
    stale.attrs = {}  # resolved container lost its port binding
    browser_env.containers.existing = [stale]
    fresh = FakeContainer(host_port=8888)
    monkeypatch.setattr(rt, "_create_container", lambda cid: (fresh, 8888))
    container, port = rt._get_or_create("chat1")
    assert container is fresh and port == 8888


def test_create_container_stop_failure_on_missing_port(browser_env):
    fake = FakeContainer()
    fake.attrs = {}

    def bad_stop(timeout=None):
        raise RuntimeError("cannot stop")

    fake.stop = bad_stop
    browser_env.containers.run_result = fake
    with pytest.raises(RuntimeError, match="did not publish a host port"):
        rt._create_container("chatZ")


# ─── db activity plumbing ───────────────────────────────────────────────

def test_touch_and_drop_db_activity(monkeypatch):
    import restai.database as rdb
    calls = []
    fake_db = types.SimpleNamespace(
        db=types.SimpleNamespace(close=lambda: calls.append("close")),
        upsert_browser_activity=lambda cid, container_id: calls.append(
            ("up", cid, container_id)),
        delete_browser_activity=lambda cid: calls.append(("del", cid)),
    )
    monkeypatch.setattr(rdb, "open_db_wrapper", lambda: fake_db)
    rt._touch_db_activity("c1", "cont9")
    rt._drop_db_activity("c1")
    assert ("up", "c1", "cont9") in calls
    assert ("del", "c1") in calls
    assert calls.count("close") == 2


def test_db_activity_noop_without_chat_id_and_swallows_errors(monkeypatch):
    import restai.database as rdb

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(rdb, "open_db_wrapper", boom)
    rt._touch_db_activity("", "x")   # early return, no db touch
    rt._drop_db_activity("")
    rt._touch_db_activity("c1", "x")  # db error swallowed
    rt._drop_db_activity("c1")


# ─── browser tool gating: domain allowlist + eval opt-in ────────────────

def _project(options: dict):
    return types.SimpleNamespace(options=json.dumps(options))


def test_parse_allowed_domains_splits_and_lowercases():
    p = _project({"browser_allowed_domains": "Example.com, *.Corp.net;other.org"})
    assert _parse_allowed_domains(p) == ["example.com", "*.corp.net", "other.org"]


def test_parse_allowed_domains_empty_or_broken():
    assert _parse_allowed_domains(_project({})) == []
    broken = types.SimpleNamespace(options="{not json")
    assert _parse_allowed_domains(broken) == []


def test_check_allowed_domain_empty_allowlist_unrestricted():
    assert _check_allowed_domain(_project({}), "https://anywhere.io/x") is None


def test_check_allowed_domain_exact_and_subdomain():
    p = _project({"browser_allowed_domains": "example.com"})
    assert _check_allowed_domain(p, "https://example.com/a") is None
    assert _check_allowed_domain(p, "https://www.example.com/a") is None
    err = _check_allowed_domain(p, "https://evil.com/a")
    assert err.startswith("ERROR: domain 'evil.com'")


def test_check_allowed_domain_wildcard():
    p = _project({"browser_allowed_domains": "*.corp.net"})
    assert _check_allowed_domain(p, "https://corp.net/") is None
    assert _check_allowed_domain(p, "https://app.corp.net/") is None
    assert _check_allowed_domain(p, "https://corp.net.evil.io/") is not None


def test_check_allowed_domain_no_host():
    p = _project({"browser_allowed_domains": "example.com"})
    assert "no host" in _check_allowed_domain(p, "not-a-url")


def test_browser_allow_eval_gating():
    assert _browser_allow_eval(_project({"browser_allow_eval": True})) is True
    assert _browser_allow_eval(_project({"browser_allow_eval": False})) is False
    assert _browser_allow_eval(_project({})) is False
    assert _browser_allow_eval(types.SimpleNamespace(options="{bad")) is False


def test_browser_ctx_requires_brain_project_and_manager():
    ctx, err = _browser_ctx({})
    assert ctx is None and "agent context" in err

    ctx, err = _browser_ctx({"_brain": object()})
    assert ctx is None and "project context" in err

    brain = types.SimpleNamespace(browser_manager=None)
    ctx, err = _browser_ctx({"_brain": brain, "_project_id": 1})
    assert ctx is None and "not enabled" in err
