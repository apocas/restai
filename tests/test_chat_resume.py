"""Tests for chat_resume: in-memory fallback + Redis-backed multi-instance.

The in-memory path must behave exactly as before (no Redis configured).
The Redis path proves cross-instance resume: a producer appending on one
"worker" session and a subscriber replaying + live-tailing on a second
session sharing the same Redis (simulating two uvicorn workers).

Redis tests use `fakeredis.aioredis` (no server needed). They skip
cleanly when fakeredis isn't installed.
"""

import asyncio
import json

import pytest

import restai.chat_resume as cr


# ── In-memory fallback (Redis unset) ───────────────────────────────────────

@pytest.fixture
def no_redis(monkeypatch):
    """Force the in-memory backend by making _get_redis return None."""
    async def _none():
        return None
    monkeypatch.setattr(cr, "_get_redis", _none)
    cr._sessions.clear()
    yield
    cr._sessions.clear()


@pytest.mark.asyncio
async def test_inmemory_get_or_create_and_replay(no_redis):
    sess, is_new = await cr.get_or_create("chat-A")
    assert is_new is True
    assert isinstance(sess, cr.StreamSession)

    same, is_new2 = await cr.get_or_create("chat-A")
    assert is_new2 is False
    assert same is sess

    await sess.append("data: " + json.dumps({"text": "hello"}) + "\n\n")
    await sess.append("data: " + json.dumps({"text": " world"}) + "\n\n")
    await sess.finish()

    out = [chunk async for chunk in sess.subscribe(last_event_id=0)]
    assert len(out) == 2
    assert out[0].startswith("id: 1\n")
    assert "hello" in out[0]
    assert out[1].startswith("id: 2\n")
    assert "world" in out[1]


@pytest.mark.asyncio
async def test_inmemory_replay_filters_last_event_id(no_redis):
    sess, _ = await cr.get_or_create("chat-B")
    await sess.append("data: a\n\n")
    await sess.append("data: b\n\n")
    await sess.append("data: c\n\n")
    await sess.finish()

    out = [chunk async for chunk in sess.subscribe(last_event_id=2)]
    assert len(out) == 1
    assert out[0].startswith("id: 3\n")


@pytest.mark.asyncio
async def test_inmemory_cancel_pushes_stopped_and_close(no_redis):
    sess, _ = await cr.get_or_create("chat-C")
    await sess.append("data: partial\n\n")
    await sess.cancel()
    assert sess.done is True

    out = [chunk async for chunk in sess.subscribe(last_event_id=0)]
    body = "".join(out)
    assert '"stopped": true' in body
    assert "event: close" in body


@pytest.mark.asyncio
async def test_inmemory_cancel_is_idempotent(no_redis):
    sess, _ = await cr.get_or_create("chat-C2")
    await sess.append("data: partial\n\n")
    await sess.cancel()
    before = list(sess.events)
    await sess.cancel()  # second call is a no-op
    assert sess.events == before


@pytest.mark.asyncio
async def test_inmemory_evict(no_redis):
    sess, _ = await cr.get_or_create("chat-D")
    assert await cr.lookup("chat-D") is sess
    assert await cr.evict("chat-D") is True
    assert await cr.lookup("chat-D") is None
    assert await cr.evict("chat-D") is False


@pytest.mark.asyncio
async def test_inmemory_live_tail(no_redis):
    sess, _ = await cr.get_or_create("chat-E")

    received = []

    async def consumer():
        async for chunk in sess.subscribe(last_event_id=0):
            received.append(chunk)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    await sess.append("data: live1\n\n")
    await asyncio.sleep(0.05)
    await sess.append("data: live2\n\n")
    await asyncio.sleep(0.05)
    await sess.finish()
    await asyncio.wait_for(task, timeout=2)

    assert len(received) == 2
    assert "live1" in received[0]
    assert "live2" in received[1]


# ── Control message handler (no Redis I/O) ─────────────────────────────────

@pytest.mark.asyncio
async def test_control_message_cancels_local_task():
    async def long_run():
        await asyncio.sleep(60)

    task = asyncio.create_task(long_run())
    cr._local_producer_tasks["ctrl-A"] = task
    try:
        cr._handle_control_message(json.dumps({"chat_id": "ctrl-A", "action": "cancel"}))
        await asyncio.sleep(0.05)
        assert task.cancelled() or task.done()
    finally:
        cr._local_producer_tasks.pop("ctrl-A", None)


