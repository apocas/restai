"""Team prepaid wallet (balance): hard stop + decrement + platform-admin top-up.

Balance is distinct from the soft budget: NULL = no wallet, a number = active
wallet, <= 0 = depleted (hard 402 for non-admins; admins bypass).
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


def test_charge_and_enforce(client):
    from restai.database import DBWrapper
    from restai.limits.budget import charge_team_balance, enforce_cost_budgets
    from restai.models.models import User

    member = "bal_member_" + _sfx
    member_pw = "bal_pass_123"
    assert client.post("/users", json={"username": member, "password": member_pw}, auth=ADMIN).status_code == 201
    tr = client.post("/teams", json={"name": "bal_team_" + _sfx, "users": [member], "admins": []}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # All mutations on one session — charge_team_balance fetches the same cached
    # team instance, so reads/writes stay consistent.
    db = DBWrapper()
    try:
        member_user = User.model_validate(db.get_user_by_username(member))
        admin_user = User.model_validate(db.get_user_by_username("admin"))
        team = db.get_team_by_id(team_id)

        # No wallet (NULL) → charge is a no-op, enforce passes.
        charge_team_balance(db, team_id, 5.0)
        assert team.balance is None
        enforce_cost_budgets(db, user=member_user, team=team)  # no raise

        # Fund the wallet, then charge it down (clamped at 0).
        team.balance = 10.0
        db.db.commit()
        charge_team_balance(db, team_id, 3.0)
        assert round(team.balance, 2) == 7.0
        charge_team_balance(db, team_id, 999.0)  # overspend
        assert team.balance == 0.0  # clamped

        # Depleted (0) → hard 402 for the member...
        with pytest.raises(HTTPException) as exc:
            enforce_cost_budgets(db, user=member_user, team=team)
        assert exc.value.status_code == 402 and exc.value.detail == "Team balance depleted"

        # ...but a platform admin bypasses it.
        enforce_cost_budgets(db, user=admin_user, team=team)  # no raise

        # Refunded → member allowed again.
        team.balance = 5.0
        db.db.commit()
        enforce_cost_budgets(db, user=member_user, team=team)
    finally:
        db.db.close()


def test_balance_topup_endpoint(client):
    member = "bal_ta_" + _sfx
    member_pw = "bal_pass_123"
    assert client.post("/users", json={"username": member, "password": member_pw}, auth=ADMIN).status_code == 201
    # team admin (not platform admin)
    tr = client.post("/teams", json={"name": "bal_ta_team_" + _sfx, "users": [member], "admins": [member]}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # Platform admin sets the balance.
    r = client.patch(f"/teams/{team_id}/balance", json={"balance": 250.0}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 250.0
    assert client.get(f"/teams/{team_id}", auth=ADMIN).json()["balance"] == 250.0

    # A team admin (non-platform) is rejected — balance is platform-only.
    r = client.patch(f"/teams/{team_id}/balance", json={"balance": 999.0}, auth=(member, member_pw))
    assert r.status_code == 403

    # Negative is rejected by validation.
    assert client.patch(f"/teams/{team_id}/balance", json={"balance": -5.0}, auth=ADMIN).status_code == 422
