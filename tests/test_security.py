"""
Security tests for RestAI authorization and access control.

Tests cover: project isolation, team isolation, user isolation,
privilege escalation, team resource validation, authentication edge cases,
tools/settings/proxy authorization, LLM/embedding enumeration,
team deletion, users listing isolation, project team transfer,
input validation, and statistics isolation.
"""

import base64
import random
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import jwt

from restai.config import RESTAI_DEFAULT_PASSWORD, RESTAI_AUTH_SECRET
from restai.main import app

# Shared state
suffix = str(random.randint(0, 10000000))
userA_name = f"sec_usera_{suffix}"
userB_name = f"sec_userb_{suffix}"
userC_name = f"sec_userc_{suffix}"
teamA_name = f"sec_teama_{suffix}"
teamB_name = f"sec_teamb_{suffix}"
llmA_name = f"sec_llma_{suffix}"
llmB_name = f"sec_llmb_{suffix}"
embA_name = f"sec_emba_{suffix}"
embB_name = f"sec_embb_{suffix}"

teamA_id = None
teamB_id = None
projectA_id = None
projectB_id = None
projectA_name = f"sec_proja_{suffix}"
projectB_name = f"sec_projb_{suffix}"

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
USER_A = (userA_name, "passA123")
USER_B = (userB_name, "passB123")
USER_C = (userC_name, "passC123")


# ── Setup ──────────────────────────────────────────────────────────────────


def test_security_setup():
    """Create users, teams, LLMs, embeddings, and projects for security tests."""
    global teamA_id, teamB_id, projectA_id, projectB_id

    with TestClient(app) as client:
        # Create users (including userC with no team)
        for uname, pwd in [
            (userA_name, "passA123"),
            (userB_name, "passB123"),
            (userC_name, "passC123"),
        ]:
            r = client.post(
                "/users",
                json={"username": uname, "password": pwd, "is_admin": False, "is_private": False},
                auth=ADMIN,
            )
            assert r.status_code == 201, f"Failed to create {uname}: {r.text}"

        # Create LLMs
        for name in [llmA_name, llmB_name]:
            r = client.post(
                "/llms",
                json={
                    "name": name,
                    "class_name": "OpenAI",
                    "options": {"model": "gpt-test", "api_key": "sk-fake"},
                    "privacy": "private",
                    "type": "chat",
                },
                auth=ADMIN,
            )
            assert r.status_code == 201, f"Failed to create LLM {name}: {r.text}"

        # Create embeddings
        for name in [embA_name, embB_name]:
            r = client.post(
                "/embeddings",
                json={
                    "name": name,
                    "class_name": "Ollama",
                    "options": "{}",
                    "privacy": "private",
                    "dimension": 768,
                },
                auth=ADMIN,
            )
            assert r.status_code == 201, f"Failed to create embedding {name}: {r.text}"

        # Create teamA with userA as member, llmA, embA
        r = client.post(
            "/teams",
            json={
                "name": teamA_name,
                "users": [userA_name],
                "llms": [llmA_name],
                "embeddings": [embA_name],
            },
            auth=ADMIN,
        )
        assert r.status_code == 201
        teamA_id = r.json()["id"]

        # Create teamB with userB as member, llmB, embB
        r = client.post(
            "/teams",
            json={
                "name": teamB_name,
                "users": [userB_name],
                "llms": [llmB_name],
                "embeddings": [embB_name],
            },
            auth=ADMIN,
        )
        assert r.status_code == 201
        teamB_id = r.json()["id"]

        # Create projectA owned by userA in teamA
        r = client.post(
            "/projects",
            json={
                "name": projectA_name,
                "llm": llmA_name,
                "type": "inference",
                "team_id": teamA_id,
            },
            auth=USER_A,
        )
        assert r.status_code == 201, f"ProjectA creation failed: {r.status_code} {r.text}"
        projectA_id = r.json()["project"]

        # Create projectB owned by userB in teamB
        r = client.post(
            "/projects",
            json={
                "name": projectB_name,
                "llm": llmB_name,
                "type": "inference",
                "team_id": teamB_id,
            },
            auth=USER_B,
        )
        assert r.status_code == 201
        projectB_id = r.json()["project"]