def test_control_message_ignores_unknown_and_malformed():
    # No matching task → no raise.
    cr._handle_control_message(json.dumps({"chat_id": "nope", "action": "cancel"}))
    # Wrong action → ignored.
    cr._handle_control_message(json.dumps({"chat_id": "nope", "action": "other"}))
    # Malformed JSON → swallowed.
    cr._handle_control_message("not json")
    cr._handle_control_message(None)


# ── Redis backend (fakeredis) ──────────────────────────────────────────────

@pytest.fixture
def fake_redis(monkeypatch):
    aioredis = pytest.importorskip("fakeredis.aioredis")
    client = aioredis.FakeRedis(decode_responses=True)

    async def _client():
        return client

    monkeypatch.setattr(cr, "_get_redis", _client)
    # No-op the control listener — the fakeredis pub/sub round-trip is
    # exercised separately by test_redis_control_listener_*.
    async def _noop_listener(_c):
        return None
    monkeypatch.setattr(cr, "_ensure_control_listener", _noop_listener)
    cr._sessions.clear()
    cr._local_producer_tasks.clear()
    yield client
    cr._sessions.clear()
    cr._local_producer_tasks.clear()
    # Defensively reset the client/listener state (which lives in the
    # redis_client submodule) so a future test that reaches the real
    # _get_redis / _ensure_control_listener can't inherit a stale client or a
    # listener bound to a dead fakeredis.
    from restai.chat_resume import redis_client as _rc
    _rc._redis_client = None
    _rc._redis_url = None
    _rc._control_listener_task = None
    _rc._control_listener_url = None


@pytest.mark.asyncio
async def test_redis_get_or_create_is_new_then_reconnect(fake_redis):
    sess, is_new = await cr.get_or_create("rchat-A")
    assert isinstance(sess, cr.RedisStreamSession)
    assert is_new is True

    # Second get_or_create (reconnect, possibly a different worker) → not new.
    sess2, is_new2 = await cr.get_or_create("rchat-A")
    assert isinstance(sess2, cr.RedisStreamSession)
    assert is_new2 is False


@pytest.mark.asyncio
async def test_redis_cross_instance_replay(fake_redis):
    # Worker 1 produces.
    producer, is_new = await cr.get_or_create("rchat-B")
    assert is_new is True
    await producer.append("data: " + json.dumps({"text": "one"}) + "\n\n")
    await producer.append("data: " + json.dumps({"text": "two"}) + "\n\n")
    await producer.finish()

    # Worker 2 subscribes via lookup (separate session object, same Redis).
    subscriber = await cr.lookup("rchat-B")
    assert isinstance(subscriber, cr.RedisStreamSession)
    out = [chunk async for chunk in subscriber.subscribe(last_event_id=0)]
    assert len(out) == 2
    assert out[0].startswith("id: 1\n")
    assert "one" in out[0]
    assert out[1].startswith("id: 2\n")
    assert "two" in out[1]


@pytest.mark.asyncio
async def test_redis_replay_filters_last_event_id(fake_redis):
    producer, _ = await cr.get_or_create("rchat-C")
    await producer.append("data: a\n\n")
    await producer.append("data: b\n\n")
    await producer.append("data: c\n\n")
    await producer.finish()

    sub = await cr.lookup("rchat-C")
    out = [chunk async for chunk in sub.subscribe(last_event_id=2)]
    assert len(out) == 1
    assert out[0].startswith("id: 3\n")


@pytest.mark.asyncio
async def test_redis_replay_with_nonzero_last_event_id_after_done(fake_redis):
    # The production /chat resume path passes the SSE Last-Event-ID header as
    # last_event_id; a reconnecting subscriber must replay only seq > header
    # and never re-yield or skip across the replay→final-drain boundary.
    producer, _ = await cr.get_or_create("rchat-LEI")
    for i in range(5):
        await producer.append(f"data: chunk{i}\n\n")
    await producer.finish()

    sub = await cr.lookup("rchat-LEI")
    out = [c async for c in sub.subscribe(last_event_id=3)]
    # Only seq 4 and 5 survive the filter, in order, exactly once each.
    assert [c.split("\n", 1)[0] for c in out] == ["id: 4", "id: 5"]
    assert "chunk3" in out[0] and "chunk4" in out[1]


