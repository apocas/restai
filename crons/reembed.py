#!/usr/bin/env python3
"""Re-embed runner. Drains queued `reembed_jobs`.

Each job migrates one RAG project's knowledge base to a different embeddings
model by re-embedding the chunk text already held in its vector store — see
`restai/reembed.py` for the phase machine and why it is safe.

A cron rather than a request-attached background task: the work is long, must
survive an API restart, and must run exactly once across workers, which the
per-job `flock` in `crons/runner.py` gives for free. (`BackgroundTasks` would
also run before the response is delivered, since a `BaseHTTPMiddleware` sits in
the stack — the same reason eval runs use a detached thread.)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.reembed_cron")

# A job claimed by a runner that was then killed stays `processing` forever,
# because the terminal status is only written when the work finishes.
STALE_PROCESSING_SECONDS = 4 * 3600


def _reclaim_stalled_jobs(db, ReembedJobDatabase, cron) -> None:
    """Requeue jobs abandoned mid-flight.

    Unlike bulk ingest, a stalled job is requeued **into its recorded phase**
    rather than back to the start. A job interrupted while `rebuilding` has
    already reset the store and written `chunks_done` chunks into it; sending
    it back to the beginning would reset again — wiping that work — and
    re-snapshot the half-rebuilt store, permanently losing the remainder.
    `run_job` reads `phase` and resumes accordingly, so the reclaim only has
    to hand the row back without touching `phase` or `chunks_done`.
    """
    from restai import reembed

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSING_SECONDS)
    try:
        stalled = (
            db.db.query(ReembedJobDatabase)
            .filter(
                ReembedJobDatabase.status == "processing",
                ReembedJobDatabase.started_at.isnot(None),
                ReembedJobDatabase.started_at < cutoff,
            )
            .all()
        )
        for job in stalled:
            # Past `snapshotting` the store may already have been reset, so
            # the snapshot is the only copy of the knowledge base — without it
            # there is nothing to resume from. Before that, nothing has been
            # destroyed and the job can simply start over.
            past_no_return = job.phase in reembed._POST_DESTRUCTIVE_PHASES
            resumable = (
                not past_no_return
                or (job.snapshot_path and os.path.exists(job.snapshot_path))
            )
            if resumable:
                job.status = "queued"
                job.started_at = None
                logger.warning("Requeued stalled re-embed job %s (phase=%s)", job.id, job.phase)
            else:
                job.status = "error"
                job.error_message = (
                    "Abandoned after the knowledge base was reset and the snapshot is "
                    "gone, so the migration cannot be resumed. Configure durable "
                    "staging storage and re-ingest the affected sources."
                )
                job.completed_at = datetime.now(timezone.utc)
                logger.error("Failed stalled re-embed job %s (snapshot missing)", job.id)
        if stalled:
            db.db.commit()
            cron.warning(f"Reclaimed {len(stalled)} stalled re-embed job(s)")
    except Exception as e:
        logger.warning("Stalled-job reclaim failed: %s", e)

    try:
        reembed.purge_orphan_snapshots(db)
    except Exception as e:
        logger.warning("Orphan snapshot purge failed: %s", e)


def main():
    from restai.settings import ensure_settings_table
    from restai.database import engine as db_engine, open_db_wrapper
    from restai.models.databasemodels import ReembedJobDatabase
    from restai.brain import Brain
    from restai.observability.cron_log import CronLogger
    from restai import reembed

    ensure_settings_table(db_engine)

    # Auto-create on pre-migration DBs (mirrors the lifespan pattern).
    try:
        ReembedJobDatabase.__table__.create(db_engine, checkfirst=True)
    except Exception:
        pass

    brain = Brain(lightweight=True)
    cron = CronLogger("reembed")
    processed = 0
    reclaimed = False

    try:
        while True:
            db = open_db_wrapper()
            try:
                if not reclaimed:
                    # Piggy-backs on this iteration's session rather than
                    # opening its own — the tests mock a fixed sequence.
                    _reclaim_stalled_jobs(db, ReembedJobDatabase, cron)
                    reclaimed = True

                # Claim one job atomically; the loop drains the queue.
                job = (
                    db.db.query(ReembedJobDatabase)
                    .filter(ReembedJobDatabase.status == "queued")
                    .order_by(ReembedJobDatabase.created_at.asc())
                    .first()
                )
                if job is None:
                    db.db.close()
                    break
                job.status = "processing"
                job.started_at = datetime.now(timezone.utc)
                db.db.commit()
                job_id = job.id
                project_id = job.project_id
            except Exception as e:
                logger.exception("Failed to claim next re-embed job: %s", e)
                try:
                    db.db.close()
                except Exception:
                    pass
                break

            logger.info(
                "Re-embedding project %s: %s -> %s (job %s, phase=%s, done=%s)",
                project_id, job.from_embeddings, job.to_embeddings, job_id,
                job.phase, job.chunks_done,
            )

            err_msg = None
            try:
                reembed.run_job(job, brain, db)
            except reembed.ReembedError as e:
                err_msg = str(e)
                logger.error("Re-embed job %s failed: %s", job_id, err_msg)
            except Exception as e:
                err_msg = f"Unexpected failure: {e}"
                logger.exception("Re-embed job %s crashed", job_id)

            if err_msg:
                # A failure raised from inside a flush leaves the session
                # poisoned, and `finish_job`'s commit would then fail too —
                # losing the error message and stranding the row at
                # `processing` until the stale-job sweep four hours later.
                try:
                    db.db.rollback()
                except Exception:
                    pass

            try:
                reembed.finish_job(job, db, error=err_msg)
                if err_msg:
                    cron.error(f"Job {job_id} (project {project_id}): {err_msg}")
                else:
                    cron.info(
                        f"Job {job_id}: re-embedded {job.chunks_done} chunks for "
                        f"project {project_id} into {job.to_embeddings}"
                    )
                    processed += 1
            except Exception:
                logger.exception("Failed to finalize re-embed job %s", job_id)
            finally:
                try:
                    db.db.close()
                except Exception:
                    pass

        cron.finish(items_processed=processed)
    except Exception as e:
        logger.exception("Re-embed cron failed: %s", e)
        cron.error(str(e))
        cron.finish(items_processed=processed)


if __name__ == "__main__":
    main()
