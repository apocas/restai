import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

suffix = str(random.randint(0, 10000000))
team_name = f"evals_team_{suffix}"
llm_name = f"evals_llm_{suffix}"
project_name = f"evals_proj_{suffix}"

team_id = None
project_id = None
dataset_id = None
case_id = None

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)


def test_setup():
    """Create team, LLM, and block project for evaluation tests."""
    global team_id, project_id
    with TestClient(app) as client:
        # Create LLM
        client.post(
            "/llms",
            json={
                "name": llm_name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
            },
            auth=ADMIN,
        )

        # Create team
        resp = client.post(
            "/teams",
            json={"name": team_name, "users": [], "admins": [], "llms": [llm_name]},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        team_id = resp.json()["id"]

        # Create block project
        resp = client.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        project_id = resp.json()["project"]


def test_create_dataset():
    """Create an evaluation dataset."""
    global dataset_id
    with TestClient(app) as client:
        resp = client.post(
            f"/projects/{project_id}/evals/datasets",
            json={"name": "test-dataset"},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-dataset"
        assert data["project_id"] == project_id
        assert "id" in data
        dataset_id = data["id"]


def test_list_datasets():
    """List datasets for the project includes the created dataset."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/evals/datasets", auth=ADMIN
        )
        assert resp.status_code == 200
        datasets = resp.json()
        assert any(d["id"] == dataset_id for d in datasets)


def test_get_dataset():
    """Get dataset details by ID."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/evals/datasets/{dataset_id}", auth=ADMIN
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == dataset_id
        assert data["name"] == "test-dataset"
        assert "test_cases" in data
        assert isinstance(data["test_cases"], list)


def test_add_test_case():
    """Add a test case to the dataset."""
    global case_id
    with TestClient(app) as client:
        resp = client.post(
            f"/projects/{project_id}/evals/datasets/{dataset_id}/cases",
            json={"question": "What is 2+2?", "expected_answer": "4"},
            auth=ADMIN,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["question"] == "What is 2+2?"
        assert data["expected_answer"] == "4"
        assert "id" in data
        case_id = data["id"]


def test_update_dataset():
    """Update the dataset name."""
    with TestClient(app) as client:
        resp = client.patch(
            f"/projects/{project_id}/evals/datasets/{dataset_id}",
            json={"name": "updated-dataset"},
            auth=ADMIN,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated-dataset"


def test_list_runs_empty():
    """No evaluation runs exist initially."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/evals/runs", auth=ADMIN
        )
        assert resp.status_code == 200
        assert resp.json() == []


def test_get_nonexistent_dataset():
    """Getting a dataset that doesn't exist returns 404."""
    with TestClient(app) as client:
        resp = client.get(
            f"/projects/{project_id}/evals/datasets/999999", auth=ADMIN
        )
        assert resp.status_code == 404


def test_delete_test_case():
    """Delete a test case from the dataset."""
    with TestClient(app) as client:
        resp = client.delete(
            f"/projects/{project_id}/evals/datasets/{dataset_id}/cases/{case_id}",
            auth=ADMIN,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify test case is gone
        resp = client.get(
            f"/projects/{project_id}/evals/datasets/{dataset_id}", auth=ADMIN
        )
        assert resp.json()["test_case_count"] == 0


def test_delete_dataset():
    """Delete the dataset."""
    with TestClient(app) as client:
        resp = client.delete(
            f"/projects/{project_id}/evals/datasets/{dataset_id}", auth=ADMIN
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify dataset is gone
        resp = client.get(
            f"/projects/{project_id}/evals/datasets/{dataset_id}", auth=ADMIN
        )
        assert resp.status_code == 404


def test_cleanup():
    """Remove all test resources."""
    with TestClient(app) as client:
        if project_id:
            client.delete(f"/projects/{project_id}", auth=ADMIN)
        if team_id:
            client.delete(f"/teams/{team_id}", auth=ADMIN)
        client.delete(f"/llms/{llm_name}", auth=ADMIN)
