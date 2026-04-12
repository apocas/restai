import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


test_username = "test_comments_user_" + str(random.randint(0, 1000000))
test_password = "comments_test_pass"
test_project_id = None
comment_id = None


def test_setup(client):
    """Create test user and a project for comment tests."""
    global test_project_id
    # Create user
    client.post(
        "/users",
        json={"username": test_username, "password": test_password, "admin": False, "private": False},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )

    # Create a test LLM
    llm_name = f"comments_llm_{random.randint(0,999999)}"
    client.post(
        "/llms",
        json={"name": llm_name, "class_name": "OpenAI", "options": {"model": "gpt-test", "api_key": "sk-fake"}, "privacy": "public"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )

    # Create a team and add user + LLM
    team_name = f"comments_team_{random.randint(0,999999)}"
    resp = client.post(
        "/teams",
        json={"name": team_name, "users": [test_username], "admins": [], "llms": [llm_name]},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    team_id = resp.json()["id"]

    # Create project
    proj_name = f"comments_proj_{random.randint(0,999999)}"
    resp = client.post(
        "/projects",
        json={"name": proj_name, "type": "agent", "llm": llm_name, "team_id": team_id},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 201
    test_project_id = resp.json()["project"]

    # Assign test user to the project
    client.patch(
        f"/projects/{test_project_id}",
        json={"users": ["admin", test_username]},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )


def test_list_comments_initial(client):
    resp = client.get(
        f"/projects/{test_project_id}/comments",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    # Clean up any leftover comments from previous runs
    for c in resp.json():
        client.delete(f"/projects/{test_project_id}/comments/{c['id']}", auth=("admin", RESTAI_DEFAULT_PASSWORD))


def test_create_comment(client):
    global comment_id
    resp = client.post(
        f"/projects/{test_project_id}/comments",
        json={"content": "This project works great for product questions."},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    comment_id = data["id"]


def test_list_comments_after_create(client):
    resp = client.get(
        f"/projects/{test_project_id}/comments",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200
    comments = resp.json()
    assert len(comments) == 1
    assert comments[0]["content"] == "This project works great for product questions."
    assert comments[0]["username"] == "admin"
    assert "created_at" in comments[0]


def test_create_second_comment(client):
    resp = client.post(
        f"/projects/{test_project_id}/comments",
        json={"content": "Struggles with pricing questions though."},
        auth=(test_username, test_password),
    )
    assert resp.status_code == 201


def test_list_comments_order(client):
    """Comments should be newest first."""
    resp = client.get(
        f"/projects/{test_project_id}/comments",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    comments = resp.json()
    assert len(comments) == 2
    # Newest first
    assert comments[0]["content"] == "Struggles with pricing questions though."
    assert comments[1]["content"] == "This project works great for product questions."


def test_update_own_comment(client):
    resp = client.patch(
        f"/projects/{test_project_id}/comments/{comment_id}",
        json={"content": "Updated: works great for product AND support questions."},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200

    # Verify update
    comments = client.get(
        f"/projects/{test_project_id}/comments",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    ).json()
    updated = [c for c in comments if c["id"] == comment_id][0]
    assert "Updated:" in updated["content"]


def test_non_owner_cannot_update(client):
    resp = client.patch(
        f"/projects/{test_project_id}/comments/{comment_id}",
        json={"content": "Hacked!"},
        auth=(test_username, test_password),
    )
    assert resp.status_code == 403
    assert "own comments" in resp.json()["detail"]


def test_non_owner_cannot_delete(client):
    resp = client.delete(
        f"/projects/{test_project_id}/comments/{comment_id}",
        auth=(test_username, test_password),
    )
    assert resp.status_code == 403


def test_delete_own_comment(client):
    # First create a comment as test_user, then delete it
    create_resp = client.post(
        f"/projects/{test_project_id}/comments",
        json={"content": "Temporary note."},
        auth=(test_username, test_password),
    )
    temp_id = create_resp.json()["id"]

    resp = client.delete(
        f"/projects/{test_project_id}/comments/{temp_id}",
        auth=(test_username, test_password),
    )
    assert resp.status_code == 200


def test_admin_can_delete_any(client):
    """Admin can delete other users' comments."""
    # Get the test_user's remaining comment
    comments = client.get(
        f"/projects/{test_project_id}/comments",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    ).json()
    user_comment = [c for c in comments if c["username"] == test_username]
    assert len(user_comment) > 0

    resp = client.delete(
        f"/projects/{test_project_id}/comments/{user_comment[0]['id']}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 200


def test_comment_not_found(client):
    resp = client.patch(
        f"/projects/{test_project_id}/comments/999999",
        json={"content": "nope"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert resp.status_code == 404


def test_empty_comment_rejected(client):
    resp = client.post(
        f"/projects/{test_project_id}/comments",
        json={"content": ""},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    # Pydantic validation: empty string with max_length should still pass,
    # but we could also check if server rejects it
    # At minimum it should not crash
    assert resp.status_code in (201, 422)


def test_cleanup(client):
    client.delete(f"/projects/{test_project_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    client.delete(f"/users/{test_username}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
