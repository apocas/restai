import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


team_id = None
team_name = "test_team_" + str(random.randint(0, 1000000))
test_user1 = "test_team_user1_" + str(random.randint(0, 1000000))
test_user2 = "test_team_user2_" + str(random.randint(0, 1000000))
test_llm_name = "test_team_llm_" + str(random.randint(0, 1000000))
test_llm_id = None
test_embedding_name = "test_team_emb_" + str(random.randint(0, 1000000))
test_embedding_id = None


def test_setup_dependencies(client):
    global test_llm_id, test_embedding_id
    # Create two test users
    for username in (test_user1, test_user2):
        response = client.post(
            "/users",
            json={
                "username": username,
                "password": "testpass",
                "admin": False,
                "private": False,
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 201

    # Create test LLM
    response = client.post(
        "/llms",
        json={
            "name": test_llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 201
    test_llm_id = response.json()["id"]

    # Create test embedding
    response = client.post(
        "/embeddings",
        json={
            "name": test_embedding_name,
            "class_name": "Ollama",
            "options": "{}",
            "privacy": "public",
            "dimension": 768,
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 201
    test_embedding_id = response.json()["id"]


def test_create_team(client):
    global team_id
    response = client.post(
        "/teams",
        json={"name": team_name},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == team_name
    assert "id" in data
    team_id = data["id"]
    assert data["users"] == []
    assert data["admins"] == []


def test_create_team_non_admin(client):
    response = client.post(
        "/teams",
        json={"name": "should_fail_team"},
        auth=(test_user1, "testpass"),
    )
    assert response.status_code == 403


def test_get_teams(client):
    response = client.get("/teams", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    data = response.json()
    assert "teams" in data
    team_names = [t["name"] for t in data["teams"]]
    assert team_name in team_names


def test_get_team(client):
    response = client.get(
        f"/teams/{team_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == team_id
    assert data["name"] == team_name


def test_update_team(client):
    response = client.patch(
        f"/teams/{team_id}",
        json={"description": "Updated team description"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200

    # Verify
    response = client.get(
        f"/teams/{team_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated team description"


def test_add_user_to_team(client):
    response = client.post(
        f"/teams/{team_id}/users/{test_user1}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["added"] == test_user1


def test_add_admin_to_team(client):
    response = client.post(
        f"/teams/{team_id}/admins/{test_user2}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["added_admin"] == test_user2


def test_verify_members(client):
    response = client.get(
        f"/teams/{team_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    data = response.json()
    user_names = [u["username"] for u in data["users"]]
    admin_names = [a["username"] for a in data["admins"]]
    assert test_user1 in user_names
    assert test_user2 in admin_names


def test_get_team_as_member(client):
    response = client.get(
        f"/teams/{team_id}",
        auth=(test_user1, "testpass"),
    )
    assert response.status_code == 200
    assert response.json()["id"] == team_id


def test_get_team_as_non_member(client):
    # Create a user who is not a team member
    outsider = "test_outsider_" + str(random.randint(0, 1000000))
    client.post(
        "/users",
        json={
            "username": outsider,
            "password": "testpass",
            "admin": False,
            "private": False,
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )

    response = client.get(
        f"/teams/{team_id}",
        auth=(outsider, "testpass"),
    )
    assert response.status_code == 403

    # Clean up
    client.delete(
        f"/users/{outsider}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )


def test_add_llm_to_team(client):
    response = client.post(
        f"/teams/{team_id}/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["added_llm"] == test_llm_name


def test_add_embedding_to_team(client):
    response = client.post(
        f"/teams/{team_id}/embeddings/{test_embedding_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["added_embedding"] == test_embedding_name


def test_remove_embedding_from_team(client):
    response = client.delete(
        f"/teams/{team_id}/embeddings/{test_embedding_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["removed_embedding"] == test_embedding_name


def test_remove_llm_from_team(client):
    response = client.delete(
        f"/teams/{team_id}/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["removed_llm"] == test_llm_name


def test_remove_user_from_team(client):
    response = client.delete(
        f"/teams/{team_id}/users/{test_user1}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["removed"] == test_user1


def test_remove_admin_from_team(client):
    response = client.delete(
        f"/teams/{team_id}/admins/{test_user2}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["removed_admin"] == test_user2


def test_delete_team(client):
    response = client.delete(
        f"/teams/{team_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200

    # Verify deleted
    response = client.get(
        f"/teams/{team_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 404


def test_cleanup_dependencies(client):
    # Delete test users
    for username in (test_user1, test_user2):
        response = client.delete(
            f"/users/{username}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200

    # Delete test LLM
    response = client.delete(
        f"/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200

    # Delete test embedding
    response = client.delete(
        f"/embeddings/{test_embedding_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
