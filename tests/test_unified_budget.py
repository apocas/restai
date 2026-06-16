"""Unified cost-budget model: spend engine, enforcement at four scopes, and the
per-(user, team) cap endpoints. Seeds OutputDatabase rows directly (no live LLM)
and drives the engine + DBWrapper helpers deterministically.
"""
import random
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
_sfx = str(random.randint(0, 1_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _seed(team_id, project_id, user_id, cost, *, api_key_id=None, direct=False, days_ago=0):
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase
    db = DBWrapper()
    try:
        db.db.add(OutputDatabase(
            user_id=user_id,
            project_id=None if direct else project_id,
            team_id=team_id,
            api_key_id=api_key_id,
            llm="ub_llm",
            question="q", answer="a",
            date=datetime.now(timezone.utc) - timedelta(days=days_ago),
            status="success",
            input_tokens=10, output_tokens=10,
            input_cost=cost / 2.0, output_cost=cost / 2.0,
        ))
        db.db.commit()
    finally:
        db.db.close()


@pytest.fixture(scope="module")
def setup(client):
    """Team with budget 1000, an LLM, a project, and a member user."""
    llm = "ub_llm_" + _sfx
    member = "ub_member_" + _sfx
    member_pw = "ub_pass_123"
    assert client.post("/users", json={"username": member, "password": member_pw}, auth=ADMIN).status_code == 201
    r = client.post("/llms", json={"name": llm, "class_name": "OpenAI",
                                   "options": {"model": "gpt-test", "api_key": "sk-fake"}, "privacy": "public"}, auth=ADMIN)
    assert r.status_code in (200, 201), r.text
    tr = client.post("/teams", json={"name": "ub_team_" + _sfx, "users": [member], "admins": [], "llms": [llm], "budget": 1000.0}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]
    pr = client.post("/projects", json={"name": "ub_proj_" + _sfx, "type": "agent", "llm": llm, "team_id": team_id}, auth=ADMIN)
    assert pr.status_code == 201, pr.text
    project_id = pr.json()["project"]
    member_id = client.get(f"/users/{member}", auth=ADMIN).json()["id"]
    return SimpleNamespace(team_id=team_id, project_id=project_id, member=member, member_pw=member_pw, member_id=member_id, llm=llm)


def test_spend_for_scopes(client, setup):
    from restai.database import DBWrapper
    # project-scoped 3.0 + direct-access 1.0 for the member (last month row excluded)
    _seed(setup.team_id, setup.project_id, setup.member_id, 3.0)
    _seed(setup.team_id, setup.project_id, setup.member_id, 1.0, direct=True)
    _seed(setup.team_id, setup.project_id, setup.member_id, 99.0, days_ago=40)  # previous month

    db = DBWrapper()
    try:
        assert round(db.spend_for(team_id=setup.team_id), 2) == 4.0
        assert round(db.spend_for(team_id=setup.team_id, user_id=setup.member_id), 2) == 4.0
        assert round(db.spend_for(project_id=setup.project_id), 2) == 3.0  # direct row has no project
        with pytest.raises(ValueError):
            db.spend_for()  # no scope → guarded
    finally:
        db.db.close()


def test_user_in_team_cap_blocks_while_team_ok(client, setup):
    from restai.database import DBWrapper
    from restai.limits.budget import enforce_cost_budgets
    from restai.models.models import User

    db = DBWrapper()
    try:
        member = User.model_validate(db.get_user_by_username(setup.member))
        team = db.get_team_by_id(setup.team_id)  # budget 1000, spend ~4 → team OK

        # No personal cap → allowed.
        enforce_cost_budgets(db, user=member, team=team)

        # Tiny personal cap → blocked (team still has headroom).
        db.set_team_user_budget(setup.team_id, setup.member_id, 0.5)
        with pytest.raises(HTTPException) as exc:
            enforce_cost_budgets(db, user=member, team=team)
        assert exc.value.status_code == 402
        assert "personal budget" in exc.value.detail.lower()

        # Clear it → allowed again.
        db.set_team_user_budget(setup.team_id, setup.member_id, -1)
        enforce_cost_budgets(db, user=member, team=team)
    finally:
        db.db.close()


def test_project_and_apikey_and_precedence(client, setup):
    from restai.database import DBWrapper
    from restai.limits.budget import enforce_cost_budgets
    from restai.models.models import User

    db = DBWrapper()
    try:
        member = User.model_validate(db.get_user_by_username(setup.member))
        team = db.get_team_by_id(setup.team_id)

        # project cap 0 (exhausted) — lightweight Project stand-in.
        proj = SimpleNamespace(props=SimpleNamespace(
            options=SimpleNamespace(budget=0.0), id=setup.project_id, name="p", team=team))
        with pytest.raises(HTTPException) as exc:
            enforce_cost_budgets(db, project=proj, user=member, team=team)
        assert exc.value.status_code == 402
        assert exc.value.detail == "Project budget exhausted"  # project wins precedence over team

        # api-key cost cap
        _seed(setup.team_id, setup.project_id, setup.member_id, 2.0, api_key_id=999001)
        key = SimpleNamespace(id=999001, cost_budget_monthly=0.5)
        with pytest.raises(HTTPException) as exc:
            enforce_cost_budgets(db, user=member, team=team, api_key_row=key)
        assert exc.value.detail == "API key cost budget exhausted"

        # admin bypasses everything
        admin = User.model_validate(db.get_user_by_username("admin"))
        proj_admin = SimpleNamespace(props=SimpleNamespace(
            options=SimpleNamespace(budget=0.0), id=setup.project_id, name="p", team=team))
        enforce_cost_budgets(db, project=proj_admin, user=admin, team=team)  # no raise
    finally:
        db.db.close()


def test_member_budget_endpoints(client, setup):
    # GET budgets (admin)
    r = client.get(f"/teams/{setup.team_id}/members/budgets", auth=ADMIN)
    assert r.status_code == 200, r.text
    rows = {m["username"]: m for m in r.json()}
    assert setup.member in rows
    assert rows[setup.member]["spending"] >= 0

    # PATCH set a cap
    r = client.patch(f"/teams/{setup.team_id}/members/{setup.member}/budget", json={"budget": 25.0}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["budget"] == 25.0

    r = client.get(f"/teams/{setup.team_id}/members/budgets", auth=ADMIN)
    assert {m["username"]: m for m in r.json()}[setup.member]["budget"] == 25.0

    # PATCH clear
    r = client.patch(f"/teams/{setup.team_id}/members/{setup.member}/budget", json={"budget": -1}, auth=ADMIN)
    assert r.status_code == 200 and r.json()["budget"] is None

    # RBAC: a non-member, non-admin user → 403
    other = "ub_outsider_" + _sfx
    assert client.post("/users", json={"username": other, "password": "ub_pass_123"}, auth=ADMIN).status_code == 201
    assert client.get(f"/teams/{setup.team_id}/members/budgets", auth=(other, "ub_pass_123")).status_code == 403

    # set cap for a non-member → 400
    r = client.patch(f"/teams/{setup.team_id}/members/{other}/budget", json={"budget": 5.0}, auth=ADMIN)
    assert r.status_code == 400

    # unknown team → 404
    assert client.get("/teams/999999/members/budgets", auth=ADMIN).status_code == 404
