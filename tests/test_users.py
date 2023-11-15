from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "RESTAI, so many 'A's and 'I's, so little time..."


def test_getUsers():
    response = client.get("/users", auth=("admin", "admin"))
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_createUser():
    response = client.post(
        "/users", json={"username": "test",  "password": "test"}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_getUser():
    response = client.get("/users/test", auth=("admin", "admin"))
    assert response.status_code == 200

def test_getAdminfromUser():
    response = client.get("/users/admin", auth=("test", "test"))
    assert response.status_code == 404

def test_createProjectUser():
    response = client.post(
        "/projects", json={"name": "test1",  "embeddings": "huggingface", "llm": "openai_gpt4_turbo"}, auth=("test", "test"))
    assert response.status_code == 200
    
def test_createProjectAdmin():
    response = client.post(
        "/projects", json={"name": "test2",  "embeddings": "huggingface", "llm": "openai_gpt4_turbo"}, auth=("admin", "admin"))
    assert response.status_code == 200

def test_getProjectsUser():
    response = client.get("/projects", auth=("test", "test"))
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_getProjectsAdmin():
    response = client.get("/projects", auth=("admin", "admin"))
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_deleteUser():
    response = client.delete("/users/test", auth=("admin", "admin"))
    assert response.status_code == 200
    
def test_deleteProject1():
    response = client.delete("/projects/test1", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == {"project": "test1"}
    
def test_deleteProjectUser():
    response = client.delete("/projects/test2", auth=("test", "test"))
    assert response.status_code == 401
    
def test_deleteProject2():
    response = client.delete("/projects/test2", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == {"project": "test2"}