@pytest.mark.asyncio
async def test_redis_xadd_bounds_stream_length(fake_redis):
    # maxlen on XADD keeps a long run from growing the stream without bound.
    producer, _ = await cr.get_or_create("rchat-CAP")
    overflow = cr.MAX_EVENTS_PER_SESSION + 50
    for i in range(overflow):
        await producer.append(f"data: {i}\n\n")
    length = await fake_redis.xlen(producer._stream_key)
    assert length <= cr.MAX_EVENTS_PER_SESSION


@pytest.mark.asyncio
async def test_redis_lookup_before_first_append(fake_redis):
    # get_or_create seeds meta, so a reconnect can find the session even
    # before the producer has emitted anything.
    await cr.get_or_create("rchat-D0")
    assert await cr.lookup("rchat-D0") is not None
    assert await cr.lookup("rchat-never") is None


@pytest.mark.asyncio
async def test_redis_finish_unblocks_live_subscriber(fake_redis):
    producer, _ = await cr.get_or_create("rchat-D")

    received = []

    async def consumer():
        sub = await cr.lookup("rchat-D")
        async for chunk in sub.subscribe(last_event_id=0):
            received.append(chunk)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.1)
    await producer.append("data: hi\n\n")
    await asyncio.sleep(0.1)
    await producer.finish()
    await asyncio.wait_for(task, timeout=5)

    assert any("hi" in c for c in received)


@pytest.mark.asyncio
async def test_redis_cancel_writes_markers_and_publishes(fake_redis):
    producer, _ = await cr.get_or_create("rchat-E")
    await producer.append("data: partial\n\n")

    published = []
    orig_publish = fake_redis.publish

    async def spy_publish(channel, msg):
        published.append((channel, msg))
        return await orig_publish(channel, msg)

    fake_redis.publish = spy_publish

    # Cancel from a *different* (non-owning) session, like a Stop landing
    # on another worker.
    canceller = await cr.lookup("rchat-E")
    await canceller.cancel()

    assert any(ch == cr._CONTROL_CHANNEL for ch, _ in published)
    cancel_msgs = [json.loads(m) for ch, m in published if ch == cr._CONTROL_CHANNEL]
    assert any(
        p.get("chat_id") == "rchat-E" and p.get("action") == "cancel"
        for p in cancel_msgs
    )

    # Buffer carries stopped + close markers.
    sub = await cr.lookup("rchat-E")
    out = "".join([c async for c in sub.subscribe(last_event_id=0)])
    assert '"stopped": true' in out
    assert "event: close" in out


@pytest.mark.asyncio
async def test_redis_cancel_cancels_local_owner_task(fake_redis):
    producer, _ = await cr.get_or_create("rchat-F")

    # Simulate this worker owning a long-running producer task.
    async def long_run():
        await asyncio.sleep(60)

    task = asyncio.create_task(long_run())
    producer.producer_task = task
    assert cr._local_producer_tasks.get("rchat-F") is task

    await producer.cancel()
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_redis_cancel_is_idempotent(fake_redis):
    producer, _ = await cr.get_or_create("rchat-F2")
    await producer.append("data: x\n\n")
    await producer.cancel()
    sub = await cr.lookup("rchat-F2")
    first = [c async for c in sub.subscribe(last_event_id=0)]
    await producer.cancel()  # no-op: already done
    sub2 = await cr.lookup("rchat-F2")
    second = [c async for c in sub2.subscribe(last_event_id=0)]
    assert first == second


@pytest.mark.asyncio
async def test_redis_evict_clears_keys(fake_redis):
    producer, _ = await cr.get_or_create("rchat-G")
    await producer.append("data: x\n\n")
    assert await cr.lookup("rchat-G") is not None

    assert await cr.evict("rchat-G") is True
    assert await cr.lookup("rchat-G") is None
    assert await cr.evict("rchat-G") is False


@pytest.mark.asyncio
async def test_redis_control_listener_cancels_local_task(fake_redis):
    """End-to-end pub/sub: a cancel published to the control channel cancels
    the matching local producer task via the listener loop."""
    async def long_run():
        await asyncio.sleep(60)

    task = asyncio.create_task(long_run())
    cr._local_producer_tasks["rchat-H"] = task

    listener = asyncio.create_task(cr._control_listener_loop(fake_redis))
    await asyncio.sleep(0.1)  # let it subscribe

    await fake_redis.publish(
        cr._CONTROL_CHANNEL,
        json.dumps({"chat_id": "rchat-H", "action": "cancel"}),
    )
    await asyncio.sleep(0.3)

    assert task.cancelled() or task.done()
    listener.cancel()
    try:
        await listener
    except asyncio.CancelledError:
        pass
