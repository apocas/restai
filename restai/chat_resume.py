"""Per-`chat_id` in-memory stream resume.

When a streaming /chat call's SSE connection drops (idle proxy timeout,
flaky network, browser tab suspended), `@microsoft/fetch-event-source`
re-POSTs the request with the SSE `Last-Event-ID` header set to the
last id it saw. Without server support, that re-POST starts a brand new
agent run on the same `chat_id` — two LLM invocations racing for the
same Docker container, with the second seeing no history (because the
first hasn't saved any yet) and repeating side-effects (re-cloning a
repo, re-installing packages, …).

This module fixes that by keeping a per-`chat_id` `StreamSession` that:
- buffers every emitted SSE chunk paired with a monotonic event id
- exposes a `subscribe(last_event_id)` async iterator that first replays
  the buffer from `last_event_id + 1`, then waits live for new chunks
  until the producer marks `done`
- self-evicts a grace period after `done`

In-memory only — works inside a single uvicorn worker. Multi-worker
deployments would need Redis pub/sub, which is out of scope for this
first cut (documented limitation).
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from dataclasses import dataclass, field
from typing import AsyncIterator


logger = logging.getLogger("restai.chat_resume")


# After the producer finishes, keep the session around for this long so
# late reconnects can still replay. 5 minutes covers the common
# "browser tab was hidden, woke up" case without leaking memory.
GRACE_SECONDS = 300

# Hard cap on a single session's buffer. Anything over this drops the
# oldest tail — a client that's >5k events behind isn't realistically
# going to catch up live anyway.
MAX_EVENTS_PER_SESSION = 5000


@dataclass
class StreamSession:
    chat_id: str
    events: list[tuple[int, str]] = field(default_factory=list)
    done: bool = False
    finished_at: float | None = None
    # Strong reference to the background producer task so asyncio doesn't
    # GC it mid-run. Set by the caller right after spawning the task.
    producer_task: asyncio.Task | None = None
    # Anyio Condition for live subscribers waiting on new chunks. We
    # rebuild it lazily on first await to bind it to the right loop.
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
            self.events.append((seq, "data: " + _json.dumps({"stopped": True}) + "\n\n"))
            self.events.append((seq + 1, "event: close\n\n"))
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
            yield f"id: {seq}\n{chunk}"

        cond = self._condition()
        while True:
            async with cond:
                # Catch up events appended between replay end and acquiring the lock.
                while idx < len(self.events):
                    seq, chunk = self.events[idx]
                    idx += 1
                    yield f"id: {seq}\n{chunk}"
                if self.done:
                    return
                await cond.wait()


# Process-global registry. Keyed by chat_id; weakref isn't appropriate
# (we explicitly want to keep the session alive past the producer's
# completion for the grace window).
_sessions: dict[str, StreamSession] = {}
_sessions_lock = asyncio.Lock()


async def get_or_create(chat_id: str) -> tuple[StreamSession, bool]:
    """Return (session, is_new). GCs expired sessions to bound the dict."""
    async with _sessions_lock:
        _gc_expired_locked()
        existing = _sessions.get(chat_id)
        if existing is not None:
            return existing, False
        sess = StreamSession(chat_id=chat_id)
        _sessions[chat_id] = sess
        return sess, True


async def lookup(chat_id: str) -> StreamSession | None:
    async with _sessions_lock:
        _gc_expired_locked()
        return _sessions.get(chat_id)


async def evict(chat_id: str) -> bool:
    """Remove a session from the registry immediately, regardless of
    its done state or grace window. Used on user-initiated stop so the
    next POST with the same chat_id starts a fresh agent run instead
    of replaying the cancelled session's buffer. Returns True if a
    session was removed."""
    async with _sessions_lock:
        return _sessions.pop(chat_id, None) is not None


def _gc_expired_locked() -> None:
    now = _time.monotonic()
    drop = [
        cid for cid, s in _sessions.items()
        if s.done and s.finished_at is not None and (now - s.finished_at) > GRACE_SECONDS
    ]
    for cid in drop:
        _sessions.pop(cid, None)
    if drop:
        logger.debug("chat_resume: evicted %d expired session(s)", len(drop))
