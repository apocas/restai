"""Tests for widget chat rate limiting."""
import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"wrl_team_{suffix}"
project_name = f"wrl_project_{suffix}"
team_id = None
project_id = None
widget_key = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_setup(client):
    """Create resources for widget rate limit tests."""
    global team_id, project_id, widget_key
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]

    resp = client.post("/projects", json={"name": project_name, "type": "block", "team_id": team_id}, auth=auth)
    assert resp.status_code == 201
    project_id = resp.json()["project"]

    resp = client.post(f"/projects/{project_id}/widgets", json={"name": "RL Widget", "allowed_domains": []}, auth=auth)
    assert resp.status_code == 201
    widget_key = resp.json()["widget_key"]


def test_widget_rate_limit_triggers(client):
    """After 30 requests in a minute, widget gets 429."""
    from restai.routers.widgets import _widget_requests, _widget_lock
    with _widget_lock:
        _widget_requests.clear()

    for i in range(30):
        client.post("/widget/chat", json={"question": "hi"}, headers={"X-Widget-Key": widget_key})

    resp = client.post("/widget/chat", json={"question": "hi"}, headers={"X-Widget-Key": widget_key})
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()

    with _widget_lock:
        _widget_requests.clear()


def test_widget_works_after_rate_limit_reset(client):
    """After clearing state, widget works again."""
    from restai.routers.widgets import _widget_requests, _widget_lock
    with _widget_lock:
        _widget_requests.clear()

    resp = client.post("/widget/chat", json={"question": "hi"}, headers={"X-Widget-Key": widget_key})
    # Block project will error on chat (no LLM), but should NOT be 429
    assert resp.status_code != 429


def test_cleanup(client):
    """Clean up."""
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/projects/{project_name}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
