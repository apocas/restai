"""Cross-team resource attachment tests.

Pin the fix for the privilege-escalation bug where a team admin of
team A could attach team B's private LLM (or embedding, or project)
to team A and consume it under team B's credentials.

The fix lives in:

- `restai/auth.py` — `check_user_can_attach_{project,llm,embedding}`
- `restai/routers/teams.py` — three per-endpoint guards
- `restai/database.py:update_team_members` — same guards on the
  PATCH-batch path so a single payload can't bypass them

These tests exercise both paths plus the legitimate "I'm admin of
both teams" workflow.
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


# Shared module state so test functions can chain. Test runner is in
# declaration order, so setup → negatives → positives → cleanup.
_RNG = random.randint(0, 1000000)
TEAM_A = f"xt_team_a_{_RNG}"
TEAM_B = f"xt_team_b_{_RNG}"
ALICE = f"xt_alice_{_RNG}"   # admin of A only (the attacker)
BOB = f"xt_bob_{_RNG}"        # admin of B only
LLM_B = f"xt_llm_b_{_RNG}"
EMB_B = f"xt_emb_b_{_RNG}"
PRJ_B = f"xt_prj_b_{_RNG}"

_state = {
    "team_a_id": None,
    "team_b_id": None,
    "llm_b_id": None,
    "emb_b_id": None,
    "prj_b_id": None,
}


def _admin_auth():
    return ("admin", RESTAI_DEFAULT_PASSWORD)


def _alice_auth():
    return (ALICE, "testpass")


# ─── Setup ──────────────────────────────────────────────────────────────


def test_setup_users(client):
    for username in (ALICE, BOB):
        r = client.post(
            "/users",
            json={"username": username, "password": "testpass", "admin": False, "private": False},
            auth=_admin_auth(),
        )
        assert r.status_code == 201, r.text


def test_setup_teams(client):
    for slot, name in (("team_a_id", TEAM_A), ("team_b_id", TEAM_B)):
        r = client.post("/teams", json={"name": name}, auth=_admin_auth())
        assert r.status_code == 201, r.text
        _state[slot] = r.json()["id"]

    # Make ALICE admin of A only; BOB admin of B only.
    r = client.post(f"/teams/{_state['team_a_id']}/admins/{ALICE}", auth=_admin_auth())
    assert r.status_code == 200, r.text
    r = client.post(f"/teams/{_state['team_b_id']}/admins/{BOB}", auth=_admin_auth())
    assert r.status_code == 200, r.text


def test_setup_team_b_resources(client):
    """LLM/embedding/project created globally then bound to team B
    only. From the attacker's perspective these are "team B's
    resources" — no team A admin should be able to attach them."""
    r = client.post(
        "/llms",
        json={"name": LLM_B, "class_name": "OpenAI",
              "options": {"model": "gpt-test", "api_key": "sk-fake"},
              "privacy": "public"},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text
    _state["llm_b_id"] = r.json()["id"]

    r = client.post(
        "/embeddings",
        json={"name": EMB_B, "class_name": "Ollama",
              "options": "{}", "privacy": "public", "dimension": 768},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text
    _state["emb_b_id"] = r.json()["id"]

    # Bind the LLM/embedding to team B (and only team B).
    r = client.post(f"/teams/{_state['team_b_id']}/llms/{_state['llm_b_id']}", auth=_admin_auth())
    assert r.status_code == 200, r.text
    r = client.post(f"/teams/{_state['team_b_id']}/embeddings/{_state['emb_b_id']}", auth=_admin_auth())
    assert r.status_code == 200, r.text

    # Create a project owned by team B. Needs the team to have at least
    # one LLM (which we just attached).
    r = client.post(
        "/projects",
        json={"name": PRJ_B, "type": "agent", "llm": LLM_B, "team_id": _state["team_b_id"]},
        auth=_admin_auth(),
    )
    assert r.status_code == 201, r.text
    # Endpoint returns `{"project": <id>}`.
    _state["prj_b_id"] = r.json()["project"]


# ─── Negative: per-endpoint cross-team attach ──────────────────────────
# Alice is admin of team A only. She tries to attach team-B-owned
# resources to team A and gets 403 each time. State unchanged after.


def test_alice_cannot_attach_team_b_llm(client):
    r = client.post(
        f"/teams/{_state['team_a_id']}/llms/{_state['llm_b_id']}",
        auth=_alice_auth(),
    )
    assert r.status_code == 403, r.text

    # Confirm not attached.
    r = client.get(f"/teams/{_state['team_a_id']}", auth=_admin_auth())
    assert r.status_code == 200
    llm_names = [(l["name"] if isinstance(l, dict) else l) for l in (r.json().get("llms") or [])]
    assert LLM_B not in llm_names


def test_alice_cannot_attach_team_b_embedding(client):
    r = client.post(
        f"/teams/{_state['team_a_id']}/embeddings/{_state['emb_b_id']}",
        auth=_alice_auth(),
    )
    assert r.status_code == 403, r.text

    r = client.get(f"/teams/{_state['team_a_id']}", auth=_admin_auth())
    emb_names = [(e["name"] if isinstance(e, dict) else e) for e in (r.json().get("embeddings") or [])]
    assert EMB_B not in emb_names


def test_alice_cannot_attach_team_b_project(client):
    r = client.post(
        f"/teams/{_state['team_a_id']}/projects/{_state['prj_b_id']}",
        auth=_alice_auth(),
    )
    assert r.status_code == 403, r.text

    r = client.get(f"/teams/{_state['team_a_id']}", auth=_admin_auth())
    prj_names = [(p["name"] if isinstance(p, dict) else p) for p in (r.json().get("projects") or [])]
    assert PRJ_B not in prj_names


# ─── Negative: PATCH-batch attack (the parallel hole) ──────────────────


def test_alice_cannot_attach_team_b_via_patch_batch(client):
    """Same attack vector through the batch-update endpoint. Without
    the `caller=` hook in `update_team_members`, this would silently
    rewrite team A's allow-list to include team B's resources."""
    r = client.patch(
        f"/teams/{_state['team_a_id']}",
        json={
            "llms": [LLM_B],
            "embeddings": [EMB_B],
            "projects": [PRJ_B],
        },
        auth=_alice_auth(),
    )
    assert r.status_code == 403, r.text

    # State should be unchanged — no half-rebuild allowed.
    r = client.get(f"/teams/{_state['team_a_id']}", auth=_admin_auth())
    j = r.json()
    llm_names = [(l["name"] if isinstance(l, dict) else l) for l in (j.get("llms") or [])]
    emb_names = [(e["name"] if isinstance(e, dict) else e) for e in (j.get("embeddings") or [])]
    prj_names = [(p["name"] if isinstance(p, dict) else p) for p in (j.get("projects") or [])]
    assert LLM_B not in llm_names
    assert EMB_B not in emb_names
    assert PRJ_B not in prj_names


# ─── Positive: multi-team admin can move resources across their own teams


def test_multi_team_admin_can_attach(client):
    """Make Alice an admin of team B too; she can now attach team B's
    LLM/embedding to team A. This is the legitimate UX the fix must
    preserve."""
    r = client.post(f"/teams/{_state['team_b_id']}/admins/{ALICE}", auth=_admin_auth())
    assert r.status_code == 200, r.text

    r = client.post(
        f"/teams/{_state['team_a_id']}/llms/{_state['llm_b_id']}",
        auth=_alice_auth(),
    )
    assert r.status_code == 200, r.text

    r = client.post(
        f"/teams/{_state['team_a_id']}/embeddings/{_state['emb_b_id']}",
        auth=_alice_auth(),
    )
    assert r.status_code == 200, r.text


# ─── Positive: platform admin bypasses ────────────────────────────────
# Already covered implicitly by the existing `tests/test_teams.py` happy
# path (which runs as admin), but worth a tight assertion here.


def test_platform_admin_bypasses(client):
    r = client.post(
        f"/teams/{_state['team_a_id']}/projects/{_state['prj_b_id']}",
        auth=_admin_auth(),
    )
    # 200 = transferred. The project's team_id is now team A.
    assert r.status_code == 200, r.text


# ─── Cleanup ──────────────────────────────────────────────────────────


def test_cleanup(client):
    # Clean up in dependency order.
    if _state["prj_b_id"]:
        client.delete(f"/projects/{_state['prj_b_id']}", auth=_admin_auth())
    if _state["llm_b_id"]:
        client.delete(f"/llms/{_state['llm_b_id']}", auth=_admin_auth())
    if _state["emb_b_id"]:
        client.delete(f"/embeddings/{_state['emb_b_id']}", auth=_admin_auth())
    if _state["team_a_id"]:
        client.delete(f"/teams/{_state['team_a_id']}", auth=_admin_auth())
    if _state["team_b_id"]:
        client.delete(f"/teams/{_state['team_b_id']}", auth=_admin_auth())
    for username in (ALICE, BOB):
        client.delete(f"/users/{username}", auth=_admin_auth())
