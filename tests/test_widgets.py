import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"wid_team_{suffix}"
project_name = f"wid_project_{suffix}"

team_id = None
project_id = None
widget_id = None
widget_key = None


@pytest.fixture(scope="module")
def client():
    """Single TestClient for all widget tests — avoids repeated lifespan init."""
    with TestClient(app) as c:
        yield c


def test_setup(client):
    global team_id, project_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    resp = client.post("/teams", json={"name": team_name}, auth=auth)
    assert resp.status_code in (200, 201)
    team_id = resp.json()["id"]

    resp = client.post("/projects", json={"name": project_name, "type": "block", "team_id": team_id}, auth=auth)
    assert resp.status_code == 201
    project_id = resp.json()["project"]


def test_create_widget(client):
    global widget_id, widget_key
    resp = client.post(
        f"/projects/{project_id}/widgets",
        json={
            "name": "Test Widget",
            "config": {"title": "Test", "stream": False},
            "allowed_domains": ["example.com", "*.mysite.com"],
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Widget"
    assert "widget_key" in data
    assert data["widget_key"].startswith("wk_")
    assert data["enabled"] is True
    assert data["allowed_domains"] == ["example.com", "*.mysite.com"]
    widget_id = data["id"]
    widget_key = data["widget_key"]


def test_list_widgets(client):
    resp = client.get(f"/projects/{project_id}/widgets", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert resp.status_code == 200
    widgets = resp.json()["widgets"]
    assert len(widgets) >= 1
    w = next(w for w in widgets if w["id"] == widget_id)
    assert w["widget_key"].startswith("wk_")
    assert w["key_prefix"].startswith("wk_")


def test_get_widget(client):
    resp = client.get(f"/projects/{project_id}/widgets/{widget_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Widget"
    assert data["widget_key"].startswith("wk_")


def test_update_widget(client):
    resp = client.patch(
        f"/projects/{project_id}/widgets/{widget_id}",
        json={"name": "Updated Widget", "allowed_domains": ["newdomain.com"]},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Widget"
    assert resp.json()["allowed_domains"] == ["newdomain.com"]


def test_widget_chat_domain_mismatch(client):
    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": widget_key, "Origin": "https://evil.com"},
    )
    assert resp.status_code == 403


def test_widget_chat_correct_domain(client):
    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": widget_key, "Origin": "https://newdomain.com"},
    )
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_disable_widget(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.patch(f"/projects/{project_id}/widgets/{widget_id}", json={"enabled": False}, auth=auth)

    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": widget_key, "Origin": "https://newdomain.com"},
    )
    assert resp.status_code == 403

    client.patch(f"/projects/{project_id}/widgets/{widget_id}", json={"enabled": True}, auth=auth)


def test_invalid_widget_key(client):
    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": "wk_invalid_key_123"},
    )
    assert resp.status_code == 401


def test_api_key_on_widget_endpoint(client):
    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": "not_a_wk_key"},
    )
    assert resp.status_code == 401


def test_regenerate_key(client):
    global widget_key
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    old_key = widget_key

    client.patch(f"/projects/{project_id}/widgets/{widget_id}", json={"allowed_domains": []}, auth=auth)

    resp = client.post(
        f"/projects/{project_id}/widgets/{widget_id}/regenerate-key",
        json={},
        auth=auth,
    )
    assert resp.status_code == 200
    new_key = resp.json()["widget_key"]
    assert new_key.startswith("wk_")
    assert new_key != old_key
    widget_key = new_key

    resp = client.post(
        "/widget/chat",
        json={"question": "hello"},
        headers={"X-Widget-Key": old_key},
    )
    assert resp.status_code == 401


def test_delete_widget(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    resp = client.delete(f"/projects/{project_id}/widgets/{widget_id}", auth=auth)
    assert resp.status_code == 204

    resp = client.get(f"/projects/{project_id}/widgets", auth=auth)
    ids = [w["id"] for w in resp.json()["widgets"]]
    assert widget_id not in ids


def test_cleanup(client):
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    client.delete(f"/projects/{project_name}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
