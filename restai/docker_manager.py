"""Docker container manager for sandboxed command execution.

Manages per-chat containers that persist across tool calls within a
conversation. Idle container cleanup is handled by an external cron script
(scripts/docker_cleanup.py), not by an internal thread.
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
                 container_timeout: int = 900, network_mode: str = "none"):
        import docker as docker_sdk
        self._client = docker_sdk.DockerClient(base_url=docker_url)
        self._image = docker_image
        self._timeout = container_timeout
        self._network_mode = network_mode
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
                tmpfs={"/tmp": "size=100M", "/home/user": "size=100M"},
                read_only=True,
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
