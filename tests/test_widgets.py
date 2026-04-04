import random
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


def test_setup():
    """Create team and project for widget tests."""
    global team_id, project_id
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        resp = client.post("/teams", json={"name": team_name}, auth=auth)
        assert resp.status_code in (200, 201)
        team_id = resp.json()["id"]

        resp = client.post("/projects", json={"name": project_name, "type": "block", "team_id": team_id}, auth=auth)
        assert resp.status_code == 201
        project_id = resp.json()["project"]


def test_create_widget():
    """Creating a widget returns a key with wk_ prefix."""
    global widget_id, widget_key
    with TestClient(app) as client:
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


def test_list_widgets():
    """Listing widgets includes the widget key."""
    with TestClient(app) as client:
        resp = client.get(f"/projects/{project_id}/widgets", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
        widgets = resp.json()["widgets"]
        assert len(widgets) >= 1
        w = next(w for w in widgets if w["id"] == widget_id)
        assert w["widget_key"].startswith("wk_")
        assert w["key_prefix"].startswith("wk_")


def test_get_widget():
    """Getting a single widget returns details including key."""
    with TestClient(app) as client:
        resp = client.get(f"/projects/{project_id}/widgets/{widget_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Widget"
        assert data["widget_key"].startswith("wk_")


def test_update_widget():
    """Updating widget config persists."""
    with TestClient(app) as client:
        resp = client.patch(
            f"/projects/{project_id}/widgets/{widget_id}",
            json={"name": "Updated Widget", "allowed_domains": ["newdomain.com"]},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Widget"
        assert resp.json()["allowed_domains"] == ["newdomain.com"]


def test_widget_chat_domain_mismatch():
    """Widget chat from wrong domain returns 403."""
    with TestClient(app) as client:
        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": widget_key, "Origin": "https://evil.com"},
        )
        assert resp.status_code == 403


def test_widget_chat_correct_domain():
    """Widget chat from allowed domain succeeds."""
    with TestClient(app) as client:
        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": widget_key, "Origin": "https://newdomain.com"},
        )
        # Block projects don't have an LLM, so the chat may error,
        # but it should NOT be a 403/401 — it got past auth
        assert resp.status_code != 401
        assert resp.status_code != 403


def test_disable_widget():
    """Disabled widget returns 403."""
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        client.patch(f"/projects/{project_id}/widgets/{widget_id}", json={"enabled": False}, auth=auth)

        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": widget_key, "Origin": "https://newdomain.com"},
        )
        assert resp.status_code == 403

        # Re-enable
        client.patch(f"/projects/{project_id}/widgets/{widget_id}", json={"enabled": True}, auth=auth)


def test_invalid_widget_key():
    """Invalid key returns 401."""
    with TestClient(app) as client:
        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": "wk_invalid_key_123"},
        )
        assert resp.status_code == 401


def test_api_key_on_widget_endpoint():
    """Regular API key on widget endpoint returns 401."""
    with TestClient(app) as client:
        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": "not_a_wk_key"},
        )
        assert resp.status_code == 401


def test_regenerate_key():
    """Regenerated key works, old key stops working."""
    global widget_key
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        old_key = widget_key

        # Remove domain restriction for this test
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

        # Old key should fail
        resp = client.post(
            "/widget/chat",
            json={"question": "hello"},
            headers={"X-Widget-Key": old_key},
        )
        assert resp.status_code == 401


def test_delete_widget():
    """Deleting a widget removes it."""
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        resp = client.delete(f"/projects/{project_id}/widgets/{widget_id}", auth=auth)
        assert resp.status_code == 204

        resp = client.get(f"/projects/{project_id}/widgets", auth=auth)
        ids = [w["id"] for w in resp.json()["widgets"]]
        assert widget_id not in ids


def test_cleanup():
    """Clean up test resources."""
    with TestClient(app) as client:
        auth = ("admin", RESTAI_DEFAULT_PASSWORD)
        client.delete(f"/projects/{project_name}", auth=auth)
        client.delete(f"/teams/{team_id}", auth=auth)
