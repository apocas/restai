"""Summarize a settled conversation into a 'conversation' bank entry.

Two paths, see `summarize_conversation`: an incremental update (cheap, only
the turns since the last summary) and a full from-scratch summary (first run
or recovery).
"""
from __future__ import annotations

from typing import Any, Optional

from restai.models.databasemodels import (
    OutputDatabase,
    ProjectMemoryBankEntryDatabase,
)
from restai.tools import tokens_from_string

from .common import (
    MAX_TURNS_PER_SUMMARY,
    _day_key,
    _now,
    _system_llm_complete,
)


_SUMMARY_INSTRUCTIONS = (
    "Summarize the conversation below into 1-3 short bullet points. "
    "Capture: (a) the topic the user was working on, (b) any concrete "
    "facts, names, IDs, or decisions that emerged, (c) any unresolved "
    "questions or follow-ups. Skip pleasantries, system messages, and "
    "tool reasoning. Output bullets only — no preamble, no headings, "
    "no quoting the user verbatim. Keep it under 80 words."
)

_INCREMENTAL_INSTRUCTIONS = (
    "You are updating an existing summary of a conversation with new "
    "turns that arrived since the previous summary. Re-emit a SINGLE "
    "consolidated summary that integrates the new information into the "
    "old (don't append, don't say 'update:' — produce a fresh summary "
    "that reads as if you'd seen the whole conversation). Same shape as "
    "before: 1-3 short bullet points covering (a) topic, (b) concrete "
    "facts/IDs/decisions, (c) unresolved questions. Skip pleasantries "
    "and tool reasoning. Keep it under 80 words."
)


def _format_messages_for_summary(rows: list[OutputDatabase]) -> str:
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
    """Summarize a chat's history via the System LLM and upsert a
    'conversation' memory bank entry. Two paths:

    - **Incremental** (preferred when an existing entry has a non-empty
      summary + last_source_at): fetch only rows newer than
      `last_source_at` and ask the LLM to integrate them into the prior
      summary. Massive saving on long chats — a 500-turn chat that grew
      by 1 turn pays for ~80 words of input instead of re-sending the
      whole transcript.
    - **Full** (first run, or recovery when prior summary is missing):
      fetch the whole history and summarize from scratch.

    Returns the persisted row, or None when nothing was written (no
    rows / no LLM / LLM failure).
    """
    sess = db_wrapper.db

    existing = (
        sess.query(ProjectMemoryBankEntryDatabase)
        .filter(
            ProjectMemoryBankEntryDatabase.project_id == project_id,
            ProjectMemoryBankEntryDatabase.granularity == "conversation",
            ProjectMemoryBankEntryDatabase.chat_id == chat_id,
        )
        .first()
    )

    can_increment = (
        existing is not None
        and (existing.summary or "").strip()
        and existing.last_source_at is not None
    )

    if can_increment:
        new_rows = (
            sess.query(OutputDatabase)
            .filter(
                OutputDatabase.project_id == project_id,
                OutputDatabase.chat_id == chat_id,
                OutputDatabase.date > existing.last_source_at,
            )
            .order_by(OutputDatabase.date.asc())
            .all()
        )
        if not new_rows:
            return None
        # Cap at the MOST RECENT N — when a chat had a backlog larger
        # than MAX_TURNS_PER_SUMMARY since the last tick, the freshest
        # turns matter most for context.
        capped = new_rows[-MAX_TURNS_PER_SUMMARY:]
        new_transcript = _format_messages_for_summary(capped)
        if not new_transcript.strip():
            return None
        prompt = (
            f"{_INCREMENTAL_INSTRUCTIONS}\n\n"
            f"--- existing summary ---\n{existing.summary}\n\n"
            f"--- new turns ---\n{new_transcript}\n---"
        )
        last_at = new_rows[-1].date or _now()
        next_source_count = (existing.source_message_count or 0) + len(new_rows)
    else:
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
        last_at = rows[-1].date or _now()
        next_source_count = len(rows)

    summary = _system_llm_complete(brain, db_wrapper, prompt)
    if not summary:
        return None

    period_key = _day_key(last_at)
    token_count = tokens_from_string(summary)
    now = _now()

    if existing is not None:
        existing.summary = summary
        existing.token_count = token_count
        existing.source_message_count = next_source_count
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
        source_message_count=next_source_count,
        last_source_at=last_at,
        created_at=now,
        updated_at=now,
    )
    sess.add(row)
    sess.commit()
    return row
