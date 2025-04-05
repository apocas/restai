from fastapi.testclient import TestClient

from restai.main import app

def test_get():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == "RESTai, so many 'A's and 'I's, so little time..."