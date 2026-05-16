"""Stateless per-chat Docker sandbox.

Replacement for the old `restai/docker_manager.py` class. Was refactored
out because the in-memory `_containers` dict and accompanying lifecycle
(`init`, `shutdown`, orphan sweep) duplicated state we already keep in
the `docker_chat_activity` DB row, drifted across uvicorn workers, and
caused the killed-container bugs from May 2026 (workers race on the
same chat, `init_docker_manager` from a settings change nukes in-flight
chats, etc.).

Now: a flat module of functions. The Docker daemon is the source of
truth for "does this chat have a container" — we look it up by the
`restai.chat_id` label per call (~5ms). The Docker client connection
is cached as a module-level lazy singleton (one TCP keepalive per
worker, same as before).

Settings are read live via `restai.config` on every call, so admin
changes to `docker_image` / `docker_network` / `docker_read_only` /
`docker_timeout` take effect on the next call without any reinit.
Existing chats keep their container until the cleanup cron evicts it
on idle.
"""
from __future__ import annotations

import base64 as _b64
import logging
import time
from typing import Optional

import docker as _docker_sdk
import docker.errors as _derrors

from restai import config as _cfg

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

ARTIFACTS_DIR = "/artifacts"
_SEEN_FILE = f"{ARTIFACTS_DIR}/.seen"
MAX_OUTPUT = 50_000
ARTIFACT_MAX_BYTES_PER_FILE = 10 * 1024 * 1024
ARTIFACT_MAX_BYTES_PER_SCAN = 50 * 1024 * 1024
PUT_FILES_CHUNK = 64 * 1024  # tar chunk for upload, < MAX_ARG_STRLEN

# ── Client (lazy singleton) ───────────────────────────────────────────

_client: Optional[_docker_sdk.DockerClient] = None
_client_url: str = ""


def _get_client() -> Optional[_docker_sdk.DockerClient]:
    """Return a connected DockerClient, or None if Docker isn't configured.
    Cached per-process; rebuilt on `docker_url` change."""
    global _client, _client_url
    if not is_enabled():
        return None
    url = (getattr(_cfg, "DOCKER_URL", "") or "").strip()
    if _client is not None and _client_url == url:
        return _client
    try:
        _client = _docker_sdk.DockerClient(base_url=url)
        _client_url = url
        logger.info("Docker client connected to %s", url)
    except Exception as e:
        logger.error("Docker client failed to connect to %s: %s", url, e)
        _client = None
        _client_url = ""
    return _client


def is_enabled() -> bool:
    if not bool(getattr(_cfg, "DOCKER_ENABLED", False)):
        return False
    return bool((getattr(_cfg, "DOCKER_URL", "") or "").strip())


def client_info() -> dict:
    """Server info from the docker daemon, for the admin connection-test
    endpoint. Raises if not connectable."""
    c = _get_client()
    if c is None:
        raise RuntimeError("Docker is not configured")
    return c.info()


# ── Container lookup / creation (label-based, no in-memory state) ─────

def _resolve_container(chat_id: str):
    """Return the running container for this chat_id, or None.
    Looked up by the `restai.chat_id=<id>` label every call — Docker
    daemon is the source of truth, no in-memory tracking."""
    c = _get_client()
    if c is None or not chat_id:
        return None
    try:
        matches = c.containers.list(
            filters={"label": [f"restai.chat_id={chat_id}", "restai.managed=true"]},
            limit=1,
        )
    except Exception as e:
        logger.warning("Docker container list failed for chat_id=%s: %s", chat_id, e)
        return None
    if matches and matches[0].status == "running":
        return matches[0]
    return None


