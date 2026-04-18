"""Project-wide memory bank: shared, compressed conversation context.

When a project has `memory_bank_enabled=True` in its options, every chat
conversation contributes a short LLM-generated summary to the project's
shared memory bank. The bank is then injected into the system prompt of
every subsequent chat in that project, giving the agent context across
users and across sessions.

Design notes:

- **Source of truth** is `OutputDatabase` (one row per inference). It is
  authoritative across multi-worker deployments, survives Redis TTLs, and
  stays bound to a `project_id`. Chat sessions in Redis are *not* used
  here — they aren't enumerable by project and would require a SCAN.
- **Summaries are produced by the System LLM** (the global setting also
  used by Smart Search / Prompt AI). When no System LLM is configured the
  cron is a no-op.
- **Compression ladder**: conversation → day → week → month. The cron
  rolls older entries up to coarser granularities until the rendered
  block fits within `memory_bank_max_tokens`. Entries that don't fit
  even after the coarsest rollup are dropped (oldest first).
- **Privacy**: every project member sees summaries derived from every
  other member's conversations — the project edit form surfaces a
  disclaimer for this reason.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func

from restai.models.databasemodels import (
    OutputDatabase,
    ProjectDatabase,
    ProjectMemoryBankEntryDatabase,
)
from restai.tools import tokens_from_string

logger = logging.getLogger(__name__)


# Conversations idle for at least this long are considered "settled" and
# eligible for summarization. Avoids re-summarizing an active chat between
# every turn.
CONVERSATION_IDLE_MINUTES = 10

# Per-summary cap. Keeps any single LLM call deterministic in cost regardless
# of how chatty a conversation got.
MAX_TURNS_PER_SUMMARY = 40

# Token budget overrun headroom before the cron triggers compression. We
# don't compress on every cron tick — only when the bank is meaningfully
# over-budget, to avoid burning System LLM tokens on rolling up entries
# that fit within a small overshoot.
COMPRESSION_HEADROOM = 1.25


# --------------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _week_key(dt: datetime) -> str:
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _system_llm_complete(brain: Any, db: Any, prompt: str) -> Optional[str]:
    """Run a one-shot completion via the System LLM. Returns None on any
    failure so callers can degrade gracefully (skip this entry, not crash)."""
    llm = brain.get_system_llm(db)
    if llm is None:
        return None
    try:
        result = llm.llm.complete(prompt)
        text = result.text if hasattr(result, "text") else str(result)
        return (text or "").strip() or None
    except Exception as e:
        logger.warning("memory_bank: System LLM completion failed: %s", e)
        return None


# --------------------------------------------------------------------- summarize


_SUMMARY_INSTRUCTIONS = (
    "Summarize the conversation below into 1-3 short bullet points. "
    "Capture: (a) the topic the user was working on, (b) any concrete "
    "facts, names, IDs, or decisions that emerged, (c) any unresolved "
    "questions or follow-ups. Skip pleasantries, system messages, and "
    "tool reasoning. Output bullets only — no preamble, no headings, "
    "no quoting the user verbatim. Keep it under 80 words."
)

_DIGEST_INSTRUCTIONS = (
    "You are merging multiple conversation summaries into a single short "
    "digest. Preserve the most important facts, names, IDs, decisions, "
    "and outstanding questions across all summaries. Output 2-4 short "
    "bullets — no preamble, no headings. Keep it under 120 words."
)


def _format_messages_for_summary(rows: list[OutputDatabase]) -> str:
    """Render OutputDatabase rows as a chat transcript for the summarizer."""
    lines = []
    for r in rows[:MAX_TURNS_PER_SUMMARY]:
        q = (r.question or "").strip()
        a = (r.answer or "").strip()
        if q:
            lines.append(f"User: {q}")
        if a:
            lines.append(f"Assistant: {a}")
    return "\n".join(lines)


def summarize_conversation(
    brain: Any,
    db_wrapper: Any,
    project_id: int,
    chat_id: str,
) -> Optional[ProjectMemoryBankEntryDatabase]:
    """Pull this chat_id's history from OutputDatabase, summarize it via the
    System LLM, and upsert a 'conversation' memory bank entry. Returns the
    persisted row, or None when nothing was written (no rows / no LLM /
    LLM failure)."""
    sess = db_wrapper.db
    rows = (
        sess.query(OutputDatabase)
        .filter(
            OutputDatabase.project_id == project_id,
            OutputDatabase.chat_id == chat_id,
        )
        .order_by(OutputDatabase.date.asc())
        .all()
    )
    if not rows:
        return None

    transcript = _format_messages_for_summary(rows)
    if not transcript.strip():
        return None

    prompt = f"{_SUMMARY_INSTRUCTIONS}\n\n---\n{transcript}\n---"
    summary = _system_llm_complete(brain, db_wrapper, prompt)
    if not summary:
        return None

    last_at = rows[-1].date or _now()
    period_key = _day_key(last_at)
    token_count = tokens_from_string(summary)

    existing = (
        sess.query(ProjectMemoryBankEntryDatabase)
        .filter(
            ProjectMemoryBankEntryDatabase.project_id == project_id,
            ProjectMemoryBankEntryDatabase.granularity == "conversation",
            ProjectMemoryBankEntryDatabase.chat_id == chat_id,
        )
        .first()
    )
    now = _now()
    if existing is not None:
        existing.summary = summary
        existing.token_count = token_count
        existing.source_message_count = len(rows)
        existing.last_source_at = last_at
        existing.period_key = period_key
        existing.updated_at = now
        sess.commit()
        return existing

    row = ProjectMemoryBankEntryDatabase(
        project_id=project_id,
        chat_id=chat_id,
        granularity="conversation",
        period_key=period_key,
        summary=summary,
        token_count=token_count,
        source_message_count=len(rows),
        last_source_at=last_at,
        created_at=now,
        updated_at=now,
    )
    sess.add(row)
    sess.commit()
    return row


# --------------------------------------------------------------------- compress


def _digest_entries(
    brain: Any,
    db_wrapper: Any,
    entries: list[ProjectMemoryBankEntryDatabase],
) -> Optional[str]:
    """Merge multiple existing summaries into a single coarser digest."""
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


# --------------------------------------------------------------------- render


_GRANULARITY_ORDER = ("conversation", "day", "week", "month")
_GRANULARITY_HEADERS = {
    "conversation": "Recent conversations",
    "day": "By day",
    "week": "By week",
    "month": "By month",
}


def render_for_prompt(db_wrapper: Any, project_id: int, max_tokens: int) -> str:
    """Produce the memory bank block that gets prepended to the system prompt.

    Returns an empty string when there are no entries (so callers can
    cheaply check `if block:` before bothering to splice it in).
    """
    sess = db_wrapper.db
    rows = (
        sess.query(ProjectMemoryBankEntryDatabase)
        .filter(ProjectMemoryBankEntryDatabase.project_id == project_id)
        .all()
    )
    if not rows:
        return ""

    by_gran: dict[str, list[ProjectMemoryBankEntryDatabase]] = {}
    for r in rows:
        by_gran.setdefault(r.granularity, []).append(r)
    for entries in by_gran.values():
        entries.sort(
            key=lambda e: e.last_source_at or e.updated_at or _now(),
            reverse=True,
        )

    lines = ["[Project Memory Bank — context aggregated from prior conversations in this project. Use only when directly relevant to the current request.]"]
    used = tokens_from_string(lines[0])

    for gran in _GRANULARITY_ORDER:
        entries = by_gran.get(gran, [])
        if not entries:
            continue
        header = f"\n## {_GRANULARITY_HEADERS[gran]}"
        header_tokens = tokens_from_string(header)
        if used + header_tokens > max_tokens:
            break
        lines.append(header)
        used += header_tokens
        for e in entries:
            label = e.period_key or (e.chat_id[:8] if e.chat_id else "")
            body = e.summary.strip()
            chunk = f"\n- ({label}) {body}" if label else f"\n- {body}"
            chunk_tokens = tokens_from_string(chunk)
            if used + chunk_tokens > max_tokens:
                break
            lines.append(chunk)
            used += chunk_tokens

    return "".join(lines).strip()


# --------------------------------------------------------------------- public


def list_enabled_projects(db_wrapper: Any) -> Iterable[ProjectDatabase]:
    """Yield projects with memory_bank_enabled=True. Done by inspecting the
    options JSON blob — there's no dedicated column."""
    import json

    rows = (
        db_wrapper.db.query(ProjectDatabase)
        .filter(ProjectDatabase.type == "agent")
        .all()
    )
    for proj in rows:
        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            continue
        if opts.get("memory_bank_enabled"):
            yield proj


