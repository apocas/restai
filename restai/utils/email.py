"""Central SMTP send helper.

One sender for the whole platform. Resolves SMTP config in this order:

    team.options.<smtp_*>   (per-team override)
        ↓ fall through on missing fields
    restai.config.SMTP_*    (platform-level GUI setting, DB read-through)

Returns ``(ok, detail)`` so callers (LLM tool, future routine /
webhook / eval senders) decide whether to bubble the error or swallow
it. Pure stdlib — no extra dependency.

Per CLAUDE.md, settings are DB read-through; using ``import
restai.config as _cfg`` keeps this module multi-worker-correct, since
no in-process mirror exists.
"""
from __future__ import annotations

import json
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional, Tuple

import restai.config as _cfg

logger = logging.getLogger(__name__)


@dataclass
class _SmtpConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    default_to: str = ""


def _coalesce(*values) -> str:
    """Return the first non-empty value, else ``""``."""
    for v in values:
        if v not in (None, ""):
            return v
    return ""


def _team_options(team_id: Optional[int], db) -> dict:
    """Return decrypted ``team.options`` as a plain dict, or ``{}``.

    Used internally — never passes the dict back through Pydantic, so
    secrets stay plaintext for the SMTP login but never enter any API
    response."""
    if team_id is None or db is None:
        return {}
    try:
        team_db = db.get_team_by_id(int(team_id))
    except Exception:
        return {}
    if team_db is None or not team_db.options:
        return {}
    try:
        opts = json.loads(team_db.options)
    except Exception:
        return {}
    if not isinstance(opts, dict):
        return {}
    try:
        from restai.utils.crypto import decrypt_sensitive_options, TEAM_SENSITIVE_KEYS
        opts = decrypt_sensitive_options(opts, TEAM_SENSITIVE_KEYS)
    except Exception:
        # Decryption failure shouldn't crash the call — the resolver
        # will see the still-encrypted password and the SMTP login will
        # fail with a clear error from the server, surfaced to the
        # caller via _send().
        pass
    return opts


def _resolve_smtp_config(team_id: Optional[int], db) -> _SmtpConfig:
    """Per-field fallback team → platform. A team that fills only
    `smtp_host` and `smtp_from` (but reuses platform user/password)
    works because each field is resolved independently."""
    team = _team_options(team_id, db)

    raw_port = _coalesce(team.get("smtp_port"), _cfg.SMTP_PORT, "587")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 587

    user = _coalesce(team.get("smtp_user"), _cfg.SMTP_USER)
    return _SmtpConfig(
        host=_coalesce(team.get("smtp_host"), _cfg.SMTP_HOST),
        port=port,
        user=user,
        password=_coalesce(team.get("smtp_password"), _cfg.SMTP_PASSWORD),
        # Sender falls back to the SMTP user (most relays require From
        # to match the authenticated identity anyway).
        sender=_coalesce(team.get("smtp_from"), _cfg.SMTP_FROM, user),
        default_to=_coalesce(team.get("email_default_to"), _cfg.EMAIL_DEFAULT_TO),
    )


def send_email(
    *,
    subject: str,
    body: str,
    to: Optional[str] = None,
    team_id: Optional[int] = None,
    db=None,
) -> Tuple[bool, str]:
    """Send a plain-text email.

    Resolves SMTP from the supplied team's options first, then the
    platform-level GUI settings. ``to`` falls back to the team /
    platform ``email_default_to``.

    Returns ``(ok, detail)``. ``detail`` is a short human-readable
    string suitable for logs or LLM tool output (never includes the
    password). Never raises.
    """
    cfg = _resolve_smtp_config(team_id, db)

    if not cfg.host:
        return (False, "SMTP not configured (set host in team Integrations or platform Notifications)")
    if not cfg.sender:
        return (False, "SMTP not configured (no From address — set smtp_from at team or platform level)")

    recipient = to or cfg.default_to
    if not recipient:
        return (False, "no recipient (provide `to` or set email_default_to at team/platform level)")

    msg = EmailMessage()
    msg["Subject"] = subject or "(no subject)"
    msg["From"] = cfg.sender
    msg["To"] = recipient
    msg.set_content(body or "")

    try:
        # Port 465 = implicit TLS (SMTPS). Anything else = STARTTLS on
        # a plaintext socket, with a graceful fall-through for local
        # relays that don't offer it (admin chose the host knowingly).
        if cfg.port == 465:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15) as s:
                if cfg.user and cfg.password:
                    s.login(cfg.user, cfg.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as s:
                s.ehlo()
                try:
                    s.starttls()
                    s.ehlo()
                except smtplib.SMTPNotSupportedError:
                    pass
                if cfg.user and cfg.password:
                    s.login(cfg.user, cfg.password)
                s.send_message(msg)
    except Exception as e:
        # smtplib's exception text frequently includes the user; the
        # password is never echoed back by servers, but be defensive
        # anyway and never include cfg.password in the returned string.
        logger.warning("SMTP send failed via %s:%s — %s", cfg.host, cfg.port, e)
        return (False, f"SMTP send failed: {e}")

    return (True, f"email sent to {recipient}")
