"""App-wide exception handlers + the CORS / security-header middleware.

Registered onto the FastAPI app by `register_middleware(app)` from `main.py`.
Kept out of `main.py` so the entry point stays focused on app construction +
lifespan; the header policy is involved enough to read on its own.
"""

import logging

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from restai.constants import ERROR_MESSAGES


# CORS — only allow wildcard origins for widget endpoints (cross-origin
# chat API calls from embedded widgets on third-party sites). All other
# endpoints use same-origin only.
_WIDGET_CORS_PATHS = ("/widget/",)
_CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept, X-Widget-Key, X-Widget-Context",
    "Access-Control-Max-Age": "86400",
}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
_ADMIN_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: blob: https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        # Monaco's language workers (TypeScript, JSON, CSS, HTML) are
        # spawned from blob: URIs at runtime; without this they crash
        # silently and the editor falls back to plain text.
        "worker-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    ),
}


# OpenAI-compatible endpoints (mounted under /v1/*) must return OpenAI's error
# envelope — `{"error":{message,type,param,code}}` — so the official OpenAI SDKs
# raise the right exception classes instead of choking on RESTai's `{detail}`.
_OPENAI_ERROR_TYPE = {
    400: "invalid_request_error", 401: "invalid_request_error", 403: "invalid_request_error",
    404: "invalid_request_error", 422: "invalid_request_error",
    402: "insufficient_quota", 429: "rate_limit_exceeded",
}
_OPENAI_ERROR_CODE = {
    401: "invalid_api_key", 402: "insufficient_quota", 404: "model_not_found",
    429: "rate_limit_exceeded",
}


def _is_openai_path(request: Request) -> bool:
    return request.url.path.startswith("/v1/")


def _openai_error(status_code: int, message, param=None, code=None, type_override=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {
            "message": str(message),
            "type": type_override or _OPENAI_ERROR_TYPE.get(status_code, "api_error"),
            "param": param,
            "code": code if code is not None else _OPENAI_ERROR_CODE.get(status_code),
        }},
    )


def register_middleware(app: FastAPI) -> None:
    """Attach the exception handlers and the CORS/security-header middleware."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if _is_openai_path(request):
            return _openai_error(exc.status_code, exc.detail)
        response = JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)
        if exc.status_code == 401:
            response.delete_cookie(key="restai_token")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
        logging.error(f"{request}: {exc_str}")
        messages = []
        for err in exc.errors():
            msg = err.get("msg", "")
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, "):]
            messages.append(msg)
        detail = "; ".join(messages) if messages else exc_str
        if _is_openai_path(request):
            first = exc.errors()[0] if exc.errors() else {}
            loc = [str(x) for x in first.get("loc", []) if x != "body"]
            return _openai_error(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail,
                param=".".join(loc) or None, type_override="invalid_request_error",
            )
        return JSONResponse(
            content={"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
        if _is_openai_path(request):
            return _openai_error(500, "Internal server error", type_override="api_error")
        return JSONResponse(
            content={"detail": "Internal server error"},
            status_code=500,
        )

    @app.middleware("http")
    async def cors_middleware(request: Request, call_next):
        path = request.url.path
        is_widget = any(path.startswith(p) for p in _WIDGET_CORS_PATHS)
        origin = request.headers.get("origin")

        # Handle preflight OPTIONS
        if request.method == "OPTIONS" and is_widget and origin:
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    **_CORS_HEADERS,
                },
            )

        response = await call_next(request)

        if is_widget and origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            for k, v in _CORS_HEADERS.items():
                response.headers[k] = v

        # Security headers — applied to all responses, with stricter rules for non-widget paths.
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if is_widget:
            pass  # widget paths exempt from frame-ancestors / CSP entirely
        else:
            for k, v in _ADMIN_SECURITY_HEADERS.items():
                response.headers.setdefault(k, v)

        return response


# ── Request body-size guard ────────────────────────────────────────────────
#
# Rejects oversized request bodies BEFORE they are consumed. Without this,
# every upload path had to read the whole file to measure it (turning an
# oversized upload into an OOM instead of a 413), and the base64 chat path
# had Starlette buffer + Pydantic parse hundreds of MB before any validator
# ran.
#
# Deliberately pure ASGI rather than `@app.middleware("http")`:
#   * BaseHTTPMiddleware runs the app in a task group and re-raises
#     receive-side errors out of `call_next`, so a clean 413 can't be emitted
#     from there — and it would add a task group to every SSE stream.
#   * Raising HTTPException from middleware does NOT reach the app's
#     exception handlers (those live in the inner ExceptionMiddleware), so it
#     would surface as a 500. We build and send the response ourselves.

# Multipart bodies carry the file plus part boundaries and the sibling form
# fields, so the envelope is always a little larger than the file itself.
# Without slack an exactly-at-the-limit file would be rejected.
_MULTIPART_SLACK_BYTES = 2 * 1024 * 1024

# Paths that stream real files. Everything else only ever carries JSON.
_UPLOAD_PATH_MARKERS = (
    "/embeddings/ingest/upload",
    "/ingest-bulk",
    "/attachments",
    "/audio/",
)

# Ceiling for ordinary JSON bodies. Generous enough for base64 images and the
# logo data-URI in settings, small enough that a runaway payload can't pin a
# worker's memory.
_JSON_BODY_LIMIT_BYTES = 32 * 1024 * 1024


class _BodyTooLarge(Exception):
    """Raised inside the wrapped `receive` once the body exceeds the limit."""


def _limit_for_path(path: str) -> int:
    if any(marker in path for marker in _UPLOAD_PATH_MARKERS):
        from restai import config as _config
        return _config.max_upload_bytes() + _MULTIPART_SLACK_BYTES
    return _JSON_BODY_LIMIT_BYTES


class BodySizeLimitMiddleware:
    """ASGI middleware enforcing a per-path request body ceiling."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        limit = _limit_for_path(path)

        # Fast path: trust Content-Length enough to reject before reading a
        # single byte. It's advisory (a client can lie or omit it under
        # Transfer-Encoding: chunked), so the streaming counter below is the
        # real enforcement.
        for name, value in scope.get("headers") or []:
            if name == b"content-length":
                try:
                    if int(value) > limit:
                        await self._reject(scope, send, limit)
                        return
                except (TypeError, ValueError):
                    pass
                break

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b"") or b"")
                if received > limit:
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            # If the app already started responding we can't replace it — a
            # second response.start is a hard ASGI protocol error.
            if not response_started:
                await self._reject(scope, send, limit)

    @staticmethod
    async def _reject(scope, send, limit: int) -> None:
        megabytes = limit // (1024 * 1024)
        path = scope.get("path", "")
        if path.startswith("/v1/"):
            # `api_error` reads as retryable to the OpenAI SDKs, which would
            # have clients re-upload the same oversized body.
            response = _openai_error(
                413,
                f"Request body too large. Maximum is {megabytes} MB.",
                type_override="invalid_request_error",
            )
        else:
            response = JSONResponse(
                status_code=413,
                content={"detail": ERROR_MESSAGES.FILE_TOO_LARGE(f"{megabytes} MB")},
            )
        # Close the connection: the peer is likely still uploading, and
        # keeping it alive on a half-read body confuses most clients.
        raw_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"connection"]
        raw_headers.append((b"connection", b"close"))
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": raw_headers,
        })
        await send({"type": "http.response.body", "body": response.body})
