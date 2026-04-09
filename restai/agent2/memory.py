"""Session store for agent2.

Two backends, picked automatically:

1. **Redis** — when `config.REDIS_HOST` is set. Sessions are persisted as
   JSON under the key `agent2_session:{chat_id}` with a TTL so abandoned
   chats get cleaned up. Survives process restarts and is shared across
   workers.

2. **In-memory dict** — fallback when Redis is not configured. Lives on
   the Brain instance as `brain._agent2_sessions: dict[str, list[dict]]`.
   Volatile across restarts and not shared between workers.

Both `get_session` and `save_session` are async so the Redis path can use
`redis.asyncio` directly. Callers (currently `restai/projects/agent2.py`)
must `await` them.
"""
from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from typing import Any, Optional

from restai import config

from .types import AgentSession, message_from_dict, message_to_dict

logger = logging.getLogger(__name__)

# Default TTL for Redis-backed sessions (7 days). Override via env var.
DEFAULT_SESSION_TTL_SECONDS = int(
    os.environ.get("AGENT2_SESSION_TTL_SECONDS") or 7 * 24 * 60 * 60
)

# Cap the in-memory fallback so a long-running process without Redis can't
# leak unboundedly on chat_id cardinality. Production should configure Redis.
LOCAL_SESSION_CAP = int(os.environ.get("AGENT2_LOCAL_SESSION_CAP") or 500)

REDIS_KEY_PREFIX = "agent2_session:"


# ---------- in-memory backend (LRU) ----------


def _ensure_local_store(brain: Any) -> "OrderedDict[str, list[dict]]":
    store = getattr(brain, "_agent2_sessions", None)
    if not isinstance(store, OrderedDict):
        store = OrderedDict(store or {})
        try:
            setattr(brain, "_agent2_sessions", store)
        except Exception:
            pass
    return store


def _local_get(store: OrderedDict, chat_id: str) -> Optional[list]:
    raw = store.get(chat_id)
    if raw is not None:
        store.move_to_end(chat_id)
    return raw


def _local_set(store: OrderedDict, chat_id: str, value: list) -> None:
    store[chat_id] = value
    store.move_to_end(chat_id)
    while len(store) > LOCAL_SESSION_CAP:
        store.popitem(last=False)


# ---------- Redis backend (lazy) ----------


def _get_redis_client(brain: Any):
    """Lazily build and cache an async Redis client on the Brain instance.

    Self-healing: if the live Redis URL (from `config`) no longer matches the
    URL the cached client was built with, the cache is dropped and a fresh
    client is built. This ensures runtime changes via the admin Settings GUI
    take effect on the next session operation, even if the explicit
    `Brain.reinit_agent2_redis()` hook hasn't been called yet.

    Returns None if Redis isn't configured or the client can't be created.
    """
    url = config.build_redis_url()
    if not url:
        # Redis turned off (or never configured) — drop any stale client.
        if getattr(brain, "_agent2_redis", None) is not None:
            try:
                setattr(brain, "_agent2_redis", None)
                setattr(brain, "_agent2_redis_url", None)
            except Exception:
                pass
        return None

    cached = getattr(brain, "_agent2_redis", None)
    cached_url = getattr(brain, "_agent2_redis_url", None)
    if cached is not None and cached_url == url:
        return cached

    try:
        import redis.asyncio as aioredis  # type: ignore
    except ImportError:
        logger.warning("redis.asyncio not installed; falling back to in-memory sessions")
        return None

    try:
        client = aioredis.from_url(url, decode_responses=True)
    except Exception as e:
        logger.warning("agent2: failed to build Redis client (%s); using in-memory fallback", e)
        return None

    try:
        setattr(brain, "_agent2_redis", client)
        setattr(brain, "_agent2_redis_url", url)
    except Exception:
        pass
    return client


def _redis_key(chat_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}{chat_id}"


# ---------- public API ----------


async def get_session(brain: Any, chat_id: str) -> AgentSession:
    """Load a session by chat_id, preferring Redis when available.

    Always returns an `AgentSession` (empty if none found or load fails).
    """
    if not chat_id:
        return AgentSession()

    client = _get_redis_client(brain)
    if client is not None:
        try:
            raw = await client.get(_redis_key(chat_id))
            if raw:
                payload = json.loads(raw)
                messages = [message_from_dict(d) for d in payload]
                return AgentSession(messages=messages)
            # Key not in Redis — fall through to local store as a safety net
            # in case a previous turn was saved before Redis became reachable.
        except Exception as e:
            logger.warning("agent2: Redis get_session failed (%s); using in-memory fallback", e)

    # In-memory backend
    store = _ensure_local_store(brain)
    raw = _local_get(store, chat_id)
    if not raw:
        return AgentSession()
    try:
        messages = [message_from_dict(d) for d in raw]
    except Exception:
        return AgentSession()
    return AgentSession(messages=messages)


async def save_session(brain: Any, chat_id: str, session: AgentSession) -> None:
    """Persist a session by chat_id, preferring Redis when available.

    Failures degrade gracefully: Redis errors fall back to the in-memory
    store so a single chat doesn't break.
    """
    if not chat_id:
        return

    serialized = [message_to_dict(m) for m in session.messages]

    client = _get_redis_client(brain)
    if client is not None:
        try:
            await client.set(
                _redis_key(chat_id),
                json.dumps(serialized),
                ex=DEFAULT_SESSION_TTL_SECONDS,
            )
            return
        except Exception as e:
            logger.warning("agent2: Redis save_session failed (%s); using in-memory fallback", e)

    # In-memory backend
    store = _ensure_local_store(brain)
    _local_set(store, chat_id, serialized)


async def clear_session(brain: Any, chat_id: str) -> None:
    """Delete a session from whichever backend is active. Best-effort."""
    if not chat_id:
        return

    client = _get_redis_client(brain)
    if client is not None:
        try:
            await client.delete(_redis_key(chat_id))
        except Exception as e:
            logger.warning("agent2: Redis clear_session failed (%s)", e)

    store = getattr(brain, "_agent2_sessions", None)
    if store and chat_id in store:
        try:
            del store[chat_id]
        except Exception:
            pass
