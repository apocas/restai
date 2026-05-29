"""Stateless per-project App-Builder runtime.

Flat module of functions; the Docker daemon is source-of-truth for
container existence (looked up by `restai.app_project_id` label per call).
Settings read live from restai.config — admin changes take effect on next call.

Bind-mount-based (project source at /var/www) — local Docker daemon only;
bind paths don't traverse to remote tcp:// daemons. is_enabled() enforces this.
"""

from __future__ import annotations

import asyncio
import logging
import os as _os
import threading
import time
from typing import Optional

import docker as _docker_sdk
import requests

from restai import config as _cfg

logger = logging.getLogger(__name__)


# PHP -S inside the container. Port > 1024 so the container can run as
# the non-root host UID without CAP_NET_BIND_SERVICE.
_CONTAINER_PORT = 8080
_HEALTH_TIMEOUT = 30
_DEFAULT_IMAGE = "restai/app-runtime:2"

_client: Optional[_docker_sdk.DockerClient] = None
_client_url: str = ""
_client_lock = threading.Lock()

# Per-project asyncio lock so two parallel preview requests don't
# race-create two containers. Lazily populated.
_project_locks: dict[int, asyncio.Lock] = {}


def is_enabled() -> bool:
    if not bool(getattr(_cfg, "APP_DOCKER_ENABLED", False)):
        return False
    url = (getattr(_cfg, "DOCKER_URL", "") or "").strip()
    if not url:
        return False
    # App requires a *local* Docker socket — bind mounts don't traverse
    # to a remote daemon's host. The cron and project-create endpoint
    # apply the same guard.
    if url.startswith("tcp://"):
        return False
    return True


def _get_client() -> Optional[_docker_sdk.DockerClient]:
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
            logger.info("App Docker client connected to %s", url)
        except Exception as e:
            logger.error("App Docker client failed to connect to %s: %s", url, e)
            _client = None
            _client_url = ""
        return _client


def _resolve_container(project_id: int):
    c = _get_client()
    if c is None:
        return None
    try:
        matches = c.containers.list(
            filters={"label": [f"restai.app_project_id={int(project_id)}", "restai.app_managed=true"]},
            limit=1,
        )
    except Exception as e:
        logger.warning("App container list failed for project=%s: %s", project_id, e)
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


def _wait_healthy(host_port: int) -> None:
    deadline = time.time() + _HEALTH_TIMEOUT
    url = f"http://127.0.0.1:{host_port}/"
    last_err = None
    while time.time() < deadline:
        try:
            # Any HTTP response (200/404/500) means php -S is up.
            resp = requests.get(url, timeout=2)
            if resp.status_code:
                return
        except Exception as e:
            last_err = e
        time.sleep(0.3)
    raise RuntimeError(f"App: container health check timed out ({last_err})")


def _create_container(project_id: int):
    c = _get_client()
    if c is None:
        raise RuntimeError("App runtime is not configured")
    image = (getattr(_cfg, "APP_DOCKER_IMAGE", _DEFAULT_IMAGE) or _DEFAULT_IMAGE)

    from restai.app.storage import ensure_project_root
    root = ensure_project_root(project_id)
    host_path = str(root.resolve())

    # Run as the host UID/GID that owns the bind mount; otherwise
    # esbuild (running as container-root) writes ``public/dist/app.js``
    # as host-root and the IDE/host can't delete it. Linux's default
    # docker has no userns remap so numeric IDs match 1:1.
    st = _os.stat(host_path)
    run_user = f"{st.st_uid}:{st.st_gid}"

    logger.info(
        "App: creating container project=%s mount=%s image=%s user=%s",
        project_id, host_path, image, run_user,
    )
    from restai.observability.instance import get_instance_id
    container = c.containers.run(
        image,
        detach=True,
        user=run_user,
        labels={
            "restai.app_managed": "true",
            "restai.app_project_id": str(int(project_id)),
            "restai.created_at": str(int(time.time())),
            "restai.observability.instance_id": get_instance_id(),
        },
        mem_limit="512m",
        cpu_period=100000,
        cpu_quota=50000,
        # Bridge so the generated app can fetch local resources;
        # bound to 127.0.0.1 on the host so it isn't externally reachable.
        network_mode="bridge",
        ports={f"{_CONTAINER_PORT}/tcp": ("127.0.0.1", None)},
        volumes={host_path: {"bind": "/var/www", "mode": "rw"}},
        remove=True,
    )
    container.reload()
    port = _discover_port(container)
    if port is None:
        try:
            container.stop(timeout=3)
        except Exception:
            pass
        raise RuntimeError("App: Docker did not publish a host port")
    try:
        _wait_healthy(port)
    except Exception:
        try:
            container.stop(timeout=3)
        except Exception:
            pass
        raise
    return container, port


def _project_lock(project_id: int) -> asyncio.Lock:
    lock = _project_locks.get(int(project_id))
    if lock is None:
        lock = asyncio.Lock()
        _project_locks[int(project_id)] = lock
    return lock


def remove_container(project_id: int) -> None:
    """Stop the per-project container if it exists. Idempotent. Sync."""
    c = _get_client()
    if c is None:
        return
    try:
        existing = c.containers.list(
            filters={"label": [f"restai.app_project_id={int(project_id)}"]},
        )
    except Exception as e:
        logger.warning("App: container reconcile during remove failed: %s", e)
        return
    for container in existing:
        try:
            container.stop(timeout=3)
            logger.info("App: removed container for project=%s (%s)", project_id, container.short_id)
        except Exception as e:
            logger.warning("App: failed to stop %s: %s", container.short_id, e)


async def get_or_create(project_id: int):
    """Returns (container, host_port). Per-project asyncio lock ensures safety."""
    pid = int(project_id)
    async with _project_lock(pid):
        container = _resolve_container(pid)
        if container is not None:
            port = _discover_port(container)
            if port is not None:
                return container, port
        return _create_container(pid)


async def restart(project_id: int):
    """Stop + recreate. Returns new (container, port)."""
    remove_container(project_id)
    return await get_or_create(project_id)


def get_port(project_id: int) -> Optional[int]:
    """Read-only host-port lookup. Does not create."""
    container = _resolve_container(project_id)
    if container is None:
        return None
    return _discover_port(container)


def get_container(project_id: int):
    """Live Container for direct exec calls; None when nothing's running."""
    return _resolve_container(project_id)


def get_docker_client() -> Optional[_docker_sdk.DockerClient]:
    return _get_client()


def touch(project_id: int) -> None:  # noqa: ARG001
    # No-op kept for API compatibility — cleanup cron evicts by container
    # created_at label, not last-activity.
    return None
