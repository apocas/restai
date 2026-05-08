"""Regression test for the MCP probe RCE attack.

Pins:
  - `POST /tools/mcp/probe` with a stdio host (`/bin/sh`, `/usr/bin/curl`,
    etc.) is rejected as 403 for non-admins.
  - `PATCH /projects/{id}` with `options.mcp_servers[].host = "/bin/sh"`
    is rejected the same way (parallel attack vector through the
    options blob).
  - Admins can still configure stdio transports for legitimate use.
  - Network transports (http/https/sse) work for any authenticated
    user — they don't spawn local processes.

The fix lives in `restai/auth.py:check_user_can_use_mcp_host` and
its two call sites in `restai/routers/tools.py` and
`restai/routers/projects.py`.
"""
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


_RNG = random.randint(0, 1000000)
USER_NORMAL = f"mcp_user_{_RNG}"
USER_ADMIN = "admin"
TEAM_NAME = f"mcp_team_{_RNG}"
PROJECT_NAME = f"mcp_proj_{_RNG}"

_state = {"team_id": None, "project_id": None, "llm_name": None}


def _admin_auth():
    return (USER_ADMIN, RESTAI_DEFAULT_PASSWORD)


def _user_auth():
    return (USER_NORMAL, "testpass")


# ─── Setup ──────────────────────────────────────────────────────────────


def test_setup(client):
    # Non-admin user
    r = client.post(
        "/users",
        json={"username": USER_NORMAL, "password": "testpass", "admin": False, "private": False},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text

    # Need a team + LLM + agent project so the user can hit
    # /projects/{id} legitimately and we can attempt the parallel
    # PATCH attack against `options.mcp_servers`.
    r = client.post("/teams", json={"name": TEAM_NAME}, auth=_admin_auth())
    assert r.status_code == 201, r.text
    _state["team_id"] = r.json()["id"]

    # Add user as a team member so they can edit project options.
    r = client.post(f"/teams/{_state['team_id']}/users/{USER_NORMAL}", auth=_admin_auth())
    assert r.status_code == 200, r.text

    # An LLM bound to the team is needed for the agent project to validate.
    llm_name = f"mcp_llm_{_RNG}"
    r = client.post(
        "/llms",
        json={"name": llm_name, "class_name": "OpenAI",
              "options": {"model": "gpt-test", "api_key": "sk-fake"},
              "privacy": "public"},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text
    _state["llm_name"] = llm_name
    r = client.post(f"/teams/{_state['team_id']}/llms/{r.json()['id']}", auth=_admin_auth())
    assert r.status_code == 200, r.text

    r = client.post(
        "/projects",
        json={"name": PROJECT_NAME, "type": "agent", "llm": llm_name, "team_id": _state["team_id"]},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text
    _state["project_id"] = r.json()["project"]

    # Add the non-admin user directly to the project so they can PATCH it.
    r = client.patch(
        f"/projects/{_state['project_id']}",
        json={"users": [USER_NORMAL]},
        auth=_admin_auth(),
    )
    assert r.status_code == 200, r.text


# ─── Negative: stdio transport blocked for non-admins ──────────────────


@pytest.mark.parametrize("payload", [
    {"host": "/bin/sh", "args": ["-c", "id"]},
    {"host": "/usr/bin/curl", "args": ["-o", "/tmp/x", "http://example.com"]},
    {"host": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
    {"host": "uvx", "args": ["some-mcp-package"]},
    {"host": "python", "args": ["-m", "some.module"]},
])
def test_probe_stdio_blocked_for_non_admin(client, payload):
    """The reported RCE primitive: any authenticated user could
    POST /tools/mcp/probe with a local executable as the host. Now
    refused with 403 unless the caller is a platform admin."""
    r = client.post("/tools/mcp/probe", json=payload, auth=_user_auth())
    assert r.status_code == 403, (
        f"stdio MCP transport leaked through probe for non-admin "
        f"(payload={payload}, status={r.status_code}, body={r.text[:200]})"
    )
    assert "admin" in (r.json().get("detail") or "").lower()


def test_patch_project_stdio_mcp_blocked_for_non_admin(client):
    """Parallel attack vector: a non-admin couldn't trigger the
    probe, but COULD save a stdio mcp_servers entry on a project
    they're a member of, then trigger it implicitly on the next
    chat. Now refused at PATCH time."""
    r = client.patch(
        f"/projects/{_state['project_id']}",
        json={
            "options": {
                "mcp_servers": [
                    {"host": "/bin/sh", "args": ["-c", "id"], "env": {}, "headers": None}
                ],
            },
        },
        auth=_user_auth(),
    )
    assert r.status_code == 403, (
        f"stdio MCP transport leaked through project PATCH for non-admin "
        f"(status={r.status_code}, body={r.text[:200]})"
    )

    # Confirm not persisted.
    r = client.get(f"/projects/{_state['project_id']}", auth=_admin_auth())
    opts = r.json().get("options") or {}
    saved = opts.get("mcp_servers") or []
    assert all(s.get("host") != "/bin/sh" for s in saved), (
        "stdio mcp_servers entry was persisted despite the 403"
    )


# ─── Positive: network transports + admin stdio still work ─────────────


@pytest.mark.parametrize("host", [
    "http://example.com/mcp",
    "https://example.com/mcp",
    "sse://example.com/mcp",
])
def test_probe_network_transport_allowed_for_non_admin(client, host):
    """Non-admins can still use network MCP transports — those don't
    spawn local processes. The probe will fail to actually reach
    example.com (502) but the auth gate must let it through."""
    r = client.post("/tools/mcp/probe", json={"host": host}, auth=_user_auth())
    # 502 = network reach failed, 200 = unexpected success against a
    # captive portal, 400 = upstream protocol mismatch — all of
    # these prove the auth gate passed. A 403 would prove regression.
    assert r.status_code != 403, (
        f"network MCP transport falsely blocked for non-admin "
        f"(host={host}, status={r.status_code}, body={r.text[:200]})"
    )


def test_probe_stdio_allowed_for_admin(client):
    """Platform admins keep their existing stdio access. The probe
    will fail to reach an actual MCP server (502 wrapping a process
    error), but the auth gate must let it through."""
    r = client.post(
        "/tools/mcp/probe",
        json={"host": "true", "args": []},
        auth=_admin_auth(),
    )
    assert r.status_code != 403, r.text


# ─── Cleanup ──────────────────────────────────────────────────────────


def test_cleanup(client):
    if _state["project_id"]:
        client.delete(f"/projects/{_state['project_id']}", auth=_admin_auth())
    if _state["llm_name"]:
        client.delete(f"/llms/{_state['llm_name']}", auth=_admin_auth())
    if _state["team_id"]:
        client.delete(f"/teams/{_state['team_id']}", auth=_admin_auth())
    client.delete(f"/users/{USER_NORMAL}", auth=_admin_auth())
