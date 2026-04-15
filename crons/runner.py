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

        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        jobs.append((name, proc, lock_fp))

    if not jobs:
        return

    # Wait phase: collect results from all jobs
    deadline = time.monotonic() + JOB_TIMEOUT

    for name, proc, lock_fp in jobs:
        remaining = max(0, deadline - time.monotonic())
        try:
            stdout, stderr = proc.communicate(timeout=remaining)

            if stdout:
                for line in stdout.strip().splitlines():
                    logger.info("[%s] %s", name, line)
            if proc.returncode != 0:
                logger.error("Cron %s exited with code %d", name, proc.returncode)
                if stderr:
                    for line in stderr.strip().splitlines()[-10:]:
                        logger.error("[%s] %s", name, line)
            else:
                logger.info("Cron %s finished", name)

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            logger.error("Cron %s timed out after %ds, killed", name, JOB_TIMEOUT)
        finally:
            fcntl.flock(lock_fp, fcntl.LOCK_UN)
            lock_fp.close()


if __name__ == "__main__":
    run_all()
