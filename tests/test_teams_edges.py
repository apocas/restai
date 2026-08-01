"""Edge-path tests for restai/routers/teams.py.

Covers branches untouched by test_teams.py / test_team_balance*.py /
test_team_analytics.py: branding, duplicate names, 404s on unknown
resources, project + image/audio generator attach/detach, the monthly
/transactions listing (with seeded OutputDatabase rows), member budget
listing + validation, and team-invitation accept/decline edge cases.
"""
import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
team_name = f"tedge_team_{suffix}"
member_user = f"tedge_member_{suffix}"
invitee_user = f"tedge_invitee_{suffix}"
decliner_user = f"tedge_decliner_{suffix}"
user_pass = "tedge_pass_123"
proj_name = f"tedge_proj_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    for username in (member_user, invitee_user, decliner_user):
        r = client.post(
            "/users",
            json={"username": username, "password": user_pass, "admin": False, "private": False},
            auth=ADMIN,
        )
        assert r.status_code == 201, r.text

    r = client.post("/teams", json={"name": team_name, "users": [member_user]}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["project_id"] = r.json()["project"]


# ---------------------------------------------------------------- branding


def test_branding_unknown_team(client):
    r = client.get("/teams/99999999/branding")
    assert r.status_code == 404


def test_branding_defaults_empty(client):
    r = client.get(f"/teams/{state['team_id']}/branding")
    assert r.status_code == 200
    data = r.json()
    assert data["primary_color"] is None
    assert data["app_name"] is None


def test_branding_roundtrip(client):
    r = client.patch(
        f"/teams/{state['team_id']}",
        json={"branding": {"primary_color": "#112233", "app_name": "EdgeCo"}},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/teams/{state['team_id']}/branding")
    assert r.status_code == 200
    data = r.json()
    assert data["primary_color"] == "#112233"
    assert data["app_name"] == "EdgeCo"


# ---------------------------------------------------------------- CRUD edges


def test_create_duplicate_team_name(client):
    r = client.post("/teams", json={"name": team_name}, auth=ADMIN)
    assert r.status_code == 400


def test_patch_rename_to_taken_name(client):
    other = f"tedge_other_{suffix}"
    r = client.post("/teams", json={"name": other}, auth=ADMIN)
    assert r.status_code == 201
    other_id = r.json()["id"]

    r = client.patch(f"/teams/{other_id}", json={"name": team_name}, auth=ADMIN)
    assert r.status_code == 400

    client.delete(f"/teams/{other_id}", auth=ADMIN)


def test_patch_unknown_team(client):
    r = client.patch("/teams/99999999", json={"description": "x"}, auth=ADMIN)
    assert r.status_code == 404


def test_delete_unknown_team(client):
    r = client.delete("/teams/99999999", auth=ADMIN)
    assert r.status_code == 404


def test_add_unknown_user_to_team(client):
    r = client.post(f"/teams/{state['team_id']}/users/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


def test_remove_unknown_user_from_team(client):
    r = client.delete(f"/teams/{state['team_id']}/users/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


def test_add_unknown_admin_to_team(client):
    r = client.post(f"/teams/{state['team_id']}/admins/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


def test_remove_unknown_admin_from_team(client):
    r = client.delete(f"/teams/{state['team_id']}/admins/no_such_user_xyz", auth=ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------- project attach


def test_add_and_remove_project_to_team(client):
    tid, pid = state["team_id"], state["project_id"]

    r = client.delete(f"/teams/{tid}/projects/{pid}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["removed_project"] == proj_name

    r = client.post(f"/teams/{tid}/projects/{pid}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["added_project"] == proj_name


def test_add_unknown_project_to_team(client):
    r = client.post(f"/teams/{state['team_id']}/projects/99999999", auth=ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------- generators


def test_image_generator_attach_detach(client):
    tid = state["team_id"]
    gen = f"img_gen_{suffix}"
    r = client.post(f"/teams/{tid}/image_generators/{gen}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["added_image_generator"] == gen

    r = client.delete(f"/teams/{tid}/image_generators/{gen}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["removed_image_generator"] == gen


def test_audio_generator_attach_detach(client):
    tid = state["team_id"]
    gen = f"aud_gen_{suffix}"
    r = client.post(f"/teams/{tid}/audio_generators/{gen}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["added_audio_generator"] == gen

    r = client.delete(f"/teams/{tid}/audio_generators/{gen}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["removed_audio_generator"] == gen


def test_image_generator_unknown_team(client):
    r = client.post("/teams/99999999/image_generators/whatever", auth=ADMIN)
    assert r.status_code == 404


# ---------------------------------------------------------------- transactions


def test_team_transactions_with_seeded_rows(client):
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase, UserDatabase

    db = DBWrapper()
    try:
        admin_id = db.db.query(UserDatabase).filter(UserDatabase.username == "admin").first().id
        now = datetime.now(timezone.utc)
        db.db.add(OutputDatabase(
            question="q project", answer="a", project_id=state["project_id"],
            user_id=admin_id, team_id=state["team_id"], llm="tedge_llm",
            input_tokens=10, output_tokens=5, input_cost=0.001, output_cost=0.002,
            date=now, latency_ms=120, chat_id=f"tedge_chat_{suffix}",
        ))
        # Direct-access style row: no project, billed to the team.
        db.db.add(OutputDatabase(
            question="q direct", answer="a", project_id=None,
            user_id=admin_id, team_id=state["team_id"], llm="tedge_llm",
            input_tokens=7, output_tokens=3, input_cost=0.0005, output_cost=0.0007,
            date=now, latency_ms=80,
        ))
        db.db.commit()
    finally:
        db.db.close()

    r = client.get(f"/teams/{state['team_id']}/transactions", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    questions = {t["question"] for t in data["transactions"]}
    assert {"q project", "q direct"} <= questions
    row = next(t for t in data["transactions"] if t["question"] == "q project")
    assert row["project"] == proj_name
    assert row["user"] == "admin"
    assert row["input_tokens"] == 10
    assert row["total_cost"] == pytest.approx(0.003)


def test_team_transactions_unknown_team(client):
    r = client.get("/teams/99999999/transactions", auth=ADMIN)
    assert r.status_code == 404


def test_team_transactions_forbidden_for_plain_member(client):
    r = client.get(f"/teams/{state['team_id']}/transactions", auth=(member_user, user_pass))
    assert r.status_code == 403


# ---------------------------------------------------------------- member budgets


def test_member_budgets_listing(client):
    r = client.get(f"/teams/{state['team_id']}/members/budgets", auth=ADMIN)
    assert r.status_code == 200
    rows = r.json()
    usernames = {row["username"] for row in rows}
    assert member_user in usernames
    row = next(row for row in rows if row["username"] == member_user)
    assert row["budget"] is None
    assert row["remaining"] is None


def test_member_budgets_unknown_team(client):
    r = client.get("/teams/99999999/members/budgets", auth=ADMIN)
    assert r.status_code == 404


def test_set_member_budget_and_clear(client):
    tid = state["team_id"]
    r = client.patch(
        f"/teams/{tid}/members/{member_user}/budget",
        json={"budget": 12.5},
        auth=ADMIN,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["budget"] == 12.5
    assert data["remaining"] == pytest.approx(12.5 - data["spending"])

    r = client.patch(
        f"/teams/{tid}/members/{member_user}/budget",
        json={"budget": None},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["budget"] is None


def test_set_member_budget_unknown_user(client):
    r = client.patch(
        f"/teams/{state['team_id']}/members/no_such_user_xyz/budget",
        json={"budget": 5},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_set_member_budget_non_member(client):
    # invitee_user exists but is not (yet) in the team.
    r = client.patch(
        f"/teams/{state['team_id']}/members/{invitee_user}/budget",
        json={"budget": 5},
        auth=ADMIN,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- invitations


def test_team_invitation_missing_username(client):
    r = client.post(f"/teams/{state['team_id']}/invitations", json={}, auth=ADMIN)
    assert r.status_code == 400


def test_team_invitation_accept_flow(client):
    tid = state["team_id"]
    r = client.post(f"/teams/{tid}/invitations", json={"username": invitee_user}, auth=ADMIN)
    assert r.status_code == 200

    # Duplicate invite is silently ignored (same opaque message, one row).
    r = client.post(f"/teams/{tid}/invitations", json={"username": invitee_user}, auth=ADMIN)
    assert r.status_code == 200

    invites = client.get("/invitations", auth=(invitee_user, user_pass)).json()
    team_invites = [i for i in invites if i["type"] == "team" and i["team_id"] == tid]
    assert len(team_invites) == 1
    inv_id = team_invites[0]["id"]
    state["accepted_invite_id"] = inv_id

    # A different user cannot accept someone else's invitation.
    r = client.post(f"/invitations/{inv_id}/accept", auth=(decliner_user, user_pass))
    assert r.status_code == 404

    r = client.post(f"/invitations/{inv_id}/accept", auth=(invitee_user, user_pass))
    assert r.status_code == 200
    assert team_name in r.json()["message"]

    team = client.get(f"/teams/{tid}", auth=ADMIN).json()
    assert invitee_user in [u["username"] for u in team["users"]]


def test_team_invitation_accept_twice(client):
    r = client.post(
        f"/invitations/{state['accepted_invite_id']}/accept",
        auth=(invitee_user, user_pass),
    )
    assert r.status_code == 400


def test_team_invitation_invite_existing_member_noop(client):
    # invitee_user is now a member — no new pending invitation is created.
    tid = state["team_id"]
    r = client.post(f"/teams/{tid}/invitations", json={"username": invitee_user}, auth=ADMIN)
    assert r.status_code == 200
    invites = client.get("/invitations", auth=(invitee_user, user_pass)).json()
    assert [i for i in invites if i["type"] == "team" and i["team_id"] == tid] == []


def test_team_invitation_decline_flow(client):
    tid = state["team_id"]
    r = client.post(f"/teams/{tid}/invitations", json={"username": decliner_user}, auth=ADMIN)
    assert r.status_code == 200

    invites = client.get("/invitations", auth=(decliner_user, user_pass)).json()
    team_invites = [i for i in invites if i["type"] == "team" and i["team_id"] == tid]
    assert len(team_invites) == 1
    inv_id = team_invites[0]["id"]

    r = client.post(f"/invitations/{inv_id}/decline", auth=(decliner_user, user_pass))
    assert r.status_code == 200

    # Declining again → no longer pending.
    r = client.post(f"/invitations/{inv_id}/decline", auth=(decliner_user, user_pass))
    assert r.status_code == 400

    team = client.get(f"/teams/{tid}", auth=ADMIN).json()
    assert decliner_user not in [u["username"] for u in team["users"]]


def test_invitation_accept_unknown_id(client):
    r = client.post("/invitations/99999999/accept", auth=(invitee_user, user_pass))
    assert r.status_code == 404


def test_invitation_decline_unknown_id(client):
    r = client.post("/invitations/99999999/decline", auth=(invitee_user, user_pass))
    assert r.status_code == 404


# ---------------------------------------------------------------- cleanup


def test_cleanup(client):
    client.delete(f"/projects/{state['project_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    for username in (member_user, invitee_user, decliner_user):
        client.delete(f"/users/{username}", auth=ADMIN)
