"""Platform-plumbing helpers shared across all agent loop implementations."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from restai.memory import bank as memory_bank


def sandbox_chat_id(project_id, user_id, chat_id: str) -> str:
    """Tenant-scoped, unforgeable key for the per-conversation sandbox
    container + agent session.

    The Docker container and the chat session are looked up *only* by this
    key. If it were the raw client-supplied ``ChatModel.id``, two different
    users could pick the same string and share a container (their uploaded
    files, downloaded artifacts, scratch state) and conversation history.
    Binding the key to the authenticated ``user_id`` + ``project_id`` makes
    cross-tenant / cross-user collision impossible — the server always derives
    it from the caller's own identity, so an attacker cannot target someone
    else's sandbox by guessing their chat id.

    Deterministic, so the same user's repeat turns in one conversation reuse
    the same container/session.
    """
    raw = f"{project_id}\x00{user_id}\x00{chat_id or uuid4().hex}".encode()
    return "sbx_" + hashlib.sha256(raw).hexdigest()[:40]


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


class ToolRunPolicy:
    """Per-request tool-execution policy for the external agent loops —
    mirrors the agent2 runtime's tool hardening so every harness offers the
    same guarantees:

    - per-call timeout from ``ProjectOptions.tool_timeout`` (0 = off); a tool
      that exceeds it returns an ``ERROR: … timed out`` string the model can
      react to instead of hanging the conversation
    - identical-call loop guard: the 3rd+ identical (tool, args) call this
      request still executes but gets a nudge appended
    - model-visible output cap (``truncate_tool_output``) so one giant tool
      result can't blow the model's context
    - exceptions become ``ERROR: …`` strings instead of harness-specific
      failures

    One instance per request, shared by every tool wrapper of that request
    (the loop-guard counter is request-scoped).
    """

    def __init__(self, project=None, timeout: float | None = None):
        if timeout is None and project is not None:
            try:
                timeout = float(getattr(project.props.options, "tool_timeout", 300) or 0)
            except (TypeError, ValueError):
                timeout = 300.0
        self.timeout: float | None = timeout or None
        self._call_counts: dict = {}

    # ── loop guard ──────────────────────────────────────────────────────
    def loop_guard_note(self, name: str, args: dict) -> str:
        import json as _json
        try:
            canonical = _json.dumps(args or {}, sort_keys=True, default=str)
        except Exception:
            canonical = str(args)
        key = (name, canonical)
        count = self._call_counts.get(key, 0) + 1
        self._call_counts[key] = count
        if count < 3:
            return ""
        return (
            f"\n\n[loop guard: this exact tool call has now run {count} times "
            "this request. If the result isn't changing, adjust the arguments "
            "or approach — or produce your final answer with what you have.]"
        )

    def _timeout_error(self, name: str) -> str:
        return (
            f"ERROR: tool '{name}' timed out after {int(self.timeout or 0)}s. "
            "The operation may still finish in the background. Try a smaller "
            "input, a quicker check, or a different approach."
        )

    @staticmethod
    def _to_text(result) -> str:
        import json as _json
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        if isinstance(result, (dict, list)):
            try:
                return _json.dumps(result, default=str)
            except Exception:
                return str(result)
        return str(result)

    def _finalize(self, name: str, args: dict, result) -> str:
        text = truncate_tool_output(self._to_text(result))
        note = self.loop_guard_note(name, args)
        return text + note if note else text

    # ── runners ─────────────────────────────────────────────────────────
    async def run_async(self, name: str, args: dict, *,
                        call_async=None, call_sync=None) -> tuple[str, bool]:
        """Execute one tool call from an async harness. Exactly one of
        ``call_async`` (zero-arg → awaitable) / ``call_sync`` (zero-arg,
        runs in a worker thread so it can't block the event loop) must be
        given. Returns ``(text, is_error)``."""
        try:
            awaitable = call_async() if call_async is not None else asyncio.to_thread(call_sync)
            if self.timeout:
                result = await asyncio.wait_for(awaitable, timeout=self.timeout)
            else:
                result = await awaitable
        except asyncio.TimeoutError:
            logging.warning("tool '%s' timed out after %.0fs", name, self.timeout or 0)
            return self._timeout_error(name), True
        except Exception as e:
            logging.exception("tool '%s' raised", name)
            return f"ERROR: {e}", True
        return self._finalize(name, args, result), False

    def run_sync(self, name: str, args: dict, call) -> tuple[str, bool]:
        """Execute one tool call from a sync harness (e.g. smolagents, whose
        agent already runs in a worker thread). With a timeout the call runs
        in a dedicated thread we abandon on expiry — same tradeoff as the
        async path (the runaway thread lingers but the conversation moves
        on)."""
        try:
            if self.timeout:
                from concurrent.futures import (
                    ThreadPoolExecutor,
                    TimeoutError as _FutureTimeout,
                )
                executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"tool-{name}"
                )
                future = executor.submit(call)
                try:
                    result = future.result(timeout=self.timeout)
                except _FutureTimeout:
                    executor.shutdown(wait=False, cancel_futures=True)
                    logging.warning("tool '%s' timed out after %.0fs", name, self.timeout)
                    return self._timeout_error(name), True
                finally:
                    executor.shutdown(wait=False)
            else:
                result = call()
        except Exception as e:
            logging.exception("tool '%s' raised", name)
            return f"ERROR: {e}", True
        return self._finalize(name, args, result), False


def max_execution_seconds(project) -> float | None:
    """The project's per-run wall-clock cap (``options.max_execution_time``),
    or None when unlimited/unset."""
    try:
        value = float(getattr(project.props.options, "max_execution_time", 0) or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def execution_deadline(project) -> float | None:
    """Monotonic deadline for this run, or None when unlimited. Loops check
    it at safe points (turn/event boundaries) — never mid-stream — so the
    run wraps up with partial results instead of being killed."""
    cap = max_execution_seconds(project)
    if cap is None:
        return None
    import time as _time
    return _time.monotonic() + cap


def max_time_notice(seconds: float | int | None) -> str:
    """Standard "hit the wall-clock cap — say 'continue'" message; mirrors
    `max_turns_notice` so every loop emits the same UX."""
    cap = int(seconds) if seconds else "max"
    return (
        f"\n\n_⚠ Reached the {cap}s execution-time cap before finishing. "
        f"Reply **\"continue\"** (or narrow the request) and I'll keep "
        f"working from here._"
    )


def fallback_llm_names(project) -> list[str]:
    """Ordered fallback LLM names from ``options.fallback_llm`` — deduped,
    minus the project's primary LLM. Loop-incompatible entries are not
    filtered here; each loop's resolver rejects them at attempt time."""
    try:
        raw = getattr(project.props.options, "fallback_llm", None) or ""
    except Exception:
        raw = ""
    seen = {getattr(project.props, "llm", None) or ""}
    out: list[str] = []
    for name in (n.strip() for n in raw.split(",")):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _fallback_error_text(e: Exception) -> str:
    detail = getattr(e, "detail", None)
    return str(detail) if detail else str(e)


async def drive_with_fallbacks(project, drive_factory, *, loop_name: str, output: dict):
    """Shared whole-run fallback driver for the external loops.

    ``drive_factory(llm_override, run_state)`` returns the loop's ``_drive``
    async generator. On failure the run is retried on the next LLM from
    ``options.fallback_llm`` — but ONLY while nothing has streamed to the
    client and no tool has executed (``run_state['tools_executed']``), so a
    retry can never duplicate output or repeat a side effect. (The agent2
    `restai` loop switches mid-run instead because it owns its transcript;
    SDK harnesses can only be restarted whole.)

    Yields the same (kind, payload) tuples as ``_drive`` plus:
      - ("event", {"llm_fallback": {from, to}}) on each switch
      - ("error", {"exception": e}) on terminal failure instead of raising
    Fallback switches are also merged into the result payload's tool_trace
    and recorded on ``output`` as ``llm_used``/``llm_fallbacks``.
    """
    import json as _json

    attempts: list = [None] + fallback_llm_names(project)
    switch_rows: list[dict] = []
    # One wall-clock budget for the WHOLE request: without this, every
    # fallback attempt would recompute its own deadline and a chain of N
    # LLMs could run N × max_execution_time.
    shared_deadline = execution_deadline(project)
    for idx, llm_override in enumerate(attempts):
        run_state = {"tools_executed": 0, "streamed": False,
                     "deadline": shared_deadline}
        try:
            async for kind, payload in drive_factory(llm_override, run_state):
                if kind == "text":
                    run_state["streamed"] = True
                elif kind == "result" and switch_rows:
                    merged = list(switch_rows) + list(payload.get("tool_trace") or [])
                    payload = dict(payload, tool_trace=merged)
                yield kind, payload
            return
        except Exception as e:
            can_retry = (
                not run_state["streamed"]
                and not run_state["tools_executed"]
                and idx + 1 < len(attempts)
            )
            if not can_retry:
                logging.exception("%s loop failed with no fallback available", loop_name)
                yield ("error", {"exception": e})
                return
            from_name = llm_override or getattr(project.props, "llm", None) or "primary"
            to_name = attempts[idx + 1]
            err_text = _fallback_error_text(e)[:300]
            logging.warning(
                "%s loop: switching to fallback LLM '%s' after '%s' failed: %s",
                loop_name, to_name, from_name, err_text,
            )
            entry = {"from": from_name, "to": to_name, "turn": 1, "error": err_text}
            output.setdefault("llm_fallbacks", []).append(entry)
            output["llm_used"] = to_name
            switch_rows.append({
                "tool": "llm_fallback",
                "args": _json.dumps({"from": from_name, "to": to_name, "turn": 1}),
                "latency_ms": None,
                "status": "ok",
                "error": err_text or None,
            })
            yield ("event", {"llm_fallback": {"from": from_name, "to": to_name}})


def estimate_input_tokens(prompt_text: str, *, system_prompt: str = "",
                          history: list | None = None,
                          tool_trace: list | None = None) -> int:
    """Transcript-aware input-token estimate for loops whose harness reported
    no real usage — mirrors the agent2 fallback: the prompt actually sent
    each turn is system prompt (incl. memory/history injections) + prior
    turns + tool round-trip context, not just the latest question."""
    import json as _json

    from restai.tools import tokens_from_string

    total = tokens_from_string(prompt_text or "")
    if system_prompt:
        total += tokens_from_string(system_prompt)
    for m in history or []:
        content = getattr(m, "content", None)
        if not content:
            continue
        total += tokens_from_string(content if isinstance(content, str) else str(content))
    if tool_trace:
        try:
            total += tokens_from_string(_json.dumps(tool_trace))
        except Exception:
            pass
    return total


def usage_from_raw_response(raw) -> tuple[int, int] | None:
    """Best-effort (input, output) token extraction from a provider's raw
    response object/dict — handles OpenAI (prompt/completion_tokens) and
    Anthropic (input/output_tokens) shapes. None when nothing usable."""
    if raw is None:
        return None
    usage = raw.get("usage") if isinstance(raw, dict) else getattr(raw, "usage", None)
    if usage is None:
        return None

    def _get(obj, *names):
        for n in names:
            v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    continue
        return 0

    in_tok = _get(usage, "prompt_tokens", "input_tokens")
    out_tok = _get(usage, "completion_tokens", "output_tokens")
    if in_tok <= 0 and out_tok <= 0:
        return None
    return in_tok, out_tok


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
