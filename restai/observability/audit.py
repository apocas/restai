import base64
import logging
import re
import threading
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

SKIP_PREFIXES = ("/setup", "/version", "/info", "/auth", "/admin", "/mcp", "/v1")

AUDIT_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Inference endpoints are reads that happen to be POSTs; they are logged as
# inference rows, not audit rows.
#
# Matched against the ROUTE TEMPLATE FastAPI resolved, never the raw path —
# same reasoning as `_READ_ONLY_ALLOWED_ROUTES` in restai/auth.py. Matching the
# raw path let a resource NAME decide whether the request was audited: the
# original `"/chat" in path` skipped `PATCH /users/chatterbox`, and even a
# suffix test skips `DELETE /users/chat`. A template cannot be chosen by an
# attacker.
_INFERENCE_ROUTES = frozenset({
    "/projects/{projectID}/chat",
    "/projects/{projectID}/chat/stop",
    "/projects/{projectID}/question",
})


def _is_inference_path(request: Request) -> bool:
    route = request.scope.get("route")
    return getattr(route, "path", None) in _INFERENCE_ROUTES


def _extract_username(request: Request) -> tuple:
    """Pull the audit-username for this request.

    Fast path: the auth dependency (`get_current_username` in `restai/auth.py`)
    has already resolved the user — including the `<owner> (api)` suffix for
    Bearer/API-key requests — and stashed it on `request.state.audit_username`.
    We just read it.

    Fallback: parse the auth header / JWT cookie ourselves. This only kicks
    in for unauthenticated audited paths (rare — most public endpoints are
    GETs and aren't in `AUDIT_METHODS`), and never needs a DB call.
    """
    cached = getattr(request.state, "audit_username", None)
    if cached:
        return None, cached

    auth_header = request.headers.get("authorization", "")

    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username = decoded.split(":")[0]
            # NOTHING has verified this. `get_current_username` does not accept
            # Basic at all, so reaching here means the request was unauthenticated
            # or failed auth — yet the row was written under the supplied name,
            # letting anyone forge audit entries attributed to a victim. Keep it
            # for forensic value, but label it and strip control characters so it
            # cannot also inject line breaks / field separators into the record.
            username = re.sub(r"[\x00-\x1f\x7f]", "", username)[:80]
            return None, f"(unverified) {username}"
        except Exception:
            pass

    if auth_header.startswith("Bearer "):
        return None, "(api_key)"

    cookie = request.cookies.get("restai_token")
    if cookie:
        try:
            import jwt
            from restai.config import RESTAI_AUTH_SECRET
            data = jwt.decode(cookie, RESTAI_AUTH_SECRET, algorithms=["HS512"])
            return None, data.get("username", "(jwt)")
        except Exception:
            pass

    return None, None


def _log_to_db(username, action, resource, status_code):
    try:
        from restai.database import open_db_wrapper
        from restai.models.databasemodels import AuditLogDatabase

        db = open_db_wrapper()
        try:
            entry = AuditLogDatabase(
                username=username,
                action=action,
                resource=resource[:500],
                status_code=status_code,
                date=datetime.now(timezone.utc),
            )
            db.db.add(entry)
            db.db.commit()
        finally:
            db.db.close()
    except Exception as e:
        logger.warning("Failed to write audit log: %s", e)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method not in AUDIT_METHODS:
            return response

        path = request.url.path
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        # Chat/question endpoints are read operations via POST — skip auditing.
        if _is_inference_path(request):
            return response

        _, username = _extract_username(request)

        threading.Thread(
            target=_log_to_db,
            args=(username, request.method, path, response.status_code),
            daemon=True,
        ).start()

        return response
