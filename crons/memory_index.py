#!/usr/bin/env python3
"""Memory Index Runner — cron-friendly script.

For every agent project with `memory_search_enabled=True` AND a
configured embedding (`Project.embeddings`), walks new `OutputDatabase`
rows and indexes them into the project's dedicated Chroma collection
(see `restai/memory_search.py`). Detects embedding-model swaps and
rebuilds the collection from scratch when needed.

Usage:
    uv run python crons/memory_index.py

Per-tick caps: BATCH_PER_PROJECT new rows, MAX_PROJECTS_PER_TICK projects.
At 200 rows/min a project's history converges within minutes even on a
freshly-enabled project with thousands of historical turns.
"""

import json
import logging
import time
import traceback
from typing import Iterable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.memory_index_cron")

from restai import config  # noqa: F401  — side effect: env loaded
from restai.settings import ensure_settings_table
from restai.database import open_db_wrapper, engine as db_engine
from restai.brain import Brain
from restai.observability.cron_log import CronLogger
from restai.memory import search as memory_search
from restai.models.databasemodels import OutputDatabase, ProjectDatabase


# Per-tick caps. The embedding call is the expensive bit — cloud
# providers cost money per call, local Ollama is ~50-200ms each. 200
# turns × 50ms = 10s per project, well under the runner's 600s ceiling.
BATCH_PER_PROJECT = 200
# Defensive ceiling so a deployment with hundreds of memory-enabled
# projects can't blow the runner's job timeout. Remaining projects
# pick up on the next tick.
MAX_PROJECTS_PER_TICK = 50


def _embed_text(embedding, text: str) -> list[float] | None:
    """One-shot embedding call. Returns None on any failure so the
    caller can skip the row instead of crashing the whole tick."""
    try:
        vec = embedding.embedding.get_text_embedding(text)
        return list(vec) if vec else None
    except Exception as e:
        logger.warning("memory_index: embedding failed: %s", e)
        return None


def _list_search_enabled_projects(db) -> Iterable[ProjectDatabase]:
    """Yield agent projects with `memory_search_enabled=True`. Independent
    of `memory_bank_enabled` — the two features are gated separately."""
    rows = (
        db.db.query(ProjectDatabase)
        .filter(ProjectDatabase.type == "agent")
        .all()
    )
    for proj in rows:
        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            continue
        if opts.get("memory_search_enabled"):
            yield proj


def _process_project(brain: Brain, proj) -> tuple[int, int]:
    """Index any new turns for one project. Returns (indexed, scanned).

    Opens its own short-lived DB session per project so a slow Chroma
    or embedding batch doesn't hold the global session for the whole
    tick."""
    embedding_name = (proj.embeddings or "").strip()
    if not embedding_name:
        return (0, 0)

    db = open_db_wrapper()
    try:
        embedding = brain.get_embedding(embedding_name, db)
        if embedding is None:
            logger.warning(
                "memory_index: project=%s — embedding '%s' not resolvable; skipping",
                proj.id, embedding_name,
            )
            return (0, 0)

        # Detect embedding swap. Different name → existing vectors are
        # dimensionally / semantically incompatible. Drop and rebuild.
        indexed_model = memory_search.get_indexed_embedding_model(proj.id)
        if indexed_model and indexed_model != embedding_name:
            logger.info(
                "memory_index: project=%s — embedding changed (%s → %s), resetting collection",
                proj.id, indexed_model, embedding_name,
            )
            memory_search.reset_collection(proj.id)
        memory_search.set_indexed_embedding_model(proj.id, embedding_name)

        last_id = memory_search.get_last_indexed_id(proj.id) or 0
        rows = (
            db.db.query(OutputDatabase)
            .filter(
                OutputDatabase.project_id == proj.id,
                OutputDatabase.id > last_id,
            )
            .order_by(OutputDatabase.id.asc())
            .limit(BATCH_PER_PROJECT)
            .all()
        )
        if not rows:
            return (0, 0)

        indexed = 0
        max_id = last_id
        for row in rows:
            max_id = max(max_id, int(row.id))
            # Skip rows with neither side populated — those are usually
            # error/budget rejections that have no useful content.
            q = (row.question or "").strip()
            a = (row.answer or "").strip()
            if not (q or a):
                continue
            text = f"{q}\n\n{a}".strip()
            vec = _embed_text(embedding, text)
            if vec is None:
                continue
            try:
                memory_search.index_turn(
                    project_id=proj.id,
                    output_id=row.id,
                    chat_id=row.chat_id,
                    question=q,
                    answer=a,
                    date_iso=row.date.isoformat() if row.date else "",
                    embedding=vec,
                )
                indexed += 1
            except Exception as e:
                logger.warning(
                    "memory_index: index_turn failed (project=%s output=%s): %s",
                    proj.id, row.id, e,
                )

        # Advance the cursor even past skipped rows — otherwise the
        # indexer would re-scan failing rows every tick forever.
        memory_search.set_last_indexed_id(proj.id, max_id)
        return (indexed, len(rows))
    finally:
        db.db.close()


def _project_has_embedding(proj) -> bool:
    return bool((proj.embeddings or "").strip())


def _run():
    ensure_settings_table(db_engine)

    cron = CronLogger("memory_index")
    brain = Brain(lightweight=True)

    db = open_db_wrapper()
    try:
        # Snapshot the project list, then drop the listing session —
        # `_process_project` opens its own short-lived session per
        # project below.
        projects = list(_list_search_enabled_projects(db))
    finally:
        db.db.close()

    try:
        total_indexed = 0
        projects_touched = 0
        missing_embedding: list[int] = []

        for i, proj in enumerate(projects):
            if i >= MAX_PROJECTS_PER_TICK:
                logger.info(
                    "memory_index: hit MAX_PROJECTS_PER_TICK=%d, deferring rest to next tick",
                    MAX_PROJECTS_PER_TICK,
                )
                break

            if not _project_has_embedding(proj):
                # Visible skip — without this the admin can have memory
                # search enabled, lots of conversations, and an empty
                # index, with no obvious reason. Surfaces in the cron
                # log viewer at WARNING level.
                missing_embedding.append(int(proj.id))
                logger.warning(
                    "memory_index: project=%s (%s) has memory_search_enabled=True "
                    "but no embedding configured — set Project.embeddings to "
                    "enable indexing.",
                    proj.id, proj.name,
                )
                continue

            t0 = time.monotonic()
            try:
                indexed, scanned = _process_project(brain, proj)
            except Exception as e:
                logger.warning(
                    "memory_index: project=%s pass crashed: %s", proj.id, e,
                )
                continue

            if scanned > 0:
                projects_touched += 1
                total_indexed += indexed
                logger.info(
                    "memory_index: project=%s — indexed %d/%d new turn(s) in %.1fs",
                    proj.id, indexed, scanned, time.monotonic() - t0,
                )

        msg = f"Indexed {total_indexed} turn(s) across {projects_touched} project(s)."
        if missing_embedding:
            msg += (
                f" Skipped {len(missing_embedding)} project(s) without an embedding: "
                + ", ".join(str(p) for p in missing_embedding)
                + "."
            )
            cron.warning(msg)
        else:
            cron.info(msg)
        cron.finish(items_processed=total_indexed)
    except Exception as e:
        cron.error(f"Memory index runner crashed: {e}", details=traceback.format_exc())
        cron.finish()


def main():
    _run()


if __name__ == "__main__":
    main()
