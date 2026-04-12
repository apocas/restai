"""Tests that restricted users cannot modify team resources."""
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"rt_team_{suffix}"
restricted_user = f"rt_restricted_{suffix}"
team_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team and restricted user who is a team admin."""
    global team_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)

    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]

    client.post("/users", json={"username": restricted_user, "password": "pass123", "admin": False, "private": False, "is_restricted": True}, auth=auth)
    client.post(f"/teams/{team_id}/users/{restricted_user}", auth=auth)
    client.post(f"/teams/{team_id}/admins/{restricted_user}", auth=auth)


def test_restricted_cannot_create_team(client):
    """Restricted user cannot create a team (also not admin, so 403)."""
    resp = client.post("/teams", json={"name": f"rt_new_{suffix}"}, auth=(restricted_user, "pass123"))
    assert resp.status_code in (403, 404)


def test_restricted_cannot_update_team(client):
    """Restricted team admin cannot update team."""
    resp = client.patch(f"/teams/{team_id}", json={"name": f"rt_renamed_{suffix}"}, auth=(restricted_user, "pass123"))
    assert resp.status_code == 403


def test_restricted_cannot_add_user_to_team(client):
    """Restricted team admin cannot add users."""
    resp = client.post(f"/teams/{team_id}/users/admin", auth=(restricted_user, "pass123"))
    assert resp.status_code == 403


def test_restricted_cannot_remove_user_from_team(client):
    """Restricted team admin cannot remove users."""
    resp = client.delete(f"/teams/{team_id}/users/admin", auth=(restricted_user, "pass123"))
    assert resp.status_code == 403


def test_restricted_cannot_send_team_invitation(client):
    """Restricted team admin cannot send team invitations."""
    resp = client.post(f"/teams/{team_id}/invitations", json={"username": "admin"}, auth=(restricted_user, "pass123"))
    assert resp.status_code == 403


def test_cleanup(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/teams/{team_id}", auth=auth)
    client.delete(f"/users/{restricted_user}", auth=auth)
