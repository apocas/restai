"""Unit tests for crons/runner.py — discovery, daemon-skip, flock and
timeout logic. Subprocesses are faked; no real cron jobs run."""

import fcntl
import os
import sys
from unittest.mock import patch

import crons.runner as runner


def _write(dirpath, name, content="def main():\n    pass\n"):
    path = os.path.join(dirpath, name)
    with open(path, "w") as f:
        f.write(content)
    return path


class FakeProc:
    """subprocess.Popen stand-in that is already finished."""

    def __init__(self, args, rc=0, out="hello", err="", **kwargs):
        self.args = args
        self._rc = rc
        self._out = out
        self._err = err
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._rc

    def communicate(self, timeout=None):
        return self._out, self._err

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self._rc


class HungProc(FakeProc):
    """Never finishes until terminated."""

    def poll(self):
        return None


# ─── discovery ──────────────────────────────────────────────────────────

def test_discover_crons_filters_and_sorts(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write(d, "b_job.py")
    _write(d, "a_job.py")
    _write(d, "runner.py")
    _write(d, "__init__.py")
    _write(d, "_private.py")
    _write(d, "notes.txt")
    monkeypatch.setattr(runner, "CRONS_DIR", d)

    scripts = runner.discover_crons()
    names = [os.path.basename(s) for s in scripts]
    assert names == ["a_job.py", "b_job.py"]


def test_discover_crons_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CRONS_DIR", str(tmp_path))
    assert runner.discover_crons() == []


# ─── daemon detection ───────────────────────────────────────────────────

def test_is_daemon_true(tmp_path):
    p = _write(str(tmp_path), "d.py", "DAEMON = True\n\ndef main():\n    pass\n")
    assert runner._is_daemon(p) is True


def test_is_daemon_false_plain(tmp_path):
    p = _write(str(tmp_path), "d.py", "def main():\n    pass\n")
    assert runner._is_daemon(p) is False


def test_is_daemon_stops_scanning_at_first_def(tmp_path):
    # DAEMON = True appearing after the first def/class is not module-level
    # daemon marking — the scanner must stop at the def line.
    p = _write(str(tmp_path), "d.py", "def main():\n    DAEMON = True\n")
    assert runner._is_daemon(p) is False


def test_is_daemon_false_when_daemon_false(tmp_path):
    p = _write(str(tmp_path), "d.py", "DAEMON = False\n\ndef main():\n    pass\n")
    assert runner._is_daemon(p) is False


# ─── run_all ────────────────────────────────────────────────────────────

def test_run_all_no_scripts(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CRONS_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "ROOT", str(tmp_path))
    with patch.object(runner.subprocess, "Popen") as popen:
        runner.run_all()
    popen.assert_not_called()


def test_run_all_skips_daemons_and_runs_rest(tmp_path, monkeypatch):
    d = str(tmp_path)
    normal = _write(d, "job.py")
    _write(d, "daemon_job.py", "DAEMON = True\n\ndef main():\n    pass\n")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)

    procs = []

    def fake_popen(args, **kwargs):
        proc = FakeProc(args)
        procs.append(proc)
        return proc

    with patch.object(runner.subprocess, "Popen", side_effect=fake_popen) as popen:
        runner.run_all()

    assert popen.call_count == 1
    assert procs[0].args == [sys.executable, normal]
    # PYTHONPATH injected so children can import restai without editable install.
    env = popen.call_args.kwargs["env"]
    assert env["PYTHONPATH"].startswith(d)
    # Lock must be released — reacquirable immediately.
    with open(os.path.join(d, ".cron-job.lock"), "w") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fp, fcntl.LOCK_UN)


def test_run_all_skips_already_locked_job(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write(d, "busy.py")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)

    holder = open(os.path.join(d, ".cron-busy.lock"), "w")
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with patch.object(runner.subprocess, "Popen") as popen:
            runner.run_all()
        popen.assert_not_called()
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()


def test_run_all_nonzero_exit_logged(tmp_path, monkeypatch, caplog):
    d = str(tmp_path)
    _write(d, "bad.py")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)

    def fake_popen(args, **kwargs):
        return FakeProc(args, rc=3, out="stdout line", err="boom traceback")

    with caplog.at_level("INFO", logger="restai.cron_runner"):
        with patch.object(runner.subprocess, "Popen", side_effect=fake_popen):
            runner.run_all()

    text = caplog.text
    assert "exited with code 3" in text
    assert "boom traceback" in text
    assert "stdout line" in text


def test_run_all_collects_slow_job_on_later_poll(tmp_path, monkeypatch):
    """poll() returns None first (still running), then finishes; the wait
    loop must sleep and re-poll rather than kill it. communicate timing
    out must degrade to empty output, not crash."""
    d = str(tmp_path)
    _write(d, "slow.py")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)

    class SlowProc(FakeProc):
        def __init__(self, args, **kwargs):
            super().__init__(args)
            self._polls = 0

        def poll(self):
            self._polls += 1
            return None if self._polls == 1 else 0

        def communicate(self, timeout=None):
            raise runner.subprocess.TimeoutExpired(cmd=self.args, timeout=timeout)

    procs = []

    def fake_popen(args, **kwargs):
        proc = SlowProc(args)
        procs.append(proc)
        return proc

    with patch.object(runner.subprocess, "Popen", side_effect=fake_popen):
        runner.run_all()

    assert procs[0]._polls >= 2
    assert procs[0].terminated is False
    with open(os.path.join(d, ".cron-slow.lock"), "w") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fp, fcntl.LOCK_UN)


def test_run_all_timeout_terminates_and_releases_lock(tmp_path, monkeypatch):
    d = str(tmp_path)
    _write(d, "hang.py")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)
    # Deadline already reached on first wait-loop iteration.
    monkeypatch.setattr(runner, "JOB_TIMEOUT", 0)

    procs = []

    def fake_popen(args, **kwargs):
        proc = HungProc(args)
        procs.append(proc)
        return proc

    with patch.object(runner.subprocess, "Popen", side_effect=fake_popen):
        runner.run_all()

    assert procs[0].terminated is True
    # Lock released after the kill path too.
    with open(os.path.join(d, ".cron-hang.lock"), "w") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fp, fcntl.LOCK_UN)


def test_run_all_sigkill_escalation_when_terminate_ignored(tmp_path, monkeypatch):
    """SIGTERM ignored (wait times out) → runner must escalate to kill()."""
    d = str(tmp_path)
    _write(d, "stubborn.py")
    monkeypatch.setattr(runner, "CRONS_DIR", d)
    monkeypatch.setattr(runner, "ROOT", d)
    monkeypatch.setattr(runner, "JOB_TIMEOUT", 0)

    class StubbornProc(HungProc):
        def wait(self, timeout=None):
            if self.terminated and not self.killed:
                raise runner.subprocess.TimeoutExpired(cmd=self.args, timeout=timeout)
            return -9

    procs = []

    def fake_popen(args, **kwargs):
        proc = StubbornProc(args)
        procs.append(proc)
        return proc

    with patch.object(runner.subprocess, "Popen", side_effect=fake_popen):
        runner.run_all()

    assert procs[0].terminated is True
    assert procs[0].killed is True
    with open(os.path.join(d, ".cron-stubborn.lock"), "w") as fp:
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fp, fcntl.LOCK_UN)
