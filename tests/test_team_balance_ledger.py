"""Team balance ledger: every prepaid-wallet movement (in & out) is recorded.

Debits come from charge_team_balance (one row per applied debit, gated on an
active wallet); credits/adjustments come from the platform-admin balance set.
Each row stores the signed amount + balance_after, so the ledger always
reconciles with teams.balance even across clamp-at-0 overspend.
"""
import random

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
_sfx = str(random.randint(0, 1_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_charge_records_usage_rows(client):
    from restai.database import DBWrapper
    from restai.limits.budget import charge_team_balance

    member = "led_member_" + _sfx
    assert client.post("/users", json={"username": member, "password": "led_pass_123"}, auth=ADMIN).status_code == 201
    tr = client.post("/teams", json={"name": "led_team_" + _sfx, "users": [member], "admins": []}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # Single session — charge_team_balance + list_balance_transactions share the
    # same cached team instance (see test_team_balance for the rationale).
    db = DBWrapper()
    try:
        member_user = db.get_user_by_username(member)
        team = db.get_team_by_id(team_id)
        team.balance = 10.0
        db.db.commit()

        # First debit.
        charge_team_balance(db, team_id, 3.0, actor_user_id=member_user.id)
        assert round(team.balance, 2) == 7.0
        rows, total = db.list_balance_transactions(team_id, 0, 100)
        assert total == 1
        row, actor_username = rows[0]
        assert row.amount == -3.0
        assert row.balance_after == 7.0
        assert row.kind == "usage"
        assert actor_username == member

        # Overspend clamps at 0 and records the APPLIED amount (-7.0), not -999.
        charge_team_balance(db, team_id, 999.0, actor_user_id=member_user.id)
        assert team.balance == 0.0
        rows, total = db.list_balance_transactions(team_id, 0, 100)
        assert total == 2
        newest, _ = rows[0]
        assert newest.amount == -7.0
        assert newest.balance_after == 0.0

        # Already empty → nothing moves → no ledger noise.
        charge_team_balance(db, team_id, 5.0, actor_user_id=member_user.id)
        _, total = db.list_balance_transactions(team_id, 0, 100)
        assert total == 2
    finally:
        db.db.close()


def test_null_wallet_charge_writes_no_row(client):
    from restai.database import DBWrapper
    from restai.limits.budget import charge_team_balance

    tr = client.post("/teams", json={"name": "led_null_" + _sfx, "users": [], "admins": []}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    db = DBWrapper()
    try:
        team = db.get_team_by_id(team_id)
        assert team.balance is None  # no wallet
        charge_team_balance(db, team_id, 5.0)
        _, total = db.list_balance_transactions(team_id, 0, 100)
        assert total == 0
    finally:
        db.db.close()


def test_topup_and_adjustment_via_endpoint(client):
    member = "led_ta_" + _sfx
    assert client.post("/users", json={"username": member, "password": "led_pass_123"}, auth=ADMIN).status_code == 201
    outsider = "led_out_" + _sfx
    assert client.post("/users", json={"username": outsider, "password": "led_pass_123"}, auth=ADMIN).status_code == 201
    # team admin (not platform admin)
    tr = client.post("/teams", json={"name": "led_ta_team_" + _sfx, "users": [member], "admins": [member]}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # Platform admin funds the wallet → a topup row.
    assert client.patch(f"/teams/{team_id}/balance", json={"balance": 250.0}, auth=ADMIN).status_code == 200
    # Downward set → an adjustment row.
    assert client.patch(f"/teams/{team_id}/balance", json={"balance": 100.0}, auth=ADMIN).status_code == 200

    # Team admin (non-platform) can read the ledger; newest movement first.
    r = client.get(f"/teams/{team_id}/balance/transactions", auth=(member, "led_pass_123"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    txs = body["transactions"]
    assert txs[0]["kind"] == "adjustment"
    assert txs[0]["amount"] == -150.0
    assert txs[0]["balance_after"] == 100.0
    assert txs[1]["kind"] == "topup"
    assert txs[1]["amount"] == 250.0
    assert txs[1]["balance_after"] == 250.0
    assert txs[1]["actor_username"] == "admin"

    # A non-member, non-admin user is rejected.
    r = client.get(f"/teams/{team_id}/balance/transactions", auth=(outsider, "led_pass_123"))
    assert r.status_code in (401, 403, 404)


def test_topup_endpoint_adds(client):
    member = "led_topup_" + _sfx
    assert client.post("/users", json={"username": member, "password": "led_pass_123"}, auth=ADMIN).status_code == 201
    tr = client.post("/teams", json={"name": "led_topup_team_" + _sfx, "users": [member], "admins": [member]}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    team_id = tr.json()["id"]

    # First top-up activates the wallet (None -> 0 + 100).
    r = client.post(f"/teams/{team_id}/balance/topup", json={"amount": 100.0}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 100.0

    # Second top-up ADDS (does not overwrite).
    r = client.post(f"/teams/{team_id}/balance/topup", json={"amount": 50.0}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["balance"] == 150.0
    assert client.get(f"/teams/{team_id}", auth=ADMIN).json()["balance"] == 150.0

    # Ledger has two topup rows, newest first, with the right running balance.
    body = client.get(f"/teams/{team_id}/balance/transactions", auth=ADMIN).json()
    assert body["total"] == 2
    assert body["transactions"][0]["kind"] == "topup"
    assert body["transactions"][0]["amount"] == 50.0
    assert body["transactions"][0]["balance_after"] == 150.0
    assert body["transactions"][1]["amount"] == 100.0
    assert body["transactions"][1]["balance_after"] == 100.0

    # Team admin (non-platform) cannot top up — it's real money, platform-only.
    assert client.post(f"/teams/{team_id}/balance/topup", json={"amount": 10.0}, auth=(member, "led_pass_123")).status_code == 403
    # Non-positive amounts are rejected by validation.
    assert client.post(f"/teams/{team_id}/balance/topup", json={"amount": 0}, auth=ADMIN).status_code == 422
    assert client.post(f"/teams/{team_id}/balance/topup", json={"amount": -5.0}, auth=ADMIN).status_code == 422
