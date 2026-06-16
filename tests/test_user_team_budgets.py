"""Self-service per-team budget view: GET /users/{username}/team-budgets.

A user sees their OWN cap + month-to-date spend for each team they're in (no
whole-team spend). Gated to self + platform admin.
"""
import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
_sfx = str(random.randint(0, 1_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_user_team_budgets(client):
    member = "utb_member_" + _sfx
    member_pw = "utb_pass_123"
    other = "utb_other_" + _sfx
    llm = "utb_llm_" + _sfx

    assert client.post("/users", json={"username": member, "password": member_pw}, auth=ADMIN).status_code == 201
    assert client.post("/users", json={"username": other, "password": member_pw}, auth=ADMIN).status_code == 201
    assert client.post("/llms", json={"name": llm, "class_name": "OpenAI",
                                      "options": {"model": "gpt-test", "api_key": "sk-fake"}, "privacy": "public"}, auth=ADMIN).status_code in (200, 201)
    tr = client.post("/teams", json={"name": "utb_team_" + _sfx, "users": [member], "admins": [], "llms": [llm], "budget": 1000.0}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]
    pr = client.post("/projects", json={"name": "utb_proj_" + _sfx, "type": "agent", "llm": llm, "team_id": team_id}, auth=ADMIN)
    assert pr.status_code == 201, pr.text
    project_id = pr.json()["project"]
    member_id = client.get(f"/users/{member}", auth=ADMIN).json()["id"]

    # Seed spend for the member + set a personal cap of 10.
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase
    db = DBWrapper()
    try:
        db.db.add(OutputDatabase(user_id=member_id, project_id=project_id, team_id=team_id, llm=llm,
                                 question="q", answer="a", date=datetime.now(timezone.utc), status="success",
                                 input_tokens=10, output_tokens=10, input_cost=1.5, output_cost=1.0))
        db.db.commit()
    finally:
        db.db.close()
    assert client.patch(f"/teams/{team_id}/members/{member}/budget", json={"budget": 10.0}, auth=ADMIN).status_code == 200

    # The member sees their own per-team budget.
    data = client.get(f"/users/{member}/team-budgets", auth=(member, member_pw)).json()
    rows = {tb["team_id"]: tb for tb in data["teams"]}
    assert team_id in rows
    tb = rows[team_id]
    assert tb["budget"] == 10.0
    assert round(tb["spending"], 2) == 2.5
    assert round(tb["remaining"], 2) == 7.5
    assert tb["is_admin"] is False
    assert tb["team_name"].startswith("utb_team_")

    # Platform admin can read any user's.
    assert client.get(f"/users/{member}/team-budgets", auth=ADMIN).status_code == 200

    # A different non-admin user cannot (self-or-admin gate → 404).
    assert client.get(f"/users/{member}/team-budgets", auth=(other, member_pw)).status_code == 404


def test_user_team_budgets_admin_role(client):
    # An admin-of-team shows is_admin=true for that team.
    owner = "utb_owner_" + _sfx
    owner_pw = "utb_pass_123"
    assert client.post("/users", json={"username": owner, "password": owner_pw}, auth=ADMIN).status_code == 201
    tr = client.post("/teams", json={"name": "utb_adm_" + _sfx, "users": [], "admins": [owner]}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]
    data = client.get(f"/users/{owner}/team-budgets", auth=(owner, owner_pw)).json()
    rows = {tb["team_id"]: tb for tb in data["teams"]}
    assert rows[team_id]["is_admin"] is True
    assert rows[team_id]["budget"] is None  # uncapped
