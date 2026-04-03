import random
from fastapi.testclient import TestClient

from restai import config
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

test_user = "test_settings_user_" + str(random.randint(0, 1000000))


def test_get_settings():
    with TestClient(app) as client:
        response = client.get("/settings", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        data = response.json()
        for key in (
            "app_name",
            "hide_branding",
            "proxy_enabled",
            "agent_max_iterations",
            "max_audio_upload_size",
        ):
            assert key in data


def test_get_settings_non_admin():
    with TestClient(app) as client:
        # Create non-admin user
        client.post(
            "/users",
            json={
                "username": test_user,
                "password": "testpass",
                "admin": False,
                "private": False,
            },
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )

        response = client.get("/settings", auth=(test_user, "testpass"))
        assert response.status_code == 403

        # Clean up
        client.delete(
            f"/users/{test_user}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )


def test_update_settings():
    with TestClient(app) as client:
        # Get current value
        original = client.get(
            "/settings", auth=("admin", RESTAI_DEFAULT_PASSWORD)
        ).json()
        original_name = original["app_name"]

        # Update
        response = client.patch(
            "/settings",
            json={"app_name": "TestApp"},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["app_name"] == "TestApp"

        # Restore
        client.patch(
            "/settings",
            json={"app_name": original_name},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )


def test_update_settings_invalid():
    with TestClient(app) as client:
        response = client.patch(
            "/settings",
            json={"agent_max_iterations": 0},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 400


def test_update_settings_bool():
    with TestClient(app) as client:
        # Get current value
        original = client.get(
            "/settings", auth=("admin", RESTAI_DEFAULT_PASSWORD)
        ).json()
        original_val = original["hide_branding"]

        # Update
        response = client.patch(
            "/settings",
            json={"hide_branding": True},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["hide_branding"] is True

        # Restore
        client.patch(
            "/settings",
            json={"hide_branding": original_val},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )


def test_sso_auto_restricted_default():
    """SSO auto-restricted should default to True."""
    with TestClient(app) as client:
        response = client.get("/settings", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        data = response.json()
        assert "sso_auto_restricted" in data
        assert data["sso_auto_restricted"] is True


def test_sso_auto_team_id_default():
    """SSO auto team ID should default to empty string."""
    with TestClient(app) as client:
        response = client.get("/settings", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert response.status_code == 200
        data = response.json()
        assert "sso_auto_team_id" in data
        assert data["sso_auto_team_id"] == ""


def test_update_sso_auto_restricted():
    """Should be able to toggle SSO auto-restricted setting."""
    with TestClient(app) as client:
        # Disable
        response = client.patch(
            "/settings",
            json={"sso_auto_restricted": False},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["sso_auto_restricted"] is False
        assert config.SSO_AUTO_RESTRICTED is False

        # Re-enable
        response = client.patch(
            "/settings",
            json={"sso_auto_restricted": True},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["sso_auto_restricted"] is True
        assert config.SSO_AUTO_RESTRICTED is True


test_team_name = "test_sso_team_" + str(random.randint(0, 1000000))


def test_update_sso_auto_team_id():
    """Should be able to set a default team for SSO users."""
    with TestClient(app) as client:
        # Create a team
        resp = client.post(
            "/teams",
            json={"name": test_team_name},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert resp.status_code in (200, 201)
        team_id = str(resp.json()["id"])

        # Set the team
        response = client.patch(
            "/settings",
            json={"sso_auto_team_id": team_id},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["sso_auto_team_id"] == team_id
        assert config.SSO_AUTO_TEAM_ID == team_id

        # Clear it
        response = client.patch(
            "/settings",
            json={"sso_auto_team_id": ""},
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
        assert response.status_code == 200
        assert response.json()["sso_auto_team_id"] == ""

        # Clean up
        client.delete(
            f"/teams/{team_id}",
            auth=("admin", RESTAI_DEFAULT_PASSWORD),
        )
