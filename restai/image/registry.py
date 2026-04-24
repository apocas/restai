"""Image-generator registry helpers.

`seed_local_generators` runs once at startup to ensure every worker module
under `restai/image/workers/*.py` has a corresponding DB row with
`class_name="local"`. Idempotent — existing rows keep their `enabled`
flag and any admin-provided description.
"""
from __future__ import annotations

import logging
import os
import pkgutil

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def seed_local_generators(db_wrapper) -> int:
    """Ensure every local worker module has a registry row. Returns the
    number of rows created (0 when everything was already in place).

    Race-safe under multi-worker uvicorn: when two workers both pass
    the pre-check and both INSERT, the second one trips the unique
    constraint and we **must** rollback() before continuing or the
    SQLAlchemy session is left in PendingRollbackError state and
    every subsequent query in the lifespan handler crashes the worker.
    """
    workers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workers")
    if not os.path.isdir(workers_dir):
        return 0

    created = 0
    for _, modname, _ in pkgutil.iter_modules(path=[workers_dir]):
        if modname.startswith("_"):
            continue
        existing = db_wrapper.get_image_generator_by_name(modname)
        if existing is not None:
            # Don't clobber admin-applied changes (description, enabled,
            # privacy). Just make sure class_name is still `local` — if
            # it drifted somehow, reset it.
            if existing.class_name != "local":
                existing.class_name = "local"
                try:
                    db_wrapper.db.commit()
                except Exception as e:
                    db_wrapper.db.rollback()
                    logger.warning("Failed to update class_name for image gen '%s': %s", modname, e)
            continue
        try:
            db_wrapper.create_image_generator(
                name=modname,
                class_name="local",
                options={},
                privacy="private",
                description=f"Local worker: restai/image/workers/{modname}.py",
                enabled=True,
            )
            created += 1
            logger.info("Seeded local image generator: %s", modname)
        except IntegrityError:
            # Another uvicorn worker beat us to the INSERT. Roll back
            # the poisoned session and move on — the row exists, which
            # is the desired state.
            db_wrapper.db.rollback()
            logger.debug("Local image generator '%s' was concurrently seeded by another worker", modname)
        except Exception as e:
            try:
                db_wrapper.db.rollback()
            except Exception:
                pass
            logger.warning("Failed to seed local image generator '%s': %s", modname, e)
    return created
