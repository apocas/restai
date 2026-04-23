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

    from restai.database import get_db_wrapper
    db = get_db_wrapper()
    try:
        project = db.get_project_by_id(int(project_id))
    except Exception:
        project = None
    if project is None:
        db.db.close()
        return None, f"ERROR: project {project_id} not found."

    return (brain, chat_id or "ephemeral", int(project_id), project, db), None


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
    allowed = _parse_allowed_domains(project)
    if not allowed:
        # Empty allowlist = unrestricted (admin choice, risky but explicit).
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return f"ERROR: invalid URL: {url}"
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
