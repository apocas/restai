import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_get_agent_tools(client):
    response = client.get("/tools/agent", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for tool in data:
        assert "name" in tool
        assert "description" in tool


def test_get_agent_tools_no_auth(client):
    response = client.get("/tools/agent")
    assert response.status_code == 401


def test_mcp_probe_invalid_host(client):
    response = client.post(
        "/tools/mcp/probe",
        json={"host": "http://localhost:99999"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    # Should fail to connect — 502 or 500
    assert response.status_code in (500, 502)


def test_mcp_probe_no_auth(client):
    response = client.post(
        "/tools/mcp/probe",
        json={"host": "http://localhost:99999"},
    )
    assert response.status_code == 401
