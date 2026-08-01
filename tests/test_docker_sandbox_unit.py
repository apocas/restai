"""Unit tests for restai/docker.py — the stateless per-chat Docker sandbox.

The `docker` SDK client is replaced by in-memory fakes; no daemon, no
network, no real containers. DB activity helpers are stubbed out.
"""
import base64
import types

import docker.errors as derrors
import pytest

import restai.config as cfg
import restai.docker as rd


# ─── fakes ──────────────────────────────────────────────────────────────

class ExecResult:
    def __init__(self, exit_code=0, output=(b"", b"")):
        self.exit_code = exit_code
        self.output = output


class FakeContainer:
    def __init__(self, handler=None, status="running", cid="c0ffee00"):
        self.status = status
        self.id = cid
        self.short_id = cid[:6]
        self.handler = handler
        self.exec_calls = []
        self.stopped = False
        self.stop_raises = False

    def exec_run(self, cmd, **kw):
        self.exec_calls.append((cmd, kw))
        if self.handler:
            return self.handler(cmd, kw)
        return ExecResult()

    def stop(self, timeout=None):
        if self.stop_raises:
            raise RuntimeError("stop failed")
        self.stopped = True


class FakeContainers:
    def __init__(self, existing=None, run_result=None):
        self.existing = list(existing or [])
        self.run_result = run_result
        self.run_calls = []
        self.list_calls = []
        self.list_raises = False
        self.run_raises = False

    def list(self, filters=None, limit=None):
        if self.list_raises:
            raise RuntimeError("daemon unreachable")
        self.list_calls.append(filters)
        return self.existing

    def run(self, image, **kw):
        if self.run_raises:
            raise RuntimeError("cannot create container")
        self.run_calls.append((image, kw))
        return self.run_result or FakeContainer()


class FakeClient:
    def __init__(self, containers):
        self.containers = containers

    def info(self):
        return {"ServerVersion": "fake-1.0"}


class FakeDBWrapper:
    upserts = []
    deletes = []

    def __init__(self):
        self.db = types.SimpleNamespace(close=lambda: None)

    def upsert_docker_activity(self, chat_id, container_id):
        FakeDBWrapper.upserts.append((chat_id, container_id))

    def delete_docker_activity(self, chat_id):
        FakeDBWrapper.deletes.append(chat_id)


@pytest.fixture
def docker_env(monkeypatch, tmp_path):
    """Enable docker, install a fake cached client, stub DB activity."""
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://fake:2375", raising=False)
    monkeypatch.setattr(cfg, "DOCKER_IMAGE", "python:3.12-slim", raising=False)
    monkeypatch.setattr(cfg, "DOCKER_NETWORK", "none", raising=False)
    monkeypatch.setattr(cfg, "DOCKER_READ_ONLY", True, raising=False)
    monkeypatch.setenv("RESTAI_AGENT_WORKSPACE_ROOT", str(tmp_path))

    containers = FakeContainers()
    client = FakeClient(containers)
    monkeypatch.setattr(rd, "_client", client)
    monkeypatch.setattr(rd, "_client_url", "tcp://fake:2375")

    import restai.database as rdb
    FakeDBWrapper.upserts = []
    FakeDBWrapper.deletes = []
    monkeypatch.setattr(rdb, "open_db_wrapper", lambda: FakeDBWrapper())
    return client


# ─── is_enabled / client plumbing ───────────────────────────────────────

def test_is_enabled_false_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", False, raising=False)
    assert rd.is_enabled() is False


def test_is_enabled_false_without_url(monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "DOCKER_URL", "   ", raising=False)
    assert rd.is_enabled() is False


def test_is_enabled_true(docker_env):
    assert rd.is_enabled() is True


def test_get_client_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", False, raising=False)
    assert rd._get_client() is None


def test_get_client_cached(docker_env):
    assert rd._get_client() is docker_env


def test_get_client_rebuilds_on_url_change(docker_env, monkeypatch):
    built = {}

    class FakeSdkClient:
        def __init__(self, base_url=None):
            built["url"] = base_url

    monkeypatch.setattr(
        rd, "_docker_sdk", types.SimpleNamespace(DockerClient=FakeSdkClient)
    )
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://other:2375", raising=False)
    client = rd._get_client()
    assert isinstance(client, FakeSdkClient)
    assert built["url"] == "tcp://other:2375"


