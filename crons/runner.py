#!/usr/bin/env python3
"""Cron Runner — single entry point for all RESTai cron jobs.

Discovers and runs all cron modules in the crons/ directory.
Each module must define a ``main()`` function.
Modules with ``DAEMON = True`` at module level are skipped.

Usage:
    uv run python crons/runner.py

Cron (every minute):
    * * * * * cd /path/to/restai && uv run python crons/runner.py >> /var/log/restai-crons.log 2>&1
"""

import logging
import os
import subprocess
import sys

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
            # Stop scanning after first function/class definition
            if stripped.startswith(("def ", "class ")):
                break
    return False


def run_all():
    """Run each discovered cron script as an isolated subprocess."""
    scripts = discover_crons()

    if not scripts:
        logger.info("No cron modules found")
        return

    for script_path in scripts:
        name = os.path.basename(script_path)[:-3]

        if _is_daemon(script_path):
            continue

        logger.info("Running cron: %s", name)

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=ROOT,
                timeout=JOB_TIMEOUT,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    logger.info("[%s] %s", name, line)
            if result.returncode != 0:
                logger.error("Cron %s exited with code %d", name, result.returncode)
                if result.stderr:
                    for line in result.stderr.strip().splitlines()[-10:]:
                        logger.error("[%s] %s", name, line)

        except subprocess.TimeoutExpired:
            logger.error("Cron %s timed out after %ds, killed", name, JOB_TIMEOUT)
        except Exception as e:
            logger.error("Cron %s failed to start: %s", name, e)


if __name__ == "__main__":
    run_all()
