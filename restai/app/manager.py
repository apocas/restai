"""Per-project Docker container lifecycle for the App Builder.

Mirrors :mod:`restai.browser.manager.BrowserManager`: each project gets one
running container, labelled and discoverable so a worker restart (or
multi-worker uvicorn) can re-attach instead of spawning duplicates. Key
differences from BrowserManager:

- Keyed by ``project_id``, not ``chat_id`` — apps live longer than chats.
- The project's source tree is **bind-mounted** as ``/var/www`` (instead of
  shipped via ``put_archive``) so IDE saves are visible to the running PHP
  server immediately, no redeploy step.
- No in-container micro-server; the image's entrypoint runs ``php -S`` plus
  ``esbuild --watch`` directly. Healthcheck is just an HTTP GET on the
  published port.

Local Docker only — bind mounts don't traverse to a remote daemon's host.
The startup guard in :mod:`restai.main` refuses to enable the feature
when ``DOCKER_URL`` is ``tcp://...``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# PHP -S inside the container. Port > 1024 so the container can run as the
# non-root host UID without needing CAP_NET_BIND_SERVICE.
_CONTAINER_PORT = 8080
_HEALTH_TIMEOUT = 30  # seconds to wait for php -S to bind


@dataclass
class _ContainerInfo:
    container_id: str
    project_id: int
    host_port: int
    last_activity: float = field(default_factory=time.time)


class AppManager:
    """Manages per-project PHP+TS preview containers.

    The Docker daemon is the source of truth — never trust ``self._containers``
    alone. Every ``get_or_create`` does a label-list reconciliation so a
    second worker can pick up a container created by the first.
    """

    def __init__(
        self,
        docker_url: str,
        image: str = "restai/app-runtime:1",
        idle_timeout: int = 1800,
    ):
        import docker as docker_sdk
        self._client = docker_sdk.DockerClient(base_url=docker_url)
        self._image = image
        self._idle_timeout = idle_timeout
        self._containers: dict[int, _ContainerInfo] = {}
        self._lock = threading.Lock()
        # Per-project asyncio locks so two parallel preview requests don't
        # race-create two containers. Lazily populated.
        self._project_locks: dict[int, asyncio.Lock] = {}

        try:
            self._client.ping()
            logger.info("AppManager connected to %s", docker_url)
        except Exception as e:
            logger.error("AppManager failed to connect to %s: %s", docker_url, e)
            raise

    # ── Container lifecycle ──────────────────────────────────────────

    async def get_or_create(self, project_id: int):
        """Return ``(container, host_port)``. Idempotent; safe under
        concurrent callers thanks to the per-project asyncio lock."""
        pid = int(project_id)
        async with self._project_lock(pid):
            return self._get_or_create_sync(pid)

    def _project_lock(self, project_id: int) -> asyncio.Lock:
        lock = self._project_locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._project_locks[project_id] = lock
        return lock

    def _get_or_create_sync(self, project_id: int):
        # 1) In-process cache
        with self._lock:
            info = self._containers.get(project_id)
        if info:
            try:
                c = self._client.containers.get(info.container_id)
                if c.status == "running":
                    self._touch(project_id)
                    return c, info.host_port
            except Exception:
                # Container is gone (NotFound) or daemon hiccupped — fall
                # through to label reconcile + cold create.
                pass
            with self._lock:
                self._containers.pop(project_id, None)

        # 2) Reconcile via label — another worker may have created it.
        try:
            existing = self._client.containers.list(
                filters={"label": [f"restai.app_project_id={project_id}"]},
                limit=1,
            )
        except Exception as e:
            logger.warning("AppManager: container list failed: %s", e)
            existing = []
        if existing and existing[0].status == "running":
            c = existing[0]
            port = self._discover_port(c)
            if port is not None:
                with self._lock:
                    self._containers[project_id] = _ContainerInfo(
                        container_id=c.id, project_id=project_id, host_port=port,
                    )
                self._touch(project_id)
                return c, port

        # 3) Cold create.
        return self._create(project_id)

    def _create(self, project_id: int):
        import os as _os
        from restai.app.storage import ensure_project_root
        root = ensure_project_root(project_id)
        # Resolve so the bind mount is canonical (defends against symlinks
        # in <apps_root> messing with Docker's path validation).
        host_path = str(root.resolve())

        # Run the container as the host UID/GID that owns the bind mount.
        # If we don't, the container's root user creates `public/dist/app.js`
        # (esbuild output) as host-root, and the IDE/host can't delete it
        # afterwards. Linux's default Docker has no user-namespace remap so
        # numeric IDs match 1:1 between host and container.
        st = _os.stat(host_path)
        run_user = f"{st.st_uid}:{st.st_gid}"

        logger.info(
            "AppManager: creating container for project=%s mount=%s image=%s user=%s",
            project_id, host_path, self._image, run_user,
        )
        container = self._client.containers.run(
            self._image,
            detach=True,
            user=run_user,
            labels={
                "restai.app_managed": "true",
                "restai.app_project_id": str(project_id),
                "restai.created_at": str(int(time.time())),
            },
            mem_limit="512m",
            cpu_period=100000,
            cpu_quota=50000,  # 0.5 CPU
            # Bridge network so the generated app can fetch local resources;
            # the container is bound to 127.0.0.1 on the host so it isn't
            # reachable externally.
            network_mode="bridge",
            ports={f"{_CONTAINER_PORT}/tcp": ("127.0.0.1", None)},
            volumes={host_path: {"bind": "/var/www", "mode": "rw"}},
            remove=True,
        )
        container.reload()
        port = self._discover_port(container)
        if port is None:
            try:
                container.stop(timeout=3)
            except Exception:
                pass
            raise RuntimeError("AppManager: Docker did not publish a host port for the container")

        try:
            self._wait_healthy(port)
        except Exception:
            try:
                container.stop(timeout=3)
            except Exception:
                pass
            raise

        with self._lock:
            self._containers[project_id] = _ContainerInfo(
                container_id=container.id, project_id=project_id, host_port=port,
            )
        return container, port

    def _discover_port(self, container) -> Optional[int]:
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

    def _wait_healthy(self, host_port: int) -> None:
        deadline = time.time() + _HEALTH_TIMEOUT
        url = f"http://127.0.0.1:{host_port}/"
        last_err = None
        while time.time() < deadline:
            try:
                # Any HTTP response (200, 404, 500) means php -S is up. We
                # don't care about the body — even a missing index.php
                # returns 404 from PHP itself, which is good enough.
                resp = requests.get(url, timeout=2)
                if resp.status_code:
                    return
            except Exception as e:
                last_err = e
            time.sleep(0.3)
        raise RuntimeError(f"AppManager: container health check timed out ({last_err})")

    def _touch(self, project_id: int) -> None:
        """Update ``last_activity`` in-process. Cron consumes the Docker
        label for cross-worker eviction; this is the in-process cache hint."""
        with self._lock:
            info = self._containers.get(project_id)
            if info:
                info.last_activity = time.time()

    # ── Admin operations ─────────────────────────────────────────────

    async def restart(self, project_id: int):
        """Stop + recreate the container. Useful when settings change or
        the user explicitly asks. Returns the new ``(container, port)``."""
        self._remove(project_id)
        return await self.get_or_create(project_id)

    def _remove(self, project_id: int):
        with self._lock:
            info = self._containers.pop(int(project_id), None)
        # Even if the in-process cache was empty, still try to find by label —
        # another worker may have created the container.
        try:
            existing = self._client.containers.list(
                filters={"label": [f"restai.app_project_id={int(project_id)}"]},
            )
            for c in existing:
                try:
                    c.stop(timeout=3)
                    logger.info("AppManager: removed container for project=%s (%s)", project_id, c.short_id)
                except Exception as e:
                    logger.warning("AppManager: failed to stop %s: %s", c.short_id, e)
        except Exception as e:
            logger.warning("AppManager: container reconcile during remove failed: %s", e)

    def shutdown(self):
        with self._lock:
            ids = list(self._containers.keys())
        for project_id in ids:
            self._remove(project_id)
        logger.info("AppManager shut down (%d container(s))", len(ids))

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._containers)

    def get_port(self, project_id: int) -> Optional[int]:
        """Read-only lookup of the cached port. Doesn't create. Used by the
        proxy router after a get_or_create has already been done."""
        with self._lock:
            info = self._containers.get(int(project_id))
            return info.host_port if info else None