def test_get_client_connect_failure_returns_none(docker_env, monkeypatch):
    def boom(base_url=None):
        raise RuntimeError("no daemon")

    monkeypatch.setattr(
        rd, "_docker_sdk", types.SimpleNamespace(DockerClient=boom)
    )
    monkeypatch.setattr(cfg, "DOCKER_URL", "tcp://broken:1", raising=False)
    assert rd._get_client() is None


def test_client_info_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", False, raising=False)
    with pytest.raises(RuntimeError):
        rd.client_info()


def test_client_info_returns_daemon_info(docker_env):
    assert rd.client_info() == {"ServerVersion": "fake-1.0"}


# ─── container resolution ───────────────────────────────────────────────

def test_resolve_container_by_label(docker_env):
    c = FakeContainer()
    docker_env.containers.existing = [c]
    assert rd._resolve_container("chat1") is c
    filters = docker_env.containers.list_calls[-1]
    assert "restai.chat_id=chat1" in filters["label"]
    assert "restai.managed=true" in filters["label"]


def test_resolve_container_ignores_non_running(docker_env):
    docker_env.containers.existing = [FakeContainer(status="exited")]
    assert rd._resolve_container("chat1") is None


def test_resolve_container_no_chat_id(docker_env):
    assert rd._resolve_container("") is None


def test_resolve_container_list_failure_returns_none(docker_env):
    docker_env.containers.list_raises = True
    assert rd._resolve_container("chat1") is None


def test_get_or_create_reuses_existing(docker_env):
    c = FakeContainer()
    docker_env.containers.existing = [c]
    assert rd._get_or_create("chat1") is c
    assert docker_env.containers.run_calls == []


