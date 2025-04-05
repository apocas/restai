import random
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

project_id = None

def test_create_project():
    with TestClient(app) as client:
        response = client.post(
            "/projects", json={"name": "test_project" + str(random.randint(0, 1000000)), "llm": "llama31_8b", "type": "inference"}, auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        global project_id
        project_id = response.json()["project"]

def test_get_projects():
    with TestClient(app) as client:
        response = client.get("/projects", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert len(response.json()["projects"]) > 0

def test_get_project():
    with TestClient(app) as client:
        response = client.get("/projects/" + str(project_id), auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert response.json()["id"] == project_id

def test_delete_project():
    with TestClient(app) as client:
        response = client.delete("/projects/" + str(project_id), auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200

