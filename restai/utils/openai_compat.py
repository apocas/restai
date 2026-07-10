"""OpenAI ↔ llama-index translation + native passthrough for the /direct API.

The `/v1/chat/completions` (and friends) endpoints in `restai/routers/direct.py`
back arbitrary platform LLMs. Two paths:

- **Native passthrough** — when the backing LLM is an OpenAI-wire-compatible
  class (`OpenAI`/`OpenAILike`/`Grok`/`vLLM`/`AzureOpenAI`), forward the request
  body straight to that provider's upstream endpoint and stream its raw SSE back.
  Maximum fidelity: real usage, logprobs, streaming tool-call deltas, `n`,
  `logit_bias`, `parallel_tool_calls`, `response_format` json_schema — because it
  IS the upstream OpenAI API.
- **Translated fallback** — for every other provider (Ollama-native, Anthropic,
  Gemini, Bedrock …), convert to llama-index `ChatMessage` + kwargs and call
  `llm.chat()` / `llm.stream_chat()`, then translate the response back.

Mirrors the (removed) `anthropic_compat` translate-in / translate-out / native
passthrough structure.
"""
import json
import uuid
from importlib.metadata import version
from typing import Optional

import httpx
from llama_index.core.base.llms.types import ChatMessage, MessageRole

_ROLE_MAP = {
    "system": MessageRole.SYSTEM,
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
    "tool": MessageRole.TOOL,
}

# Params forwarded verbatim into llama-index `llm.chat(**kwargs)`. Whether each
# reaches the wire depends on the concrete provider class.
_FORWARD_PARAMS = (
    "temperature", "top_p", "frequency_penalty", "presence_penalty",
    "stop", "seed", "response_format", "logprobs", "top_logprobs",
    "logit_bias", "parallel_tool_calls",
)

# LLM classes that speak the OpenAI HTTP wire format → eligible for passthrough.
_OPENAI_NATIVE_CLASSES = {"OpenAI", "OpenAILike", "Grok", "vLLM", "AzureOpenAI"}


def system_fingerprint() -> str:
    try:
        return f"restai-{version('restai')}"
    except Exception:
        return "restai"


# ── translate-in ────────────────────────────────────────────────────────────

def convert_messages(messages) -> list[ChatMessage]:
    """OpenAI messages (Pydantic or dicts) → llama-index ChatMessage list."""
    result = []
    for m in messages:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None) or "user"
        content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
        tool_call_id = getattr(m, "tool_call_id", None) if not isinstance(m, dict) else m.get("tool_call_id")
        name = getattr(m, "name", None) if not isinstance(m, dict) else m.get("name")
        tool_calls = getattr(m, "tool_calls", None) if not isinstance(m, dict) else m.get("tool_calls")

        additional_kwargs = {}
        if tool_call_id:
            additional_kwargs["tool_call_id"] = tool_call_id
        if name:
            additional_kwargs["name"] = name
        if tool_calls:
            additional_kwargs["tool_calls"] = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in tool_calls
            ]
        result.append(ChatMessage(
            role=_ROLE_MAP.get(role, MessageRole.USER),
            content=content or "",
            additional_kwargs=additional_kwargs,
        ))
    return result


def _tools_from_functions(functions) -> list[dict]:
    """Legacy `functions` → OpenAI `tools` shape."""
    return [{"type": "function", "function": f} for f in (functions or [])]


def build_kwargs(body) -> dict:
    """Request model → kwargs forwarded to `llm.chat()`. Handles max_tokens /
    max_completion_tokens and legacy functions/function_call."""
    kwargs = {}
    for param in _FORWARD_PARAMS:
        val = getattr(body, param, None)
        if val is not None:
            kwargs[param] = val

    max_tokens = getattr(body, "max_completion_tokens", None) or getattr(body, "max_tokens", None)
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    tools = getattr(body, "tools", None)
    tool_choice = getattr(body, "tool_choice", None)
    functions = getattr(body, "functions", None)
    function_call = getattr(body, "function_call", None)
    if not tools and functions:
        tools = _tools_from_functions(functions)
        if tool_choice is None and function_call is not None:
            tool_choice = function_call

    if tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.function.name,
                    "description": t.function.description or "",
                    "parameters": t.function.parameters or {"type": "object", "properties": {}},
                },
            } if hasattr(t, "function") else t
            for t in tools
        ]
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    return kwargs


# ── translate-out ───────────────────────────────────────────────────────────

