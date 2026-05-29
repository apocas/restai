"""Per-`chat_id` stream resume — in-memory by default, Redis when configured.

When a streaming /chat call's SSE connection drops (idle proxy timeout, flaky
network, browser tab suspended), `@microsoft/fetch-event-source` re-POSTs the
request with the SSE `Last-Event-ID` header set to the last id it saw. Without
server support, that re-POST starts a brand new agent run on the same
`chat_id` — two LLM invocations racing for the same Docker container, with the
second seeing no history and repeating side-effects.

This package fixes that by keeping a per-`chat_id` session that buffers every
emitted SSE chunk with a monotonic event id, exposes a `subscribe(last_event_id)`
async iterator that replays the buffer then live-tails until the producer is
done, and self-evicts a grace period after `done`.

Two backends share one public surface — the functions `get_or_create` /
`lookup` / `evict` and the session methods `append` / `finish` / `cancel` /
`subscribe` plus a settable `producer_task` (see `sse.StreamSessionProtocol`) —
so no call site changes:

- **In-memory** (`memory.StreamSession`): the default when no Redis is
  configured. Single uvicorn worker only.
- **Redis** (`redis_session.RedisStreamSession`): used when `build_redis_url()`
  returns a URL. Backs the buffer with a Redis Stream, elects a single producer
  per `chat_id` via an owner key, and routes the Stop button across workers over
  a pub/sub control channel — surviving multi-instance deployments where a
  reconnect or Stop lands on a worker that never saw the session.

Module layout:
- `sse.py`            wire format, shared constants, the session Protocol
- `memory.py`         in-memory backend (registry + StreamSession)
- `redis_client.py`   async client + cross-worker cancel control channel
- `redis_session.py`  Redis-backed session
- `__init__.py`       backend dispatch (this file)

Backend is chosen per call: the in-memory registry is consulted first (so
flipping Redis on at runtime degrades gracefully and the no-Redis path stays
untouched), then Redis when a URL is configured.
"""

from __future__ import annotations

from .memory import StreamSession, _sessions, _sessions_lock, gc_expired_locked
from .redis_client import (
    CONTROL_CHANNEL as _CONTROL_CHANNEL,
    _local_producer_tasks,
    control_listener_loop as _control_listener_loop,
    ensure_control_listener as _ensure_control_listener,
    get_redis as _get_redis,
    handle_control_message as _handle_control_message,
)
from .redis_session import RedisStreamSession
from .sse import (
    ACTIVE_TTL_SECONDS,
    GRACE_SECONDS,
    MAX_EVENTS_PER_SESSION,
    StreamSessionProtocol,
)

__all__ = ["get_or_create", "lookup", "evict", "StreamSessionProtocol"]


async def get_or_create(chat_id: str) -> "tuple[StreamSessionProtocol, bool]":
    """Return (session, is_new). The in-memory registry is checked first, then
    Redis when configured; on Redis the owner-key SET NX elects the single
    producer and decides `is_new`."""
    async with _sessions_lock:
        gc_expired_locked()
        existing = _sessions.get(chat_id)
        if existing is not None:
            return existing, False

    client = await _get_redis()
    if client is None:
        async with _sessions_lock:
            existing = _sessions.get(chat_id)
            if existing is not None:
                return existing, False
            sess = StreamSession(chat_id=chat_id)
            _sessions[chat_id] = sess
            return sess, True

    sess = RedisStreamSession(chat_id, client)
    is_new = bool(await client.set(sess._owner_key, "1", nx=True, ex=ACTIVE_TTL_SECONDS))
    if is_new:
        await client.hset(sess._meta_key, mapping={"done": "0"})
        await client.expire(sess._meta_key, ACTIVE_TTL_SECONDS)
    await _ensure_control_listener(client)
    return sess, is_new


async def lookup(chat_id: str) -> "StreamSessionProtocol | None":
    async with _sessions_lock:
        gc_expired_locked()
        existing = _sessions.get(chat_id)
        if existing is not None:
            return existing

    client = await _get_redis()
    if client is None:
        return None
    sess = RedisStreamSession(chat_id, client)
    # EXISTS over all session keys in one round-trip; the owner key covers the
    # election-crash window where owner is set but meta/stream aren't yet.
    if await client.exists(sess._meta_key, sess._stream_key, sess._owner_key):
        return sess
    return None


async def evict(chat_id: str) -> bool:
    """Remove a session immediately, regardless of done state or grace window.
    Used on user-initiated stop so the next POST with the same chat_id starts a
    fresh agent run instead of replaying the cancelled session's buffer.
    Returns True if something was removed."""
    async with _sessions_lock:
        if _sessions.pop(chat_id, None) is not None:
            return True

    client = await _get_redis()
    if client is None:
        return False
    sess = RedisStreamSession(chat_id, client)
    deleted = await client.delete(
        sess._stream_key, sess._seq_key, sess._meta_key, sess._owner_key
    )
    return deleted > 0
