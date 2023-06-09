from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "REST AI API, so many 'A's and 'I's, so little time..."


def test_getProjects():
    response = client.get("/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}


def test_createProject():
    response = client.post(
        "/projects", json={"name": "test_openai",  "embeddings": "openai", "llm": "openai"})
    assert response.status_code == 200


def test_getProject():
    response = client.get("/projects/test_openai")
    assert response.status_code == 200


def test_ingestURL():
    response = client.post("/projects/test_openai/ingest/url",
                           json={"url": "https://www.google.com"})
    assert response.status_code == 200


def test_getProjectAfterIngestURL():
    response = client.get("/projects/test_openai")
    assert response.status_code == 200
    assert response.json() == {
        "project": "test_openai", "embeddings": "openai", "documents": 1, "metadatas": 1}


def test_ingestUpload():
    response = client.post("/projects/test_openai/ingest/upload",
                           files={"file": ("test.txt", open("tests/test.txt", "rb"))})
    assert response.status_code == 200


def test_getProjectAfterIngestUpload():
    response = client.get("/projects/test_openai")
    assert response.status_code == 200
    assert response.json() == {
        "project": "test_openai", "embeddings": "openai", "documents": 2, "metadatas": 2}


def test_questionProject():
    response = client.post("/projects/test_openai/question",
                           json={"question": "What is the secret?"})
    assert response.status_code == 200
    assert response.json() == {"question": "What is the secret?",
                               "answer": "The secret is that ingenuity should be bigger than politics and corporate greed."}


def test_questionSystemProject():
    response = client.post("/projects/test_openai/question",
                           json={"system": "You are a digital assistant, answer only in french.", "question": "What is the secret?"})
    assert response.status_code == 200
    assert response.json() == {"question": "What is the secret?",
                               "answer": "Le secret est que l'ingéniosité doit être plus grande que la politique et la cupidité des entreprises."}

def test_chatProject():
    response1 = client.post("/projects/test_openai/chat",
                            json={"message": "What is the secret?"})
    assert response1.status_code == 200
    output1 = response1.json()
    response2 = client.post("/projects/test_openai/chat",
                            json={"message": "Do you agree with this secret?", "id": output1["id"]})
    assert response2.status_code == 200
    output2 = response2.json()


def test_deleteProject():
    response = client.delete("/projects/test_openai")
    assert response.status_code == 200
    assert response.json() == {"project": "test_openai"}


def test_getProjectAfterDelete():
    response = client.get("/projects/test_openai")
    assert response.status_code == 404


def test_getProjectsAfterDelete():
    response = client.get("/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}
