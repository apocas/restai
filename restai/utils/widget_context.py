"""Widget context verification and system prompt injection.

Supports signed (JWT) context tokens that site owners generate on their
backend. The token is verified server-side before injecting claims into
the project's system prompt.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import jwt

logger = logging.getLogger(__name__)

# JWT claims that are never exposed as template variables
_JWT_RESERVED = {"exp", "iat", "nbf", "iss", "aud", "jti"}

# Keys that could be used to override system behavior
_DANGEROUS_KEYS = {"system", "prompt", "instructions"}

_MAX_PAYLOAD_BYTES = 4096
_MAX_TTL_SECONDS = 86400  # 24 hours

_CONTEXT_PATTERN = re.compile(r"\{\{context\.([a-zA-Z0-9_.]+)\}\}")


def verify_widget_context(
    token: str,
    secret: str,
    max_ttl: int = _MAX_TTL_SECONDS,
) -> dict:
    """Verify a signed JWT context token and return clean claims.

    Raises ValueError on any verification failure.
    """
    if not token or not secret:
        raise ValueError("Missing token or secret")

    # Size check on raw token
    if len(token) > _MAX_PAYLOAD_BYTES * 2:
        raise ValueError("Context token too large")

    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
    except jwt.ExpiredSignatureError:
        raise ValueError("Context token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid context token: {e}")

    # Enforce max TTL cap
    import time
    iat = claims.get("iat")
    exp = claims.get("exp")
    now = time.time()
    if exp and iat and (exp - iat) > max_ttl:
        raise ValueError("Context token TTL exceeds maximum allowed")
    if exp and not iat and (exp - now) > max_ttl:
        raise ValueError("Context token TTL exceeds maximum allowed")

    # Check decoded payload size
    cleaned = {k: v for k, v in claims.items() if k not in _JWT_RESERVED}
    payload_json = json.dumps(cleaned)
    if len(payload_json.encode()) > _MAX_PAYLOAD_BYTES:
        raise ValueError("Context payload too large")

    # Strip dangerous keys
    for key in _DANGEROUS_KEYS:
        cleaned.pop(key, None)

    return cleaned


def apply_widget_context(
    system_prompt: str,
    context: dict,
    prepend_block: bool = True,
) -> str:
    """Inject verified context into a system prompt.

    1. Optionally prepends a structured [User Context] block
    2. Replaces {{context.key}} template variables (single-pass, no recursion)
    """
    if not context:
        return system_prompt

    result = system_prompt or ""

    # Prepend context block
    if prepend_block:
        lines = []
        for key, value in context.items():
            if isinstance(value, dict):
                for sub_key, sub_value in _flatten_dict(value, key):
                    lines.append(f"{sub_key}: {sub_value}")
            else:
                lines.append(f"{key}: {value}")
        if lines:
            block = "[User Context]\n" + "\n".join(lines) + "\n[/User Context]\n\n"
            result = block + result

    # Template variable substitution (single-pass)
    def _replace(match):
        dotted_key = match.group(1)
        return str(_resolve_dotted_key(context, dotted_key))

    result = _CONTEXT_PATTERN.sub(_replace, result)

    return result


def _resolve_dotted_key(context: dict, dotted_key: str) -> str:
    """Resolve a dotted key path like 'meta.plan' against the context dict."""
    parts = dotted_key.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return ""
    return str(current) if current is not None else ""


def _flatten_dict(d: dict, prefix: str) -> list[tuple[str, Any]]:
    """Flatten a nested dict into dotted key-value pairs."""
    items = []
    for key, value in d.items():
        full_key = f"{prefix}.{key}"
        if isinstance(value, dict):
            items.extend(_flatten_dict(value, full_key))
        else:
            items.append((full_key, value))
    return items
