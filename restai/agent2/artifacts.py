"""Per-chat artifact staging for the agent's `/artifacts/` convention.

Tools that produce binary side-effects (today: `terminal` → files saved
to the sandbox's `/artifacts/` directory) call `stage()` to register
those bytes against the current chat. The agent loop drains via
`consume()` between LLM turns and turns each entry into the right
multimodal block (ImageBlock for images, text mention otherwise).

In-memory module-level dict by design — staging only needs to survive
across tool calls within ONE chat turn, never across processes. Locked
because tool execution is concurrent (asyncio.gather in the runtime
fires multiple tools per assistant message in parallel).

Each entry is a plain dict so producers don't have to import a model
class:
    {name, path, mime, size, bytes, truncated}
"""
from __future__ import annotations

import threading

_pending: dict[str, list[dict]] = {}
_lock = threading.Lock()


def stage(chat_id: str, items: list[dict]) -> None:
    if not chat_id or not items:
        return
    with _lock:
        _pending.setdefault(chat_id, []).extend(items)


def consume(chat_id: str) -> list[dict]:
    if not chat_id:
        return []
    with _lock:
        return _pending.pop(chat_id, [])
