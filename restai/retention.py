"""Data retention cleanup — deletes old records from event tables."""

import logging
from datetime import datetime, timedelta, timezone

from restai import config
from restai.database import DBWrapper
from restai.models.databasemodels import (
    OutputDatabase,
    GuardEventDatabase,
    RetrievalEventDatabase,
    AuditLogDatabase,
)

logger = logging.getLogger(__name__)


def run_retention_cleanup(db_wrapper: DBWrapper):
    """Delete records older than DATA_RETENTION_DAYS from all event tables.

    Called on startup. If DATA_RETENTION_DAYS is 0 or not set, does nothing.
    """
    days = config.DATA_RETENTION_DAYS
    if not days or days <= 0:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logger.info("Retention cleanup: removing records older than %d days (before %s)", days, cutoff.isoformat())

    total_deleted = 0
    for Model in [OutputDatabase, GuardEventDatabase, RetrievalEventDatabase, AuditLogDatabase]:
        try:
            deleted = db_wrapper.db.query(Model).filter(Model.date < cutoff).delete()
            if deleted:
                logger.info("Retention: deleted %d rows from %s", deleted, Model.__tablename__)
                total_deleted += deleted
        except Exception as e:
            logger.warning("Retention: failed to clean %s: %s", Model.__tablename__, e)

    if total_deleted > 0:
        db_wrapper.db.commit()
        logger.info("Retention cleanup complete: %d total rows deleted", total_deleted)
