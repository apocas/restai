"""STT registry helpers."""
from __future__ import annotations

import logging
import os
import pkgutil

from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def seed_local_stt_models(db_wrapper) -> int:
    """Ensure every local audio worker has a registry row. Returns count created.

    Race-safe under multi-worker uvicorn: two workers can both pass the
    pre-check and INSERT; the second trips the unique constraint and we
    MUST rollback() or the session enters PendingRollbackError and every
    subsequent lifespan query crashes the worker.
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
            # Another worker beat us to the INSERT; rollback to free the session.
            db_wrapper.db.rollback()
            logger.debug("Local STT model '%s' was concurrently seeded by another worker", modname)
        except Exception as e:
            # Rollback or subsequent lifespan queries crash.
            try:
                db_wrapper.db.rollback()
            except Exception:
                pass
            logger.warning("Failed to seed local STT model '%s': %s", modname, e)
    return created
