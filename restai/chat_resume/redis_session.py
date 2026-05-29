"""`RedisStreamSession` — the buffer + liveness for one chat_id, in Redis.

Any worker sharing the same Redis can replay, live-tail, and stop a run that
was started on another worker. State spans four keys per chat_id:

- ``stream:<id>``  Redis Stream of ``{seq, data}`` entries (the SSE buffer)
- ``seq:<id>``     INCR counter → the monotonic SSE ``id:`` field
- ``meta:<id>``    Hash ``{done, cancelling}``
- ``owner:<id>``   SET-NX election + liveness heartbeat (TTL refreshed on append)
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import AsyncIterator

from . import redis_client as rc
from .sse import (
    ACTIVE_TTL_SECONDS,
    CLOSE_MARKER,
    GRACE_SECONDS,
    MAX_EVENTS_PER_SESSION,
    STOPPED_MARKER,
    frame,
)

# Marker XADDed only to wake a blocked XREAD (on finish/cancel). Never yielded.
_WAKE = "__wake__"


def _emit(entries, last_event_id: int):
    """Frame the Stream entries worth yielding as ready-to-send SSE strings.

    Skips wake sentinels and anything already seen (seq <= last_event_id), and
    reports the last Stream id consumed so the caller can advance its XREAD
    cursor past entries it didn't yield (e.g. a lone wake)."""
    frames = []
    new_last = None
    for entry_id, fields in entries:
        new_last = entry_id
        data = fields.get("data", "")
        if data == _WAKE:
            continue
        seq = int(fields.get("seq") or 0)
        if seq <= last_event_id:
            continue
        frames.append(frame(seq, data))
    return frames, new_last


class RedisStreamSession:
    def __init__(self, chat_id: str, client):
        self.chat_id = chat_id
        self._client = client
        self._stream_key = f"{rc.KEY_PREFIX}stream:{chat_id}"
        self._seq_key = f"{rc.KEY_PREFIX}seq:{chat_id}"
        self._meta_key = f"{rc.KEY_PREFIX}meta:{chat_id}"
        self._owner_key = f"{rc.KEY_PREFIX}owner:{chat_id}"

    # The producer task can't move between workers, so it's tracked in this
    # worker's local registry rather than on the (per-call) session object.
    @property
    def producer_task(self) -> asyncio.Task | None:
        return rc.get_producer_task(self.chat_id)

    @producer_task.setter
    def producer_task(self, task: asyncio.Task | None) -> None:
        rc.register_producer_task(self.chat_id, task)

    async def append(self, chunk: str) -> int:
        # Single producer per chat_id (owner-key election) → no append race.
        # INCR first (its result is the SSE id), then one pipeline for the
        # XADD + the four sliding-TTL refreshes, so the per-chunk streaming
        # hot path costs 2 round-trips instead of 6.
        seq = await self._client.incr(self._seq_key)
        pipe = self._client.pipeline(transaction=False)
        # maxlen bounds the stream to the same ceiling the in-memory buffer
        # enforces; approximate trimming keeps the per-chunk cost ~O(1).
        pipe.xadd(
            self._stream_key,
            {"seq": str(seq), "data": chunk},
            maxlen=MAX_EVENTS_PER_SESSION,
            approximate=True,
        )
        for key in (self._stream_key, self._seq_key, self._meta_key, self._owner_key):
            pipe.expire(key, ACTIVE_TTL_SECONDS)
        await pipe.execute()
        return seq

    async def _close(self) -> None:
        # One pipeline: flip done, wake any blocked XREAD with a sentinel,
        # drop to the grace TTL, and release the owner key.
        pipe = self._client.pipeline(transaction=False)
        pipe.hset(self._meta_key, mapping={"done": "1"})
        pipe.xadd(self._stream_key, {"seq": "0", "data": _WAKE})
        for key in (self._stream_key, self._seq_key, self._meta_key):
            pipe.expire(key, GRACE_SECONDS)
        pipe.delete(self._owner_key)
        await pipe.execute()
        rc.register_producer_task(self.chat_id, None)

    async def finish(self) -> None:
        await self._close()

    async def cancel(self) -> None:
        """User-initiated stop, cross-worker. Cancels the producer task on
        whichever worker owns it (locally if that's us, else over the pub/sub
        control channel), writes the stopped + close markers into the buffer,
        and marks done. Idempotent."""
        if await self._client.hget(self._meta_key, "done") == "1":
            return
        # Atomic single-winner guard: HSETNX returns 1 only for the first
        # caller, so two Stops racing (possibly on different workers) can't
        # both append the stopped/close markers. The in-memory path gets the
        # same guarantee from its re-check under the Condition lock.
        if not await self._client.hsetnx(self._meta_key, "cancelling", "1"):
            return
        # Append the terminal markers BEFORE cancelling the local producer
        # task. Cancelling it triggers its `finally: finish() -> _close()`,
        # which flips `done` and wakes subscribers; if that raced ahead of
        # these appends a draining subscriber could return without ever
        # seeing the stopped/close frames. Writing them first guarantees
        # they're in the stream before `done` can be observed — matching the
        # in-memory path, where cancel() appends under the Condition lock
        # before setting done.
        await self.append(STOPPED_MARKER)
        await self.append(CLOSE_MARKER)
        # Fast path: if this worker owns the task, kill it directly.
        task = rc.get_producer_task(self.chat_id)
        if task is not None and not task.done():
            task.cancel()
        # Tell the owning worker (if it's a different one) to cancel its task.
        await self._client.publish(
            rc.CONTROL_CHANNEL,
            _json.dumps({"chat_id": self.chat_id, "action": "cancel"}),
        )
        await self._close()

    async def subscribe(self, last_event_id: int = 0) -> AsyncIterator[str]:
        client = self._client
        last_id = "0-0"

        # Replay everything buffered so far.
        frames, new_last = _emit(await client.xrange(self._stream_key), last_event_id)
        if new_last is not None:
            last_id = new_last
        for f in frames:
            yield f

        # Live tail until the producer is done (or has vanished).
        while True:
            if await client.hget(self._meta_key, "done") == "1":
                # Final drain, looped until the stream is exhausted, so a
                # burst of >count markers appended right before `done` (e.g.
                # stopped/close on cancel) is never truncated.
                while True:
                    resp = await client.xread({self._stream_key: last_id}, count=1000)
                    entries = resp[0][1] if resp else []
                    if not entries:
                        return
                    frames, new_last = _emit(entries, last_event_id)
                    if new_last is not None:
                        last_id = new_last
                    for f in frames:
                        yield f

            resp = await client.xread({self._stream_key: last_id}, block=2000, count=1000)
            entries = resp[0][1] if resp else []
            if entries:
                frames, new_last = _emit(entries, last_event_id)
                if new_last is not None:
                    last_id = new_last
                for f in frames:
                    yield f
            elif not await client.exists(self._owner_key):
                # No new events and the producer's owner key is gone — the
                # run finished or its worker died. Don't hang the subscriber.
                #
                # Liveness limitation: the owner key's TTL is ACTIVE_TTL,
                # refreshed on every append. A producer that emits nothing
                # for > ACTIVE_TTL (e.g. a single >1h tool call) lets the key
                # lapse mid-run, so this branch can return early on a still-
                # live run; conversely, a SIGKILLed producer leaves the key
                # until its TTL, so a reconnecting subscriber can block up to
                # ACTIVE_TTL before returning. Both are bounded and rare for
                # token-streaming chats; a separate short heartbeat would be
                # the deeper fix if long-idle runs become common.
                return
