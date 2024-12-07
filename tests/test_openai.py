from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == "RESTAI, so many 'A's and 'I's, so little time..."


def test_get_projects():
    response = client.get("/projects", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == []


def test_create_project():
    response = client.post(
        "/projects", json={"name": "test_openai", "embeddings": "openai", "llm": "openai"}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_get_project():
    response = client.get("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 200


def test_create_project2():
    response = client.post(
        "/projects", json={"name": "test_openai2", "embeddings": "openai", "llm": "openai"}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_get_projects2():
    response = client.get("/projects", auth=("admin", "admin"))
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_ingest_url():
    response = client.post("/projects/test_openai/embeddings/ingest/url",
                           json={"url": "https://info.cern.ch/"}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_get_project_after_ingest_url():
    response = client.get("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json()["documents"] == 1


def test_ingest_upload():
    response = client.post("/projects/test_openai/embeddings/ingest/upload",
                           files={"file": ("test.txt", open("tests/test.txt", "rb"))}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_get_project_after_ingest_upload():
    response = client.get("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json()["documents"] == 2


def test_ingest_upload2():
    response = client.post("/projects/test_openai/embeddings/ingest/upload",
                           files={"file": ("test2.txt", open("tests/test2.txt", "rb"))}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_get_embeddings():
    response = client.post(
        "/projects/test_openai/embeddings/find", json={"source": "test2.txt"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert len(response.json()["ids"]) == 1


def test_delete_embeddings():
    response = client.delete(
        "/projects/test_openai/embeddings/files/dGVzdDIudHh0", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == {"deleted": 1}


def test_get_embeddings_after_delete():
    response = client.post(
        "/projects/test_openai/embeddings/find", json={"source": "test2.txt"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert len(response.json()["ids"]) == 0


def test_question_project():
    response = client.post("/projects/test_openai/question",
                           json={"question": "What is the secret?"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json()[
               "answer"] == "The secret is that ingenuity should be bigger than politics and corporate greed."


def test_question_project2():
    response = client.post("/projects/test_openai2/question",
                           json={"question": "What is the secret?"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert "ingenuity" not in response.json()["answer"]


def test_question_system_project():
    response = client.post("/projects/test_openai/question",
                           json={"system": "You are a digital assistant, answer only in french.",
                                 "question": "What is the secret?"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert "Le secret" in response.json()["answer"]


def test_chat_project():
    response1 = client.post("/projects/test_openai/chat",
                            json={"message": "What is the secret?"}, auth=("admin", "admin"))
    assert response1.status_code == 200
    output1 = response1.json()
    response2 = client.post("/projects/test_openai/chat",
                            json={"message": "Do you agree with this secret?", "id": output1["id"]},
                            auth=("admin", "admin"))
    assert response2.status_code == 200

def test_reset_project():
    response = client.post(
        "/projects/test_openai/embeddings/reset", auth=("admin", "admin"))
    assert response.status_code == 200


def test_question_project_after_reset():
    response = client.post("/projects/test_openai/question",
                           json={"question": "What is the secret?"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert "ingenuity" not in response.json()["answer"]


def test_get_project_after_ingest_upload_after_reset():
    response = client.get("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json()["documents"] == 0


def test_ingest_upload_json_after_reset():
    # response = client.post("/projects/test_openai/embeddings/ingest/upload", files={"file": ("test.txt", open("tests/test.txt", "rb"))}, auth=("admin", "admin"))
    options = {"options": "{\"jq_schema\": \".messages[].content\"}"}
    response = client.post("/projects/test_openai/embeddings/ingest/upload", data=options,
                           files={"file": ("test.json", open("tests/test.json", "rb"))}, auth=("admin", "admin"))
    assert response.status_code == 200


def test_question_project_after_reset_after_ingest():
    response = client.post("/projects/test_openai/question",
                           json={"question": "What is the secret?"}, auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json()[
               "answer"] == "The secret is that ingenuity should be bigger than politics and corporate greed."


def test_delete_project():
    response = client.delete("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == {"project": "test_openai"}


def test_delete_project2():
    response = client.delete("/projects/test_openai2", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == {"project": "test_openai2"}


def test_get_project_after_delete():
    response = client.get("/projects/test_openai", auth=("admin", "admin"))
    assert response.status_code == 404


def test_get_projects_after_delete():
    response = client.get("/projects", auth=("admin", "admin"))
    assert response.status_code == 200
    assert response.json() == []
