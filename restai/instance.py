"""Per-install instance identity.

A stable UUID kept in the `telemetry_instance_id` setting (originally
added for anonymized telemetry, re-used here for any context that needs
to distinguish *this* RESTai install from any other sharing the same
infrastructure — Docker socket, NFS volume, etc.).

The motivating case: two RESTai installs (e.g. `/home/restai/` and
`/home/pedrodias/restai/`) share the same dockerd. Both label
containers with `restai.managed=true`, so each install's cleanup cron
sees the OTHER install's containers and applies its own (possibly
shorter) `docker_timeout`. Stamping `restai.instance_id` on every
container we create + filtering it in the cron isolates ownership.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_cached_id: Optional[str] = None


def get_instance_id() -> str:
    """Return the persistent UUID for this RESTai install.

    Cached after first read; lazily created on first call if missing.
    Safe to call from any worker / cron subprocess — the value lives in
    the `telemetry_instance_id` settings row, shared across them.
    """
    global _cached_id
    if _cached_id is not None:
        return _cached_id
    try:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            setting = db.get_setting("telemetry_instance_id")
            if setting and setting.value:
                _cached_id = setting.value
                return _cached_id
            new_id = uuid.uuid4().hex
            db.upsert_setting("telemetry_instance_id", new_id)
            _cached_id = new_id
            return new_id
        finally:
            db.db.close()
    except Exception as e:
        # Fall back to a process-local UUID. This means cross-process
        # cron isolation would degrade but it's better than crashing
        # container creation when the DB is briefly unreachable.
        logger.warning("Failed to read instance_id from DB (%s); using process-local fallback", e)
        _cached_id = uuid.uuid4().hex
        return _cached_id
