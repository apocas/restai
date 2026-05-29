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

This used to be a single ``restai/memory_bank.py`` module; it's now split
by responsibility (``common`` / ``summarize`` / ``compress`` / ``render``
/ ``scheduling``). The public surface is unchanged and re-exported here,
so ``from restai.memory import bank`` then ``bank.summarize_conversation``
etc. works exactly as before.
"""
from __future__ import annotations

from .common import (
    COMPRESSION_HEADROOM,
    CONVERSATION_IDLE_MINUTES,
    MAX_TURNS_PER_SUMMARY,
)
from .compress import compress_entries
from .render import render_for_prompt
from .scheduling import chat_ids_needing_refresh, list_enabled_projects
from .summarize import summarize_conversation

__all__ = [
    "CONVERSATION_IDLE_MINUTES",
    "MAX_TURNS_PER_SUMMARY",
    "COMPRESSION_HEADROOM",
    "summarize_conversation",
    "compress_entries",
    "render_for_prompt",
    "list_enabled_projects",
    "chat_ids_needing_refresh",
]
