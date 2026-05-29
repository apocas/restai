"""SSE framing primitives + the contract both chat-resume backends honor.

Pure module — no Redis, no asyncio I/O — so the wire format lives in exactly
one place and the in-memory and Redis backends can't drift apart.
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import AsyncIterator, Protocol


# After the producer finishes, keep the session around this long so late
# reconnects can still replay. 5 minutes covers the common "browser tab was
# hidden, woke up" case without leaking memory.
GRACE_SECONDS = 300

# Sliding TTL refreshed on every Redis append while a run is live, so an
# abandoned session (the producer's worker died mid-run) can't linger forever
# in Redis. The refresh rides on `append`, so a run that emits NOTHING for
# longer than this (>1h of total stream silence — well beyond a realistic
# agent run, which streams thoughts/tool events as chunks) lets the keys
# expire; a reconnect after that starts fresh. Kept generous so this is
# unreachable in practice.
ACTIVE_TTL_SECONDS = 3600

# Hard cap on a single session's buffer (in-memory list length / Redis stream
# MAXLEN). A client that's >5k events behind isn't realistically going to
# catch up live anyway.
MAX_EVENTS_PER_SESSION = 5000

# Terminal SSE markers pushed on a user-initiated stop, shared by both backends
# so they stay byte-identical.
STOPPED_MARKER = "data: " + _json.dumps({"stopped": True}) + "\n\n"
CLOSE_MARKER = "event: close\n\n"


def frame(seq: int, chunk: str) -> str:
    """Format one buffered chunk as an SSE event carrying its resume id."""
    return f"id: {seq}\n{chunk}"


class StreamSessionProtocol(Protocol):
    """The contract both backends honor, so callers (`helper.py`, the `/chat`
    router) stay backend-agnostic and the in-memory and Redis implementations
    can't silently drift apart."""

    chat_id: str
    producer_task: asyncio.Task | None

    async def append(self, chunk: str) -> int: ...
    async def finish(self) -> None: ...
    async def cancel(self) -> None: ...
    def subscribe(self, last_event_id: int = 0) -> AsyncIterator[str]: ...