def _create_container(chat_id: str):
    """Spin up a fresh per-chat container with current settings."""
    c = _get_client()
    if c is None:
        raise RuntimeError("Docker is not configured")
    image = getattr(_cfg, "DOCKER_IMAGE", "python:3.12-slim") or "python:3.12-slim"
    network = getattr(_cfg, "DOCKER_NETWORK", "none") or "none"
    read_only = bool(getattr(_cfg, "DOCKER_READ_ONLY", True))
    container = c.containers.run(
        image,
        command="tail -f /dev/null",
        detach=True,
        labels={
            "restai.managed": "true",
            "restai.chat_id": chat_id,
            "restai.created_at": str(int(time.time())),
        },
        mem_limit="512m",
        cpu_period=100000,
        cpu_quota=50000,
        network_mode=network,
        tmpfs={"/tmp": "size=1G", "/home/user": "size=1G"},
        read_only=read_only,
        remove=True,
    )
    logger.info("Created container %s for chat_id=%s", container.short_id, chat_id)
    return container


def _get_or_create(chat_id: str):
    container = _resolve_container(chat_id)
    if container is not None:
        return container
    return _create_container(chat_id)


def _container_is_dead(container) -> bool:
    """True only when Docker confirms not-running. Default False (keep
    alive) on inspection errors — spurious removal is the bug we avoid."""
    try:
        container.reload()
        return container.status != "running"
    except Exception:
        return False


def remove_container(chat_id: str) -> None:
    """Stop the per-chat container if it exists. Idempotent."""
    container = _resolve_container(chat_id)
    if container is None:
        _drop_db_activity(chat_id)
        return
    try:
        container.stop(timeout=5)
        logger.info("Removed container %s for chat_id=%s", container.short_id, chat_id)
    except Exception as e:
        logger.warning("Failed to stop container for chat_id=%s: %s", chat_id, e)
    _drop_db_activity(chat_id)


# ── Activity heartbeat (DB-backed, multi-worker safe) ─────────────────

def _touch_db_activity(chat_id: str, container_id: Optional[str]) -> None:
    if not chat_id:
        return
    try:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            db.upsert_docker_activity(chat_id, container_id)
        finally:
            db.db.close()
    except Exception as e:
        logger.debug("docker_chat_activity upsert failed for %s: %s", chat_id, e)


def _drop_db_activity(chat_id: str) -> None:
    if not chat_id:
        return
    try:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            db.delete_docker_activity(chat_id)
        finally:
            db.db.close()
    except Exception as e:
        logger.debug("docker_chat_activity delete failed for %s: %s", chat_id, e)


# ── Exec helpers ──────────────────────────────────────────────────────

def _exec_with_retry(chat_id: str, container, command_argv, **exec_kwargs):
    """One retry on transient OCI errors (setns, runc blips). Caller
    decides what to do on final failure."""
    last_err = None
    for attempt in range(2):
        try:
            return container.exec_run(command_argv, **exec_kwargs)
        except _derrors.APIError as e:
            last_err = e
            msg = str(e).lower()
            transient = (
                "setns" in msg
                or "oci runtime exec failed" in msg
                or "executing setns process" in msg
            )
            if transient and attempt == 0:
                logger.warning(
                    "Docker exec hit transient OCI error for chat_id=%s, "
                    "retrying once: %s", chat_id, e,
                )
                time.sleep(0.5)
                continue
            break
        except Exception as e:
            last_err = e
            break
    raise last_err


# ── Public exec API (the bits agent code calls) ───────────────────────

def exec_command(chat_id: str, command: str, env: Optional[dict] = None) -> str:
    """Run a shell command in the per-chat sandbox container.

    `env` is a per-exec environment overlay — used by the terminal tool
    to inject project secrets so the LLM never sees the plaintext.
    """
    if not chat_id:
        chat_id = "ephemeral"
    container = _get_or_create(chat_id)
    _touch_db_activity(chat_id, container.id)

    exec_kwargs = {"demux": True, "workdir": "/home/user"}
    if env:
        exec_kwargs["environment"] = env

    try:
        result = _exec_with_retry(chat_id, container, ["sh", "-c", command], **exec_kwargs)
        stdout = (result.output[0] or b"").decode("utf-8", errors="replace")
        stderr = (result.output[1] or b"").decode("utf-8", errors="replace")
        output = stdout + stderr
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + "\n... (output truncated)"
        return output if output else "(no output)"
    except Exception as e:
        logger.exception("Docker exec failed for chat_id=%s: %s", chat_id, e)
        if _container_is_dead(container):
            remove_container(chat_id)
        return f"ERROR: Command execution failed: {e}"


