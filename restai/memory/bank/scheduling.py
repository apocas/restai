"""Cron-facing enumeration: which projects/chats need (re)summarizing.

`list_enabled_projects` finds agent projects with the bank turned on;
`chat_ids_needing_refresh` finds settled conversations whose summary is
stale (or missing and not already absorbed into a coarser digest).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import func

from restai.models.databasemodels import (
    OutputDatabase,
    ProjectDatabase,
    ProjectMemoryBankEntryDatabase,
)

from .common import (
    CONVERSATION_IDLE_MINUTES,
    _day_key,
    _month_key,
    _now,
    _week_key,
)


def list_enabled_projects(db_wrapper: Any) -> Iterable[ProjectDatabase]:
    """Yield projects with memory_bank_enabled=True (read from options JSON)."""
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
    """Chat_ids with new rows since last summarization, now idle longer than `idle_minutes`."""
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
        if existing is not None:
            if (existing.last_source_at or datetime.min) >= latest:
                continue  # up to date
            out.append(chat_id)
            continue
        # No conversation entry — but the chat may already be absorbed
        # into a day/week/month digest from a previous compression cycle.
        # Without this check, every compression tick that rolls a chat up
        # would re-add it to the refresh queue (the conversation row is
        # deleted by `_rollup`), causing infinite re-summarization on the
        # same chats and the backlog never drains.
        absorbed = (
            sess.query(ProjectMemoryBankEntryDatabase.id)
            .filter(
                ProjectMemoryBankEntryDatabase.project_id == project_id,
                ProjectMemoryBankEntryDatabase.granularity != "conversation",
                ProjectMemoryBankEntryDatabase.last_source_at >= latest,
                ProjectMemoryBankEntryDatabase.period_key.in_([
                    _day_key(latest),
                    _week_key(latest),
                    _month_key(latest),
                ]),
            )
            .first()
        )
        if absorbed is not None:
            continue
        out.append(chat_id)
    return out