def extract_finish_reason(response) -> str:
    if hasattr(response, "raw") and response.raw is not None:
        try:
            raw = response.raw
            choices = raw["choices"] if isinstance(raw, dict) else raw.choices
            fr = choices[0]["finish_reason"] if isinstance(choices[0], dict) else choices[0].finish_reason
            if fr:
                return fr
        except (AttributeError, IndexError, TypeError, KeyError):
            pass
    if hasattr(response, "message") and hasattr(response.message, "additional_kwargs"):
        if response.message.additional_kwargs.get("tool_calls"):
            return "tool_calls"
    return "stop"


def extract_tool_calls(response) -> Optional[list[dict]]:
    if not hasattr(response, "message") or not hasattr(response.message, "additional_kwargs"):
        return None
    raw_calls = response.message.additional_kwargs.get("tool_calls")
    if not raw_calls:
        return None
    result = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            func = tc.get("function", {})
            result.append({
                "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {"name": func.get("name", ""), "arguments": func.get("arguments", "{}")},
            })
        else:
            result.append({
                "id": getattr(tc, "id", f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {
                    "name": getattr(tc.function, "name", ""),
                    "arguments": getattr(tc.function, "arguments", "{}"),
                },
            })
    return result


def usage_from_response(response):
    """Return the provider's real `(prompt, completion, total)` token counts when
    the underlying response carries a usage block, else None (caller estimates)."""
    raw = getattr(response, "raw", None)
    if raw is None:
        return None
    try:
        usage = raw["usage"] if isinstance(raw, dict) else getattr(raw, "usage", None)
        if usage is None:
            return None
        get = (lambda k: usage.get(k)) if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
        p = get("prompt_tokens")
        c = get("completion_tokens")
        t = get("total_tokens")
        if p is None and c is None:
            return None
        p = int(p or 0)
        c = int(c or 0)
        return (p, c, int(t) if t is not None else p + c)
    except Exception:
        return None


# ── native passthrough ──────────────────────────────────────────────────────

def is_openai_native(class_name: Optional[str]) -> bool:
    return class_name in _OPENAI_NATIVE_CLASSES


def resolve_upstream(llm_model, endpoint: str = "chat/completions"):
    """Resolve `(url, headers, upstream_model)` for a native passthrough, or
    None when the LLM's stored options are insufficient (→ caller falls back to
    the translated path)."""
    opts = llm_model.options or {}
    if isinstance(opts, str):
        try:
            opts = json.loads(opts)
        except Exception:
            opts = {}
    class_name = llm_model.class_name
    api_key = opts.get("api_key") or ""
    upstream_model = opts.get("model") or opts.get("engine") or opts.get("model_name")

    if class_name == "AzureOpenAI":
        base = (opts.get("azure_endpoint") or opts.get("api_base") or "").rstrip("/")
        api_version = opts.get("api_version") or "2024-02-15-preview"
        deployment = opts.get("engine") or opts.get("deployment_name") or upstream_model
        if not base or not api_key or not deployment:
            return None
        url = f"{base}/openai/deployments/{deployment}/{endpoint}?api-version={api_version}"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        return url, headers, deployment

    # OpenAI / OpenAILike / Grok / vLLM
    base = (opts.get("api_base") or opts.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    if not api_key and class_name == "OpenAI":
        return None  # real OpenAI requires a key; without it, fall back
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return f"{base}/{endpoint}", headers, upstream_model


async def passthrough_json(url: str, headers: dict, body: dict, timeout: float = 300.0):
    """Forward a non-streaming request upstream; return `(status_code, json)`."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=body)
        try:
            data = resp.json()
        except Exception:
            data = {"error": {"message": resp.text[:500] or "upstream error",
                              "type": "api_error", "code": None, "param": None}}
        return resp.status_code, data


async def passthrough_sse(url: str, headers: dict, body: dict, usage_holder: dict, forward_usage: bool):
    """Async-generate the upstream SSE stream verbatim. Forces
    `stream_options.include_usage` upstream so we can capture real usage for
    billing (stashed in `usage_holder`), forwarding the usage frame to the client
    only when it asked for it."""
    body = dict(body)
    so = dict(body.get("stream_options") or {})
    so["include_usage"] = True
    body["stream_options"] = so

    timeout = httpx.Timeout(connect=15.0, read=None, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                text = (await resp.aread()).decode("utf-8", "replace")
                try:
                    err = json.loads(text)
                except Exception:
                    err = {"error": {"message": text[:500] or "upstream error", "type": "api_error"}}
                yield f"data: {json.dumps(err)}\n\n"
                yield "data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    yield "data: [DONE]\n\n"
                    continue
                # Capture the usage-only frame; forward it only if the client wants it.
                try:
                    obj = json.loads(payload)
                    if obj.get("usage") and not obj.get("choices"):
                        usage_holder["usage"] = obj["usage"]
                        if not forward_usage:
                            continue
                except Exception:
                    pass
                yield f"data: {payload}\n\n"
