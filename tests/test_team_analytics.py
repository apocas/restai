"""Team analytics endpoint.

GET /teams/{id}/analytics aggregates OutputDatabase usage for a whole team —
project-scoped rows PLUS direct-access rows (project_id NULL, team_id set), the
same scope as get_team_spending. We seed a few OutputDatabase rows directly (no
live LLM) and assert the aggregation + RBAC.
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


def _seed(team_id, project_id, user_id, llm):
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase

    now = datetime.now(timezone.utc)
    rows = [
        # two project-scoped rows
        dict(project_id=project_id, team_id=team_id, input_tokens=100, output_tokens=50,
             input_cost=0.001, output_cost=0.002, chat_id="c1", latency_ms=120),
        dict(project_id=project_id, team_id=team_id, input_tokens=200, output_tokens=100,
             input_cost=0.002, output_cost=0.004, chat_id="c1", latency_ms=1500),
        # one direct-access row (no project, team_id set)
        dict(project_id=None, team_id=team_id, input_tokens=10, output_tokens=5,
             input_cost=0.0005, output_cost=0.0005, chat_id="c2", latency_ms=80),
    ]
    db = DBWrapper()
    try:
        for r in rows:
            db.db.add(OutputDatabase(
                user_id=user_id, llm=llm, question="q", answer="a",
                date=now, status="success", **r,
            ))
        db.db.commit()
    finally:
        db.db.close()


def test_team_analytics(client):
    admin_id = client.get("/users/admin", auth=ADMIN).json()["id"]
    llm = "ta_llm_" + _sfx

    r = client.post(
        "/llms",
        json={"name": llm, "class_name": "OpenAI",
              "options": {"model": "gpt-test", "api_key": "sk-fake"}, "privacy": "public"},
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), r.text

    tr = client.post(
        "/teams",
        json={"name": "ta_team_" + _sfx, "users": [], "admins": [], "llms": [llm], "budget": 100.0},
        auth=ADMIN,
    )
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    pr = client.post(
        "/projects",
        json={"name": "ta_proj_" + _sfx, "type": "agent", "llm": llm, "team_id": team_id},
        auth=ADMIN,
    )
    assert pr.status_code == 201, pr.text
    project_id = pr.json()["project"]

    _seed(team_id, project_id, admin_id, llm)

    data = client.get(f"/teams/{team_id}/analytics", auth=ADMIN).json()

    s = data["summary"]
    assert s["total_messages"] == 3
    assert s["total_tokens"] == 465  # 150 + 300 + 15
    assert round(s["total_cost"], 4) == 0.01
    assert s["active_projects"] == 1
    assert s["direct_access_messages"] == 1
    assert round(s["direct_access_cost"], 4) == 0.001

    # budget block present (team budget was 100)
    assert data["budget"]["budget"] == 100.0
    assert data["budget"]["unlimited"] is False
    assert data["budget"]["spending_month"] >= 0.01

    # per-project: the project AND a direct-access (null) bucket
    projects = {(p["project"]) for p in data["per_project"]}
    assert any(p and p.startswith("ta_proj_") for p in projects)
    assert None in projects  # direct-access bucket

    # per-user / per-llm populated
    assert any(u["user_id"] == admin_id for u in data["per_user"])
    assert any(l["llm"] == llm for l in data["per_llm"])

    # daily + latency present
    assert isinstance(data["daily"], list) and len(data["daily"]) >= 1
    assert sum(b["count"] for b in data["latency_buckets"]) == 3


def test_team_analytics_rbac(client):
    # A non-member, non-admin user cannot read team analytics.
    uname = "ta_outsider_" + _sfx
    upass = "ta_pass_123"
    assert client.post("/users", json={"username": uname, "password": upass}, auth=ADMIN).status_code == 201

    tr = client.post("/teams", json={"name": "ta_rbac_" + _sfx, "users": [], "admins": []}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    r = client.get(f"/teams/{team_id}/analytics", auth=(uname, upass))
    assert r.status_code == 403

    # Unknown team → 404 (admin bypasses the admin check, hits the existence guard).
    r = client.get("/teams/999999/analytics", auth=ADMIN)
    assert r.status_code == 404
