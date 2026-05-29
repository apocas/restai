"""Redis plumbing shared by the Redis backend: the async client + the
cross-worker cancel control channel.

The producer `asyncio.Task` can't move between workers, so a Stop landing on
any worker is broadcast over a pub/sub control channel; each worker runs one
listener that cancels the matching task from its local registry.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging

from restai.config import build_redis_url

logger = logging.getLogger("restai.chat_resume")

KEY_PREFIX = "chat_resume:"
CONTROL_CHANNEL = "chat_resume:control"

# Lazy, self-healing async Redis client (same pattern as
# agent2/memory.py:_get_redis_client and brain.py:_image_cache_redis): cached
# keyed on the URL, rebuilt when the URL changes, None when Redis is unset or
# the client can't be built.
_redis_client = None
_redis_url: str | None = None
_redis_lock = asyncio.Lock()

# Per-worker registry of the *local* producer task for each chat_id.
_local_producer_tasks: dict[str, asyncio.Task] = {}

# Single per-worker pub/sub listener for cross-worker cancel.
_control_listener_task: asyncio.Task | None = None
_control_listener_url: str | None = None
_control_listener_lock = asyncio.Lock()


async def get_redis():
    """Return a cached async Redis client, or None when Redis is unset.

    Rebuilds the client when `build_redis_url()` changes so a runtime settings
    edit takes effect without a restart."""
    global _redis_client, _redis_url
    url = build_redis_url()
    if not url:
        return None
    if _redis_client is not None and _redis_url == url:
        return _redis_client
    async with _redis_lock:
        if _redis_client is not None and _redis_url == url:
            return _redis_client
        try:
            import redis.asyncio as aioredis
        except ImportError:
            logger.warning(
                "chat_resume: redis.asyncio not installed; using in-memory fallback"
            )
            return None
        try:
            _redis_client = aioredis.from_url(url, decode_responses=True)
            _redis_url = url
        except Exception:
            logger.exception("chat_resume: failed to build async Redis client")
            return None
        return _redis_client


def register_producer_task(chat_id: str, task: asyncio.Task | None) -> None:
    if task is None:
        _local_producer_tasks.pop(chat_id, None)
    else:
        _local_producer_tasks[chat_id] = task


def get_producer_task(chat_id: str) -> asyncio.Task | None:
    return _local_producer_tasks.get(chat_id)


def handle_control_message(raw) -> None:
    """Cancel the local producer task named by a `cancel` control message.

    Pure (no I/O) so the cross-worker Stop logic is unit-testable without
    standing up a real pub/sub round-trip. Workers that don't hold the task
    for that chat_id simply find nothing to cancel."""
    try:
        msg = _json.loads(raw)
    except (ValueError, TypeError):
        return
    if not isinstance(msg, dict) or msg.get("action") != "cancel":
        return
    task = _local_producer_tasks.get(msg.get("chat_id"))
    if task is not None and not task.done():
        task.cancel()


async def control_listener_loop(client) -> None:
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CONTROL_CHANNEL)
        async for message in pubsub.listen():
            if message and message.get("type") == "message":
                handle_control_message(message.get("data"))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("chat_resume: control listener crashed")
    finally:
        try:
            await pubsub.aclose()
        except Exception:
            pass


async def ensure_control_listener(client) -> None:
    """Start (or restart, on Redis URL change) the per-worker control listener."""
    global _control_listener_task, _control_listener_url
    alive = _control_listener_task is not None and not _control_listener_task.done()
    if alive and _control_listener_url == _redis_url:
        return
    async with _control_listener_lock:
        alive = _control_listener_task is not None and not _control_listener_task.done()
        if alive and _control_listener_url == _redis_url:
            return
        if alive:
            _control_listener_task.cancel()
        _control_listener_task = asyncio.create_task(control_listener_loop(client))
        _control_listener_url = _redis_url
