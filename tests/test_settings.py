import random
from fastapi.testclient import TestClient

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