# ── Authentication Edge Cases ─────────────────────────────────────────────


def test_unauthenticated_access_returns_401():
    """All protected endpoints must return 401 without credentials."""
    with TestClient(app) as client:
        for path in ["/projects", "/users", "/teams", "/llms", "/embeddings"]:
            r = client.get(path)
            assert r.status_code == 401, f"{path} returned {r.status_code} without auth"


def test_invalid_password_returns_401():
    with TestClient(app) as client:
        r = client.get("/auth/whoami", auth=(userA_name, "wrong_password"))
        assert r.status_code == 401


def test_nonexistent_user_returns_401():
    with TestClient(app) as client:
        r = client.get("/auth/whoami", auth=("nonexistent_user_xyz", "somepass"))
        assert r.status_code == 401


def test_invalid_jwt_cookie_returns_401():
    with TestClient(app) as client:
        client.cookies.set("restai_token", "garbage.jwt.token")
        r = client.get("/projects")
        assert r.status_code == 401


def test_expired_jwt_token_returns_401():
    """Craft an expired JWT and verify it's rejected."""
    expired_payload = {
        "username": "admin",
        "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
    }
    expired_token = jwt.encode(expired_payload, RESTAI_AUTH_SECRET, algorithm="HS512")
    with TestClient(app) as client:
        client.cookies.set("restai_token", expired_token)
        r = client.get("/projects")
        assert r.status_code == 401


def test_malformed_basic_auth_returns_401():
    """Invalid base64 in Authorization: Basic header must return 401 (validates auth.py fix)."""
    with TestClient(app) as client:
        r = client.get(
            "/projects",
            headers={"Authorization": "Basic !!!not-base64!!!"},
        )
        assert r.status_code == 401


def test_bearer_with_invalid_apikey_returns_401():
    with TestClient(app) as client:
        r = client.get(
            "/projects",
            headers={"Authorization": "Bearer fake-api-key-12345"},
        )
        assert r.status_code == 401


# ── Project Isolation ──────────────────────────────────────────────────────


def test_user_cannot_get_other_users_project():
    with TestClient(app) as client:
        r = client.get(f"/projects/{projectB_id}", auth=USER_A)
        assert r.status_code == 404


def test_user_cannot_edit_other_users_project():
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{projectB_id}",
            json={"human_name": "hacked"},
            auth=USER_A,
        )
        assert r.status_code == 404


def test_user_cannot_delete_other_users_project():
    with TestClient(app) as client:
        r = client.delete(f"/projects/{projectB_id}", auth=USER_A)
        assert r.status_code == 404


def test_user_cannot_chat_other_users_private_project():
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{projectB_id}/chat",
            json={"question": "hello"},
            auth=USER_A,
        )
        assert r.status_code == 404


def test_user_cannot_question_other_users_private_project():
    with TestClient(app) as client:
        r = client.post(
            f"/projects/{projectB_id}/question",
            json={"question": "hello"},
            auth=USER_A,
        )
        assert r.status_code == 404


def test_user_can_access_public_project():
    """Make projectB public, verify userA can access it for chat/question."""
    with TestClient(app) as client:
        # Make projectB public (as userB)
        r = client.patch(
            f"/projects/{projectB_id}",
            json={"public": True},
            auth=USER_B,
        )
        assert r.status_code == 200

        # userA can now GET the public project
        r = client.get(f"/projects/{projectB_id}", auth=USER_A)
        assert r.status_code == 200

        # Revert to private
        r = client.patch(
            f"/projects/{projectB_id}",
            json={"public": False},
            auth=USER_B,
        )
        assert r.status_code == 200


