"""Per-`chat_id` stream resume — in-memory, mirrored to Redis when configured.

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

## Multi-instance

The producer (detached agent run) lives on ONE instance, but a reconnect
or Stop POST can land on ANY instance behind a load balancer. When Redis
is configured (`config.build_redis_url()`), the producing instance keeps
its fast in-memory session AND mirrors every event to a Redis Stream, so
other instances can:
- `lookup` / `get_or_create` find the session (shared producer claim lock)
- `subscribe` replay + tail the buffer via the Redis Stream
- `cancel` halt the remote producer over a Redis pub/sub control channel

SSE event ids stay plain integers (assigned by the producer, stored as a
field on each stream entry), so a reconnect's `Last-Event-ID` is a valid
cursor regardless of which instance serves it.

When Redis is NOT configured this is pure in-memory, single-instance —
exactly the prior behavior. Redis errors degrade to in-memory (the
same-instance stream keeps working; only cross-instance reach is lost).
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Union

from restai import config

logger = logging.getLogger("restai.chat_resume")


# After the producer finishes, keep the session around for this long so
# late reconnects can still replay. 5 minutes covers the common
# "browser tab was hidden, woke up" case without leaking memory.
GRACE_SECONDS = 300

# Hard cap on a single session's buffer. Anything over this drops the
# oldest tail — a client that's >5k events behind isn't realistically
# going to catch up live anyway.
MAX_EVENTS_PER_SESSION = 5000

# Producer-claim lock TTL. Outlasts any realistic agent turn; refreshed
# on every append so a live producer keeps it, and a crashed producer's
# lock expires (freeing the chat_id) within this window.
PRODUCER_LOCK_TTL = 600

# Stream/meta TTL while a producer is active. Dropped to GRACE_SECONDS on
# finish/cancel so finished sessions self-expire like the in-memory ones.
ACTIVE_TTL = 3600

# How long an idle Redis subscriber blocks per XREAD before re-checking
# the done flag. Small enough to notice end promptly, large enough to
# avoid busy-looping.
XREAD_BLOCK_MS = 5000

_KEY_PREFIX = "chat_resume:"


def _k_events(chat_id: str) -> str:
    return f"{_KEY_PREFIX}{chat_id}:events"


def _k_meta(chat_id: str) -> str:
    return f"{_KEY_PREFIX}{chat_id}:meta"


def _k_lock(chat_id: str) -> str:
    return f"{_KEY_PREFIX}{chat_id}:lock"


def _k_control(chat_id: str) -> str:
    return f"{_KEY_PREFIX}{chat_id}:control"


# --------------------------------------------------------------------------
# Redis client (module-global, lazy, self-healing on URL change)
# --------------------------------------------------------------------------

_redis_client = None
_redis_url: Optional[str] = None


def _close_client_async(client) -> None:
    """Fire-and-forget close of a superseded async Redis client."""
    if client is None:
        return
    closer = getattr(client, "aclose", None) or getattr(client, "close", None)
    if closer is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.create_task(closer())
    except Exception:
        pass


def _redis():
    """Cached `redis.asyncio` client, or None when Redis is unconfigured /
    unavailable. Rebuilds when the configured URL changes so admin Settings
    edits are picked up without a restart."""
    global _redis_client, _redis_url
    url = config.build_redis_url()
    if not url:
        if _redis_client is not None:
            _close_client_async(_redis_client)
            _redis_client = None
            _redis_url = None
        return None
    if _redis_client is not None and _redis_url == url:
        return _redis_client
    if _redis_client is not None:
        _close_client_async(_redis_client)
        _redis_client = None
        _redis_url = None
    try:
        import redis.asyncio as aioredis  # type: ignore
    except ImportError:
        logger.warning(
            "redis.asyncio not installed; chat_resume is single-instance only"
        )
        return None
    try:
        _redis_client = aioredis.from_url(url, decode_responses=True)
        _redis_url = url
    except Exception as e:
        logger.warning(
            "chat_resume: failed to build Redis client (%s); single-instance only", e
        )
        _redis_client = None
        _redis_url = None
        return None
    return _redis_client


# --------------------------------------------------------------------------
# Producing session — in-memory buffer, optionally mirrored to Redis
# --------------------------------------------------------------------------


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
    # True when this session mirrors to Redis (Redis was configured when
    # the producer was created). Stays fixed for the session's lifetime
    # so the backend can't flip mid-stream.
    _redis: bool = False
    # Value written to the producer-claim lock; used for guarded release.
    _lock_token: str | None = None
    # Cross-instance cancel watcher (pub/sub subscriber) task.
    _watcher: asyncio.Task | None = None

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
        if self._redis:
            await self._mirror_append(seq, chunk)
        return seq

    async def finish(self) -> None:
        cond = self._condition()
        async with cond:
            if not self.done:
                self.done = True
                self.finished_at = _time.monotonic()
            cond.notify_all()
        self._stop_watcher()
        if self._redis:
            await self._mirror_end()

    async def cancel(self) -> None:
        """User-initiated stop: cancel the background producer task so
        the agent loop unwinds (no more LLM calls, no more tool calls),
        push a final 'stopped' marker into the buffer, and mark done.
        Idempotent — calling on an already-done session is a no-op."""
        if self.done:
            # Already ended; still nudge any remote producer to be safe.
            if self._redis:
                await self._publish_cancel()
            return
        task = self.producer_task
        if task is not None and not task.done():
            task.cancel()
        cond = self._condition()
        markers: list[tuple[int, str]] = []
        async with cond:
            if not self.done:
                seq = (self.events[-1][0] + 1) if self.events else 1
                stopped = "data: " + _json.dumps({"stopped": True}) + "\n\n"
                close = "event: close\n\n"
                self.events.append((seq, stopped))
                self.events.append((seq + 1, close))
                markers = [(seq, stopped), (seq + 1, close)]
                self.done = True
                self.finished_at = _time.monotonic()
            cond.notify_all()
        self._stop_watcher()
        if self._redis:
            await self._publish_cancel()
            await self._mirror_end(extra_markers=markers)

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

    async def is_in_flight(self) -> bool:
        return not self.done

    # ---- Redis mirroring ------------------------------------------------

    async def _mirror_append(self, seq: int, chunk: str) -> None:
        client = _redis()
        if client is None:
            return
        cid = self.chat_id
        try:
            await client.xadd(
                _k_events(cid),
                {"s": str(seq), "d": chunk},
                maxlen=MAX_EVENTS_PER_SESSION,
                approximate=True,
            )
            await client.expire(_k_events(cid), ACTIVE_TTL)
            await client.expire(_k_lock(cid), PRODUCER_LOCK_TTL)
        except Exception as e:
            logger.warning("chat_resume: redis append mirror failed (%s)", e)

    async def _mirror_end(
        self, extra_markers: list[tuple[int, str]] | None = None
    ) -> None:
        """Write terminal markers + eof to Redis exactly once (HSETNX guard),
        release our producer lock, and shrink the grace TTL. Safe to call
        from any instance; only the guard winner writes the markers."""
        client = _redis()
        if client is None:
            return
        cid = self.chat_id
        try:
            won = await client.hsetnx(_k_meta(cid), "ended", "1")
            if won:
                for seq, chunk in extra_markers or []:
                    await client.xadd(
                        _k_events(cid),
                        {"s": str(seq), "d": chunk},
                        maxlen=MAX_EVENTS_PER_SESSION,
                        approximate=True,
                    )
                await client.xadd(_k_events(cid), {"eof": "1"})
                await client.hset(
                    _k_meta(cid),
                    mapping={"status": "done", "finished_at": str(_time.time())},
                )
            await self._release_lock(client)
            await client.expire(_k_events(cid), GRACE_SECONDS)
            await client.expire(_k_meta(cid), GRACE_SECONDS)
        except Exception as e:
            logger.warning("chat_resume: redis end mirror failed (%s)", e)

    async def _release_lock(self, client) -> None:
        """Delete the producer lock only if we still own it (guards against
        deleting a lock a later producer claimed after ours expired)."""
        if not self._lock_token:
            return
        try:
            await client.eval(_UNLOCK_LUA, 1, _k_lock(self.chat_id), self._lock_token)
        except Exception:
            pass

    async def _publish_cancel(self) -> None:
        client = _redis()
        if client is None:
            return
        try:
            await client.publish(_k_control(self.chat_id), "cancel")
        except Exception as e:
            logger.warning("chat_resume: redis publish cancel failed (%s)", e)

    # ---- Cross-instance cancel watcher ----------------------------------

    def start_cancel_watcher(self) -> None:
        """Spawn a pub/sub subscriber that cancels this producer when any
        instance publishes 'cancel' on the control channel. No-op without
        Redis or if already running."""
        if not self._redis or self._watcher is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._watcher = loop.create_task(self._watch_control())

    async def _watch_control(self) -> None:
        client = _redis()
        if client is None:
            return
        pubsub = None
        try:
            pubsub = client.pubsub()
            await pubsub.subscribe(_k_control(self.chat_id))
            async for message in pubsub.listen():
                if not message or message.get("type") != "message":
                    continue
                data = message.get("data")
                if data == "cancel" or data == b"cancel":
                    # Cancels the local producer task + emits the local
                    # 'stopped' marker so this instance's subscribers see it.
                    await self.cancel()
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("chat_resume: control watcher error (%s)", e)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(_k_control(self.chat_id))
                except Exception:
                    pass
                try:
                    closer = getattr(pubsub, "aclose", None) or getattr(
                        pubsub, "close", None
                    )
                    if closer is not None:
                        await closer()
                except Exception:
                    pass

    def _stop_watcher(self) -> None:
        w = self._watcher
        if w is None:
            return
        self._watcher = None
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        # When cancel() is invoked BY the watcher itself, don't self-cancel
        # mid-flight — let it finish the Redis mirror then exit via `break`.
        if w is not current and not w.done():
            w.cancel()


# Lua: delete the lock only if its value matches our token.
_UNLOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


# --------------------------------------------------------------------------
# Redis subscriber proxy — used on instances that are NOT the producer
# --------------------------------------------------------------------------


@dataclass
class RedisSubscriberSession:
    """Read-only view of a session whose producer runs on another instance.
    Backed entirely by Redis. `subscribe` tails the stream; `cancel` signals
    the producing instance over pub/sub and writes the terminal markers."""

    chat_id: str
    producer_task: asyncio.Task | None = None  # never set; API symmetry only

    def start_cancel_watcher(self) -> None:
        return  # proxies never produce

    async def append(self, chunk: str) -> int:
        return 0  # defensive: a proxy must never produce

    async def finish(self) -> None:
        return

    async def is_in_flight(self) -> bool:
        client = _redis()
        if client is None:
            return False
        try:
            return (await client.hget(_k_meta(self.chat_id), "status")) == "active"
        except Exception:
            return False

    async def subscribe(self, last_event_id: int = 0) -> AsyncIterator[str]:
        client = _redis()
        if client is None:
            return
        cid = self.chat_id
        cursor = "0"  # Redis stream entry-id cursor (distinct from SSE seq)

        # Replay everything already in the stream, skipping seqs the client
        # has already seen. Stop if we hit the eof marker.
        try:
            entries = await client.xrange(_k_events(cid), min="-", max="+")
        except Exception as e:
            logger.warning("chat_resume: redis replay failed (%s)", e)
            entries = []
        for entry_id, fields in entries:
            cursor = entry_id
            if "eof" in fields:
                return
            line = _render(fields, last_event_id)
            if line is not None:
                yield line

        # Tail live entries.
        while True:
            try:
                resp = await client.xread(
                    {_k_events(cid): cursor}, block=XREAD_BLOCK_MS, count=64
                )
            except Exception as e:
                logger.warning("chat_resume: redis tail failed (%s)", e)
                return
            if not resp:
                # Idle timeout — stop if the producer finished, or the keys
                # were evicted out from under us.
                try:
                    if (await client.hget(_k_meta(cid), "status")) == "done":
                        return
                    if not await client.exists(_k_events(cid)):
                        return
                except Exception:
                    return
                continue
            for _stream, items in resp:
                for entry_id, fields in items:
                    cursor = entry_id
                    if "eof" in fields:
                        return
                    line = _render(fields, last_event_id)
                    if line is not None:
                        yield line

    async def cancel(self) -> None:
        client = _redis()
        if client is None:
            return
        cid = self.chat_id
        # Halt the producer on whichever instance owns it.
        try:
            await client.publish(_k_control(cid), "cancel")
        except Exception as e:
            logger.warning("chat_resume: redis publish cancel failed (%s)", e)
        # Write the terminal markers ourselves (guarded) in case the producer
        # is unreachable, so cross-instance subscribers still stop cleanly.
        try:
            won = await client.hsetnx(_k_meta(cid), "ended", "1")
            if won:
                last_seq = 0
                try:
                    rev = await client.xrevrange(_k_events(cid), count=1)
                    if rev and "s" in rev[0][1]:
                        last_seq = int(rev[0][1]["s"])
                except Exception:
                    pass
                stopped = "data: " + _json.dumps({"stopped": True}) + "\n\n"
                close = "event: close\n\n"
                await client.xadd(
                    _k_events(cid),
                    {"s": str(last_seq + 1), "d": stopped},
                    maxlen=MAX_EVENTS_PER_SESSION,
                    approximate=True,
                )
                await client.xadd(
                    _k_events(cid),
                    {"s": str(last_seq + 2), "d": close},
                    maxlen=MAX_EVENTS_PER_SESSION,
                    approximate=True,
                )
                await client.xadd(_k_events(cid), {"eof": "1"})
                await client.hset(
                    _k_meta(cid),
                    mapping={"status": "done", "finished_at": str(_time.time())},
                )
            await client.delete(_k_lock(cid))
            await client.expire(_k_events(cid), GRACE_SECONDS)
            await client.expire(_k_meta(cid), GRACE_SECONDS)
        except Exception as e:
            logger.warning("chat_resume: redis proxy cancel failed (%s)", e)


def _render(fields: dict, last_event_id: int) -> Optional[str]:
    """Turn a Redis stream data entry into an SSE block, or None to skip."""
    s = fields.get("s")
    if s is None:
        return None
    try:
        seq = int(s)
    except (TypeError, ValueError):
        return None
    if seq <= last_event_id:
        return None
    return f"id: {seq}\n{fields.get('d', '')}"


Session = Union[StreamSession, RedisSubscriberSession]


# Process-local registry of producing sessions. Keyed by chat_id; weakref
# isn't appropriate (we explicitly keep the session alive past the
# producer's completion for the grace window).
_sessions: dict[str, StreamSession] = {}
_sessions_lock = asyncio.Lock()


async def get_or_create(chat_id: str) -> tuple[Session, bool]:
    """Return (session, is_new). `is_new` means the caller owns the producer
    (should spawn the agent run). Attaches to an in-flight session for dedup;
    a finished session is discarded so a reused chat_id starts a fresh run."""
    async with _sessions_lock:
        _gc_expired_locked()
        existing = _sessions.get(chat_id)
        if existing is not None:
            if not existing.done:
                return existing, False
            # Finished local session: drop it so the new turn starts fresh.
            _sessions.pop(chat_id, None)

    client = _redis()
    if client is None:
        # In-memory only (single instance) — the prior behavior.
        async with _sessions_lock:
            existing = _sessions.get(chat_id)
            if existing is not None and not existing.done:
                return existing, False
            sess = StreamSession(chat_id=chat_id, _redis=False)
            _sessions[chat_id] = sess
            return sess, True

    # Redis on: claim the single-producer lock.
    token = _uuid.uuid4().hex
    try:
        claimed = await client.set(
            _k_lock(chat_id), token, nx=True, ex=PRODUCER_LOCK_TTL
        )
    except Exception as e:
        logger.warning(
            "chat_resume: lock claim failed (%s); falling back to in-memory", e
        )
        claimed = None

    if claimed:
        # We own the producer. Clear any leftover stream/meta from a prior
        # finished turn on this chat_id, then mark active.
        try:
            await client.delete(_k_events(chat_id), _k_meta(chat_id))
            await client.hset(
                _k_meta(chat_id), mapping={"status": "active", "finished_at": ""}
            )
            await client.expire(_k_meta(chat_id), ACTIVE_TTL)
        except Exception as e:
            logger.warning("chat_resume: redis meta init failed (%s)", e)
        async with _sessions_lock:
            existing = _sessions.get(chat_id)
            if existing is not None and not existing.done:
                return existing, False
            sess = StreamSession(chat_id=chat_id, _redis=True, _lock_token=token)
            _sessions[chat_id] = sess
            return sess, True

    if claimed is None:
        # Redis error — keep streaming locally (no cross-instance reach).
        async with _sessions_lock:
            existing = _sessions.get(chat_id)
            if existing is not None and not existing.done:
                return existing, False
            sess = StreamSession(chat_id=chat_id, _redis=False)
            _sessions[chat_id] = sess
            return sess, True

    # A producer is active on another instance — attach as a subscriber.
    return RedisSubscriberSession(chat_id=chat_id), False


async def lookup(chat_id: str) -> Optional[Session]:
    async with _sessions_lock:
        _gc_expired_locked()
        local = _sessions.get(chat_id)
    if local is not None:
        return local
    client = _redis()
    if client is None:
        return None
    try:
        if (
            await client.exists(_k_lock(chat_id))
            or await client.exists(_k_meta(chat_id))
            or await client.exists(_k_events(chat_id))
        ):
            return RedisSubscriberSession(chat_id=chat_id)
    except Exception as e:
        logger.warning("chat_resume: redis lookup failed (%s)", e)
    return None


async def evict(chat_id: str) -> bool:
    """Remove a session immediately, regardless of done state or grace
    window. Used on user-initiated stop so the next POST with the same
    chat_id starts a fresh agent run instead of replaying the cancelled
    session's buffer. Returns True if anything was removed."""
    async with _sessions_lock:
        had_local = _sessions.pop(chat_id, None) is not None
    had_redis = await _evict_redis(chat_id)
    return had_local or had_redis


async def _evict_redis(chat_id: str) -> bool:
    client = _redis()
    if client is None:
        return False
    try:
        await client.publish(_k_control(chat_id), "cancel")
    except Exception:
        pass
    try:
        n = await client.delete(_k_events(chat_id), _k_meta(chat_id), _k_lock(chat_id))
        return bool(n)
    except Exception as e:
        logger.warning("chat_resume: redis evict failed (%s)", e)
        return False


def _gc_expired_locked() -> None:
    now = _time.monotonic()
    drop = [
        cid
        for cid, s in _sessions.items()
        if s.done
        and s.finished_at is not None
        and (now - s.finished_at) > GRACE_SECONDS
    ]
    for cid in drop:
        _sessions.pop(cid, None)
    if drop:
        logger.debug("chat_resume: evicted %d expired session(s)", len(drop))
