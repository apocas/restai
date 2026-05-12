import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 1000000))
team_name = f"wid_team_{suffix}"
project_name = f"wid_project_{suffix}"
sub_project_name = f"wid_subproj_{suffix}"

team_id = None
project_id = None
sub_project_id = None
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


def test_widget_call_project_end_to_end(client):
    """Regression for the b9f75b5 access-guard bug: a block-widget calling
    `Call Project` against another project used to silently return ""
    because the synthetic widget user had `projects=[]` and the new
    `user_can_access_project` check refused every sub-project call →
    JS widget rendered "No response."

    The pre-existing widget tests didn't catch this because they used an
    empty block workspace (so `_eval_call_project` was never reached) and
    only asserted `status_code != 401, != 403` — a 200 with empty body
    was indistinguishable from a 200 with content. This test wires up a
    real Call Project chain and asserts on `answer` content.
    """
    global sub_project_id
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)

    # Sub-project: passthrough block workspace that echoes the input
    # back as the output. Using `block` type so we don't depend on a
    # configured LLM (other test files note tests/test_projects.py
    # fails when no LLMs are present). ProjectModelCreate doesn't
    # accept `options`, so the workspace is set via PATCH afterwards.
    resp = client.post(
        "/projects",
        json={"name": sub_project_name, "type": "block", "team_id": team_id},
        auth=auth,
    )
    assert resp.status_code == 201, f"sub-project create failed: {resp.text}"
    sub_project_id = resp.json()["project"]

    resp = client.patch(
        f"/projects/{sub_project_id}",
        json={
            "options": {
                "blockly_workspace": {
                    "blocks": {
                        "blocks": [
                            {
                                "type": "restai_set_output",
                                "inputs": {
                                    "VALUE": {
                                        "block": {"type": "restai_get_input"}
                                    }
                                },
                            }
                        ]
                    },
                    "variables": [],
                },
            },
        },
        auth=auth,
    )
    assert resp.status_code == 200, f"sub-project workspace patch failed: {resp.text}"

    # Widget's project: workspace that delegates to the sub-project via
    # restai_call_project, passing the user input through. If the
    # access guard rejects the synthetic widget user, _eval_call_project
    # returns "" and the widget answer is empty.
    resp = client.patch(
        f"/projects/{project_id}",
        json={
            "options": {
                "blockly_workspace": {
                    "blocks": {
                        "blocks": [
                            {
                                "type": "restai_set_output",
                                "inputs": {
                                    "VALUE": {
                                        "block": {
                                            "type": "restai_call_project",
                                            "fields": {"PROJECT_NAME": sub_project_name},
                                            "inputs": {
                                                "TEXT": {"block": {"type": "restai_get_input"}}
                                            },
                                        }
                                    }
                                },
                            }
                        ]
                    },
                    "variables": [],
                },
            },
        },
        auth=auth,
    )
    assert resp.status_code == 200

    marker = f"call_project_marker_{suffix}"
    resp = client.post(
        "/widget/chat",
        json={"question": marker},
        headers={"X-Widget-Key": widget_key, "Origin": "https://newdomain.com"},
    )
    assert resp.status_code == 200, f"widget chat failed: {resp.status_code} {resp.text}"
    answer = (resp.json().get("answer") or "")
    assert marker in answer, (
        f"Call Project chain returned empty/wrong answer (likely "
        f"user_can_access_project rejected the synthetic widget user). "
        f"Got: {answer!r}"
    )


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
    if sub_project_id is not None:
        client.delete(f"/projects/{sub_project_id}", auth=auth)
    client.delete(f"/projects/{project_id}", auth=auth)
    client.delete(f"/teams/{team_id}", auth=auth)
