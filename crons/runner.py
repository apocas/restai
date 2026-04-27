#!/usr/bin/env python3
"""Cron Runner — single entry point for all RESTai cron jobs.

Discovers and runs all cron modules in the crons/ directory.
Each module must define a ``main()`` function.
Modules with ``DAEMON = True`` at module level are skipped.

All jobs launch in parallel so a slow job never blocks the others.
Per-job file locks prevent overlapping runs of the same job.

Usage:
    uv run python crons/runner.py

Cron (every minute):
    * * * * * cd /path/to/restai && uv run python crons/runner.py >> /var/log/restai-crons.log 2>&1
"""

import fcntl
import logging
import os
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.cron_runner")

CRONS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CRONS_DIR)
SKIP_FILES = {"__init__.py", "runner.py"}
JOB_TIMEOUT = 600  # seconds per job


def discover_crons():
    """Return sorted list of cron script paths in this directory."""
    scripts = []

    for filename in sorted(os.listdir(CRONS_DIR)):
        if not filename.endswith(".py") or filename in SKIP_FILES or filename.startswith("_"):
            continue
        scripts.append(os.path.join(CRONS_DIR, filename))

    return scripts


def _is_daemon(script_path):
    """Check if a script has DAEMON = True without importing it."""
    with open(script_path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("DAEMON") and "True" in stripped:
                return True
            if stripped.startswith(("def ", "class ")):
                break
    return False


def run_all():
    """Launch all cron scripts in parallel, each in its own subprocess."""
    scripts = discover_crons()

    if not scripts:
        logger.info("No cron modules found")
        return

    # Launch phase: start all jobs in parallel
    jobs = []  # list of (name, process, lock_fp)

    for script_path in scripts:
        name = os.path.basename(script_path)[:-3]

        if _is_daemon(script_path):
            continue

        # Per-job lock: skip if a previous instance is still running
        lock_path = os.path.join(ROOT, f".cron-{name}.lock")
        lock_fp = open(lock_path, "w")
        try:
            fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("Cron %s is already running, skipping", name)
            lock_fp.close()
            continue

        logger.info("Starting cron: %s", name)

        # PYTHONPATH=ROOT so child can `import restai.X` regardless of
        # whether the workspace package is editably installed in the
        # venv. `uv run` on a dev box installs it; the Dockerfile uses
        # `--no-install-project` and doesn't, so without this the docker
        # / helm cron paths every-job-fails with ModuleNotFoundError.
        child_env = {**os.environ, "PYTHONPATH": ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}

        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=ROOT,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        jobs.append((name, proc, lock_fp))

    if not jobs:
        return

    # Wait phase: collect results in *completion order*, not declaration
    # order. Previously this loop awaited jobs[0] to completion before
    # touching jobs[1], which meant the runner held every lock for the
    # duration of the slowest job — even subprocesses that had already
    # exited keep their lockfile pinned by the runner's open FD. Result
    # was the next minute's tick logging "Cron X is already running,
    # skipping" for jobs whose actual subprocesses had exited a minute
    # ago. Now we poll all jobs each cycle and release each lock the
    # instant its subprocess returns.
    deadline = time.monotonic() + JOB_TIMEOUT
    pending = list(jobs)

    while pending:
        if time.monotonic() >= deadline:
            for name, proc, lock_fp in pending:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
                logger.error("Cron %s timed out after %ds, killed", name, JOB_TIMEOUT)
                try:
                    fcntl.flock(lock_fp, fcntl.LOCK_UN)
                except Exception:
                    pass
                lock_fp.close()
            break

        still_pending = []
        for name, proc, lock_fp in pending:
            rc = proc.poll()
            if rc is None:
                still_pending.append((name, proc, lock_fp))
                continue

            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""

            if stdout:
                for line in stdout.strip().splitlines():
                    logger.info("[%s] %s", name, line)
            if rc != 0:
                logger.error("Cron %s exited with code %d", name, rc)
                if stderr:
                    for line in stderr.strip().splitlines()[-10:]:
                        logger.error("[%s] %s", name, line)
            else:
                logger.info("Cron %s finished", name)

            try:
                fcntl.flock(lock_fp, fcntl.LOCK_UN)
            except Exception:
                pass
            lock_fp.close()

        pending = still_pending
        if pending:
            # Short sleep so we don't busy-loop while subprocesses run.
            # Resolution of 0.5s is plenty given crons fire every minute
            # and most jobs take seconds, not milliseconds.
            time.sleep(0.5)


if __name__ == "__main__":
    run_all()
