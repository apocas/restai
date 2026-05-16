"""Stateless per-chat agentic-browser runtime.

Replacement for the old ``restai.browser.manager.BrowserManager`` class.
Same reasoning as ``restai/docker.py``: in-memory ``_containers`` dict
plus an ``init/shutdown`` lifecycle duplicated state we already get for
free by querying the Docker daemon, drifted between uvicorn workers,
and made the settings-reinit path racy.

Now: a flat module of functions. The Docker daemon is the source of
truth for "does this chat have a browser container" — looked up by the
``restai.browser_chat_id`` label per call. The Docker client connection
is cached as a module-level lazy singleton; settings are read live from
``restai.config`` so admin changes (image / network / timeout) take
effect on the next call.

Storage-state persistence (cookies / localStorage keyed by
``(project_id, domain)``) keeps its Redis-with-in-process-fallback
shape. The Redis client itself is the same lazy-singleton pattern.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tarfile
import threading
import time
from typing import Optional

import docker as _docker_sdk
import requests

from restai import config as _cfg

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

_CONTAINER_PORT = 7000
_MICRO_SERVER_PATH_HOST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "micro_server.py")
_MICRO_SERVER_PATH_CONTAINER = "/opt/restai_browser/micro_server.py"
_HEALTH_TIMEOUT = 60
_STORAGE_STATE_REDIS_PREFIX = "restai_browser_state:"
_STORAGE_STATE_TTL = 30 * 24 * 60 * 60  # 30 days

_DEFAULT_IMAGE = "mcr.microsoft.com/playwright/python:v1.48.0-jammy"

# ── Client (lazy singletons) ──────────────────────────────────────────

_client: Optional[_docker_sdk.DockerClient] = None
_client_url: str = ""
_client_lock = threading.Lock()

_storage_local: dict[str, dict] = {}
_storage_redis_client = None
_storage_redis_url: Optional[str] = None

# Per-chat asyncio lock so two parallel browser_* calls in the same chat
# don't race-create two containers. Lazily populated.
_chat_locks: dict[str, asyncio.Lock] = {}


def is_enabled() -> bool:
    if not bool(getattr(_cfg, "BROWSER_ENABLED", False)):
        return False
    return bool((getattr(_cfg, "DOCKER_URL", "") or "").strip())


def _get_client() -> Optional[_docker_sdk.DockerClient]:
    """Cached DockerClient. Rebuilt on docker_url change."""
    global _client, _client_url
    if not is_enabled():
        return None
    url = (getattr(_cfg, "DOCKER_URL", "") or "").strip()
    with _client_lock:
        if _client is not None and _client_url == url:
            return _client
        try:
            _client = _docker_sdk.DockerClient(base_url=url)
            _client_url = url
            logger.info("Browser Docker client connected to %s", url)
        except Exception as e:
            logger.error("Browser Docker client failed to connect to %s: %s", url, e)
            _client = None
            _client_url = ""
        return _client


# ── Storage-state persistence (Redis + in-process fallback) ───────────

def _redis():
    global _storage_redis_client, _storage_redis_url
    url = _cfg.build_redis_url()
    if not url:
        if _storage_redis_client is not None:
            try:
                _storage_redis_client.close()
            except Exception:
                pass
            _storage_redis_client = None
            _storage_redis_url = None
        return None
    if _storage_redis_client is not None and _storage_redis_url == url:
        return _storage_redis_client
    try:
        import redis
        _storage_redis_client = redis.Redis.from_url(url)
        _storage_redis_url = url
    except Exception as e:
        logger.warning("Browser: Redis unavailable (%s); using in-process storage-state fallback", e)
        return None
    return _storage_redis_client


def load_storage_state(project_id: int, domain: str) -> Optional[dict]:
    key = f"{_STORAGE_STATE_REDIS_PREFIX}{project_id}:{domain}"
    r = _redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Browser: failed to load storage_state from Redis (%s)", e)
    return _storage_local.get(key)


def save_storage_state(project_id: int, domain: str, state: dict) -> None:
    key = f"{_STORAGE_STATE_REDIS_PREFIX}{project_id}:{domain}"
    r = _redis()
    if r is not None:
        try:
            r.set(key, json.dumps(state), ex=_STORAGE_STATE_TTL)
            return
        except Exception as e:
            logger.warning("Browser: failed to save storage_state to Redis (%s)", e)
    _storage_local[key] = state


# ── Container lookup / creation (label-based, no in-memory state) ─────

def _resolve_container(chat_id: str):
    c = _get_client()
    if c is None or not chat_id:
        return None
    try:
        matches = c.containers.list(
            filters={"label": [f"restai.browser_chat_id={chat_id}", "restai.browser_managed=true"]},
            limit=1,
        )
    except Exception as e:
        logger.warning("Browser container list failed for chat_id=%s: %s", chat_id, e)
        return None
    if matches and matches[0].status == "running":
        return matches[0]
    return None


def _discover_port(container) -> Optional[int]:
    try:
        binding = container.attrs["NetworkSettings"]["Ports"].get(f"{_CONTAINER_PORT}/tcp")
        if not binding:
            return None
        for b in binding:
            if b.get("HostIp") in ("127.0.0.1", "0.0.0.0", ""):
                return int(b["HostPort"])
    except Exception:
        return None
    return None


def _parse_playwright_version(image: str) -> Optional[str]:
    """Pluck Playwright version out of the image tag so the in-container
    pip install pins to the version whose browser binaries are baked in.
    Example: ``...:v1.48.0-jammy`` → ``1.48.0``. Unknown tag → None."""
    try:
        tag = image.split(":", 1)[1]
    except (IndexError, AttributeError):
        return None
    if tag.startswith("v"):
        tag = tag[1:]
    version = tag.split("-", 1)[0].split("+", 1)[0]
    parts = version.split(".")
    if len(parts) >= 2 and all(p.isdigit() for p in parts):
        return version
    return None


def _ensure_playwright_pkg(container, image: str) -> None:
    """The Microsoft Playwright image ships browser binaries but NOT the
    `playwright` pip package. Install on first create; fast (<10s)
    because PLAYWRIGHT_BROWSERS_PATH already points at the prebuilt
    Chromium so `playwright install` is skipped."""
    probe = container.exec_run(["sh", "-c", "python3 -c 'import playwright' 2>/dev/null"])
    if probe.exit_code == 0:
        return
    pin = _parse_playwright_version(image)
    pkg = f"playwright=={pin}" if pin else "playwright"
    logger.info("Browser: installing %s inside container", pkg)
    cmd = ["sh", "-c", f"pip install --quiet --break-system-packages {pkg}"]
    result = container.exec_run(cmd)
    if result.exit_code != 0:
        cmd = ["sh", "-c", f"pip install --quiet {pkg}"]
        result = container.exec_run(cmd)
    if result.exit_code != 0:
        out = (result.output or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to install {pkg} in browser container: {out.strip()}")


def _install_micro_server(container) -> None:
    with open(_MICRO_SERVER_PATH_HOST, "rb") as f:
        script_bytes = f.read()
    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT)
    info = tarfile.TarInfo(name="restai_browser/micro_server.py")
    info.size = len(script_bytes)
    info.mode = 0o644
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(script_bytes))
    tar.close()
    container.exec_run(["sh", "-c", "mkdir -p /opt"])
    ok = container.put_archive("/opt", buf.getvalue())
    if not ok:
        raise RuntimeError("Browser: failed to put_archive micro_server.py into container")


def _start_micro_server(container) -> None:
    cmd = ["sh", "-c", f"python3 {_MICRO_SERVER_PATH_CONTAINER} > /tmp/browser_server.log 2>&1 &"]
    container.exec_run(cmd, detach=True)


def _wait_healthy(host_port: int) -> None:
    deadline = time.time() + _HEALTH_TIMEOUT
    url = f"http://127.0.0.1:{host_port}/health"
    last_err = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return
        except Exception as e:
            last_err = e
        time.sleep(0.3)
    raise RuntimeError(f"Browser: micro-server health check timed out ({last_err})")


def _create_container(chat_id: str):
    c = _get_client()
    if c is None:
        raise RuntimeError("Browser runtime is not configured")
    image = (getattr(_cfg, "BROWSER_IMAGE", _DEFAULT_IMAGE) or _DEFAULT_IMAGE)
    network = (getattr(_cfg, "BROWSER_NETWORK", "bridge") or "bridge")
    logger.info("Browser: creating container for chat_id=%s", chat_id)
    from restai.instance import get_instance_id
    container = c.containers.run(
        image,
        command=["sleep", "infinity"],
        detach=True,
        labels={
            "restai.browser_managed": "true",
            "restai.browser_chat_id": chat_id,
            "restai.created_at": str(int(time.time())),
            "restai.instance_id": get_instance_id(),
        },
        mem_limit="1g",
        cpu_period=100000,
        cpu_quota=100000,
        network_mode=network,
        # Chromium needs >64M /dev/shm or tabs crash unpredictably.
        shm_size="512m",
        ports={f"{_CONTAINER_PORT}/tcp": ("127.0.0.1", None)},
        remove=True,
    )
    container.reload()
    port = _discover_port(container)
    if port is None:
        try:
            container.stop(timeout=3)
        except Exception:
            pass
        raise RuntimeError("Browser: Docker did not publish a host port")
    _install_micro_server(container)
    _ensure_playwright_pkg(container, image)
    _start_micro_server(container)
    _wait_healthy(port)
    return container, port


def _get_or_create(chat_id: str):
    container = _resolve_container(chat_id)
    if container is not None:
        port = _discover_port(container)
        if port is not None:
            return container, port
    return _create_container(chat_id)


def _chat_lock(chat_id: str) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock


def remove_container(chat_id: str) -> None:
    """Stop the per-chat container if it exists. Idempotent."""
    container = _resolve_container(chat_id)
    _drop_db_activity(chat_id)
    if container is None:
        return
    try:
        container.stop(timeout=3)
        logger.info("Browser: removed container for chat_id=%s", chat_id)
    except Exception as e:
        logger.warning("Browser: failed to stop container for chat_id=%s: %s", chat_id, e)


# ── Activity heartbeat (DB-backed, multi-worker safe) ─────────────────

def _touch_db_activity(chat_id: str, container_id: Optional[str]) -> None:
    if not chat_id:
        return
    try:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            db.upsert_browser_activity(chat_id, container_id)
        finally:
            db.db.close()
    except Exception as e:
        logger.debug("browser_chat_activity upsert failed for %s: %s", chat_id, e)


def _drop_db_activity(chat_id: str) -> None:
    if not chat_id:
        return
    try:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            db.delete_browser_activity(chat_id)
        finally:
            db.db.close()
    except Exception as e:
        logger.debug("browser_chat_activity delete failed for %s: %s", chat_id, e)


# ── Public API ────────────────────────────────────────────────────────

def call(chat_id: str, path: str, payload: Optional[dict] = None) -> dict:
    """Post JSON to the in-container micro-server and return parsed
    response. Sync — used by the synchronous browser_* tools."""
    if not chat_id:
        chat_id = "ephemeral"
    container, port = _get_or_create(chat_id)
    _touch_db_activity(chat_id, container.id)

    url = f"http://127.0.0.1:{port}{path}"
    try:
        resp = requests.post(url, json=payload or {}, timeout=90)
    except requests.exceptions.RequestException:
        # Container might have died — drop + retry once.
        remove_container(chat_id)
        container, port = _get_or_create(chat_id)
        _touch_db_activity(chat_id, container.id)
        url = f"http://127.0.0.1:{port}{path}"
        resp = requests.post(url, json=payload or {}, timeout=90)

    # Re-touch after request returns so a long browser call (e.g.
    # navigation that takes >timeout) doesn't leave a stale heartbeat
    # that the next cron tick would evict on.
    _touch_db_activity(chat_id, container.id)

    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"browser {path}: {detail}")
    return resp.json()
