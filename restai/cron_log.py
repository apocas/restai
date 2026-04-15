"""DB-backed logging helper for cron scripts.

Usage:
    from restai.cron_log import CronLogger

    def main():
        log = CronLogger("sync")
        try:
            # ... do work ...
            log.info("Synced 3 sources")
            log.finish(items_processed=3)
        except Exception as e:
            log.error(f"Failed: {e}", details=traceback.format_exc())
            log.finish()
"""
from __future__ import annotations

import time
import traceback


class CronLogger:
    """Collects log messages during a cron run and writes a single DB entry on finish."""

    def __init__(self, job: str):
        self.job = job
        self._start = time.time()
        self._messages: list[str] = []
        self._details: str | None = None
        self._has_error = False
        self._has_warning = False
        self._finished = False

    def info(self, message: str):
        self._messages.append(message)

    def warning(self, message: str):
        self._messages.append(f"WARNING: {message}")
        self._has_warning = True

    def error(self, message: str, details: str = None):
        self._messages.append(f"ERROR: {message}")
        self._has_error = True
        if details:
            self._details = details

    def finish(self, items_processed: int = 0):
        """Write the log entry to the database."""
        if self._finished:
            return
        self._finished = True

        duration_ms = int((time.time() - self._start) * 1000)

        if self._has_error:
            status = "error"
        elif self._has_warning:
            status = "warning"
        else:
            status = "success"

        message = "\n".join(self._messages) if self._messages else "No output"

        try:
            from restai.database import DBWrapper
            db = DBWrapper()
            try:
                db.create_cron_log(
                    job=self.job,
                    status=status,
                    message=message,
                    details=self._details,
                    items_processed=items_processed,
                    duration_ms=duration_ms,
                )
            finally:
                db.db.close()
        except Exception:
            # If DB write fails, at least print to stdout
            import logging
            logging.getLogger(__name__).warning(
                "Failed to write cron log to DB for job '%s'", self.job
            )

    def __del__(self):
        """Safety net: if finish() was never called (script crashed), write an error entry."""
        if not self._finished:
            self.error("Script exited without calling finish()")
            self.finish()
