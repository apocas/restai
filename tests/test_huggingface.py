from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "REST AI API, so many 'A's and 'I's, so little time..."


def test_createProjectHF():
    response = client.post(
        "/projects", json={"name": "test_huggingface",  "embeddings": "huggingface"})
    assert response.status_code == 200


def test_getProjectHF():
    response = client.get("/projects/test_huggingface")
    assert response.status_code == 200


def test_ingestURLHF():
    response = client.post("/projects/test_huggingface/ingest/url",
                           json={"url": "https://www.google.com"})
    assert response.status_code == 200


def test_getProjectAfterIngestURLHF():
    response = client.get("/projects/test_huggingface")
    assert response.status_code == 200
    assert response.json() == {
        "project": "test_huggingface", "embeddings": "huggingface", "documents": 1, "metadatas": 1}


def test_ingestUploadHF():
    response = client.post("/projects/test_huggingface/ingest/upload",
                           files={"file": ("test.txt", open("tests/test.txt", "rb"))})
    assert response.status_code == 200


def test_getProjectAfterIngestUploadHF():
    response = client.get("/projects/test_huggingface")
    assert response.status_code == 200
    assert response.json() == {
        "project": "test_huggingface", "embeddings": "huggingface", "documents": 2, "metadatas": 2}


def test_questionProjectHF():
    response = client.post("/projects/test_huggingface/question",
                           json={"question": "What is the secret?", "llm": "gpt4all"})
    assert response.status_code == 200
    assert response.json() == {"question": "What is the secret?",
                               "answer": "The secret is that ingenuity should be bigger than politics and corporate greed."}


def test_deleteProjectHF():
    response = client.delete("/projects/test_huggingface")
    assert response.status_code == 200
    assert response.json() == {"project": "test_huggingface"}


def test_getProjectsAfterDelete():
    response = client.get("/projects")
    assert response.status_code == 200
    assert response.json() == {"projects": []}
