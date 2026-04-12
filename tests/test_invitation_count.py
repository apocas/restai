"""Tests for invitation count accuracy across accept/decline."""
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"ic_team_{suffix}"
project_name = f"ic_project_{suffix}"
user1 = f"ic_user1_{suffix}"
user2 = f"ic_user2_{suffix}"
team_id = None
project_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create team, project, and users."""
    global team_id, project_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    team_id = resp.json()["id"]

    client.post("/users", json={"username": user1, "password": "pass123", "admin": False, "private": False}, auth=auth)
    client.post("/users", json={"username": user2, "password": "pass123", "admin": False, "private": False}, auth=auth)
    client.post(f"/teams/{team_id}/users/{user1}", auth=auth)
    client.post(f"/teams/{team_id}/users/{user2}", auth=auth)

    resp = client.post("/projects", json={"name": project_name, "type": "block", "team_id": team_id}, auth=auth)
    assert resp.status_code == 201
    project_id = resp.json()["project"]


def test_count_starts_at_zero(client):
    """Users with no invites have count 0."""
    resp = client.get("/invitations/count", auth=(user1, "pass123"))
    assert resp.json()["count"] == 0


def test_count_increments_on_invite(client):
    """Count goes up when an invite is sent."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    # Send project invite to user1
    client.post(f"/projects/{project_id}/invitations", json={"username": user1}, auth=auth)

    resp = client.get("/invitations/count", auth=(user1, "pass123"))
    assert resp.json()["count"] == 1


def test_count_increments_with_team_invite(client):
    """Count includes both team and project invites."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    # Also send team invite to user1 (for a new team)
    new_team = f"ic_team2_{suffix}"
    resp = client.post("/teams", json={"name": new_team}, auth=auth)
    new_team_id = resp.json()["id"]
    client.post(f"/teams/{new_team_id}/invitations", json={"username": user1}, auth=auth)

    resp = client.get("/invitations/count", auth=(user1, "pass123"))
    assert resp.json()["count"] == 2

    # Cleanup extra team
    client.delete(f"/teams/{new_team_id}", auth=auth)


def test_count_decrements_on_accept(client):
    """Count goes down when invite is accepted."""
    # First decline any team invites so we start clean
    resp = client.get("/invitations", auth=(user1, "pass123"))
    for inv in resp.json():
        if inv.get("type") == "team":
            client.post(f"/invitations/{inv['id']}/decline", json={}, auth=(user1, "pass123"))

    resp = client.get("/invitations/count", auth=(user1, "pass123"))
    count_before = resp.json()["count"]
    assert count_before >= 1

    resp = client.get("/invitations", auth=(user1, "pass123"))
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project"]
    invite_id = project_invites[0]["id"]

    client.post(f"/invitations/projects/{invite_id}/accept", json={}, auth=(user1, "pass123"))

    resp = client.get("/invitations/count", auth=(user1, "pass123"))
    assert resp.json()["count"] == count_before - 1


def test_count_decrements_on_decline(client):
    """Count goes down when invite is declined."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    # Send invite to user2
    client.post(f"/projects/{project_id}/invitations", json={"username": user2}, auth=auth)

    resp = client.get("/invitations/count", auth=(user2, "pass123"))
    assert resp.json()["count"] == 1

    # Decline
    resp = client.get("/invitations", auth=(user2, "pass123"))
    project_invites = [inv for inv in resp.json() if inv.get("type") == "project"]
    invite_id = project_invites[0]["id"]
    client.post(f"/invitations/projects/{invite_id}/decline", json={}, auth=(user2, "pass123"))

    resp = client.get("/invitations/count", auth=(user2, "pass123"))
    assert resp.json()["count"] == 0


def test_cleanup(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/projects/{project_name}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
    client.delete(f"/users/{user1}", auth=auth)
    client.delete(f"/users/{user2}", auth=auth)
