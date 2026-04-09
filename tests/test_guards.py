"""Tests for the guardrail system — guard events, analytics endpoints, and guard parsing."""

import random
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.guard import Guard, GuardResult

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
team_name = f"guard_team_{suffix}"
llm_name = f"guard_llm_{suffix}"
project_name = f"guard-proj-{suffix}"

team_id = None
project_id = None


def test_guard_setup():
    """Create team, LLM, and project for guard tests."""
    global team_id, project_id

    with TestClient(app) as client:
        r = client.post(
            "/llms",
            json={
                "name": llm_name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
            },
            auth=ADMIN,
        )
        assert r.status_code in (200, 201)

        r = client.post(
            "/teams",
            json={"name": team_name, "llms": [llm_name]},
            auth=ADMIN,
        )
        assert r.status_code == 201
        team_id = r.json()["id"]

        # Create a block project (no LLM needed, easy to test)
        r = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert r.status_code == 201
        project_id = r.json()["project"]


# ── Guard response parsing tests ─────────────────────────────────────────


def test_guard_parse_block_keywords():
    """Guard should block on known block keywords."""
    for word in ["BAD", "NO", "FALSE", "DENY", "BLOCK", "REJECT", "UNSAFE", "NOK"]:
        assert Guard._parse_response(word) is True, f"Expected block for '{word}'"
        assert Guard._parse_response(word.lower()) is True, f"Expected block for '{word.lower()}'"


def test_guard_parse_allow_keywords():
    """Guard should allow on known allow keywords."""
    for word in ["GOOD", "OK", "YES", "TRUE", "ALLOW", "PASS", "SAFE", "APPROVE"]:
        assert Guard._parse_response(word) is False, f"Expected allow for '{word}'"
        assert Guard._parse_response(word.lower()) is False, f"Expected allow for '{word.lower()}'"


def test_guard_parse_first_line_only():
    """Guard should only check the first line of the response."""
    assert Guard._parse_response("SAFE\nBut this line says BAD") is False
    assert Guard._parse_response("BLOCK\nBut this line says OK") is True


def test_guard_parse_keyword_in_text():
    """Guard should detect keywords within longer text."""
    assert Guard._parse_response("This content is UNSAFE for users") is True
    assert Guard._parse_response("The content is SAFE and appropriate") is False


def test_guard_parse_unknown_defaults_to_block():
    """Unknown responses should default to block (fail-safe)."""
    assert Guard._parse_response("I'm not sure about this") is True
    assert Guard._parse_response("Maybe") is True
    assert Guard._parse_response("") is True


def test_guard_result_dataclass():
    """GuardResult should store blocked status and raw response."""
    r = GuardResult(blocked=True, raw_response="DENY - harmful content")
    assert r.blocked is True
    assert r.raw_response == "DENY - harmful content"

    r2 = GuardResult(blocked=False, raw_response="SAFE")
    assert r2.blocked is False


# ── Guard configuration tests ────────────────────────────────────────────


def test_guard_output_option():
    """guard_output and guard_mode should be settable via project options."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{project_id}",
            json={
                "options": {
                    "guard_output": "some-guard-project",
                    "guard_mode": "warn",
                },
            },
            auth=ADMIN,
        )
        assert r.status_code == 200

        r = client.get(f"/projects/{project_id}", auth=ADMIN)
        assert r.status_code == 200
        opts = r.json().get("options", {})
        assert opts.get("guard_output") == "some-guard-project"
        assert opts.get("guard_mode") == "warn"

        # Reset
        r = client.patch(
            f"/projects/{project_id}",
            json={"options": {"guard_output": None, "guard_mode": "block"}},
            auth=ADMIN,
        )
        assert r.status_code == 200


# ── Guard analytics endpoint tests ───────────────────────────────────────


def test_guard_summary_empty():
    """Guard summary should return zeros when no events exist."""
    with TestClient(app) as client:
        r = client.get(f"/projects/{project_id}/guards/summary", auth=ADMIN)
        assert r.status_code == 200
        data = r.json()
        assert data["total_checks"] == 0
        assert data["total_blocks"] == 0
        assert data["block_rate"] == 0
        assert data["warn_count"] == 0


def test_guard_daily_empty():
    """Guard daily should return empty events when no data."""
    with TestClient(app) as client:
        r = client.get(f"/projects/{project_id}/guards/daily", auth=ADMIN)
        assert r.status_code == 200
        assert "events" in r.json()


def test_guard_events_empty():
    """Guard events should return empty list when no events."""
    with TestClient(app) as client:
        r = client.get(f"/projects/{project_id}/guards/events", auth=ADMIN)
        assert r.status_code == 200
        data = r.json()
        assert data["events"] == []
        assert data["total"] == 0


def test_guard_log_and_query():
    """Manually log guard events and verify they appear in analytics."""
    from restai.database import get_db_wrapper
    from restai.models.databasemodels import GuardEventDatabase

    db = get_db_wrapper()
    try:
        # Insert test events
        for action in ["block", "pass", "block", "warn"]:
            event = GuardEventDatabase(
                project_id=project_id,
                guard_project="test-guard",
                user_id=None,
                phase="input",
                action=action,
                mode="block" if action != "warn" else "warn",
                text_checked="test question",
                guard_response="TEST",
                date=datetime.now(timezone.utc),
            )
            db.db.add(event)
        # Add an output block
        event = GuardEventDatabase(
            project_id=project_id,
            guard_project="test-guard",
            user_id=None,
            phase="output",
            action="block",
            mode="block",
            text_checked="test answer",
            guard_response="UNSAFE",
            date=datetime.now(timezone.utc),
        )
        db.db.add(event)
        db.db.commit()
    finally:
        db.db.close()

    with TestClient(app) as client:
        # Summary
        r = client.get(f"/projects/{project_id}/guards/summary", auth=ADMIN)
        assert r.status_code == 200
        data = r.json()
        assert data["total_checks"] == 5
        assert data["total_blocks"] == 3
        assert data["warn_count"] == 1
        assert data["input_blocks"] >= 2
        assert data["output_blocks"] >= 1
        assert data["block_rate"] > 0

        # Daily
        r = client.get(f"/projects/{project_id}/guards/daily", auth=ADMIN)
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) > 0
        assert events[0]["checks"] > 0

        # Events (all)
        r = client.get(f"/projects/{project_id}/guards/events", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["total"] == 5

        # Events filtered by action
        r = client.get(f"/projects/{project_id}/guards/events?action=block", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["total"] == 3

        # Events filtered by phase
        r = client.get(f"/projects/{project_id}/guards/events?phase=output", auth=ADMIN)
        assert r.status_code == 200
        assert r.json()["total"] == 1


# ── Teardown ─────────────────────────────────────────────────────────────


def test_guard_teardown():
    """Clean up resources."""
    # Clean up guard events first
    from restai.database import get_db_wrapper
    from restai.models.databasemodels import GuardEventDatabase

    db = get_db_wrapper()
    try:
        db.db.query(GuardEventDatabase).filter(
            GuardEventDatabase.project_id == project_id
        ).delete()
        db.db.commit()
    finally:
        db.db.close()

    with TestClient(app) as client:
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
