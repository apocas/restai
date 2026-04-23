"""Host-side BrowserManager — mirrors `DockerManager` but for Chromium
containers driven via an in-container HTTP micro-server.

Lifecycle:
- `get_or_create(chat_id)` — reuse a running container with the matching
  label or spin up a fresh one. Publishes port 7000 on a random host port
  (`127.0.0.1:<random>`), drops `micro_server.py` into `/opt/restai_browser/`
  via `put_archive`, launches it detached, and health-checks until ready.
- `call(chat_id, path, payload)` — posts JSON to the micro-server and
  returns the parsed response. Retries once on connection failures.
- `load_storage_state(chat_id, project_id, domain)` /
  `save_storage_state(...)` — Redis-backed (or in-process fallback)
  persistence of cookies/localStorage keyed by `(project_id, domain)`.
- `shutdown()` — stop every managed container on app shutdown.
"""
from __future__ import annotations

import io
import json
import logging
import os
import tarfile
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from restai import config

logger = logging.getLogger(__name__)


_CONTAINER_PORT = 7000  # inside-container port the micro-server listens on
_MICRO_SERVER_PATH_HOST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "micro_server.py")
_MICRO_SERVER_PATH_CONTAINER = "/opt/restai_browser/micro_server.py"
_HEALTH_TIMEOUT = 60  # seconds to wait for the micro-server to come up
_STORAGE_STATE_REDIS_PREFIX = "restai_browser_state:"
_STORAGE_STATE_TTL = 30 * 24 * 60 * 60  # 30 days


@dataclass
class _ContainerInfo:
    container_id: str
    chat_id: str
    host_port: int
    last_activity: float = field(default_factory=time.time)


