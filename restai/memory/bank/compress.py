"""Compression ladder: roll older entries up into coarser time buckets.

conversation → day (>1d) → week (>7d) → month (>30d), then drop oldest as a
last resort. Each rollup merges a group of entries into a single System-LLM
digest at the coarser granularity.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func

from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
from restai.tools import tokens_from_string

from .common import (
    COMPRESSION_HEADROOM,
    _day_key,
    _month_key,
    _now,
    _system_llm_complete,
    _week_key,
)


_DIGEST_INSTRUCTIONS = (
    "You are merging multiple conversation summaries into a single short "
    "digest. Preserve the most important facts, names, IDs, decisions, "
    "and outstanding questions across all summaries. Output 2-4 short "
    "bullets — no preamble, no headings. Keep it under 120 words."
)


def _digest_entries(
    brain: Any,
    db_wrapper: Any,
    entries: list[ProjectMemoryBankEntryDatabase],
) -> Optional[str]:
    if not entries:
        return None
    parts = []
    for e in entries:
        prefix = f"[{e.granularity}:{e.period_key or ''}]" if e.period_key else f"[{e.granularity}]"
        parts.append(f"{prefix} {e.summary.strip()}")
    blob = "\n".join(parts)
    prompt = f"{_DIGEST_INSTRUCTIONS}\n\n---\n{blob}\n---"
    return _system_llm_complete(brain, db_wrapper, prompt)


def _rollup(
    brain: Any,
    db_wrapper: Any,
    project_id: int,
    from_granularity: str,
    to_granularity: str,
    age_threshold: timedelta,
    key_fn,
) -> int:
    """Group entries of `from_granularity` older than `age_threshold` by
    `key_fn(last_source_at)` and replace each group with a single digest at
    `to_granularity`. Returns the number of digests created."""
    sess = db_wrapper.db
    cutoff = _now() - age_threshold
    rows = (
        sess.query(ProjectMemoryBankEntryDatabase)
        .filter(
            ProjectMemoryBankEntryDatabase.project_id == project_id,
            ProjectMemoryBankEntryDatabase.granularity == from_granularity,
            ProjectMemoryBankEntryDatabase.last_source_at != None,
            ProjectMemoryBankEntryDatabase.last_source_at < cutoff,
        )
        .all()
    )
    if not rows:
        return 0

    groups: dict[str, list[ProjectMemoryBankEntryDatabase]] = {}
    for r in rows:
        groups.setdefault(key_fn(r.last_source_at), []).append(r)

    created = 0
    for period_key, group in groups.items():
        # If this period already has a digest at the target granularity,
        # fold the new group into it via a re-digest.
        existing_digest = (
            sess.query(ProjectMemoryBankEntryDatabase)
            .filter(
                ProjectMemoryBankEntryDatabase.project_id == project_id,
                ProjectMemoryBankEntryDatabase.granularity == to_granularity,
                ProjectMemoryBankEntryDatabase.period_key == period_key,
            )
            .first()
        )
        merge_inputs = list(group)
        if existing_digest is not None:
            merge_inputs.append(existing_digest)

        digest = _digest_entries(brain, db_wrapper, merge_inputs)
        if not digest:
            # System LLM unavailable / failed — skip this rollup; the cron
            # will retry next tick. Don't delete sources, don't half-commit.
            continue

        last_source_at = max((r.last_source_at for r in group), default=_now())
        source_message_count = sum(r.source_message_count or 0 for r in group)
        token_count = tokens_from_string(digest)
        now = _now()

        if existing_digest is not None:
            existing_digest.summary = digest
            existing_digest.token_count = token_count
            existing_digest.source_message_count += source_message_count
            existing_digest.last_source_at = max(
                existing_digest.last_source_at or last_source_at, last_source_at
            )
            existing_digest.updated_at = now
        else:
            sess.add(ProjectMemoryBankEntryDatabase(
                project_id=project_id,
                chat_id=None,
                granularity=to_granularity,
                period_key=period_key,
                summary=digest,
                token_count=token_count,
                source_message_count=source_message_count,
                last_source_at=last_source_at,
                created_at=now,
                updated_at=now,
            ))
        for r in group:
            sess.delete(r)
        created += 1

    sess.commit()
    return created


def compress_entries(
    brain: Any,
    db_wrapper: Any,
    project_id: int,
    max_tokens: int,
) -> None:
    """Run the rollup ladder until the project's bank fits within budget.

    Order: conversation→day (>1d old), day→week (>7d old), week→month
    (>30d old). If still over budget after the coarsest rollup, drop the
    oldest entries until we fit.
    """
    sess = db_wrapper.db

    def total_tokens() -> int:
        return int(
            sess.query(func.coalesce(func.sum(ProjectMemoryBankEntryDatabase.token_count), 0))
            .filter(ProjectMemoryBankEntryDatabase.project_id == project_id)
            .scalar()
            or 0
        )

    if total_tokens() <= max_tokens * COMPRESSION_HEADROOM:
        return

    _rollup(brain, db_wrapper, project_id, "conversation", "day",
            timedelta(days=1), _day_key)
    if total_tokens() <= max_tokens:
        return

    _rollup(brain, db_wrapper, project_id, "day", "week",
            timedelta(days=7), _week_key)
    if total_tokens() <= max_tokens:
        return

    _rollup(brain, db_wrapper, project_id, "week", "month",
            timedelta(days=30), _month_key)
    if total_tokens() <= max_tokens:
        return

    # Last resort: drop oldest entries until we're within budget. Use
    # coalesce(last_source_at, created_at) so a row with a NULL last_source_at
    # still has a deterministic ordering position across SQLite/Postgres/MySQL.
    while total_tokens() > max_tokens:
        oldest = (
            sess.query(ProjectMemoryBankEntryDatabase)
            .filter(ProjectMemoryBankEntryDatabase.project_id == project_id)
            .order_by(
                func.coalesce(
                    ProjectMemoryBankEntryDatabase.last_source_at,
                    ProjectMemoryBankEntryDatabase.created_at,
                ).asc()
            )
            .first()
        )
        if oldest is None:
            return
        sess.delete(oldest)
        sess.commit()
