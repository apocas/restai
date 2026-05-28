"""Tests for chat_resume.

In-memory backend (the no-Redis "current setup") is exercised in CI by
patching ``build_redis_url`` to return None. The cross-instance Redis path
only runs when ``REDIS_TEST_URL`` is set (else it skips) so it can be
verified against a real Redis without requiring one in CI.
"""

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest

import restai.chat_resume as cr
from restai.chat_resume import (
    RedisSubscriberSession,
    evict,
    get_or_create,
    lookup,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test runs under its own ``asyncio.run`` loop; recreate the
    module-level lock so it binds to that loop, and clear shared state."""
    cr._sessions.clear()
    cr._sessions_lock = asyncio.Lock()
    cr._redis_client = None
    cr._redis_url = None
    yield
    cr._sessions.clear()
    cr._redis_client = None
    cr._redis_url = None


async def _drain(session, last_event_id=0, timeout=2.0):
    """Collect SSE chunks from a subscribe() async generator. Stops on the
    producer's done signal (StopAsyncIteration) or after `timeout` idle."""
    out = []
    agen = session.subscribe(last_event_id=last_event_id)
    try:
        while True:
            out.append(await asyncio.wait_for(agen.__anext__(), timeout=timeout))
    except (StopAsyncIteration, asyncio.TimeoutError):
        pass
    finally:
        await agen.aclose()
    return out


# --------------------------------------------------------------------------
# In-memory backend (no Redis configured)
# --------------------------------------------------------------------------


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_get_or_create_new_then_in_flight_dedup(_mock):
    async def scenario():
        s1, new1 = await get_or_create("k")
        s2, new2 = await get_or_create("k")
        return s1, new1, s2, new2

    s1, new1, s2, new2 = asyncio.run(scenario())
    assert new1 is True, "first caller owns the producer"
    assert new2 is False, "second caller attaches to the in-flight session"
    assert s1 is s2


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_subscribe_replays_then_ends_on_done(_mock):
    async def scenario():
        s, _ = await get_or_create("k")
        await s.append("data: one\n\n")
        await s.append("data: two\n\n")
        await s.finish()
        return await _drain(s)

    out = asyncio.run(scenario())
    joined = "".join(out)
    assert "data: one" in joined
    assert "data: two" in joined
    assert "id: 1" in joined and "id: 2" in joined


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_subscribe_skips_already_seen(_mock):
    async def scenario():
        s, _ = await get_or_create("k")
        await s.append("data: 1\n\n")
        await s.append("data: 2\n\n")
        await s.append("data: 3\n\n")
        await s.finish()
        return await _drain(s, last_event_id=2)

    joined = "".join(asyncio.run(scenario()))
    assert "data: 3" in joined and "id: 3" in joined
    assert "data: 1" not in joined
    assert "data: 2" not in joined


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_subscribe_live_tail(_mock):
    async def scenario():
        s, _ = await get_or_create("live")
        received = []

        async def consumer():
            async for chunk in s.subscribe(0):
                received.append(chunk)

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.05)
        await s.append("data: a\n\n")
        await s.append("data: b\n\n")
        await asyncio.sleep(0.05)
        await s.finish()
        await asyncio.wait_for(task, timeout=2)
        return received

    received = asyncio.run(scenario())
    joined = "".join(received)
    assert "data: a" in joined
    assert "data: b" in joined


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_cancel_emits_stopped_marker_and_ends(_mock):
    async def scenario():
        s, _ = await get_or_create("c")
        await s.append("data: partial\n\n")
        await s.cancel()
        assert s.done is True
        return await _drain(s)

    joined = "".join(asyncio.run(scenario()))
    assert "partial" in joined
    assert "stopped" in joined
    assert "event: close" in joined


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_finished_session_starts_fresh_run(_mock):
    """A reused chat_id whose prior turn finished must NOT be reattached —
    get_or_create discards it and returns a brand new producer session."""

    async def scenario():
        s1, new1 = await get_or_create("k")
        await s1.finish()
        s2, new2 = await get_or_create("k")
        return s1, new1, s2, new2

    s1, new1, s2, new2 = asyncio.run(scenario())
    assert new1 is True
    assert new2 is True, "finished session should not be reattached"
    assert s1 is not s2


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_is_in_flight_transitions(_mock):
    async def scenario():
        s, _ = await get_or_create("k")
        before = await s.is_in_flight()
        await s.finish()
        after = await s.is_in_flight()
        return before, after

    before, after = asyncio.run(scenario())
    assert before is True
    assert after is False


@patch("restai.chat_resume.config.build_redis_url", return_value=None)
def test_lookup_and_evict(_mock):
    async def scenario():
        await get_or_create("k")
        found = await lookup("k")
        removed = await evict("k")
        after = await lookup("k")
        unknown = await lookup("nope")
        return found, removed, after, unknown

    found, removed, after, unknown = asyncio.run(scenario())
    assert found is not None
    assert removed is True
    assert after is None
    assert unknown is None


# --------------------------------------------------------------------------
# Cross-instance Redis backend (opt-in via REDIS_TEST_URL)
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("REDIS_TEST_URL"), reason="REDIS_TEST_URL not set"
)
def test_redis_cross_instance_replay_and_evict():
    url = os.environ["REDIS_TEST_URL"]
    cid = "chat-resume-test-" + uuid.uuid4().hex

    with patch("restai.chat_resume.config.build_redis_url", return_value=url):

        async def scenario():
            # Producing instance: claims the lock, mirrors to Redis.
            sess, is_new = await get_or_create(cid)
            assert is_new is True
            assert getattr(sess, "_redis", False) is True
            await sess.append('data: {"text": "hello"}\n\n')
            await sess.finish()

            # Another instance only sees Redis — a subscriber proxy.
            proxy = RedisSubscriberSession(chat_id=cid)
            assert await proxy.is_in_flight() is False
            out = await _drain(proxy)
            joined = "".join(out)
            assert "hello" in joined

            # lookup from "another instance" (no local session) finds it.
            cr._sessions.clear()
            found = await lookup(cid)
            assert isinstance(found, RedisSubscriberSession)

            # evict clears the shared keys.
            assert await evict(cid) is True
            assert await lookup(cid) is None

        asyncio.run(scenario())
