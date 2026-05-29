"""Render a project's memory bank into a system-prompt block.

Walks granularities coarsest-relevant-first and packs entries until the
token budget is hit. Returns an empty string when the project has no
entries (callers skip injection entirely in that case).
"""
from __future__ import annotations

from typing import Any

from restai.models.databasemodels import ProjectMemoryBankEntryDatabase
from restai.tools import tokens_from_string

from .common import _now


_GRANULARITY_ORDER = ("conversation", "day", "week", "month")
_GRANULARITY_HEADERS = {
    "conversation": "Recent conversations",
    "day": "By day",
    "week": "By week",
    "month": "By month",
}


def render_for_prompt(db_wrapper: Any, project_id: int, max_tokens: int) -> str:
    """Returns empty string when there are no entries."""
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
