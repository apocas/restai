"""Shape tests for restai/routers/projects/analytics.py with seeded data.

Seeds OutputDatabase rows directly (mixed chat_ids, statuses, latencies,
LLMs) and verifies /analytics/conversations returns correct
status_breakdown, latency_buckets, llm_breakdown, top_users, daily and
hourly shapes; plus the /logs, conversation replay and /tokens/daily
aggregation paths.
"""
import random
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
team_name = f"aseed_team_{suffix}"
proj_name = f"aseed_proj_{suffix}"
llm_a = f"aseed_llm_a_{suffix}"
llm_b = f"aseed_llm_b_{suffix}"
chat_a = f"aseed_chat_a_{suffix}"
chat_b = f"aseed_chat_b_{suffix}"
chat_c = f"aseed_chat_c_{suffix}"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    r = client.post("/teams", json={"name": team_name}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": proj_name, "type": "block", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["project_id"] = r.json()["project"]

    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase, UserDatabase

    db = DBWrapper()
    try:
        admin_id = db.db.query(UserDatabase).filter(UserDatabase.username == "admin").first().id
        now = datetime.now(timezone.utc)
        pid = state["project_id"]

        rows = [
            # chat_id, llm, status, latency, in_tok, out_tok, in_cost, out_cost
            (chat_a, llm_a, "success", 50, 10, 5, 0.001, 0.002),
            (chat_a, llm_a, "success", 300, 20, 10, 0.002, 0.004),
            (chat_b, llm_b, "success", 1500, 30, 15, 0.003, 0.006),
            (None, llm_b, "error", 5000, 40, 20, 0.004, 0.008),
            (chat_c, None, "success", 20000, 50, 25, 0.005, 0.010),
            (chat_a, llm_a, "error", None, 60, 30, 0.006, 0.012),
        ]
        for chat_id, llm, status, latency, itok, otok, icost, ocost in rows:
            db.db.add(OutputDatabase(
                question=f"q {chat_id} {llm}", answer="a",
                project_id=pid, user_id=admin_id, team_id=state["team_id"],
                llm=llm, status=status, latency_ms=latency,
                input_tokens=itok, output_tokens=otok,
                input_cost=icost, output_cost=ocost,
                date=now, chat_id=chat_id,
            ))
        db.db.commit()
    finally:
        db.db.close()


def test_conversations_summary(client):
    r = client.get(f"/projects/{state['project_id']}/analytics/conversations", auth=ADMIN)
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["total_messages"] == 6
    assert s["total_conversations"] == 3
    assert s["avg_messages_per_conversation"] == 2.0
    assert s["total_tokens"] == 315
    assert s["total_cost"] == pytest.approx(0.063, abs=1e-6)
    assert s["avg_latency_ms"] > 0


def test_conversations_status_breakdown(client):
    r = client.get(f"/projects/{state['project_id']}/analytics/conversations", auth=ADMIN)
    breakdown = {row["status"]: row["count"] for row in r.json()["status_breakdown"]}
    assert breakdown["success"] == 4
    assert breakdown["error"] == 2


def test_conversations_latency_buckets(client):
    r = client.get(f"/projects/{state['project_id']}/analytics/conversations", auth=ADMIN)
    buckets = {row["bucket"]: row["count"] for row in r.json()["latency_buckets"]}
    assert buckets == {
        "0-100ms": 1,
        "100-500ms": 1,
        "500ms-2s": 1,
        "2-10s": 1,
        "10s+": 1,
    }


def test_conversations_llm_breakdown(client):
    r = client.get(f"/projects/{state['project_id']}/analytics/conversations", auth=ADMIN)
    llms = {row["llm"]: row for row in r.json()["llm_breakdown"]}
    # NULL-llm row is excluded.
    assert set(llms.keys()) == {llm_a, llm_b}
    assert llms[llm_a]["messages"] == 3
    assert llms[llm_a]["tokens"] == 10 + 5 + 20 + 10 + 60 + 30
    assert llms[llm_a]["cost"] == pytest.approx(0.027, abs=1e-6)
    assert llms[llm_b]["messages"] == 2


def test_conversations_top_users_daily_hourly(client):
    r = client.get(f"/projects/{state['project_id']}/analytics/conversations", auth=ADMIN)
    data = r.json()

    top = data["top_users"]
    assert top[0]["username"] == "admin"
    assert top[0]["messages"] == 6

    assert len(data["daily"]) >= 1
    assert sum(d["messages"] for d in data["daily"]) == 6

    hourly = data["hourly"]
    assert len(hourly) == 24
    assert sum(h["messages"] for h in hourly) == 6


def test_conversations_empty_month(client):
    r = client.get(
        f"/projects/{state['project_id']}/analytics/conversations?year=2020&month=1",
        auth=ADMIN,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_messages"] == 0
    assert data["status_breakdown"] == []
    assert data["llm_breakdown"] == []
    assert all(b["count"] == 0 for b in data["latency_buckets"])


def test_logs_listing(client):
    r = client.get(f"/projects/{state['project_id']}/logs", auth=ADMIN)
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert len(logs) == 6


def test_logs_pagination(client):
    r = client.get(f"/projects/{state['project_id']}/logs?start=0&end=2", auth=ADMIN)
    assert r.status_code == 200
    assert len(r.json()["logs"]) == 2


def test_conversation_replay(client):
    r = client.get(
        f"/projects/{state['project_id']}/logs/conversation/{chat_a}",
        auth=ADMIN,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chat_id"] == chat_a
    assert data["truncated"] is False
    assert len(data["turns"]) == 3


def test_conversation_replay_invalid_chat_id(client):
    r = client.get(
        f"/projects/{state['project_id']}/logs/conversation/bad%20chat%20id!",
        auth=ADMIN,
    )
    assert r.status_code == 400


def test_conversation_replay_unknown_chat(client):
    r = client.get(
        f"/projects/{state['project_id']}/logs/conversation/never_seen_{suffix}",
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["turns"] == []


def test_tokens_daily_aggregation(client):
    r = client.get(f"/projects/{state['project_id']}/tokens/daily", auth=ADMIN)
    assert r.status_code == 200
    tokens = r.json()["tokens"]
    assert len(tokens) >= 1
    total_in = sum(t["input_tokens"] or 0 for t in tokens)
    total_out = sum(t["output_tokens"] or 0 for t in tokens)
    assert total_in == 210
    assert total_out == 105
    assert any(t["avg_latency_ms"] > 0 for t in tokens)


def test_tokens_daily_unknown_project(client):
    r = client.get("/projects/99999999/tokens/daily", auth=ADMIN)
    assert r.status_code == 404


def test_logs_unknown_project(client):
    r = client.get("/projects/99999999/logs", auth=ADMIN)
    assert r.status_code == 404


def test_cleanup(client):
    client.delete(f"/projects/{state['project_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
