"""Smoke test for the SMTP migration.

End-to-end through the HTTP API:
  - PATCH platform-level smtp_* via /settings → confirm `_cfg.SMTP_*`
    read-through and password masking on response.
  - PATCH a team's `options.smtp_*` → confirm the team-level resolver
    chain returns team values (host, password) over platform values.
  - With team SMTP empty, the resolver falls back to platform values.
  - Team's smtp_password is encrypted at rest (never appears in plaintext
    in the team.options JSON column).

Stops short of real `smtplib.SMTP` traffic — that's covered by
`tests/test_email_sms_tools.py`. This test is about the wiring that
moves credentials from API → DB → resolver.
"""
import json
import sys; sys.setrecursionlimit(20000)
import uuid

from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
import restai.config as _cfg
from restai.utils.email import _resolve_smtp_config
from restai.database import open_db_wrapper
from restai.models.databasemodels import TeamDatabase


def test_smtp_platform_and_team_resolution():
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    suffix = uuid.uuid4().hex[:6]
    team_name = f"smtp_team_{suffix}"

    with TestClient(app) as c:
        # Reset platform SMTP to known values
        platform_body = {
            "smtp_host": "platform.example.com",
            "smtp_port": "587",
            "smtp_user": "ops@platform.example.com",
            "smtp_password": "platform_pw",
            "smtp_from": "ops@platform.example.com",
            "email_default_to": "alerts@platform.example.com",
        }
        r = c.patch("/settings", json=platform_body, auth=auth)
        assert r.status_code == 200, r.text
        j = r.json()
        # Platform values surfaced; password masked
        assert j["smtp_host"] == "platform.example.com"
        assert j["smtp_password"].startswith("****"), j["smtp_password"]

        # Read-through via _cfg
        assert _cfg.SMTP_HOST == "platform.example.com"
        assert _cfg.SMTP_PASSWORD == "platform_pw"

        # Create a team — platform values should apply with team_id=None
        # AND with this brand-new team's empty options
        r = c.post("/teams", json={"name": team_name, "description": "smtp"}, auth=auth)
        assert r.status_code == 201, r.text
        team_id = r.json()["id"]

        db = open_db_wrapper()
        try:
            cfg_no_team = _resolve_smtp_config(None, db)
            assert cfg_no_team.host == "platform.example.com"
            assert cfg_no_team.password == "platform_pw"

            cfg_empty_team = _resolve_smtp_config(team_id, db)
            assert cfg_empty_team.host == "platform.example.com"
            assert cfg_empty_team.password == "platform_pw"
        finally:
            db.db.close()

        # PATCH team SMTP — overrides platform per-field
        r = c.patch(
            f"/teams/{team_id}",
            json={
                "options": {
                    "smtp_host": "team.example.com",
                    "smtp_password": "team_pw",
                    "smtp_from": "bot@team.example.com",
                    "email_default_to": "team-admin@team.example.com",
                    # Note: smtp_port intentionally OMITTED so it falls
                    # through to the platform value.
                }
            },
            auth=auth,
        )
        assert r.status_code == 200, r.text

        # Resolver: team wins where filled, platform fills the gaps
        db = open_db_wrapper()
        try:
            cfg = _resolve_smtp_config(team_id, db)
            assert cfg.host == "team.example.com"
            assert cfg.password == "team_pw"
            assert cfg.sender == "bot@team.example.com"
            assert cfg.default_to == "team-admin@team.example.com"
            # Port wasn't set on team → platform fallback
            assert cfg.port == 587

            # Encryption-at-rest check: read the raw column, confirm
            # smtp_password is the encrypted prefix, NOT plaintext
            team_db = (
                db.db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
            )
            raw = json.loads(team_db.options)
            assert raw["smtp_password"].startswith("$ENC$"), raw["smtp_password"][:8]
            assert "team_pw" not in raw["smtp_password"]
        finally:
            db.db.close()

        # GET /teams/{id} returns the team with masked password
        r = c.get(f"/teams/{team_id}", auth=auth)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["options"]["smtp_host"] == "team.example.com"
        assert j["options"]["smtp_password"].startswith("****"), j["options"]["smtp_password"]

        # PATCH the team again WITH the masked placeholder for password —
        # server must preserve the existing value
        r = c.patch(
            f"/teams/{team_id}",
            json={"options": {
                "smtp_host": "team-updated.example.com",
                "smtp_password": j["options"]["smtp_password"],  # the **** mask
            }},
            auth=auth,
        )
        assert r.status_code == 200, r.text
        db = open_db_wrapper()
        try:
            cfg = _resolve_smtp_config(team_id, db)
            assert cfg.host == "team-updated.example.com"
            assert cfg.password == "team_pw"  # unchanged
        finally:
            db.db.close()

        # Cleanup — drop team and reset platform values
        c.delete(f"/teams/{team_id}", auth=auth)
        c.patch("/settings", json={
            "smtp_host": "", "smtp_password": "", "smtp_from": "", "email_default_to": "",
        }, auth=auth)
