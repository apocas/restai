"""DB-backed logging helper for cron scripts.

The constructor installs a root-logger handler so all log calls during the
cron run mirror into the DB entry, plus a SIGTERM handler so deadline-kills
get an "interrupted" row before process exit.
"""
from __future__ import annotations

import logging
import signal
import sys
import time
import traceback


class _CronLogHandler(logging.Handler):
    def __init__(self, owner: "CronLogger"):
        super().__init__(level=logging.INFO)
        self._owner = owner
        # Match CronLogger's prefix scheme so explicit and captured calls render the same.
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
    def __init__(self, job: str):
        self.job = job
        self._start = time.time()
        self._messages: list[str] = []
        self._details: str | None = None
        self._has_error = False
        self._has_warning = False
        self._finished = False

        # Attach to root so every named logger propagates into our buffer.
        self._log_handler = _CronLogHandler(self)
        logging.getLogger().addHandler(self._log_handler)

        # SIGTERM handler — runner sends SIGTERM on the per-job deadline.
        # Default Python behavior is to exit without flushing; we want a
        # row in the cron log explaining what happened. raise SystemExit
        # so try/finally + atexit + __del__ all fire normally.
        try:
            signal.signal(signal.SIGTERM, self._on_sigterm)
        except (ValueError, OSError):
            # signal.signal only works in the main thread; harmless when
            # CronLogger is constructed elsewhere.
            pass

    def _on_sigterm(self, signum, frame):
        if not self._finished:
            self.error(
                "Cron interrupted by SIGTERM (likely runner deadline). "
                "Backlog rolls over to the next tick."
            )
            self.finish()
        sys.exit(143)  # 128 + 15 (SIGTERM) — POSIX convention.

    def _capture(self, level: str | None, message: str, exc_info=None) -> None:
        # Separate from public info()/warning()/error() so prefixes aren't doubled.
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
        if self._finished:
            return
        self._finished = True

        # Detach to avoid handler leaks when a cron re-runs in the same process.
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
            import logging
            logging.getLogger(__name__).warning(
                "Failed to write cron log to DB for job '%s'", self.job
            )

    def __del__(self):
        # Safety net: finish() never called (script crashed).
        if not self._finished:
            self.error("Script exited without calling finish()")
            self.finish()