def run_script(chat_id: str, script: str, stdin_data: str = "") -> str:
    """Pipe a Python script into the container via `python3 -c`.
    No file writes — works under read-only rootfs."""
    if not chat_id:
        chat_id = "ephemeral"
    container = _get_or_create(chat_id)
    _touch_db_activity(chat_id, container.id)

    try:
        b64_script = _b64.b64encode(script.encode("utf-8")).decode("ascii")
        b64_stdin = _b64.b64encode(stdin_data.encode("utf-8")).decode("ascii") if stdin_data else ""
        if b64_stdin:
            cmd = f'echo "{b64_stdin}" | base64 -d | python3 -c "$(echo {b64_script} | base64 -d)"'
        else:
            cmd = f'python3 -c "$(echo {b64_script} | base64 -d)"'
        result = _exec_with_retry(
            chat_id, container, ["sh", "-c", cmd],
            demux=True, workdir="/home/user",
        )
        stdout = (result.output[0] or b"").decode("utf-8", errors="replace")
        stderr = (result.output[1] or b"").decode("utf-8", errors="replace")
        if stderr.strip():
            return stdout + "\nSTDERR: " + stderr if stdout else "ERROR: " + stderr
        return stdout.strip() if stdout.strip() else "(no output)"
    except Exception as e:
        logger.exception("Docker run_script failed for chat_id=%s: %s", chat_id, e)
        if _container_is_dead(container):
            remove_container(chat_id)
        return f"ERROR: Script execution failed: {e}"


