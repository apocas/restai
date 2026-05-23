"""Platform-plumbing helpers shared across all agent loop implementations."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime, timezone

from restai import memory_bank


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


# Shared per-chat history used by every external agent loop (claude,
# llamaindex, smolagents, openai_agents). The `restai` loop (agent2) keeps
# its own rich session at restai/agent2/memory.py because its messages
# carry full tool_use / tool_result blocks — that store is separate.
# Backend: brain.chat_store; one key per chat_id; value is the raw list of
# llama-index ChatMessage objects.
_AGENT_HISTORY_KEY_PREFIX = "agent_history:"


def _history_key(chat_id: str) -> str:
    return f"{_AGENT_HISTORY_KEY_PREFIX}{chat_id}"


def load_chat_history(brain, chat_id: str) -> list:
    """Load prior turns as list of ChatMessage; [] on missing/corrupt; never raises.

    All four external loops share the same key so switching `agent_loop` on
    a project preserves continuity.
    """
    store = getattr(brain, "chat_store", None)
    if store is None or not chat_id:
        return []
    try:
        from llama_index.core.llms import ChatMessage
    except Exception:
        return []
    try:
        raw = store.get_messages(_history_key(chat_id)) or []
    except Exception as e:
        logging.warning("agent_shared: load_chat_history failed for %s: %s", chat_id, e)
        return []
    out: list = []
    for m in raw:
        if isinstance(m, ChatMessage):
            out.append(m)
        elif isinstance(m, dict):
            try:
                out.append(ChatMessage.model_validate(m))
            except Exception:
                continue
    return out


def persist_chat_turn(brain, chat_id: str, prior: list, user_msg: str, assistant_answer: str) -> None:
    """Append the just-completed turn to `prior` and save back; failures logged, never raised."""
    store = getattr(brain, "chat_store", None)
    if store is None or not chat_id:
        return
    try:
        from llama_index.core.llms import ChatMessage
    except Exception:
        return
    try:
        updated = list(prior)
        if user_msg:
            updated.append(ChatMessage(role="user", content=user_msg))
        if assistant_answer:
            updated.append(ChatMessage(role="assistant", content=assistant_answer))
        store.set_messages(_history_key(chat_id), updated)
    except Exception as e:
        logging.warning("agent_shared: persist_chat_turn failed for %s: %s", chat_id, e)


def parse_data_url(data_url: str | None) -> tuple[str, bytes] | None:
    """Decode `data:<mime>;base64,<payload>` URL into `(mime, raw_bytes)`."""
    if not data_url or not data_url.startswith("data:"):
        return None
    try:
        header, b64 = data_url.split(",", 1)
        mime = header[5:].split(";")[0] or "image/png"
        return (mime, base64.b64decode(b64))
    except Exception:
        return None


def chat_history_as_text(messages: list, max_turns: int = 20) -> str:
    """Render history as plain-text transcript for SDKs without native chat_history."""
    if not messages:
        return ""
    # Bound the block to avoid eating the context window on long chats.
    tail = messages[-max_turns:]
    lines = ["[Previous conversation in this chat — for context only, "
             "do not re-state these to the user:]"]
    for m in tail:
        role = (getattr(m, "role", None) or "user")
        if hasattr(role, "value"):
            role = role.value
        content = getattr(m, "content", None) or ""
        if not isinstance(content, str):
            # Multimodal / block-shaped content — flatten to text.
            try:
                content = " ".join(
                    getattr(b, "text", "") for b in content
                    if getattr(b, "text", None)
                )
            except Exception:
                content = str(content)
        if content.strip():
            lines.append(f"{role}: {content.strip()}")
    return "\n".join(lines)


# Module-level set keeps fire-and-forget save tasks alive past GC. Without
# this, request-side cancellation (Starlette middleware teardown) skips the
# synchronous save and the next chat turn loads stale messages — manifests
# as the agent "losing its thoughts".
_PENDING_SESSION_SAVES: set = set()


def spawn_session_save(brain, chat_id, session) -> None:
    """Schedule session persist that outlives request cancellation; safe from finally blocks."""
    from restai.agent2.memory import save_session

    if not chat_id or session is None or not getattr(session, "messages", None):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        task = loop.create_task(save_session(brain, chat_id, session))
    except Exception as e:
        logging.warning("agent2: failed to schedule fallback session save: %s", e)
        return
    _PENDING_SESSION_SAVES.add(task)
    task.add_done_callback(_PENDING_SESSION_SAVES.discard)


# Mirrors `_PENDING_SESSION_SAVES` for the external-loop chat-history store.
_PENDING_HISTORY_SAVES: set = set()


def spawn_persist_chat_turn(brain, chat_id: str, prior: list,
                            user_msg: str, assistant_answer: str) -> None:
    """Schedule `persist_chat_turn` so a Starlette cancel during the
    final yield doesn't drop the just-completed turn. Same fire-and-
    forget pattern as `spawn_session_save`."""
    if not chat_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g. tests calling synchronously) — fall
        # through to the synchronous variant.
        try:
            persist_chat_turn(brain, chat_id, prior, user_msg, assistant_answer)
        except Exception:
            pass
        return

    async def _persist():
        try:
            persist_chat_turn(brain, chat_id, prior, user_msg, assistant_answer)
        except Exception as e:
            logging.warning("agent_shared: spawn_persist_chat_turn failed for %s: %s", chat_id, e)

    try:
        task = loop.create_task(_persist())
    except Exception as e:
        logging.warning("agent_shared: failed to schedule persist_chat_turn for %s: %s", chat_id, e)
        return
    _PENDING_HISTORY_SAVES.add(task)
    task.add_done_callback(_PENDING_HISTORY_SAVES.discard)


# Cap tool output strings before persisting/yielding. Mirrors the 20k
# cap in `restai/agent2/agent.py:381-383`. A tool that dumps a 5MB log
# would otherwise blow the model's context.
TOOL_OUTPUT_MAX_CHARS = 20_000


def truncate_tool_output(text: str, max_chars: int = TOOL_OUTPUT_MAX_CHARS) -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars] + f"\n\n[…truncated {len(text) - max_chars} chars]"


def looks_repetitive(texts: list[str], min_chars: int = 120,
                     prefix_ratio: float = 0.75, min_prefix_chars: int = 100) -> bool:
    """Detect classic open-model self-prompting loop: last 3 turns share
    enough common prefix to qualify as rambling without progress.

    Tightened thresholds (vs the original `_looks_repetitive` in
    `agent.py`) because a textual heuristic alone misfires on legitimate
    multi-step exploration where the model opens each turn with a short
    task-summary preamble before diverging into distinct work. Callers
    should ALSO reset the rolling buffer whenever a tool actually
    executes — a tool call is hard evidence of progress."""
    if len(texts) < 3:
        return False
    norms = [(t or "").strip().lower()[:600] for t in texts[-3:]]
    if any(len(n) < min_chars for n in norms):
        return False
    prefix = norms[0]
    for n in norms[1:]:
        i = 0
        cap = min(len(prefix), len(n))
        while i < cap and prefix[i] == n[i]:
            i += 1
        prefix = prefix[:i]
        if len(prefix) < min_prefix_chars:
            return False
    return len(prefix) >= prefix_ratio * min(len(n) for n in norms)


REPETITION_NOTICE = (
    "(stopped — model produced repetitive output across the last 3 turns "
    "without making progress. Try rephrasing the request, breaking it into "
    "smaller steps, or switching to a more capable model.)"
)


_IMAGE_URL_RE = re.compile(
    r"!\[[^\]]*\]\((https?://[^)\s]+/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+|/image/cache/[A-Fa-f0-9]+\.[A-Za-z0-9]+)\)"
)


def harvest_image_urls(text: str) -> list[str]:
    """Return every image-cache markdown URL found in `text`. Used by
    each loop's tool-result handler to collect `draw_image` outputs so
    they can be re-appended to the final answer if the model forgets to
    quote them (some models summarize tool results and silently swallow
    the image link)."""
    if not text:
        return []
    return list({m.group(1) for m in _IMAGE_URL_RE.finditer(text)})


def append_unreferenced_image_urls(answer: str, urls: list[str]) -> str:
    """Append image markdown for any URL in `urls` that doesn't already
    appear in `answer`. Caller-side dedup so the agent's final answer
    keeps the image links visible to the chat UI."""
    if not urls:
        return answer or ""
    out = answer or ""
    missing = [u for u in urls if u not in out]
    if not missing:
        return out
    suffix = "\n\n" + "\n".join(f"![]({u})" for u in missing)
    return (out + suffix).strip()


_JSON_TO_PY = {
    "string": str, "integer": int, "number": float, "boolean": bool,
    "array": list, "object": dict, "any": object,
}


def adapted_to_function_tool(adapted):
    """Convert an `agent2.tool_adapter.AdaptedTool` into a llama-index
    `FunctionTool` with a Pydantic fn_schema synthesized from the
    AdaptedTool's `input_schema` JSON. Lets external loops route
    MCP-discovered tools through their existing FunctionTool wrappers."""
    from llama_index.core.tools import FunctionTool
    from pydantic import create_model

    fields: dict = {}
    schema = adapted.input_schema or {}
    props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
    required = set(schema.get("required") or [])
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        raw_t = spec.get("type")
        if isinstance(raw_t, list):
            raw_t = next((t for t in raw_t if t and t != "null"), raw_t[0] if raw_t else "string")
        py_t = _JSON_TO_PY.get(str(raw_t or "string").lower(), str)
        fields[name] = (py_t, ... if name in required else None)

    model = create_model(f"{adapted.name}_Schema", **fields) if fields else None
    return FunctionTool.from_defaults(
        fn=adapted.fn,
        name=adapted.name,
        description=adapted.description or adapted.name,
        fn_schema=model,
    )


def max_turns_notice(max_iterations: int | str | None) -> str:
    """Standard "hit the cap — say 'continue'" message; matches the text
    `agent.py:621-624` appends so all loops emit the same UX."""
    cap = max_iterations or "max"
    return (
        f"\n\n_⚠ Reached the {cap}-iteration tool-call cap before producing a "
        f"final answer. Reply **\"continue\"** (or give a more focused next "
        f"step) and I'll keep working from here._"
    )


def is_image_attachment(f) -> bool:
    """True if attachment should go through the multimodal vision flow."""
    mime = (getattr(f, "mime_type", None) or "").lower()
    if mime.startswith("image/"):
        return True
    name = (getattr(f, "name", "") or "").lower()
    return name.endswith(_IMAGE_EXTS)


def prepend_current_time(base_system_prompt: str | None) -> str | None:
    """Stamp current UTC time at top of system prompt; otherwise model falls back to training cutoff."""
    now = datetime.now(timezone.utc)
    stamp = f"[Current time: {now.strftime('%Y-%m-%d %H:%M UTC (%A)')}]"
    if base_system_prompt:
        return f"{stamp}\n\n{base_system_prompt}"
    return stamp


def augment_system_prompt_with_memory_bank(project, db, base_system_prompt: str | None) -> str | None:
    """Prepend rendered memory bank block when enabled. Degrades silently."""
    try:
        if not getattr(project.props.options, "memory_bank_enabled", False):
            return base_system_prompt
        max_tokens = int(getattr(project.props.options, "memory_bank_max_tokens", 2000) or 2000)
        block = memory_bank.render_for_prompt(db, project.props.id, max_tokens)
    except Exception:
        return base_system_prompt
    if not block:
        return base_system_prompt
    if base_system_prompt:
        return f"{block}\n\n{base_system_prompt}"
    return block


def project_tool_names(project) -> set[str]:
    """Lowercased set of tool names enabled on the project."""
    try:
        raw = (getattr(project.props.options, "tools", None) or "")
    except Exception:
        raw = ""
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def project_has_terminal(project) -> bool:
    """True iff project has `terminal` enabled — only that tool reads /home/user/uploads/."""
    return "terminal" in project_tool_names(project)


def augment_system_prompt_with_memory_search_hint(
    project, base_system_prompt: str | None
) -> str | None:
    """Prepend hint telling LLM WHEN to call `search_memories` (docstrings only describe HOW)."""
    try:
        if not getattr(project.props.options, "memory_search_enabled", False):
            return base_system_prompt
        if "search_memories" not in project_tool_names(project):
            return base_system_prompt
    except Exception:
        return base_system_prompt

    hint = (
        "[Memory Search]\n"
        "You have a `search_memories` tool that semantically searches every "
        "past conversation in this project. When the user references something "
        "that might have come up before — \"have we discussed X\", \"what did "
        "we decide about Y\", \"remind me of Z\", \"did we ever try W\" — call "
        "`search_memories` BEFORE answering. Don't guess at history when a "
        "search will tell you the truth."
    )
    if base_system_prompt:
        return f"{hint}\n\n{base_system_prompt}"
    return hint


def upload_files_and_augment_prompt(files, chat_id, prompt, brain):
    """Push attached files into sandbox, augment prompt with manifest; returns (prompt, warning_or_none)."""
    if not files:
        return prompt, None

    docker = getattr(brain, "docker_manager", None)
    if docker is None:
        note = "\n\n[The user attached files but the agent sandbox (Docker) isn't configured on this RESTai instance, so the files cannot be processed.]"
        return prompt + note, "no_docker"

    decoded: list[tuple[str, bytes]] = []
    for f in files:
        try:
            raw = base64.b64decode(f.content, validate=False)
        except Exception:
            continue
        if raw:
            decoded.append((f.name, raw))

    if not decoded:
        return prompt, None

    try:
        manifest = docker.put_files(chat_id or "ephemeral", decoded)
    except Exception as e:
        return prompt + f"\n\n[File upload to sandbox failed: {e}]", "upload_failed"

    if not manifest:
        return prompt, None

    lines = ["", "[Files attached by the user (available in /home/user/uploads/ — use the terminal tool to inspect them):]"]
    for entry in manifest:
        lines.append(f"  - {entry['path']}  ({entry['size']} bytes)")
    return prompt + "\n" + "\n".join(lines), None


def route_attachments(files, chat_id, prompt, brain, existing_image=None, project=None):
    """Route image vs doc attachments; explicit `image` wins over anything in `files`."""
    if not files:
        return prompt, existing_image

    images = [f for f in files if is_image_attachment(f)]
    docs = [f for f in files if not is_image_attachment(f)]

    image_url = existing_image
    if images and image_url is None:
        primary = images[0]
        mime = primary.mime_type or "image/png"
        image_url = f"data:{mime};base64,{primary.content}"

    if docs and project is not None and project_has_terminal(project):
        prompt, _ = upload_files_and_augment_prompt(docs, chat_id, prompt, brain)
    elif docs:
        names = ", ".join(f.name for f in docs[:5])
        if len(docs) > 5:
            names += f", …(+{len(docs) - 5} more)"
        prompt += (
            "\n\n[Attached file(s) ignored: this project has no tool that can "
            f"process them ({names}). Enable the `terminal` tool on the "
            "project to let the agent read uploaded files.]"
        )

    return prompt, image_url
