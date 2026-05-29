"""In-memory `StreamSession` — the default backend when Redis is unset.

Single uvicorn worker only: the registry, the live-notify `Condition`, and the
producer task all live in one process. Behavior is byte-identical to the
original pre-Redis implementation.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from typing import AsyncIterator

from .sse import (
    CLOSE_MARKER,
    GRACE_SECONDS,
    MAX_EVENTS_PER_SESSION,
    STOPPED_MARKER,
    frame,
)

logger = logging.getLogger("restai.chat_resume")


@dataclass
class StreamSession:
    chat_id: str
    events: list[tuple[int, str]] = field(default_factory=list)
    done: bool = False
    finished_at: float | None = None
    # Strong reference to the background producer task so asyncio doesn't
    # GC it mid-run. Set by the caller right after spawning the task.
    producer_task: asyncio.Task | None = None
    # Condition for live subscribers waiting on new chunks. Rebuilt lazily on
    # first await to bind it to the right loop.
    _cond: asyncio.Condition | None = None

    def _condition(self) -> asyncio.Condition:
        if self._cond is None:
            self._cond = asyncio.Condition()
        return self._cond

    async def append(self, chunk: str) -> int:
        cond = self._condition()
        async with cond:
            seq = (self.events[-1][0] + 1) if self.events else 1
            self.events.append((seq, chunk))
            if len(self.events) > MAX_EVENTS_PER_SESSION:
                # Drop oldest. The subscriber that fell that far behind
                # will get nothing useful from a replay anyway.
                del self.events[: len(self.events) - MAX_EVENTS_PER_SESSION]
            cond.notify_all()
        return seq

    async def finish(self) -> None:
        cond = self._condition()
        async with cond:
            self.done = True
            self.finished_at = _time.monotonic()
            cond.notify_all()

    async def cancel(self) -> None:
        """User-initiated stop: cancel the background producer task so
        the agent loop unwinds (no more LLM calls, no more tool calls),
        push a final 'stopped' marker into the buffer, and mark done.
        Idempotent — calling on an already-done session is a no-op."""
        if self.done:
            return
        task = self.producer_task
        if task is not None and not task.done():
            task.cancel()
        cond = self._condition()
        async with cond:
            if self.done:
                return
            seq = (self.events[-1][0] + 1) if self.events else 1
            self.events.append((seq, STOPPED_MARKER))
            self.events.append((seq + 1, CLOSE_MARKER))
            self.done = True
            self.finished_at = _time.monotonic()
            cond.notify_all()

    async def subscribe(self, last_event_id: int = 0) -> AsyncIterator[str]:
        """Replay events with id > last_event_id, then yield live ones until done."""
        # Replay (no lock — list slicing is cheap; tolerating mid-mutation is fine).
        idx = 0
        while idx < len(self.events):
            seq, chunk = self.events[idx]
            idx += 1
            if seq <= last_event_id:
                continue
            yield frame(seq, chunk)

        cond = self._condition()
        while True:
            async with cond:
                # Catch up events appended between replay end and acquiring the lock.
                while idx < len(self.events):
                    seq, chunk = self.events[idx]
                    idx += 1
                    yield frame(seq, chunk)
                if self.done:
                    return
                await cond.wait()


# Process-global in-memory registry. Keyed by chat_id; weakref isn't
# appropriate (we explicitly want to keep the session alive past the
# producer's completion for the grace window).
_sessions: dict[str, StreamSession] = {}
_sessions_lock = asyncio.Lock()


def gc_expired_locked() -> None:
    """Drop sessions whose grace window has elapsed. Caller holds the lock."""
    now = _time.monotonic()
    drop = [
        cid for cid, s in _sessions.items()
        if s.done and s.finished_at is not None and (now - s.finished_at) > GRACE_SECONDS
    ]
    for cid in drop:
        _sessions.pop(cid, None)
    if drop:
        logger.debug("chat_resume: evicted %d expired session(s)", len(drop))