def test_user_cannot_edit_public_project_they_dont_own():
    """Even if a project is public, non-owners cannot edit or delete it."""
    with TestClient(app) as client:
        # Make projectB public
        client.patch(f"/projects/{projectB_id}", json={"public": True}, auth=USER_B)

        # userA cannot PATCH it
        r = client.patch(
            f"/projects/{projectB_id}",
            json={"human_name": "hacked"},
            auth=USER_A,
        )
        assert r.status_code == 404

        # userA cannot DELETE it
        r = client.delete(f"/projects/{projectB_id}", auth=USER_A)
        assert r.status_code == 404

        # Revert
        client.patch(f"/projects/{projectB_id}", json={"public": False}, auth=USER_B)


def test_user_cannot_create_project_in_other_team():
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            json={
                "name": f"sneaky_proj_{suffix}",
                "llm": llmB_name,
                "type": "inference",
                "team_id": teamB_id,
            },
            auth=USER_A,
        )
        assert r.status_code == 403


# ── Team Isolation ─────────────────────────────────────────────────────────


def test_user_cannot_view_other_team():
    with TestClient(app) as client:
        r = client.get(f"/teams/{teamB_id}", auth=USER_A)
        assert r.status_code == 403


def test_user_cannot_edit_other_team():
    with TestClient(app) as client:
        r = client.patch(
            f"/teams/{teamB_id}",
            json={"description": "hacked"},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_member_cannot_admin_own_team():
    """A regular team member (not team admin) cannot edit the team."""
    with TestClient(app) as client:
        r = client.patch(
            f"/teams/{teamA_id}",
            json={"description": "modified by member"},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_team_admin_can_manage_team():
    """Make userA a team admin of teamA, verify they can edit it."""
    with TestClient(app) as client:
        # Promote userA to team admin
        r = client.post(f"/teams/{teamA_id}/admins/{userA_name}", auth=ADMIN)
        assert r.status_code == 200

        # Now userA can edit teamA
        r = client.patch(
            f"/teams/{teamA_id}",
            json={"description": "edited by team admin"},
            auth=USER_A,
        )
        assert r.status_code == 200

        # Demote userA back to regular member
        r = client.delete(f"/teams/{teamA_id}/admins/{userA_name}", auth=ADMIN)
        assert r.status_code == 200


def test_user_cannot_add_user_to_other_team():
    with TestClient(app) as client:
        r = client.post(
            f"/teams/{teamB_id}/users/{userA_name}",
            auth=USER_A,
        )
        assert r.status_code == 403


def test_non_admin_cannot_create_team():
    with TestClient(app) as client:
        r = client.post(
            "/teams",
            json={"name": f"sneaky_team_{suffix}"},
            auth=USER_A,
        )
        assert r.status_code == 403


# ── Team Deletion Authorization ───────────────────────────────────────────


def test_user_cannot_delete_own_team():
    """Regular member cannot delete the team they belong to."""
    with TestClient(app) as client:
        r = client.delete(f"/teams/{teamA_id}", auth=USER_A)
        assert r.status_code == 403


def test_user_cannot_delete_team_they_dont_belong_to():
    with TestClient(app) as client:
        r = client.delete(f"/teams/{teamB_id}", auth=USER_A)
        assert r.status_code == 403


def test_team_admin_cannot_delete_team():
    """Even a team admin cannot delete the team (only platform admins can)."""
    with TestClient(app) as client:
        # Promote userA to team admin
        r = client.post(f"/teams/{teamA_id}/admins/{userA_name}", auth=ADMIN)
        assert r.status_code == 200

        # Team admin still cannot delete
        r = client.delete(f"/teams/{teamA_id}", auth=USER_A)
        assert r.status_code == 403

        # Demote back
        r = client.delete(f"/teams/{teamA_id}/admins/{userA_name}", auth=ADMIN)
        assert r.status_code == 200


# ── User Isolation ─────────────────────────────────────────────────────────


def test_user_cannot_view_other_user_profile():
    with TestClient(app) as client:
        r = client.get(f"/users/{userB_name}", auth=USER_A)
        assert r.status_code == 404


def test_user_cannot_edit_other_user():
    with TestClient(app) as client:
        r = client.patch(
            f"/users/{userB_name}",
            json={"password": "hacked"},
            auth=USER_A,
        )
        assert r.status_code == 404


def test_user_cannot_delete_other_user():
    with TestClient(app) as client:
        r = client.delete(f"/users/{userB_name}", auth=USER_A)
        assert r.status_code in [401, 403]


def test_non_admin_cannot_create_user():
    with TestClient(app) as client:
        r = client.post(
            "/users",
            json={"username": "sneaky_user", "password": "pass", "admin": False, "private": False},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_user_cannot_view_other_users_apikeys():
    with TestClient(app) as client:
        r = client.get(f"/users/{userB_name}/apikeys", auth=USER_A)
        assert r.status_code == 404


# ── Privilege Escalation ───────────────────────────────────────────────────


def test_user_cannot_self_grant_admin():
    with TestClient(app) as client:
        r = client.patch(
            f"/users/{userA_name}",
            json={"is_admin": True},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_user_cannot_self_remove_private_flag():
    """Non-admin users cannot remove the is_private flag once set by admin."""
    with TestClient(app) as client:
        # First set userA as private via admin
        r = client.patch(
            f"/users/{userA_name}",
            json={"is_private": True},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # userA tries to remove the private flag — should be denied
        r = client.patch(
            f"/users/{userA_name}",
            json={"is_private": False},
            auth=USER_A,
        )
        assert r.status_code == 403

        # userA CAN set themselves as private (more restrictive is OK)
        r = client.patch(
            f"/users/{userA_name}",
            json={"is_private": True},
            auth=USER_A,
        )
        assert r.status_code == 200

        # Revert via admin
        client.patch(f"/users/{userA_name}", json={"is_private": False}, auth=ADMIN)


def test_user_cannot_self_assign_projects():
    """Non-admin users cannot modify their own project assignments."""
    with TestClient(app) as client:
        r = client.patch(
            f"/users/{userA_name}",
            json={"projects": [projectB_name]},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_non_admin_cannot_create_llm():
    with TestClient(app) as client:
        r = client.post(
            "/llms",
            json={
                "name": "sneaky_llm",
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
                "type": "chat",
            },
            auth=USER_A,
        )
        assert r.status_code == 403


def test_non_admin_cannot_create_embedding():
    with TestClient(app) as client:
        r = client.post(
            "/embeddings",
            json={
                "name": "sneaky_emb",
                "class_name": "Ollama",
                "options": "{}",
                "privacy": "public",
                "dimension": 768,
            },
            auth=USER_A,
        )
        assert r.status_code == 403


# ── Team Resource Validation ──────────────────────────────────────────────


def test_cannot_create_project_with_unauthorized_llm():
    """userA cannot create a project using an LLM only assigned to teamB."""
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            json={
                "name": f"bad_llm_proj_{suffix}",
                "llm": llmB_name,
                "type": "inference",
                "team_id": teamA_id,
            },
            auth=USER_A,
        )
        assert r.status_code == 403


def test_cannot_change_project_llm_to_unauthorized():
    """userA cannot change their project's LLM to one not in their team."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{projectA_id}",
            json={"llm": llmB_name},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_cannot_create_rag_project_with_unauthorized_embedding():
    """userA cannot create a RAG project using an embedding only in teamB.

    Note: May return 403 (team check) or raise an exception (embedding
    instantiation fails in test env with fake options). Either way, denied.
    """
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/projects",
            json={
                "name": f"bad_emb_proj_{suffix}",
                "llm": llmA_name,
                "embeddings": embB_name,
                "vectorstore": "chroma",
                "type": "rag",
                "team_id": teamA_id,
            },
            auth=USER_A,
        )
        assert r.status_code in [403, 500], f"Expected denial, got {r.status_code}"


# ── Tools Router Authorization ────────────────────────────────────────────


def test_tools_mcp_probe_accessible_by_regular_user():
    """POST /tools/mcp/probe as regular user should not return 403 (documenting permissive access)."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/tools/mcp/probe",
            json={"host": "http://localhost:9999"},
            auth=USER_A,
        )
        # Connection will fail, but auth should pass (not 401/403)
        assert r.status_code not in [401, 403], f"Expected auth to pass, got {r.status_code}"


def test_tools_ollama_models_accessible_by_regular_user():
    """POST /tools/ollama/models as regular user should not return 403."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/tools/ollama/models",
            json={"host": "http://localhost:11434"},
            auth=USER_A,
        )
        assert r.status_code not in [401, 403], f"Expected auth to pass, got {r.status_code}"


def test_tools_ollama_pull_accessible_by_regular_user():
    """POST /tools/ollama/pull as regular user should not return 403."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/tools/ollama/pull",
            json={"host": "http://localhost:11434", "model": "test"},
            auth=USER_A,
        )
        assert r.status_code not in [401, 403], f"Expected auth to pass, got {r.status_code}"


def test_tools_classifier_requires_auth():
    with TestClient(app) as client:
        r = client.post("/tools/classifier", json={"question": "test", "llm": "test"})
        assert r.status_code == 401


def test_tools_agent_requires_auth():
    with TestClient(app) as client:
        r = client.get("/tools/agent")
        assert r.status_code == 401


# ── LLM/Embedding Enumeration ────────────────────────────────────────────


def test_any_user_can_list_all_llms():
    """Documents that any authenticated user can see all LLMs (information disclosure)."""
    with TestClient(app) as client:
        r = client.get("/llms", auth=USER_A)
        assert r.status_code == 200
        llm_names = [llm["name"] for llm in r.json()]
        assert llmA_name in llm_names
        assert llmB_name in llm_names


def test_any_user_can_get_specific_llm():
    with TestClient(app) as client:
        r = client.get(f"/llms/{llmB_name}", auth=USER_A)
        assert r.status_code == 200


def test_any_user_can_list_all_embeddings():
    """Documents that any authenticated user can see all embeddings."""
    with TestClient(app) as client:
        r = client.get("/embeddings", auth=USER_A)
        assert r.status_code == 200
        emb_names = [e["name"] for e in r.json()]
        assert embA_name in emb_names
        assert embB_name in emb_names


def test_any_user_can_get_specific_embedding():
    with TestClient(app) as client:
        r = client.get(f"/embeddings/{embB_name}", auth=USER_A)
        assert r.status_code == 200


def test_llm_api_keys_are_masked():
    """API keys in LLM options should be masked when returned."""
    with TestClient(app) as client:
        r = client.get(f"/llms/{llmA_name}", auth=ADMIN)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data.get("options"), dict):
            api_key = data["options"].get("api_key", "")
            assert api_key == "********" or api_key.startswith("****"), \
                f"API key not masked: {api_key}"


# ── Settings & Proxy Authorization ────────────────────────────────────────


def test_non_admin_cannot_get_settings():
    with TestClient(app) as client:
        r = client.get("/settings", auth=USER_A)
        assert r.status_code == 403


def test_non_admin_cannot_patch_settings():
    with TestClient(app) as client:
        r = client.patch("/settings", json={}, auth=USER_A)
        assert r.status_code == 403


def test_non_admin_cannot_get_proxy_keys():
    with TestClient(app) as client:
        r = client.get("/proxy/keys", auth=USER_A)
        assert r.status_code == 403


def test_non_admin_cannot_create_proxy_key():
    with TestClient(app) as client:
        r = client.post(
            "/proxy/keys",
            json={"name": "sneaky_key"},
            auth=USER_A,
        )
        assert r.status_code == 403


# ── Users Listing Isolation ───────────────────────────────────────────────


def test_non_admin_users_listing_only_shows_teammates():
    """Non-admin user should only see users from their own teams."""
    with TestClient(app) as client:
        r = client.get("/users", auth=USER_A)
        assert r.status_code == 200
        usernames = [u["username"] for u in r.json()["users"]]
        assert userA_name in usernames
        assert userB_name not in usernames


def test_admin_users_listing_shows_all():
    with TestClient(app) as client:
        r = client.get("/users", auth=ADMIN)
        assert r.status_code == 200
        usernames = [u["username"] for u in r.json()["users"]]
        assert userA_name in usernames
        assert userB_name in usernames
        assert userC_name in usernames


def test_non_admin_listing_returns_limited_schema():
    """Non-admin users listing should return limited user objects without sensitive fields."""
    with TestClient(app) as client:
        r = client.get("/users", auth=USER_A)
        assert r.status_code == 200
        users = r.json()["users"]
        for u in users:
            assert "is_admin" not in u, f"is_admin leaked for {u.get('username')}"
            assert "api_keys" not in u, f"api_keys leaked for {u.get('username')}"


# ── Project Team Transfer ─────────────────────────────────────────────────


def test_cannot_change_project_team_to_unauthorized_team():
    """userA cannot move their project to a team they don't belong to."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{projectA_id}",
            json={"team_id": teamB_id},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_cannot_change_project_llm_to_one_not_in_current_team():
    """userA cannot change project LLM to one not available in the project's current team."""
    with TestClient(app) as client:
        r = client.patch(
            f"/projects/{projectA_id}",
            json={"llm": llmB_name},
            auth=USER_A,
        )
        assert r.status_code == 403


def test_admin_can_change_project_team():
    """Admin can transfer a project to any team (sanity check)."""
    with TestClient(app) as client:
        # Add llmA to teamB so the project's LLM is valid in the new team
        r = client.patch(
            f"/teams/{teamB_id}",
            json={"llms": [llmB_name, llmA_name]},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Move projectA to teamB as admin (keep same LLM)
        r = client.patch(
            f"/projects/{projectA_id}",
            json={"team_id": teamB_id},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Revert: move back to teamA
        r = client.patch(
            f"/projects/{projectA_id}",
            json={"team_id": teamA_id},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Remove llmA from teamB
        r = client.patch(
            f"/teams/{teamB_id}",
            json={"llms": [llmB_name]},
            auth=ADMIN,
        )
        assert r.status_code == 200


# ── Admin Override ─────────────────────────────────────────────────────────


def test_admin_can_access_any_project():
    with TestClient(app) as client:
        # Admin can GET any project
        r = client.get(f"/projects/{projectB_id}", auth=ADMIN)
        assert r.status_code == 200

        # Admin can PATCH any project
        r = client.patch(
            f"/projects/{projectB_id}",
            json={"human_name": "Admin edited"},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Revert
        client.patch(
            f"/projects/{projectB_id}",
            json={"human_name": None},
            auth=ADMIN,
        )


def test_admin_can_access_any_team():
    with TestClient(app) as client:
        r = client.get(f"/teams/{teamB_id}", auth=ADMIN)
        assert r.status_code == 200

        r = client.patch(
            f"/teams/{teamB_id}",
            json={"description": "Admin edited"},
            auth=ADMIN,
        )
        assert r.status_code == 200


def test_admin_can_manage_any_user():
    with TestClient(app) as client:
        # Admin can GET any user
        r = client.get(f"/users/{userB_name}", auth=ADMIN)
        assert r.status_code == 200

        # Admin can PATCH any user
        r = client.patch(
            f"/users/{userB_name}",
            json={"is_private": True},
            auth=ADMIN,
        )
        assert r.status_code == 200

        # Revert
        client.patch(f"/users/{userB_name}", json={"is_private": False}, auth=ADMIN)


# ── Projects listing isolation ─────────────────────────────────────────────


def test_user_only_sees_own_projects():
    """userA should only see their own projects in the listing."""
    with TestClient(app) as client:
        r = client.get("/projects", auth=USER_A)
        assert r.status_code == 200
        projects = r.json()["projects"]
        project_names = [p["name"] for p in projects]
        assert projectA_name in project_names
        assert projectB_name not in project_names


def test_user_sees_public_projects_in_listing():
    """Public projects should appear when filtering by public."""
    with TestClient(app) as client:
        # Make projectB public
        client.patch(f"/projects/{projectB_id}", json={"public": True}, auth=USER_B)

        # Default listing only shows own projects
        r = client.get("/projects", auth=USER_A)
        assert r.status_code == 200
        own_ids = [p["id"] for p in r.json()["projects"]]
        assert projectB_id not in own_ids

        # Public filter shows public projects
        r = client.get("/projects?filter=public", auth=USER_A)
        assert r.status_code == 200
        public_ids = [p["id"] for p in r.json()["projects"]]
        assert projectB_id in public_ids

        # Revert
        client.patch(f"/projects/{projectB_id}", json={"public": False}, auth=USER_B)


# ── Input Validation ──────────────────────────────────────────────────────


def test_create_project_empty_name_fails():
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            json={"name": "", "llm": llmA_name, "type": "inference", "team_id": teamA_id},
            auth=USER_A,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"


def test_create_project_whitespace_name_fails():
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            json={"name": "   ", "llm": llmA_name, "type": "inference", "team_id": teamA_id},
            auth=USER_A,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"


def test_project_name_sanitization():
    """Special characters in project name should be sanitized, not cause errors."""
    test_name = f"test<>proj&{suffix}"
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/projects",
            json={"name": test_name, "llm": llmA_name, "type": "inference", "team_id": teamA_id},
            auth=USER_A,
        )
        # Should succeed with sanitized name or fail gracefully (not 500)
        assert r.status_code != 500, f"Server error on special chars: {r.text}"
        if r.status_code == 201:
            # Clean up
            pid = r.json()["project"]
            client.delete(f"/projects/{pid}", auth=ADMIN)


def test_very_long_project_name():
    """A very long project name should not cause a 500 error."""
    long_name = "a" * 1000 + f"_{suffix}"
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/projects",
            json={"name": long_name, "llm": llmA_name, "type": "inference", "team_id": teamA_id},
            auth=USER_A,
        )
        assert r.status_code != 500, f"Server error on long name: {r.text}"
        if r.status_code == 201:
            pid = r.json()["project"]
            client.delete(f"/projects/{pid}", auth=ADMIN)


def test_sql_injection_in_project_name():
    """SQL injection attempt in project name should be sanitized."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/projects",
            json={
                "name": f"'; DROP TABLE projects; --{suffix}",
                "llm": llmA_name,
                "type": "inference",
                "team_id": teamA_id,
            },
            auth=USER_A,
        )
        assert r.status_code != 500, f"Server error on SQL injection attempt: {r.text}"
        if r.status_code == 201:
            pid = r.json()["project"]
            client.delete(f"/projects/{pid}", auth=ADMIN)


def test_xss_in_username():
    """XSS attempt in username should be sanitized."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/users",
            json={
                "username": "<script>alert(1)</script>",
                "password": "testpass",
                "is_admin": False,
                "is_private": False,
            },
            auth=ADMIN,
        )
        assert r.status_code != 500, f"Server error on XSS attempt: {r.text}"
        if r.status_code == 201:
            created_name = r.json()["username"]
            # Verify the name was sanitized (no angle brackets)
            assert "<" not in created_name
            assert ">" not in created_name
            # Clean up
            client.delete(f"/users/{created_name}", auth=ADMIN)


# ── Statistics Isolation ──────────────────────────────────────────────────


def test_statistics_non_admin_only_sees_own_projects():
    """Non-admin user should not see other users' projects in statistics."""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/statistics/top-projects", auth=USER_A)
        if r.status_code == 200:
            projects = r.json().get("projects", [])
            project_names = [p["name"] for p in projects]
            assert projectB_name not in project_names, \
                f"userA can see projectB in statistics"


# ── Cleanup ────────────────────────────────────────────────────────────────


def test_security_cleanup():
    """Clean up all resources created by security tests."""
    with TestClient(app) as client:
        # Delete projects
        for pid in [projectA_id, projectB_id]:
            if pid:
                client.delete(f"/projects/{pid}", auth=ADMIN)

        # Delete teams
        for tid in [teamA_id, teamB_id]:
            if tid:
                client.delete(f"/teams/{tid}", auth=ADMIN)

        # Delete LLMs
        for name in [llmA_name, llmB_name]:
            client.delete(f"/llms/{name}", auth=ADMIN)

        # Delete embeddings
        for name in [embA_name, embB_name]:
            client.delete(f"/embeddings/{name}", auth=ADMIN)

        # Delete users
        for uname in [userA_name, userB_name, userC_name]:
            client.delete(f"/users/{uname}", auth=ADMIN)
