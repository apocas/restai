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

The constructor also installs a `logging.Handler` on the root logger so any
`logger.info()` / `logger.warning()` / `logger.error()` call from anywhere in
the codebase during the cron run is mirrored into the DB log entry. That
gives the admin the same view in `/admin/cron-logs` that they would have
gotten by tailing the console.
"""
from __future__ import annotations

import logging
import time
import traceback


class _CronLogHandler(logging.Handler):
    """Forwards every log record into a CronLogger's message buffer."""

    def __init__(self, owner: "CronLogger"):
        super().__init__(level=logging.INFO)
        self._owner = owner
        # Match the CronLogger's own prefix scheme so explicit cron.info()
        # calls and captured log.info() calls render the same way.
        self.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            self._owner._capture("ERROR", msg, exc_info=record.exc_info)
        elif record.levelno >= logging.WARNING:
            self._owner._capture("WARNING", msg)
        else:
            self._owner._capture(None, msg)


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

        # Mirror everything `logging` produces into our buffer so the cron
        # log entry contains the same console output. We attach to the root
        # logger so ALL named loggers propagate up here.
        self._log_handler = _CronLogHandler(self)
        # Filter out our own handler's output so a cron.info() that triggers
        # nothing else doesn't get double-counted.
        logging.getLogger().addHandler(self._log_handler)

    def _capture(self, level: str | None, message: str, exc_info=None) -> None:
        """Internal: record a message originating from the logging handler.
        Distinct from the public info()/warning()/error() so we don't add
        prefixes twice."""
        if level == "ERROR":
            self._messages.append(f"ERROR: {message}")
            self._has_error = True
            if exc_info and not self._details:
                try:
                    self._details = "".join(traceback.format_exception(*exc_info))
                except Exception:
                    pass
        elif level == "WARNING":
            self._messages.append(f"WARNING: {message}")
            self._has_warning = True
        else:
            self._messages.append(message)

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

        # Detach the logging handler — otherwise re-running a cron in the
        # same process (e.g. unit tests, the admin "Run Now" button if it
        # ever runs in-process) leaks handlers.
        try:
            logging.getLogger().removeHandler(self._log_handler)
        except Exception:
            pass

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