def put_files(chat_id: str, files: list[tuple[str, bytes]],
              extract_to: str = "/home/user", subdir: str = "uploads") -> list[dict]:
    """Stage a list of `(name, bytes)` tuples into `extract_to/subdir/`
    via base64-piped tar. Returns a manifest of what landed."""
    import io
    import tarfile

    if not chat_id:
        chat_id = "ephemeral"
    if not files:
        return []

    container = _get_or_create(chat_id)
    target_dir = f"{extract_to}/{subdir}"
    manifest: list[dict] = []

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files:
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
            manifest.append({"name": name, "size": len(data), "path": f"{target_dir}/{name}"})
    tar_bytes = buf.getvalue()

    tmp_path = f"{extract_to}/_restai_upload.tar"
    try:
        res = _exec_with_retry(chat_id, container,
                               ["sh", "-c", f"mkdir -p {target_dir} && : > {tmp_path}"])
        if res.exit_code != 0:
            raise RuntimeError(f"tar staging failed (exit {res.exit_code})")

        for offset in range(0, len(tar_bytes), PUT_FILES_CHUNK):
            chunk = tar_bytes[offset:offset + PUT_FILES_CHUNK]
            chunk_b64 = _b64.b64encode(chunk).decode("ascii")
            cmd = f"printf '%s' {chunk_b64} | base64 -d >> {tmp_path}"
            res = _exec_with_retry(chat_id, container, ["sh", "-c", cmd])
            if res.exit_code != 0:
                err_out = (res.output or b"").decode("utf-8", errors="replace")
                raise RuntimeError(f"tar chunk write failed (exit {res.exit_code}): {err_out.strip()}")

        cmd = f"tar xf {tmp_path} -C {target_dir} && rm -f {tmp_path}"
        res = _exec_with_retry(chat_id, container, ["sh", "-c", cmd])
        if res.exit_code != 0:
            err_out = (res.output or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"tar extract failed (exit {res.exit_code}): {err_out.strip()}")
    except Exception as e:
        logger.exception("Failed to put files into container for chat_id=%s: %s", chat_id, e)
        raise RuntimeError(f"Failed to upload files to sandbox: {e}")

    expected = " ".join(f"'{entry['path']}'" for entry in manifest)
    check = _exec_with_retry(
        chat_id, container,
        ["sh", "-c", f"for p in {expected}; do [ -f \"$p\" ] || {{ echo MISSING:$p; exit 1; }}; done"],
    )
    if check.exit_code != 0:
        missing = (check.output or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Files not present after upload: {missing}")

    _touch_db_activity(chat_id, container.id)
    logger.info("Uploaded %d file(s) to chat_id=%s at %s", len(manifest), chat_id, target_dir)
    return manifest


# ── /artifacts/ collection (dedup state lives in the container) ───────

def collect_new_artifacts(chat_id: str) -> list[dict]:
    """List + read everything new in /artifacts/ since the last call.
    Identity is `(path, mtime, size)`. Dedup state is a marker file
    inside the container (`/artifacts/.seen`) — multi-worker safe and
    naturally dies with the container."""
    if not chat_id:
        chat_id = "ephemeral"
    container = _resolve_container(chat_id)
    if container is None:
        return []

    container.exec_run(
        ["sh", "-c", f"mkdir -p {ARTIFACTS_DIR} && chmod 0777 {ARTIFACTS_DIR} 2>/dev/null; true"],
        workdir="/home/user",
    )

    # Read prior-seen identifiers from marker file inside the container.
    seen_res = container.exec_run(
        ["sh", "-c", f"cat {_SEEN_FILE} 2>/dev/null || true"],
        workdir="/home/user",
    )
    seen_payload = seen_res.output or b""
    if isinstance(seen_payload, tuple):
        seen_payload = seen_payload[0] or b""
    seen = {ln.strip() for ln in seen_payload.decode("utf-8", errors="replace").splitlines() if ln.strip()}

    # List files (skip marker), NUL-separated for filename safety.
    listing = container.exec_run(
        ["sh", "-c",
         f"find {ARTIFACTS_DIR} -type f ! -name .seen -printf '%T@ %s %P\\0' 2>/dev/null"],
        workdir="/home/user",
    )
    payload = listing.output or b""
    if isinstance(payload, tuple):
        payload = payload[0] or b""
    raw = payload.decode("utf-8", errors="replace")

    entries: list[tuple[float, int, str, str]] = []
    new_idents: list[str] = []
    for chunk in raw.split("\0"):
        if not chunk.strip():
            continue
        try:
            ts_str, size_str, rel = chunk.split(" ", 2)
            mtime, size = float(ts_str), int(size_str)
        except Exception:
            continue
        ident = f"{rel}\t{ts_str}\t{size}"
        if ident in seen:
            continue
        entries.append((mtime, size, rel, ident))
        new_idents.append(ident)
    if not entries:
        return []

    import mimetypes
    entries.sort(key=lambda e: e[0])

    artifacts: list[dict] = []
    total = 0
    for mtime, size, rel, _ident in entries:
        full = f"{ARTIFACTS_DIR}/{rel}"
        mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
        base_entry = {"name": rel, "path": full, "mime": mime, "size": size}
        if size > ARTIFACT_MAX_BYTES_PER_FILE or total + size > ARTIFACT_MAX_BYTES_PER_SCAN:
            artifacts.append({**base_entry, "bytes": None, "truncated": True})
            continue
        ex = container.exec_run(
            ["sh", "-c", f"base64 -w0 {full!r}"],
            workdir="/home/user", demux=False,
        )
        ex_out = ex.output or b""
        if isinstance(ex_out, tuple):
            ex_out = ex_out[0] or b""
        try:
            data = _b64.b64decode(ex_out, validate=False)
        except Exception:
            data = b""
        if not data:
            continue
        total += len(data)
        artifacts.append({**base_entry, "bytes": data, "truncated": False})

    # Persist updated seen set inside the container. Single-line writes
    # via printf to avoid shell escaping pitfalls; filenames with funky
    # chars become tab-separated tokens encoded above.
    if new_idents:
        all_idents = sorted(seen | set(new_idents))
        # Stream via base64 to dodge any quoting hazard.
        marker_b64 = _b64.b64encode("\n".join(all_idents).encode("utf-8")).decode("ascii")
        container.exec_run(
            ["sh", "-c", f"printf '%s' {marker_b64} | base64 -d > {_SEEN_FILE}"],
            workdir="/home/user",
        )
    return artifacts
