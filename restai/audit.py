"""Audit logging middleware — records all mutation requests (POST/PATCH/DELETE)."""

import base64
import logging
import threading
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Paths to skip auditing (health checks, auth, static, read-heavy endpoints)
SKIP_PREFIXES = ("/setup", "/version", "/info", "/auth", "/admin", "/mcp", "/v1")

# Only audit mutation methods
AUDIT_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _extract_username(request: Request) -> tuple:
    """Extract user_id and username from the Authorization header without DB lookup."""
    auth_header = request.headers.get("authorization", "")

    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username = decoded.split(":")[0]
            return None, username
        except Exception:
            pass

    if auth_header.startswith("Bearer "):
        # Can't resolve username from Bearer without DB lookup — mark as API key
        return None, "(api_key)"

    # Check for JWT cookie
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
    """Write audit entry to database in a background thread."""
    try:
        from restai.database import get_db_wrapper
        from restai.models.databasemodels import AuditLogDatabase

        db = get_db_wrapper()
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

        # Only audit mutations
        if request.method not in AUDIT_METHODS:
            return response

        # Skip non-API paths
        path = request.url.path
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        # Skip chat/question endpoints (these are read operations via POST)
        if "/chat" in path or "/question" in path:
            return response

        # Extract user identity
        _, username = _extract_username(request)

        # Log in background thread to avoid blocking the response
        threading.Thread(
            target=_log_to_db,
            args=(username, request.method, path, response.status_code),
            daemon=True,
        ).start()

        return response
