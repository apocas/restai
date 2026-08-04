"""Shared helpers for the browser_* builtin tools.

All nine tools bottleneck through `_browser_ctx(kwargs)` which:
- Validates the agent has project context (`_project_id`, `_brain`, `_chat_id`).
- Checks the admin-enabled flag (`BrowserManager` is not None).
- Surfaces a friendly error string otherwise.

Tools also reuse `_check_allowed_domain(project, url)` for `browser_goto`.
"""
from __future__ import annotations

import logging
import re
from uuid import uuid4 as _uuid4
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _browser_ctx(kwargs: dict):
    """Resolve (brain, chat_id, project_id, project_db_row). Returns None
    on misconfig + an error string to hand back to the agent."""
    brain = kwargs.get("_brain")
    chat_id = kwargs.get("_chat_id")
    project_id = kwargs.get("_project_id")

    if not brain:
        return None, "ERROR: browser tool requires an agent context."
    if project_id is None:
        return None, "ERROR: browser tool requires a project context."
    if not getattr(brain, "browser_manager", None):
        return None, (
            "ERROR: Agentic Browser is not enabled. Ask an admin to turn it on "
            "in Settings → Agentic Browser."
        )

    from restai.database import open_db_wrapper
    db = open_db_wrapper()
    try:
        project = db.get_project_by_id(int(project_id))
    except Exception:
        project = None
    if project is None:
        db.db.close()
        return None, f"ERROR: project {project_id} not found."

    return (brain, chat_id or f"ephemeral-{_uuid4().hex}", int(project_id), project, db), None


def _parse_allowed_domains(project) -> list[str]:
    raw = ""
    try:
        opts_json = project.options or "{}"
        import json as _json
        opts = _json.loads(opts_json)
        raw = (opts.get("browser_allowed_domains") or "").strip()
    except Exception:
        return []
    if not raw:
        return []
    return [d.strip().lower() for d in re.split(r"[,;\s]+", raw) if d.strip()]


def _check_allowed_domain(project, url: str) -> Optional[str]:
    """Returns an error string if the URL is blocked, or None when allowed."""
    # Unconditional SSRF gate, applied BEFORE (and independently of) the
    # allowlist. An empty `browser_allowed_domains` means "any public site" —
    # it never meant "including 169.254.169.254 and everything on the LAN".
    # crawler_classic and _sync_url are guarded; this path was not, so an agent
    # could read cloud metadata through its own browser.
    try:
        parsed = urlparse(url)
    except Exception:
        return f"ERROR: invalid URL: {url}"
    if parsed.scheme not in ("http", "https"):
        return f"ERROR: only http(s) URLs can be browsed (got {parsed.scheme!r})."
    try:
        from restai.helper import is_blocked_network_host
        if is_blocked_network_host(url):
            return (
                f"ERROR: refusing to browse to internal or unresolvable host "
                f"{parsed.hostname!r}."
            )
    except Exception:
        return f"ERROR: could not validate host for {url}"

    allowed = _parse_allowed_domains(project)
    if not allowed:
        # Empty allowlist = any public site (admin choice; risky but explicit).
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return f"ERROR: URL has no host: {url}"
    for pattern in allowed:
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if host == suffix or host.endswith("." + suffix):
                return None
        elif host == pattern or host.endswith("." + pattern):
            return None
    return (
        f"ERROR: domain {host!r} is not in this project's browser_allowed_domains "
        f"(allowed: {', '.join(allowed)})."
    )


def _browser_allow_eval(project) -> bool:
    try:
        import json as _json
        opts = _json.loads(project.options or "{}")
        return bool(opts.get("browser_allow_eval", False))
    except Exception:
        return False
