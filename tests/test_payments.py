"""Payment system — checkout, idempotent webhook crediting, RBAC, auto-recharge.

Providers are mocked (no Stripe/PayPal network): we patch the registry instances'
methods + force payments_enabled, so the test exercises RESTai's own plumbing —
pending-row creation, the webhook crediting path into the ledger, idempotency,
auth gating, and the auto-recharge cron.
"""
import random

import pytest
from fastapi.testclient import TestClient

import restai.config as rconfig
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai import payments
from restai.payments.base import CheckoutResult, PaymentEvent, PaymentError

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
_sfx = str(random.randint(0, 1_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def stripe_on(monkeypatch):
    """Enable payments + a mocked, configured Stripe provider."""
    monkeypatch.setattr(rconfig, "RESTAI_URL", "https://test.restai", raising=False)
    monkeypatch.setattr(payments, "payments_enabled", lambda: True)
    sp = payments.PROVIDERS["stripe"]
    monkeypatch.setattr(sp, "is_configured", lambda: True)
    return sp


def _make_team(client):
    member = "pay_admin_" + _sfx + str(random.randint(0, 99999))
    assert client.post("/users", json={"username": member, "password": "pay_pass_123"}, auth=ADMIN).status_code == 201
    tr = client.post("/teams", json={"name": "pay_team_" + _sfx + str(random.randint(0, 99999)),
                                     "users": [member], "admins": [member]}, auth=ADMIN)
    assert tr.status_code == 201, tr.text
    return tr.json()["id"], member


def test_checkout_requires_payments_enabled(client):
    team_id, _ = _make_team(client)
    # payments disabled by default → 400
    r = client.post(f"/teams/{team_id}/balance/checkout",
                    json={"amount": 10, "provider": "stripe"}, auth=ADMIN)
    assert r.status_code == 400


def _uref(prefix):
    return f"{prefix}_{random.randint(0, 1_000_000_000)}"


def test_checkout_creates_pending_and_redirects(client, stripe_on):
    ref = _uref("cs")
    stripe_on.create_checkout = lambda **kw: CheckoutResult(provider_ref=ref, redirect_url="https://checkout.test/go")

    team_id, _ = _make_team(client)
    r = client.post(f"/teams/{team_id}/balance/checkout",
                    json={"amount": 25, "provider": "stripe"}, auth=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["redirect_url"] == "https://checkout.test/go"

    from restai.database import DBWrapper
    db = DBWrapper()
    try:
        row = db.get_payment("stripe", ref)
        assert row is not None and row.status == "pending" and row.kind == "topup"
        assert round(row.amount, 2) == 25.0
    finally:
        db.db.close()


def test_webhook_credits_once_idempotent(client, stripe_on):
    ref = _uref("cs")
    stripe_on.create_checkout = lambda **kw: CheckoutResult(ref, "https://checkout.test/go")
    # Webhook returns a verified paid event for our session.
    stripe_on.parse_webhook = lambda raw, headers: PaymentEvent(
        provider_ref=ref, status="paid", amount=40.0, currency="EUR", kind="topup")

    team_id, _ = _make_team(client)
    assert client.post(f"/teams/{team_id}/balance/checkout",
                       json={"amount": 40, "provider": "stripe"}, auth=ADMIN).status_code == 200

    # First webhook → credited.
    assert client.post("/webhooks/payments/stripe", content=b"{}").json()["status"] == "ok"
    bal1 = client.get(f"/teams/{team_id}", auth=ADMIN).json()["balance"]
    assert round(bal1, 2) == 40.0

    # A topup ledger row was written.
    led = client.get(f"/teams/{team_id}/balance/transactions", auth=ADMIN).json()
    assert any(tx["kind"] == "topup" and round(tx["amount"], 2) == 40.0 for tx in led["transactions"])

    # Second identical webhook → no double credit.
    client.post("/webhooks/payments/stripe", content=b"{}")
    bal2 = client.get(f"/teams/{team_id}", auth=ADMIN).json()["balance"]
    assert round(bal2, 2) == 40.0


def test_webhook_bad_signature_401(client, stripe_on):
    def boom(raw, headers):
        raise PaymentError("signature mismatch")
    stripe_on.parse_webhook = boom
    r = client.post("/webhooks/payments/stripe", content=b"{}")
    assert r.status_code == 401


def test_checkout_rbac_outsider_forbidden(client, stripe_on):
    stripe_on.create_checkout = lambda **kw: CheckoutResult(_uref("cs"), "https://checkout.test/go")
    team_id, _ = _make_team(client)
    outsider = "pay_out_" + _sfx
    assert client.post("/users", json={"username": outsider, "password": "pay_pass_123"}, auth=ADMIN).status_code == 201
    r = client.post(f"/teams/{team_id}/balance/checkout",
                    json={"amount": 10, "provider": "stripe"}, auth=(outsider, "pay_pass_123"))
    assert r.status_code in (401, 403)


def test_paypal_auto_recharge_rejected(client, stripe_on, monkeypatch):
    # PayPal can't auto-recharge in v1 → enabling must 400.
    team_id, _ = _make_team(client)
    from restai.database import DBWrapper
    db = DBWrapper()
    try:
        db.upsert_team_payment_config(team_id, provider="paypal", customer_ref="cus", method_ref="pm")
    finally:
        db.db.close()
    r = client.put(f"/teams/{team_id}/payment/auto-recharge",
                   json={"enabled": True, "threshold": 5, "amount": 20}, auth=ADMIN)
    assert r.status_code == 400


def test_auto_recharge_cron_charges_when_low(client, stripe_on, monkeypatch):
    import crons.auto_recharge as ar

    team_id, _ = _make_team(client)
    from restai.database import DBWrapper
    db = DBWrapper()
    try:
        team = db.get_team_by_id(team_id)
        team.balance = 2.0
        db.db.commit()
        db.upsert_team_payment_config(
            team_id, provider="stripe", customer_ref="cus_1", method_ref="pm_1",
            brand="visa", last4="4242", auto_recharge_enabled=True,
            auto_recharge_threshold=5.0, auto_recharge_amount=50.0,
        )
    finally:
        db.db.close()

    charges = {"n": 0}
    def fake_charge(**kw):
        charges["n"] += 1
        return PaymentEvent(provider_ref=_uref("pi"), status="paid", amount=50.0, currency="EUR")
    stripe_on.charge_saved_method = fake_charge

    ar.main()  # below threshold → one charge → +50
    bal = client.get(f"/teams/{team_id}", auth=ADMIN).json()["balance"]
    assert round(bal, 2) == 52.0
    assert charges["n"] == 1

    ar.main()  # now above threshold → no further charge
    assert charges["n"] == 1