def test_create_container_settings(docker_env, monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_IMAGE", "custom:img", raising=False)
    monkeypatch.setattr(cfg, "DOCKER_NETWORK", "bridge", raising=False)
    monkeypatch.setattr(cfg, "DOCKER_READ_ONLY", False, raising=False)
    container = rd._create_container("chatX")
    assert isinstance(container, FakeContainer)
    image, kw = docker_env.containers.run_calls[0]
    assert image == "custom:img"
    assert kw["network_mode"] == "bridge"
    assert kw["read_only"] is False
    assert kw["labels"]["restai.chat_id"] == "chatX"
    assert kw["labels"]["restai.managed"] == "true"
    assert kw["remove"] is True
    assert kw["mem_limit"] == "512m"


def test_create_container_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(cfg, "DOCKER_ENABLED", False, raising=False)
    with pytest.raises(RuntimeError):
        rd._create_container("x")


# ─── workspace helpers ──────────────────────────────────────────────────

def test_chat_workspace_dir_sanitizes(monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    path = rd.chat_workspace_dir("../evil/../../id")
    assert str(tmp_path) in path
    assert ".." not in path.split("restai-chat-")[1]
    assert "/" not in path.split("restai-chat-")[1]


def test_chat_workspace_dir_defaults_ephemeral(monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    assert rd.chat_workspace_dir("").endswith("restai-chat-ephemeral")
    assert rd.chat_workspace_dir(None).endswith("restai-chat-ephemeral")


def test_ensure_and_rm_chat_workspace(monkeypatch, tmp_path):
    import os
    monkeypatch.setenv("RESTAI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    path = rd._ensure_chat_workspace("w1")
    assert os.path.isdir(path)
    rd._rm_chat_workspace("w1")
    assert not os.path.isdir(path)
    # Removing a non-existent workspace is a no-op.
    rd._rm_chat_workspace("w1")


# ─── exec retry ─────────────────────────────────────────────────────────

def test_exec_with_retry_transient_oci_retries_once(docker_env, monkeypatch):
    monkeypatch.setattr(rd.time, "sleep", lambda s: None)
    attempts = []

    def handler(cmd, kw):
        attempts.append(cmd)
        if len(attempts) == 1:
            raise derrors.APIError("oci runtime exec failed: setns blip")
        return ExecResult(output=(b"ok", b""))

    c = FakeContainer(handler)
    res = rd._exec_with_retry("chat1", c, ["sh", "-c", "true"])
    assert res.output[0] == b"ok"
    assert len(attempts) == 2


def test_exec_with_retry_non_transient_api_error_raises(docker_env):
    def handler(cmd, kw):
        raise derrors.APIError("permission denied")

    with pytest.raises(derrors.APIError):
        rd._exec_with_retry("chat1", FakeContainer(handler), ["sh", "-c", "true"])


def test_exec_with_retry_generic_error_raises_immediately(docker_env):
    calls = []

    def handler(cmd, kw):
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        rd._exec_with_retry("chat1", FakeContainer(handler), ["sh", "-c", "true"])
    assert len(calls) == 1


# ─── exec_command ───────────────────────────────────────────────────────

def test_exec_command_reuses_container_and_touches_activity(docker_env):
    c = FakeContainer(lambda cmd, kw: ExecResult(output=(b"hello", b"")))
    docker_env.containers.existing = [c]
    out = rd.exec_command("chat1", "echo hello")
    assert out == "hello"
    assert docker_env.containers.run_calls == []
    cmd, kw = c.exec_calls[0]
    assert cmd == ["sh", "-c", "echo hello"]
    assert kw["demux"] is True
    assert kw["workdir"] == "/home/user"
    # heartbeat before AND after exec
    assert FakeDBWrapper.upserts == [("chat1", c.id), ("chat1", c.id)]


def test_exec_command_env_overlay(docker_env):
    c = FakeContainer()
    docker_env.containers.existing = [c]
    rd.exec_command("chat1", "env", env={"SECRET": "x"})
    _, kw = c.exec_calls[0]
    assert kw["environment"] == {"SECRET": "x"}


def test_exec_command_combines_stdout_stderr(docker_env):
    c = FakeContainer(lambda cmd, kw: ExecResult(output=(b"out", b"err")))
    docker_env.containers.existing = [c]
    assert rd.exec_command("chat1", "x") == "outerr"


def test_exec_command_no_output(docker_env):
    docker_env.containers.existing = [FakeContainer()]
    assert rd.exec_command("chat1", "true") == "(no output)"


def test_exec_command_truncates_giant_output(docker_env):
    big = b"x" * (rd.MAX_OUTPUT + 100)
    docker_env.containers.existing = [
        FakeContainer(lambda cmd, kw: ExecResult(output=(big, b"")))
    ]
    out = rd.exec_command("chat1", "x")
    assert out.endswith("... (output truncated)")
    assert len(out) < len(big) + 100


def test_exec_command_ephemeral_default_chat_id(docker_env):
    c = FakeContainer()
    docker_env.containers.existing = [c]
    rd.exec_command("", "true")
    assert FakeDBWrapper.upserts[0][0] == "ephemeral"


def test_exec_command_soft_error_on_create_failure(docker_env):
    docker_env.containers.run_raises = True
    out = rd.exec_command("chat1", "true")
    assert out.startswith("ERROR: Command execution failed:")


def test_exec_command_soft_error_on_exec_failure(docker_env):
    def handler(cmd, kw):
        raise RuntimeError("exec died")

    docker_env.containers.existing = [FakeContainer(handler)]
    out = rd.exec_command("chat1", "true")
    assert "ERROR: Command execution failed" in out


# ─── run_script ─────────────────────────────────────────────────────────

def test_run_script_pipes_base64(docker_env):
    c = FakeContainer(lambda cmd, kw: ExecResult(output=(b"result\n", b"")))
    docker_env.containers.existing = [c]
    script = "print('hi')"
    out = rd.run_script("chat1", script)
    assert out == "result"
    cmd, _ = c.exec_calls[0]
    b64 = base64.b64encode(script.encode()).decode()
    assert b64 in cmd[2]
    assert 'python3 -c' in cmd[2]
    assert "|" not in cmd[2].split("python3")[0]  # no stdin pipe


def test_run_script_with_stdin(docker_env):
    c = FakeContainer(lambda cmd, kw: ExecResult(output=(b"ok", b"")))
    docker_env.containers.existing = [c]
    rd.run_script("chat1", "print(1)", stdin_data='{"a":1}')
    cmd, _ = c.exec_calls[0]
    b64_stdin = base64.b64encode(b'{"a":1}').decode()
    assert b64_stdin in cmd[2]
    assert "base64 -d | python3" in cmd[2]


def test_run_script_stderr_only_is_error(docker_env):
    docker_env.containers.existing = [
        FakeContainer(lambda cmd, kw: ExecResult(output=(b"", b"Traceback")))
    ]
    out = rd.run_script("chat1", "boom")
    assert out.startswith("ERROR: Traceback")


def test_run_script_stdout_plus_stderr(docker_env):
    docker_env.containers.existing = [
        FakeContainer(lambda cmd, kw: ExecResult(output=(b"partial", b"warn")))
    ]
    out = rd.run_script("chat1", "x")
    assert out == "partial\nSTDERR: warn"


def test_run_script_no_output(docker_env):
    docker_env.containers.existing = [FakeContainer()]
    assert rd.run_script("chat1", "pass") == "(no output)"


def test_run_script_soft_error_on_failure(docker_env):
    docker_env.containers.run_raises = True
    assert rd.run_script("chat1", "x").startswith("ERROR: Script execution failed")


# ─── put_files ──────────────────────────────────────────────────────────

def _upload_handler(state):
    """Simulate the tar staging protocol well enough for put_files."""
    def handler(cmd, kw):
        if isinstance(cmd, list) and cmd and cmd[0] == "test":
            return ExecResult(exit_code=0 if cmd[2] in state["files"] else 1)
        shell = cmd[2]
        if "mkdir -p" in shell:
            return ExecResult()
        if "base64 -d >>" in shell:
            state["chunks"] += 1
            return ExecResult()
        if "tar xf" in shell:
            # "Extract": mark every expected file present.
            state["files"].update(state["expected"])
            return ExecResult()
        return ExecResult()
    return handler


def test_put_files_success_manifest(docker_env):
    state = {"files": set(), "chunks": 0,
             "expected": {"/home/user/uploads/a.txt", "/home/user/uploads/b.bin"}}
    c = FakeContainer(_upload_handler(state))
    docker_env.containers.existing = [c]
    manifest = rd.put_files("chat1", [("a.txt", b"hello"), ("b.bin", b"\x00\x01")])
    assert [m["name"] for m in manifest] == ["a.txt", "b.bin"]
    assert manifest[0]["path"] == "/home/user/uploads/a.txt"
    assert manifest[0]["size"] == 5
    assert state["chunks"] >= 1
    assert FakeDBWrapper.upserts[-1] == ("chat1", c.id)


def test_put_files_chunked_upload(docker_env, monkeypatch):
    monkeypatch.setattr(rd, "PUT_FILES_CHUNK", 1024)
    state = {"files": set(), "chunks": 0,
             "expected": {"/home/user/uploads/big.bin"}}
    docker_env.containers.existing = [FakeContainer(_upload_handler(state))]
    rd.put_files("chat1", [("big.bin", b"z" * 5000)])
    assert state["chunks"] > 1


def test_put_files_empty_list(docker_env):
    assert rd.put_files("chat1", []) == []


def test_put_files_extract_failure_raises(docker_env):
    def handler(cmd, kw):
        shell = cmd[2] if cmd[0] == "sh" else ""
        if "tar xf" in shell:
            return ExecResult(exit_code=2, output=b"tar: broken")
        return ExecResult()

    docker_env.containers.existing = [FakeContainer(handler)]
    with pytest.raises(RuntimeError, match="Failed to upload files to sandbox"):
        rd.put_files("chat1", [("a.txt", b"x")])


def test_put_files_staging_failure_raises(docker_env):
    def handler(cmd, kw):
        shell = cmd[2] if cmd[0] == "sh" else ""
        if "mkdir -p" in shell:
            return ExecResult(exit_code=1)
        return ExecResult()

    docker_env.containers.existing = [FakeContainer(handler)]
    with pytest.raises(RuntimeError, match="Failed to upload files to sandbox"):
        rd.put_files("chat1", [("a.txt", b"x")])


def test_put_files_missing_after_upload_raises(docker_env):
    def handler(cmd, kw):
        if isinstance(cmd, list) and cmd and cmd[0] == "test":
            return ExecResult(exit_code=1)  # nothing verifies
        return ExecResult()

    docker_env.containers.existing = [FakeContainer(handler)]
    with pytest.raises(RuntimeError, match="Files not present after upload"):
        rd.put_files("chat1", [("gone.txt", b"x")])


def test_put_files_verify_uses_argv_not_shell(docker_env):
    """Filenames must be verified via argv `test -f`, never `sh -c` interpolation."""
    evil = "a'; rm -rf /; echo '.txt"
    seen = []

    def handler(cmd, kw):
        seen.append(cmd)
        if isinstance(cmd, list) and cmd and cmd[0] == "test":
            return ExecResult(exit_code=0)
        return ExecResult()

    docker_env.containers.existing = [FakeContainer(handler)]
    rd.put_files("chat1", [(evil, b"x")])
    verify_calls = [c for c in seen if c[0] == "test"]
    assert verify_calls and verify_calls[0][1] == "-f"
    assert evil in verify_calls[0][2]


# ─── remove_container ───────────────────────────────────────────────────

def test_remove_container_stops_and_drops(docker_env, monkeypatch, tmp_path):
    monkeypatch.setenv("RESTAI_AGENT_WORKSPACE_ROOT", str(tmp_path))
    c = FakeContainer()
    docker_env.containers.existing = [c]
    rd.remove_container("chat1")
    assert c.stopped is True
    assert FakeDBWrapper.deletes == ["chat1"]


def test_remove_container_missing_still_cleans(docker_env):
    rd.remove_container("chatgone")
    assert FakeDBWrapper.deletes == ["chatgone"]


def test_remove_container_stop_failure_swallowed(docker_env):
    c = FakeContainer()
    c.stop_raises = True
    docker_env.containers.existing = [c]
    rd.remove_container("chat1")  # must not raise
    assert FakeDBWrapper.deletes == ["chat1"]


# ─── db activity best-effort ────────────────────────────────────────────

def test_touch_db_activity_ignores_db_errors(docker_env, monkeypatch):
    import restai.database as rdb

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(rdb, "open_db_wrapper", boom)
    rd._touch_db_activity("chat1", "cid")  # must not raise
    rd._drop_db_activity("chat1")  # must not raise


def test_touch_db_activity_noop_without_chat_id(docker_env):
    rd._touch_db_activity("", "cid")
    rd._drop_db_activity("")
    assert FakeDBWrapper.upserts == []
    assert FakeDBWrapper.deletes == []


# ─── collect_new_artifacts ──────────────────────────────────────────────

def _artifact_handler(fs):
    """fs: {'seen': str, 'listing': str, 'files': {path: bytes}}"""
    def handler(cmd, kw):
        shell = cmd[2] if (isinstance(cmd, list) and cmd[0] == "sh") else ""
        if "mkdir -p /artifacts" in shell:
            return ExecResult()
        if "cat /artifacts/.seen" in shell:
            return ExecResult(output=fs["seen"].encode())
        if shell.startswith("find /artifacts"):
            return ExecResult(output=fs["listing"].encode())
        if "base64 -w0" in shell:
            for path, data in fs["files"].items():
                if repr(path) in shell:
                    return ExecResult(output=base64.b64encode(data))
            return ExecResult(output=b"")
        if "> /artifacts/.seen" in shell:
            marker_b64 = shell.split("printf '%s' ")[1].split(" |")[0]
            fs["seen"] = base64.b64decode(marker_b64).decode()
            return ExecResult()
        return ExecResult()
    return handler


def test_collect_new_artifacts_no_container(docker_env):
    assert rd.collect_new_artifacts("nochat") == []


def test_collect_new_artifacts_reads_and_dedupes(docker_env):
    fs = {
        "seen": "",
        "listing": "1700000000.0 5 hello.txt\x001700000001.0 3 img.png\x00",
        "files": {
            "/artifacts/hello.txt": b"hello",
            "/artifacts/img.png": b"png",
        },
    }
    c = FakeContainer(_artifact_handler(fs))
    docker_env.containers.existing = [c]

    arts = rd.collect_new_artifacts("chat1")
    assert [a["name"] for a in arts] == ["hello.txt", "img.png"]
    assert arts[0]["bytes"] == b"hello"
    assert arts[0]["mime"] == "text/plain"
    assert arts[1]["mime"] == "image/png"
    assert arts[0]["truncated"] is False
    # marker got persisted → second scan returns nothing
    assert "hello.txt" in fs["seen"]
    assert rd.collect_new_artifacts("chat1") == []


def test_collect_new_artifacts_oversized_marked_truncated(docker_env, monkeypatch):
    monkeypatch.setattr(rd, "ARTIFACT_MAX_BYTES_PER_FILE", 4)
    fs = {
        "seen": "",
        "listing": "1700000000.0 100 big.bin\x00",
        "files": {"/artifacts/big.bin": b"x" * 100},
    }
    docker_env.containers.existing = [FakeContainer(_artifact_handler(fs))]
    arts = rd.collect_new_artifacts("chat1")
    assert arts == [{
        "name": "big.bin", "path": "/artifacts/big.bin",
        "mime": "application/octet-stream", "size": 100,
        "bytes": None, "truncated": True,
    }]


def test_collect_new_artifacts_skips_malformed_listing(docker_env):
    fs = {
        "seen": "",
        "listing": "garbage-no-fields\x00not_a_ts x y\x00",
        "files": {},
    }
    docker_env.containers.existing = [FakeContainer(_artifact_handler(fs))]
    assert rd.collect_new_artifacts("chat1") == []


def test_collect_new_artifacts_unreadable_file_skipped(docker_env):
    fs = {
        "seen": "",
        "listing": "1700000000.0 5 ghost.txt\x00",
        "files": {},  # base64 read returns empty
    }
    docker_env.containers.existing = [FakeContainer(_artifact_handler(fs))]
    assert rd.collect_new_artifacts("chat1") == []
