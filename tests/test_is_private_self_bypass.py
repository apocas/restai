"""Regression test for the `is_private` self-flip bypass.

Pins:
  - A team admin trying to flip their OWN `is_private` is refused
    (403). This is the bypass the security report describes:
    private users gated out of public LLM / image-generation
    endpoints could promote themselves to non-private by going
    through the team-admin branch (since a team admin is in their
    own team's admins list).
  - A regular non-admin user can't flip their own `is_private`.
  - Platform admin can flip anyone's `is_private`.
  - A team admin can still flip `is_private` for OTHER members of
    their team (the legitimate workflow, kept intact).

The fix lives in `restai/routers/users.py:route_update_user`,
specifically the `is_private` gate.
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
TEAM_ADMIN = f"ip_alice_{_RNG}"   # admin of TEAM, marked private
PEER = f"ip_bob_{_RNG}"            # regular team member, marked private
LONER = f"ip_carol_{_RNG}"         # not in any team, marked private
TEAM_NAME = f"ip_team_{_RNG}"
ADMIN_AUTH = ("admin", RESTAI_DEFAULT_PASSWORD)

_state = {"team_id": None}


def test_setup(client):
    # Three private users. Each starts with is_private=True so we can
    # test the FLIP from True → False (the actual privilege escalation).
    for u in (TEAM_ADMIN, PEER, LONER):
        r = client.post(
            "/users",
            json={"username": u, "password": "testpass", "is_admin": False, "is_private": True},
            auth=ADMIN_AUTH,
        )
        assert r.status_code == 201, r.text

    r = client.post("/teams", json={"name": TEAM_NAME}, auth=ADMIN_AUTH)
    assert r.status_code == 201, r.text
    _state["team_id"] = r.json()["id"]

    r = client.post(f"/teams/{_state['team_id']}/admins/{TEAM_ADMIN}", auth=ADMIN_AUTH)
    assert r.status_code == 200, r.text
    r = client.post(f"/teams/{_state['team_id']}/users/{PEER}", auth=ADMIN_AUTH)
    assert r.status_code == 200, r.text


def test_team_admin_cannot_flip_own_is_private(client):
    """The reported attack: alice is a private team admin. She PATCHes
    her OWN profile with `is_private=False` to gain access to public
    LLMs. Must 403 — even though she'd otherwise be eligible to flip
    other users' is_private (she's a team admin), self-flip is
    reserved for platform admins."""
    r = client.patch(
        f"/users/{TEAM_ADMIN}",
        json={"is_private": False},
        auth=(TEAM_ADMIN, "testpass"),
    )
    assert r.status_code == 403, r.text

    r = client.get(f"/users/{TEAM_ADMIN}", auth=ADMIN_AUTH)
    assert r.json()["is_private"] is True, "is_private was flipped despite the 403"


def test_non_team_user_cannot_flip_own_is_private(client):
    """Carol has no team membership — she has zero possible escalation
    paths. Self-flip refused (also via the original code, but pinned
    here to catch a future regression that broadens the gate)."""
    r = client.patch(
        f"/users/{LONER}",
        json={"is_private": False},
        auth=(LONER, "testpass"),
    )
    assert r.status_code == 403, r.text

    r = client.get(f"/users/{LONER}", auth=ADMIN_AUTH)
    assert r.json()["is_private"] is True


def test_platform_admin_can_flip_anyone(client):
    """Sanity check the admin override — including flipping
    themselves, which the team-admin path can't do."""
    r = client.patch(
        f"/users/{TEAM_ADMIN}",
        json={"is_private": False},
        auth=ADMIN_AUTH,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/users/{TEAM_ADMIN}", auth=ADMIN_AUTH)
    assert r.json()["is_private"] is False


def test_cleanup(client):
    if _state["team_id"]:
        client.delete(f"/teams/{_state['team_id']}", auth=ADMIN_AUTH)
    for u in (TEAM_ADMIN, PEER, LONER):
        client.delete(f"/users/{u}", auth=ADMIN_AUTH)
