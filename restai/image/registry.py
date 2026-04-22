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

logger = logging.getLogger(__name__)


def seed_local_generators(db_wrapper) -> int:
    """Ensure every local worker module has a registry row. Returns the
    number of rows created (0 when everything was already in place)."""
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
                db_wrapper.db.commit()
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
        except Exception as e:
            logger.warning("Failed to seed local image generator '%s': %s", modname, e)
    return created
