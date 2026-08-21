"""Transient-error classification + backoff policy for the agent2 loop.

A tool-heavy agent run makes one provider call per turn — often 10-30 calls
per request. Without retries, a single transient 429/503/connection blip at
turn N kills the entire run and throws away every tool result gathered so
far. This module centralizes the two policy questions:

- `is_retryable_error` — is this provider failure worth retrying on the
  SAME provider (rate limit, overloaded, 5xx, connection/timeout blip)?
  Auth errors, invalid requests, and context-length overflows are not:
  retrying those burns time and money without changing the outcome.
- `backoff_delay` — capped exponential backoff with jitter so parallel
  chats hitting the same rate limit don't stampede in lockstep.

Kept SDK-agnostic on purpose: providers surface errors as openai.*,
anthropic.*, botocore ClientError, httpx exceptions, or plain RuntimeErrors
from OpenAI-compatible gateways — classification goes by status code
attributes and message shape, never by imported exception classes.
"""
from __future__ import annotations

import random

# HTTP statuses worth a retry. 408 request timeout, 429 rate limit,
# 5xx server side, 529 Anthropic "overloaded".
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504, 529}

# Statuses that must NEVER be retried — the request itself is the problem.
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 405, 409, 413, 422}

# Lowercase message fragments that mark a transient failure when no status
# code is available (OpenAI-compatible gateways often wrap errors in plain
# exceptions). Kept deliberately specific — a generic match would retry
# permanent failures.
_RETRYABLE_MESSAGE_FRAGMENTS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "overloaded",
    "temporarily unavailable",
    "service unavailable",
    "connection error",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "server had an error",
    "internal server error",
    "bad gateway",
    "please try again",
)

# Fragments that veto a retry even when something above matched — retrying
# a request that exceeds the model's context window can never succeed.
_NON_RETRYABLE_MESSAGE_FRAGMENTS = (
    "context length",
    "context window",
    "maximum context",
    "too many tokens",
    "api key",
    "authentication",
    "unauthorized",
)

# Exception class names (checked across the MRO) that signal a transient
# failure regardless of message. Covers openai.APIConnectionError /
# APITimeoutError / RateLimitError / InternalServerError, anthropic's
# equivalents, and httpx transport errors without importing any of them.
_RETRYABLE_CLASS_FRAGMENTS = (
    "ratelimit",
    "timeout",
    "connectionerror",
    "connecterror",
    "internalservererror",
    "serviceunavailable",
    "overloaded",
    "apiconnection",
)


def _status_code_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction across SDK error shapes."""
    for attr in ("status_code", "http_status", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    # botocore ClientError: error metadata dict.
    meta = getattr(exc, "response", None)
    if isinstance(meta, dict):
        value = (meta.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if isinstance(value, int):
            return value
    return None


def is_retryable_error(exc: BaseException) -> bool:
    """True when retrying the same provider call may plausibly succeed."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False

    message = str(exc).lower()
    if any(f in message for f in _NON_RETRYABLE_MESSAGE_FRAGMENTS):
        return False

    status = _status_code_of(exc)
    if status is not None:
        if status in NON_RETRYABLE_STATUS_CODES:
            return False
        if status in RETRYABLE_STATUS_CODES:
            return True

    for klass in type(exc).__mro__:
        name = klass.__name__.lower()
        if any(f in name for f in _RETRYABLE_CLASS_FRAGMENTS):
            return True

    return any(f in message for f in _RETRYABLE_MESSAGE_FRAGMENTS)


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 15.0) -> float:
    """Delay before retry number `attempt` (0-based): capped exponential with
    ±25% jitter. attempt=0 → ~base, attempt=1 → ~2*base, …"""
    if base <= 0:
        return 0.0
    raw = min(cap, base * (2 ** max(0, attempt)))
    return raw * random.uniform(0.75, 1.25)
