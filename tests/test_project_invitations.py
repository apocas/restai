import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"inv_team_{suffix}"
project_name = f"inv_project_{suffix}"
user_in_team = f"inv_user_{suffix}"
user_outside = f"inv_outsider_{suffix}"

team_id = None
project_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, project, and users for invite tests."""
    global team_id, project_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)

    # Create team
    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]

    # Create user in team
    client.post("/users", json={"username": user_in_team, "password": "pass123", "admin": False, "private": False}, auth=auth)
    client.post(f"/teams/{team_id}/users/{user_in_team}", auth=auth)

    # Create user outside team
    client.post("/users", json={"username": user_outside, "password": "pass123", "admin": False, "private": False}, auth=auth)

    # Create project in team (block type needs no LLM)
    resp = client.post("/projects", json={"name": project_name, "type": "block", "team_id": team_id}, auth=auth)
    assert resp.status_code == 201
    project_id = resp.json()["project"]


def test_send_invite_to_team_member(client):
    """Sending invite to a user in the same team succeeds."""
    resp = client.post(
        f"/projects/{project_id}/invitations",
        json={"username": user_in_team},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    assert "invitation" in resp.json()["message"].lower() or "user" in resp.json()["message"].lower()


def test_send_invite_to_outsider(client):
    """Sending invite to user not in team returns same message (no info leak)."""
    resp = client.post(
        f"/projects/{project_id}/invitations",
        json={"username": user_outside},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    # Same response regardless
    assert "message" in resp.json()


def test_send_invite_nonexistent_user(client):
    """Sending invite to nonexistent user returns same message."""
    resp = client.post(
        f"/projects/{project_id}/invitations",
        json={"username": "definitely_not_a_user_xyz"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    assert "message" in resp.json()


def test_duplicate_invite_not_created(client):
    """Sending the same invite twice should not create a duplicate."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    # First invite already sent in test_send_invite_to_team_member
    # Send again
    client.post(f"/projects/{project_id}/invitations", json={"username": user_in_team}, auth=auth)

    # Check only 1 pending invite
    resp = client.get("/invitations", auth=(user_in_team, "pass123"))
    assert resp.status_code == 200
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project" and inv.get("project_id") == project_id]
    assert len(project_invites) == 1


def test_invite_shows_in_invitations(client):
    """Invited user sees the project invitation."""
    resp = client.get("/invitations", auth=(user_in_team, "pass123"))
    assert resp.status_code == 200
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project"]
    assert len(project_invites) >= 1
    inv = project_invites[0]
    assert inv["project_name"] == project_name
    assert inv["invited_by"] == "admin"


def test_invitation_count_includes_projects(client):
    """Invitation count includes project invitations."""
    resp = client.get("/invitations/count", auth=(user_in_team, "pass123"))
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_accept_project_invite(client):
    """Accepting a project invite adds the user to the project."""
    # Get the invitation
    resp = client.get("/invitations", auth=(user_in_team, "pass123"))
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project" and inv.get("project_id") == project_id]
    assert len(project_invites) >= 1
    invite_id = project_invites[0]["id"]

    # Accept
    resp = client.post(f"/invitations/projects/{invite_id}/accept", json={}, auth=(user_in_team, "pass123"))
    assert resp.status_code == 200
    assert "Joined" in resp.json()["message"]

    # Verify user has access
    resp = client.get(f"/projects/{project_id}", auth=(user_in_team, "pass123"))
    assert resp.status_code == 200


def test_decline_project_invite(client):
    """Declining a project invite does not add the user."""
    auth_admin = ("admin", RESTAI_DEFAULT_PASSWORD)

    # Create another user in team
    decline_user = f"inv_decline_{suffix}"
    client.post("/users", json={"username": decline_user, "password": "pass123", "admin": False, "private": False}, auth=auth_admin)
    client.post(f"/teams/{team_id}/users/{decline_user}", auth=auth_admin)

    # Send invite
    client.post(f"/projects/{project_id}/invitations", json={"username": decline_user}, auth=auth_admin)

    # Get invitation
    resp = client.get("/invitations", auth=(decline_user, "pass123"))
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project" and inv.get("project_id") == project_id]
    assert len(project_invites) >= 1
    invite_id = project_invites[0]["id"]

    # Decline
    resp = client.post(f"/invitations/projects/{invite_id}/decline", json={}, auth=(decline_user, "pass123"))
    assert resp.status_code == 200

    # Verify user does NOT have access
    resp = client.get(f"/projects/{project_id}", auth=(decline_user, "pass123"))
    assert resp.status_code == 404

    # Cleanup
    client.delete(f"/users/{decline_user}", auth=auth_admin)


def test_non_member_cannot_send_invite(client):
    """A user who is not a project member cannot send invites."""
    resp = client.post(
        f"/projects/{project_id}/invitations",
        json={"username": user_outside},
        auth=(user_outside, "pass123"),
    )
    assert resp.status_code == 404


def test_cleanup(client):
    """Clean up test resources."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/projects/{project_name}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
    client.delete(f"/users/{user_in_team}", auth=auth)
    client.delete(f"/users/{user_outside}", auth=auth)
