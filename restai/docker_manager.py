"""Docker container manager for sandboxed command execution.

Manages per-chat containers that persist across tool calls within a
conversation. Idle container cleanup is handled by an external cron script
(crons/docker_cleanup.py), not by an internal thread.
"""
from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field

from restai import config

logger = logging.getLogger(__name__)


@dataclass
class ContainerInfo:
    container_id: str
    chat_id: str
    last_activity: float = field(default_factory=time.time)


class DockerManager:
    """Manages Docker containers keyed by chat_id for sandboxed command execution."""

    def __init__(self, docker_url: str, docker_image: str = "python:3.12-slim",
                 container_timeout: int = 900, network_mode: str = "none",
                 read_only: bool = True):
        import docker as docker_sdk
        self._client = docker_sdk.DockerClient(base_url=docker_url)
        self._image = docker_image
        self._timeout = container_timeout
        self._network_mode = network_mode
        self._read_only = read_only
        self._containers: dict[str, ContainerInfo] = {}
        self._lock = threading.Lock()

        # Verify connectivity
        try:
            self._client.ping()
            logger.info("Docker manager connected to %s", docker_url)
        except Exception as e:
            logger.error("Docker manager failed to connect to %s: %s", docker_url, e)
            raise

    def exec_command(self, chat_id: str, command: str) -> str:
        """Execute a command in the container for this chat_id.
        Creates a new container if one doesn't exist."""
        if not chat_id:
            chat_id = "ephemeral"

        container = self._get_or_create_container(chat_id)

        # Update last activity (label on the container for the cron script)
        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                info.last_activity = time.time()

        try:
            exec_result = container.exec_run(
                ["sh", "-c", command],
                demux=True,
                workdir="/home/user",
            )
            stdout = (exec_result.output[0] or b"").decode("utf-8", errors="replace")
            stderr = (exec_result.output[1] or b"").decode("utf-8", errors="replace")
            output = stdout + stderr

            # Truncate very large outputs
            if len(output) > 50000:
                output = output[:50000] + "\n... (output truncated)"

            return output if output else "(no output)"
        except Exception as e:
            logger.exception("Docker exec failed for chat_id=%s: %s", chat_id, e)
            # Container may have died — remove it so next call creates a fresh one
            self._remove_container(chat_id)
            return f"ERROR: Command execution failed: {e}"

    def run_script(self, chat_id: str, script: str, stdin_data: str = "") -> str:
        """Execute a Python script in the container by piping code via python3 -c.

        No file writes needed — avoids read-only filesystem issues.
        Returns stdout. Stderr is appended if non-empty.
        """
        if not chat_id:
            chat_id = "ephemeral"

        container = self._get_or_create_container(chat_id)

        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                info.last_activity = time.time()

        try:
            import base64
            # Encode script as base64 to avoid shell quoting issues
            b64_script = base64.b64encode(script.encode("utf-8")).decode("ascii")
            b64_stdin = base64.b64encode(stdin_data.encode("utf-8")).decode("ascii") if stdin_data else ""

            if b64_stdin:
                cmd = f'echo "{b64_stdin}" | base64 -d | python3 -c "$(echo {b64_script} | base64 -d)"'
            else:
                cmd = f'python3 -c "$(echo {b64_script} | base64 -d)"'

            exec_result = container.exec_run(
                ["sh", "-c", cmd],
                demux=True,
                workdir="/home/user",
            )
            stdout = (exec_result.output[0] or b"").decode("utf-8", errors="replace")
            stderr = (exec_result.output[1] or b"").decode("utf-8", errors="replace")

            if stderr.strip():
                return stdout + "\nSTDERR: " + stderr if stdout else "ERROR: " + stderr
            return stdout.strip() if stdout.strip() else "(no output)"
        except Exception as e:
            logger.exception("Docker run_script failed for chat_id=%s: %s", chat_id, e)
            self._remove_container(chat_id)
            return f"ERROR: Script execution failed: {e}"

    def put_files(self, chat_id: str, files: list[tuple[str, bytes]],
                  extract_to: str = "/home/user", subdir: str = "uploads") -> list[dict]:
        """Copy a batch of files into the container for this chat_id.

        ``files`` is a list of ``(filename, raw_bytes)`` tuples. We build a
        single tarball that contains a ``{subdir}/`` directory with every
        file inside it, and extract it to ``{extract_to}``. ``{extract_to}``
        must exist (it's a tmpfs mount, ``/home/user``, which is always
        present). ``{subdir}`` is created by tar extraction — no shell call
        needed, so this works on read-only root filesystems.

        Returns a manifest suitable for embedding into the LLM prompt:
        ``[{name, path, size}, ...]``.
        """
        if not files:
            return []
        if not chat_id:
            chat_id = "ephemeral"

        container = self._get_or_create_container(chat_id)

        import io
        import os
        import tarfile
        import time as _time

        # Always use the chunked-exec path: Docker's put_archive API is
        # unreliable for tmpfs-mounted targets (silent extraction into the
        # underlying rootfs layer that the tmpfs mount shadows, or 404s on
        # runtime-created subdirs). Writing via `sh -c` inside the container
        # always sees the live mount namespace, so files end up visible to
        # every subsequent `exec_run`.
        target_dir = f"{extract_to}/{subdir}"
        buf = io.BytesIO()
        manifest: list[dict] = []
        now = int(_time.time())

        tar = tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT)
        try:
            seen: set[str] = set()
            for name, data in files:
                safe = os.path.basename(name).replace("\x00", "") or "file"
                base = safe
                counter = 1
                while safe in seen:
                    stem, _, ext = base.rpartition(".")
                    safe = f"{stem}_{counter}.{ext}" if stem else f"{base}_{counter}"
                    counter += 1
                seen.add(safe)

                info = tarfile.TarInfo(name=safe)
                info.size = len(data)
                info.mtime = now
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
                manifest.append({
                    "name": safe,
                    "path": f"{target_dir}/{safe}",
                    "size": len(data),
                })
        finally:
            tar.close()

        tar_bytes = buf.getvalue()

        # Stream the tar into the container in small base64 chunks appended
        # to a staging file, then extract. Chunk size has to stay under the
        # per-argv limit (Linux MAX_ARG_STRLEN = 128 KB) because the base64
        # blob rides as a single `sh -c` argument. 64 KB raw → ~87 KB base64
        # → safely under the cap.
        import base64 as _b64
        CHUNK = 64 * 1024
        tmp_path = f"{extract_to}/_restai_upload.tar"

        try:
            res = container.exec_run(["sh", "-c", f"mkdir -p {target_dir} && : > {tmp_path}"])
            if res.exit_code != 0:
                raise RuntimeError(f"tar staging failed (exit {res.exit_code})")

            for offset in range(0, len(tar_bytes), CHUNK):
                chunk = tar_bytes[offset:offset + CHUNK]
                chunk_b64 = _b64.b64encode(chunk).decode("ascii")
                cmd = f"printf '%s' {chunk_b64} | base64 -d >> {tmp_path}"
                res = container.exec_run(["sh", "-c", cmd])
                if res.exit_code != 0:
                    err_out = (res.output or b"").decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"tar chunk write failed (exit {res.exit_code}): {err_out.strip()}"
                    )

            cmd = f"tar xf {tmp_path} -C {target_dir} && rm -f {tmp_path}"
            res = container.exec_run(["sh", "-c", cmd])
            if res.exit_code != 0:
                err_out = (res.output or b"").decode("utf-8", errors="replace")
                raise RuntimeError(f"tar extract failed (exit {res.exit_code}): {err_out.strip()}")
        except Exception as e:
            logger.exception("Failed to put files into container for chat_id=%s: %s", chat_id, e)
            raise RuntimeError(f"Failed to upload files to sandbox: {e}")

        # Sanity check: stat each file we claim to have uploaded. Cheap, and
        # catches any surprise where the tar silently extracted to nowhere.
        expected_paths = " ".join(f"'{entry['path']}'" for entry in manifest)
        check = container.exec_run(
            ["sh", "-c", f"for p in {expected_paths}; do [ -f \"$p\" ] || {{ echo MISSING:$p; exit 1; }}; done"]
        )
        if check.exit_code != 0:
            missing = (check.output or b"").decode("utf-8", errors="replace").strip()
            logger.error(
                "Upload verification failed for chat_id=%s: %s (tar=%d bytes, target=%s)",
                chat_id, missing, len(tar_bytes), target_dir,
            )
            raise RuntimeError(f"Files not present after upload: {missing}")

        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                info.last_activity = time.time()

        logger.info("Uploaded %d file(s) to chat_id=%s at %s",
                    len(manifest), chat_id, target_dir)
        return manifest

    def _get_or_create_container(self, chat_id: str):
        """Return existing container or create a new one."""
        import docker as docker_sdk

        with self._lock:
            info = self._containers.get(chat_id)
            if info:
                try:
                    container = self._client.containers.get(info.container_id)
                    if container.status == "running":
                        return container
                except docker_sdk.errors.NotFound:
                    pass
                del self._containers[chat_id]

        # Also check for orphaned containers from a previous process
        try:
            existing = self._client.containers.list(
                filters={"label": [f"restai.chat_id={chat_id}"]},
                limit=1,
            )
            if existing and existing[0].status == "running":
                container = existing[0]
                with self._lock:
                    self._containers[chat_id] = ContainerInfo(
                        container_id=container.id,
                        chat_id=chat_id,
                    )
                return container
        except Exception:
            pass

        # Create new container
        try:
            container = self._client.containers.run(
                self._image,
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
                network_mode=self._network_mode,
                # Roomy tmpfs so the LLM can `pip install` modest packages
                # (pandas wheel ~60MB + build/temp space) and drop result
                # files without hitting ENOSPC.
                tmpfs={"/tmp": "size=1G", "/home/user": "size=1G"},
                # Rootfs read-only by default for sandbox hardening. Toggled
                # via the `docker_read_only` admin setting — admins can flip
                # to false when they need `pip install` inside the sandbox.
                read_only=self._read_only,
                remove=True,
            )
            with self._lock:
                self._containers[chat_id] = ContainerInfo(
                    container_id=container.id,
                    chat_id=chat_id,
                )
            logger.info("Created container %s for chat_id=%s", container.short_id, chat_id)
            return container
        except Exception as e:
            logger.exception("Failed to create container for chat_id=%s: %s", chat_id, e)
            raise RuntimeError(f"Failed to create sandbox container: {e}")

    def _remove_container(self, chat_id: str):
        """Stop and remove a container by chat_id."""
        with self._lock:
            info = self._containers.pop(chat_id, None)
        if not info:
            return
        try:
            container = self._client.containers.get(info.container_id)
            container.stop(timeout=5)
            logger.info("Removed container %s for chat_id=%s", info.container_id[:12], chat_id)
        except Exception:
            pass

    def shutdown(self):
        """Remove all managed containers. Called on app shutdown."""
        with self._lock:
            chat_ids = list(self._containers.keys())

        for chat_id in chat_ids:
            self._remove_container(chat_id)

        logger.info("Docker manager shut down, removed %d containers", len(chat_ids))

    @property
    def active_container_count(self) -> int:
        with self._lock:
            return len(self._containers)
