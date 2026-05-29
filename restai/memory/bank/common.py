"""Shared constants and small helpers for the memory bank submodules.

Everything here is dependency-light (datetime + the System LLM accessor)
so the heavier summarize/compress/render/scheduling modules can all import
from one place without cycles.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("restai.memory.bank")


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
    """Returns None on any failure so callers can degrade gracefully."""
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
