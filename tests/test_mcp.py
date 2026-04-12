"""Tests for the internal MCP server (restai/mcp.py)."""

import asyncio
import json
import random
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
user_name = f"mcp_user_{suffix}"
user_pass = "mcp_pass_123"
team_name = f"mcp_team_{suffix}"
llm_name = f"mcp_llm_{suffix}"
project_name = f"mcp-proj-{suffix}"

team_id = None
project_id = None
api_key = None
admin_api_key = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_mcp_setup(client):
    """Create user, team, LLM, project, and API keys for MCP tests."""
    global team_id, project_id, api_key, admin_api_key

    # Create user
    r = client.post(
        "/users",
        json={"username": user_name, "password": user_pass, "is_admin": False, "is_private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201, f"Failed to create user: {r.text}"

    # Create LLM
    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code in (200, 201), f"Failed to create LLM: {r.text}"

    # Create team with user and LLM
    r = client.post(
        "/teams",
        json={
            "name": team_name,
            "users": [user_name],
            "admins": [],
            "llms": [llm_name],
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, f"Failed to create team: {r.text}"
    team_id = r.json()["id"]

    # Create project
    r = client.post(
        "/projects",
        json={
            "name": project_name,
            "llm": llm_name,
            "type": "agent",
            "team_id": team_id,
            "human_description": "Test project for MCP",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, f"Failed to create project: {r.text}"
    project_id = r.json()["project"]

    # Assign project to user
    r = client.patch(
        f"/projects/{project_id}",
        json={"users": [user_name]},
        auth=ADMIN,
    )
    assert r.status_code == 200, f"Failed to assign project: {r.text}"

    # Create API key for user
    r = client.post(
        f"/users/{user_name}/apikeys",
        json={"description": "mcp test key"},
        auth=(user_name, user_pass),
    )
    assert r.status_code == 201, f"Failed to create API key: {r.text}"
    api_key = r.json()["api_key"]

    # Create API key for admin
    r = client.post(
        "/users/admin/apikeys",
        json={"description": "mcp admin key"},
        auth=ADMIN,
    )
    assert r.status_code == 201, f"Failed to create admin API key: {r.text}"
    admin_api_key = r.json()["api_key"]


# ── Authentication tests ─────────────────────────────────────────────────


def test_mcp_auth_missing_header():
    """MCP auth with no Authorization header should fail."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        try:
            _authenticate()
            assert False, "Should have raised PermissionError"
        except PermissionError as e:
            assert "Bearer" in str(e)


def test_mcp_auth_basic_rejected():
    """MCP auth with Basic auth should be rejected."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": "Basic dXNlcjpwYXNz"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        try:
            _authenticate()
            assert False, "Should have raised PermissionError"
        except PermissionError as e:
            assert "Bearer" in str(e)


def test_mcp_auth_invalid_key():
    """MCP auth with invalid Bearer key should fail."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": "Bearer invalid-key-12345"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        try:
            _authenticate()
            assert False, "Should have raised PermissionError"
        except PermissionError as e:
            assert "Invalid" in str(e)


def test_mcp_auth_valid_user_key():
    """MCP auth with valid user API key should return the user."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {api_key}"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        user, db_wrapper = _authenticate()
        try:
            assert user.username == user_name
            assert not user.is_admin
        finally:
            db_wrapper.db.close()


def test_mcp_auth_valid_admin_key():
    """MCP auth with valid admin API key should return admin user."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {admin_api_key}"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        user, db_wrapper = _authenticate()
        try:
            assert user.username == "admin"
            assert user.is_admin
        finally:
            db_wrapper.db.close()


# ── Access control tests ─────────────────────────────────────────────────


def test_mcp_user_has_project_access():
    """User should have access to their assigned project."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {api_key}"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        user, db_wrapper = _authenticate()
        try:
            assert user.has_project_access(project_id)
        finally:
            db_wrapper.db.close()


def test_mcp_user_no_access_to_unassigned():
    """User should not have access to unassigned projects."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {api_key}"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        user, db_wrapper = _authenticate()
        try:
            assert not user.has_project_access(999999)
        finally:
            db_wrapper.db.close()


def test_mcp_admin_has_access_to_all():
    """Admin should have access to any project."""
    from restai.mcp import _authenticate

    mock_request = MagicMock()
    mock_request.headers = {"authorization": f"Bearer {admin_api_key}"}

    with patch("restai.mcp.get_http_request", return_value=mock_request):
        user, db_wrapper = _authenticate()
        try:
            assert user.has_project_access(project_id)
            assert user.has_project_access(999999)  # Admin bypasses check
        finally:
            db_wrapper.db.close()


# ── Server creation tests ────────────────────────────────────────────────


def test_mcp_server_has_tools():
    """MCP server should have list_projects and query_project tools."""
    from restai.mcp import create_mcp_server

    mcp = create_mcp_server(MagicMock())
    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}
    assert "list_projects" in tool_names
    assert "query_project" in tool_names


def test_mcp_server_name():
    """MCP server should be named RestAI."""
    from restai.mcp import create_mcp_server

    mcp = create_mcp_server(MagicMock())
    assert mcp.name == "RestAI"


def test_mcp_server_produces_sse_app():
    """MCP server should produce a valid SSE ASGI app."""
    from restai.mcp import create_mcp_server

    mcp = create_mcp_server(MagicMock())
    sse_app = mcp.http_app(transport="sse")
    assert sse_app is not None


# ── Teardown ─────────────────────────────────────────────────────────────


def test_mcp_teardown(client):
    """Clean up resources created for MCP tests."""
    # Delete project before team to avoid orphaned records
    if project_id:
        client.delete(f"/projects/{project_id}", auth=ADMIN)
    if team_id:
        client.delete(f"/teams/{team_id}", auth=ADMIN)
    client.delete(f"/users/{user_name}", auth=ADMIN)
    client.delete(f"/llms/{llm_name}", auth=ADMIN)
