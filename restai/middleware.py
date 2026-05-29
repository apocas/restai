"""App-wide exception handlers + the CORS / security-header middleware.

Registered onto the FastAPI app by `register_middleware(app)` from `main.py`.
Kept out of `main.py` so the entry point stays focused on app construction +
lifespan; the header policy is involved enough to read on its own.
"""

import logging
import re

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
# App Builder preview proxy — same-origin iframe embed needs softened
# headers (otherwise frame-ancestors 'none' / X-Frame-Options: DENY block
# the embed). The generated app's own CSP, if any, applies inside the
# iframe; what we set here is just the outer envelope so the admin SPA
# can host the iframe.
_PREVIEW_PATH_RE = re.compile(r"^/projects/\d+/app/preview(?:/|$)")
_PREVIEW_SECURITY_HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": "frame-ancestors 'self'",
}


def register_middleware(app: FastAPI) -> None:
    """Attach the exception handlers and the CORS/security-header middleware."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
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
        return JSONResponse(
            content={"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logging.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
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
        elif _PREVIEW_PATH_RE.match(path):
            # App-builder live preview iframe: same-origin embed allowed.
            # Force-set (not setdefault) to override any header the proxy
            # forwarded from the upstream PHP server.
            for k, v in _PREVIEW_SECURITY_HEADERS.items():
                response.headers[k] = v
        else:
            for k, v in _ADMIN_SECURITY_HEADERS.items():
                response.headers.setdefault(k, v)

        return response
