"""STT registry helpers.

`seed_local_stt_models` runs once on startup to ensure every worker module
under `restai/audio/workers/*.py` has a corresponding DB row with
`class_name="local"`. Idempotent — existing rows keep their `enabled`
flag and admin-applied description / privacy.
"""
from __future__ import annotations

import logging
import os
import pkgutil

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def seed_local_stt_models(db_wrapper) -> int:
    """Ensure every local audio worker has a registry row. Returns the
    number of rows created (0 when everything was already in place).

    Workers physically live under `restai/audio/workers/` (legacy module
    path); we don't move them to keep the diff small. Only the public
    naming changed to "Speech-to-Text".

    Idempotent and **race-safe**. With multiple uvicorn workers, two
    processes can both see "no row" from the pre-check and then both
    try to INSERT — one wins on the unique constraint, the other has
    to roll back. Without the rollback the SQLAlchemy session enters
    PendingRollbackError state and every subsequent query in lifespan
    (e.g. retention cleanup, OAuth load) crashes the worker.
    """
    workers_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audio", "workers")
    )
    if not os.path.isdir(workers_dir):
        return 0

    created = 0
    for _, modname, _ in pkgutil.iter_modules(path=[workers_dir]):
        if modname.startswith("_"):
            continue
        existing = db_wrapper.get_speech_to_text_by_name(modname)
        if existing is not None:
            if existing.class_name != "local":
                existing.class_name = "local"
                try:
                    db_wrapper.db.commit()
                except Exception as e:
                    db_wrapper.db.rollback()
                    logger.warning("Failed to update class_name for STT '%s': %s", modname, e)
            continue
        try:
            db_wrapper.create_speech_to_text(
                name=modname,
                class_name="local",
                options={},
                privacy="private",
                description=f"Local worker: restai/audio/workers/{modname}.py",
                enabled=True,
            )
            created += 1
            logger.info("Seeded local speech-to-text model: %s", modname)
        except IntegrityError:
            # Another uvicorn worker beat us to the INSERT. Roll back
            # so the session is reusable, then move on — the row is
            # there, which is what we wanted.
            db_wrapper.db.rollback()
            logger.debug("Local STT model '%s' was concurrently seeded by another worker", modname)
        except Exception as e:
            # Any other failure — make sure the session is clean
            # before continuing, otherwise everything after this point
            # in the lifespan handler crashes.
            try:
                db_wrapper.db.rollback()
            except Exception:
                pass
            logger.warning("Failed to seed local STT model '%s': %s", modname, e)
    return created
