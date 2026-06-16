"""API-key team attribution.

A key carries a required `team_id`; on the team-less direct-access path the
key's team pins billing deterministically (instead of the order-dependent
first-granting-team scan). This exercises `resolve_team_for_llm` directly so
no live LLM call is needed (the LLM rows use a fake `gpt-test` model that is
never actually invoked).
"""
import random

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
_sfx = str(random.randint(0, 1_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_api_key_team_pins_direct_access(client):
    from restai.database import DBWrapper
    from restai.integrations.direct_access import resolve_team_for_llm
    from restai.models.models import User

    user_name = "akt_user_" + _sfx
    user_pw = "akt_pass_123"
    llm_a = "akt_llm_a_" + _sfx
    llm_b = "akt_llm_b_" + _sfx

    assert client.post(
        "/users", json={"username": user_name, "password": user_pw}, auth=ADMIN
    ).status_code == 201
    for name in (llm_a, llm_b):
        r = client.post(
            "/llms",
            json={
                "name": name,
                "class_name": "OpenAI",
                "options": {"model": "gpt-test", "api_key": "sk-fake"},
                "privacy": "public",
            },
            auth=ADMIN,
        )
        assert r.status_code in (200, 201), r.text

    # Team A grants llm_a, team B grants llm_b. The user is in both.
    ta = client.post(
        "/teams",
        json={"name": "akt_team_a_" + _sfx, "users": [user_name], "admins": [], "llms": [llm_a]},
        auth=ADMIN,
    )
    tb = client.post(
        "/teams",
        json={"name": "akt_team_b_" + _sfx, "users": [user_name], "admins": [], "llms": [llm_b]},
        auth=ADMIN,
    )
    assert ta.status_code == 201, ta.text
    assert tb.status_code == 201, tb.text
    team_a = ta.json()["id"]
    team_b = tb.json()["id"]

    # The key must belong to one of the owner's teams.
    kr = client.post(
        f"/users/{user_name}/apikeys",
        json={"description": "akt", "team_id": team_a},
        auth=(user_name, user_pw),
    )
    assert kr.status_code == 201, kr.text
    assert kr.json()["team_id"] == team_a

    db = DBWrapper()
    try:
        user = User.model_validate(db.get_user_by_username(user_name))

        # Pinned to team A: llm_a (granted by A) bills A.
        user.api_key_team_id = team_a
        assert resolve_team_for_llm(user, llm_a, db) == team_a

        # llm_b is not granted by the pinned team A → deterministic 403,
        # NOT a silent fall-through to team B.
        with pytest.raises(HTTPException) as exc:
            resolve_team_for_llm(user, llm_b, db)
        assert exc.value.status_code == 403

        # No pin (basic/cookie auth): legacy fall-through to any granting team.
        user.api_key_team_id = None
        assert resolve_team_for_llm(user, llm_b, db) == team_b
    finally:
        db.db.close()
