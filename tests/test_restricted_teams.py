"""Tests that restricted users cannot modify team resources."""
import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"rt_team_{suffix}"
restricted_user = f"rt_restricted_{suffix}"
team_id = None


def test_setup():
    """Create team and restricted user who is a team admin."""
    global team_id
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)

        resp = client.post("/teams", json={"name": team_name}, auth=auth)
        assert resp.status_code in (200, 201)
        team_id = resp.json()["id"]

        client.post("/users", json={"username": restricted_user, "password": "pass123", "admin": False, "private": False, "is_restricted": True}, auth=auth)
        client.post(f"/teams/{team_id}/users/{restricted_user}", auth=auth)
        client.post(f"/teams/{team_id}/admins/{restricted_user}", auth=auth)


def test_restricted_cannot_create_team():
    """Restricted user cannot create a team (also not admin, so 403)."""
    with TestClient(app) as client:
        resp = client.post("/teams", json={"name": f"rt_new_{suffix}"}, auth=(restricted_user, "pass123"))
        assert resp.status_code in (403, 404)


def test_restricted_cannot_update_team():
    """Restricted team admin cannot update team."""
    with TestClient(app) as client:
        resp = client.patch(f"/teams/{team_id}", json={"name": f"rt_renamed_{suffix}"}, auth=(restricted_user, "pass123"))
        assert resp.status_code == 403


def test_restricted_cannot_add_user_to_team():
    """Restricted team admin cannot add users."""
    with TestClient(app) as client:
        resp = client.post(f"/teams/{team_id}/users/admin", auth=(restricted_user, "pass123"))
        assert resp.status_code == 403


def test_restricted_cannot_remove_user_from_team():
    """Restricted team admin cannot remove users."""
    with TestClient(app) as client:
        resp = client.delete(f"/teams/{team_id}/users/admin", auth=(restricted_user, "pass123"))
        assert resp.status_code == 403


def test_restricted_cannot_send_team_invitation():
    """Restricted team admin cannot send team invitations."""
    with TestClient(app) as client:
        resp = client.post(f"/teams/{team_id}/invitations", json={"username": "admin"}, auth=(restricted_user, "pass123"))
        assert resp.status_code == 403


def test_cleanup():
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        client.delete(f"/teams/{team_id}", auth=auth)
        client.delete(f"/users/{restricted_user}", auth=auth)
