import random
import json
import base64
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.models.models import ProjectModelCreate, ProjectModelUpdate, FindModel, TextIngestModel, URLIngestModel, ChatModel, QuestionModel

project_id = None
test_project_name = "test_project_" + str(random.randint(0, 1000000))

def test_create_project():
    with TestClient(app) as client:
        response = client.post(
            "/projects", 
            json={
                "name": test_project_name, 
                "llm": "llama31_8b",
                "embeddings": "all-mpnet-base-v2",
                "vectorstore": "chroma",
                "type": "rag",
                "human_name": "Test Project",
                "human_description": "A test project",
                "censorship": False,
                "guard": False,
                "public": False,
                "options": {}
            }, 
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        global project_id
        project_id = response.json()["project"]

def test_get_projects():
    with TestClient(app) as client:
        # Test getting all projects
        response = client.get("/projects", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert len(response.json()["projects"]) > 0
        
        # Test filtering public projects
        response = client.get("/projects?filter=public", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        
        # Test pagination
        response = client.get("/projects?start=0&end=5", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert len(response.json()["projects"]) <= 5

def test_get_project():
    with TestClient(app) as client:
        response = client.get(f"/projects/{project_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == test_project_name
        assert data["type"] == "rag"
        assert data["llm"] == "llama31_8b"
        assert data["embeddings"] == "all-mpnet-base-v2"
        assert data["human_name"] == "Test Project"
        assert data["human_description"] == "A test project"
        assert data["public"] == False

def test_edit_project():
    with TestClient(app) as client:
        updated_name = "updated_" + test_project_name
        response = client.patch(
            f"/projects/{project_id}", 
            json={
                "name": updated_name,
                "human_name": "Updated Test Project",
                "human_description": "An updated test project",
                "public": True
            }, 
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        assert response.json()["project"] == project_id
        
        # Verify changes
        response = client.get(f"/projects/{project_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == updated_name
        assert data["human_name"] == "Updated Test Project"
        assert data["human_description"] == "An updated test project"
        assert data["public"] == True

def test_embeddings_endpoints():
    with TestClient(app) as client:
        # Test reset embeddings
        response = client.post(
            f"/projects/{project_id}/embeddings/reset", 
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test search embeddings
        response = client.post(
            f"/projects/{project_id}/embeddings/search",
            json={"query": "test query", "k": 5},
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test ingest text
        response = client.post(
            f"/projects/{project_id}/embeddings/ingest/text",
            json={"text": "This is a test document for embedding.", "source": "test_doc"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test ingest URL
        response = client.post(
            f"/projects/{project_id}/embeddings/ingest/url",
            json={"url": "http://info.cern.ch/", "source": "example"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test get embeddings
        response = client.get(
            f"/projects/{project_id}/embeddings",
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test get embedding by source
        response = client.get(
            f"/projects/{project_id}/embeddings/source/" + base64.b64encode(b"test_doc").decode("utf-8"),
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test delete embedding
        response = client.delete(
            f"/projects/{project_id}/embeddings/" + base64.b64encode(b"test_doc").decode("utf-8"),
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200

def test_chat_and_question_endpoints():
    with TestClient(app) as client:
        # Test chat endpoint
        response = client.post(
            f"/projects/{project_id}/chat",
            json={"question": "Hello, how are you?"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test question endpoint
        response = client.post(
            f"/projects/{project_id}/question",
            json={"question": "What is this project about?"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200

def test_logs_endpoints():
    with TestClient(app) as client:
        # Test get logs
        response = client.get(
            f"/projects/{project_id}/logs",
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test get daily token consumption
        response = client.get(
            f"/projects/{project_id}/tokens/daily",
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200
        
        # Test get monthly token consumption with specific month
        response = client.get(
            f"/projects/{project_id}/tokens/daily?year=2023&month=12",
            auth=("admin", RESTAI_DEFAULT_PASSWORD)
        )
        assert response.status_code == 200

def test_delete_project():
    with TestClient(app) as client:
        response = client.delete(f"/projects/{project_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        assert response.json()["project"] == project_id
        
        # Verify project is deleted
        response = client.get(f"/projects/{project_id}", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 404