class BrowserManager:
    """Manages per-chat Playwright/Chromium containers."""

    def __init__(
        self,
        docker_url: str,
        image: str = "mcr.microsoft.com/playwright/python:v1.48.0-jammy",
        network: str = "bridge",
        timeout: int = 900,
    ):
        import docker as docker_sdk
        self._client = docker_sdk.DockerClient(base_url=docker_url)
        self._image = image
        self._network = network
        self._timeout = timeout
        self._containers: dict[str, _ContainerInfo] = {}
        self._lock = threading.Lock()
        self._storage_local: dict[str, dict] = {}  # fallback when Redis isn't configured
        self._storage_redis_client = None
        self._storage_redis_url: Optional[str] = None

        try:
            self._client.ping()
            logger.info("BrowserManager connected to %s", docker_url)
        except Exception as e:
            logger.error("BrowserManager failed to connect to %s: %s", docker_url, e)
            raise

    # ── Redis client for storage-state persistence ───────────────────

    def _redis(self):
        url = config.build_redis_url()
        if not url:
            if self._storage_redis_client is not None:
                try:
                    self._storage_redis_client.close()
                except Exception:
                    pass
                self._storage_redis_client = None
                self._storage_redis_url = None
            return None
        if self._storage_redis_client is not None and self._storage_redis_url == url:
            return self._storage_redis_client
        try:
            import redis  # sync client
            self._storage_redis_client = redis.Redis.from_url(url)
            self._storage_redis_url = url
        except Exception as e:
            logger.warning("BrowserManager: Redis unavailable (%s); using in-process storage-state fallback", e)
            return None
        return self._storage_redis_client

    def load_storage_state(self, project_id: int, domain: str) -> Optional[dict]:
        key = f"{_STORAGE_STATE_REDIS_PREFIX}{project_id}:{domain}"
        r = self._redis()
        if r is not None:
            try:
                raw = r.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning("BrowserManager: failed to load storage_state from Redis (%s)", e)
        return self._storage_local.get(key)

    def save_storage_state(self, project_id: int, domain: str, state: dict) -> None:
        key = f"{_STORAGE_STATE_REDIS_PREFIX}{project_id}:{domain}"
        r = self._redis()
        if r is not None:
            try:
                r.set(key, json.dumps(state), ex=_STORAGE_STATE_TTL)
                return
            except Exception as e:
                logger.warning("BrowserManager: failed to save storage_state to Redis (%s)", e)
        self._storage_local[key] = state

    # ── Container lifecycle ──────────────────────────────────────────

    def get_or_create(self, chat_id: str):
        """Return ``(container, host_port)``. Creates the container +
        starts the micro-server if none exists for this chat_id."""
        if not chat_id:
            chat_id = "ephemeral"

        import docker as docker_sdk

        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                try:
                    c = self._client.containers.get(info.container_id)
                    if c.status == "running":
                        info.last_activity = time.time()
                        return c, info.host_port
                except docker_sdk.errors.NotFound:
                    pass
                del self._containers[chat_id]

        # Look for an orphaned container left by a previous process.
        try:
            existing = self._client.containers.list(
                filters={"label": [f"restai.browser_chat_id={chat_id}"]},
                limit=1,
            )
            if existing and existing[0].status == "running":
                c = existing[0]
                port = self._discover_port(c)
                if port is not None:
                    with self._lock:
                        self._containers[chat_id] = _ContainerInfo(
                            container_id=c.id, chat_id=chat_id, host_port=port,
                        )
                    return c, port
        except Exception:
            pass

        # Create new.
        return self._create(chat_id)

    def _create(self, chat_id: str):
        logger.info("BrowserManager: creating container for chat_id=%s", chat_id)
        # Port 7000 inside → Docker-picked free port on 127.0.0.1.
        container = self._client.containers.run(
            self._image,
            command=["sleep", "infinity"],
            detach=True,
            labels={
                "restai.browser_managed": "true",
                "restai.browser_chat_id": chat_id,
                "restai.created_at": str(int(time.time())),
            },
            mem_limit="1g",       # Chromium is hungry
            cpu_period=100000,
            cpu_quota=100000,     # 1 CPU max
            network_mode=self._network,
            # Chromium wants /dev/shm larger than Docker's 64 MB default,
            # otherwise tabs crash unpredictably.
            shm_size="512m",
            ports={f"{_CONTAINER_PORT}/tcp": ("127.0.0.1", None)},
            remove=True,
        )
        # Fetch assigned host port (requires a reload because docker run
        # returns before port mapping finalizes).
        container.reload()
        port = self._discover_port(container)
        if port is None:
            container.stop(timeout=3)
            raise RuntimeError("BrowserManager: Docker did not publish a host port for the container.")

        # Drop the micro-server into /opt/restai_browser/ and start it.
        self._install_micro_server(container)
        self._ensure_playwright_pkg(container)
        self._start_micro_server(container)
        self._wait_healthy(port)

        with self._lock:
            self._containers[chat_id] = _ContainerInfo(
                container_id=container.id, chat_id=chat_id, host_port=port,
            )
        return container, port

    def _discover_port(self, container) -> Optional[int]:
        try:
            binding = container.attrs["NetworkSettings"]["Ports"].get(f"{_CONTAINER_PORT}/tcp")
            if not binding:
                return None
            # Take the first 127.0.0.1 binding.
            for b in binding:
                if b.get("HostIp") in ("127.0.0.1", "0.0.0.0", ""):
                    return int(b["HostPort"])
        except Exception:
            return None
        return None

    def _parse_playwright_version(self) -> Optional[str]:
        """Pluck the Playwright version out of the image tag so the pip
        install pins to the exact version whose browser binaries are
        baked into the image. Example:
        `mcr.microsoft.com/playwright/python:v1.48.0-jammy` → `1.48.0`.
        Returns None for unrecognized tags; the bootstrap then installs
        the latest PyPI release."""
        try:
            tag = self._image.split(":", 1)[1]
        except (IndexError, AttributeError):
            return None
        if tag.startswith("v"):
            tag = tag[1:]
        version = tag.split("-", 1)[0].split("+", 1)[0]
        parts = version.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts):
            return version
        return None

    def _ensure_playwright_pkg(self, container) -> None:
        """The Microsoft Playwright image ships the browser binaries at
        `/ms-playwright/` but NOT the `playwright` pip package — it's
        meant for CI where users bind-mount their own venv. For our
        standalone use we pip-install it inside the container on first
        create. Fast (< 10s) because `PLAYWRIGHT_BROWSERS_PATH` already
        points at the pre-downloaded Chromium, so `playwright install`
        is skipped."""
        # Skip if already importable (re-used container).
        probe = container.exec_run(["sh", "-c", "python3 -c 'import playwright' 2>/dev/null"])
        if probe.exit_code == 0:
            return

        pin = self._parse_playwright_version()
        pkg = f"playwright=={pin}" if pin else "playwright"
        logger.info("BrowserManager: installing %s inside the container", pkg)
        # --break-system-packages because the image uses the system Python
        # with PEP 668 guardrails. --quiet keeps the log short.
        cmd = ["sh", "-c", f"pip install --quiet --break-system-packages {pkg}"]
        result = container.exec_run(cmd)
        if result.exit_code != 0:
            # Try without --break-system-packages as a fallback for older images.
            cmd = ["sh", "-c", f"pip install --quiet {pkg}"]
            result = container.exec_run(cmd)
        if result.exit_code != 0:
            out = (result.output or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"Failed to install {pkg} in the browser container: {out.strip()}")

    def _install_micro_server(self, container) -> None:
        """Tar-and-put_archive the micro_server.py script into /opt/."""
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

        # Make sure /opt exists, put_archive extracts there.
        container.exec_run(["sh", "-c", "mkdir -p /opt"])
        ok = container.put_archive("/opt", buf.getvalue())
        if not ok:
            raise RuntimeError("BrowserManager: failed to put_archive micro_server.py into container")

    def _start_micro_server(self, container) -> None:
        """Detached `python /opt/restai_browser/micro_server.py`."""
        # The Playwright image ships `python3` on PATH.
        cmd = ["sh", "-c", f"python3 {_MICRO_SERVER_PATH_CONTAINER} > /tmp/browser_server.log 2>&1 &"]
        container.exec_run(cmd, detach=True)

    def _wait_healthy(self, host_port: int) -> None:
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
        raise RuntimeError(f"BrowserManager: micro-server health check timed out ({last_err})")

    # ── RPC ──────────────────────────────────────────────────────────

    def call(self, chat_id: str, path: str, payload: Optional[dict] = None) -> dict:
        """Post JSON to the micro-server and return the parsed response."""
        container, port = self.get_or_create(chat_id)
        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                info.last_activity = time.time()

        url = f"http://127.0.0.1:{port}{path}"
        try:
            resp = requests.post(url, json=payload or {}, timeout=90)
        except requests.exceptions.RequestException as e:
            # Container might have died — drop + retry once.
            self._remove(chat_id)
            container, port = self.get_or_create(chat_id)
            url = f"http://127.0.0.1:{port}{path}"
            resp = requests.post(url, json=payload or {}, timeout=90)

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            raise RuntimeError(f"browser {path}: {detail}")
        return resp.json()

    def _remove(self, chat_id: str):
        with self._lock:
            info = self._containers.pop(chat_id, None)
        if not info:
            return
        try:
            c = self._client.containers.get(info.container_id)
            c.stop(timeout=3)
            logger.info("BrowserManager: removed container for chat_id=%s", chat_id)
        except Exception:
            pass

    def shutdown(self):
        with self._lock:
            ids = list(self._containers.keys())
        for chat_id in ids:
            self._remove(chat_id)
        logger.info("BrowserManager shut down (%d container(s))", len(ids))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._containers)