def chat_ids_needing_refresh(
    db_wrapper: Any,
    project_id: int,
    idle_minutes: int = CONVERSATION_IDLE_MINUTES,
) -> list[str]:
    """Return chat_ids that have new OutputDatabase rows since the last
    summarization and are now idle (last activity older than `idle_minutes`).
    """
    sess = db_wrapper.db
    cutoff = _now() - timedelta(minutes=idle_minutes)

    latest_per_chat = (
        sess.query(
            OutputDatabase.chat_id,
            func.max(OutputDatabase.date).label("latest"),
        )
        .filter(
            OutputDatabase.project_id == project_id,
            OutputDatabase.chat_id.isnot(None),
        )
        .group_by(OutputDatabase.chat_id)
        .having(func.max(OutputDatabase.date) <= cutoff)
        .all()
    )

    out: list[str] = []
    for chat_id, latest in latest_per_chat:
        if not chat_id:
            continue
        existing = (
            sess.query(ProjectMemoryBankEntryDatabase)
            .filter(
                ProjectMemoryBankEntryDatabase.project_id == project_id,
                ProjectMemoryBankEntryDatabase.granularity == "conversation",
                ProjectMemoryBankEntryDatabase.chat_id == chat_id,
            )
            .first()
        )
        if existing is None or (existing.last_source_at or datetime.min) < latest:
            out.append(chat_id)
    return out
