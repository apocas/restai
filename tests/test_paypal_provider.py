"""Unit tests for restai/payments/paypal_provider.py — token fetch, order
create/capture, webhook verification branches and failure mapping, with
httpx.Client fully faked (no network)."""

import json

import httpx
import pytest

import restai.config as rconfig
from restai.payments.base import PaymentError, PaymentNotConfigured
from restai.payments.paypal_provider import PayPalProvider

SANDBOX = "https://api-m.sandbox.paypal.com"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.text = text if text is not None else json.dumps(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeClient:
    """Route table shared per-test via the `paypal` fixture."""
    routes = {}
    calls = []

    def __init__(self, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _handle(self, method, url, **kwargs):
        FakeClient.calls.append((method, url, kwargs))
        for (m, suffix), resp in FakeClient.routes.items():
            if m == method and url.endswith(suffix):
                if callable(resp):
                    return resp()
                return resp
        raise AssertionError(f"unrouted request: {method} {url}")

    def post(self, url, **kwargs):
        return self._handle("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._handle("GET", url, **kwargs)


@pytest.fixture
def paypal(monkeypatch):
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_ENABLED", True, raising=False)
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_MODE", "sandbox", raising=False)
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_CLIENT_ID", "cid", raising=False)
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_CLIENT_SECRET", "sec", raising=False)
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_WEBHOOK_ID", "wh-1", raising=False)
    FakeClient.routes = {}
    FakeClient.calls = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    return PayPalProvider()


def _route_token():
    FakeClient.routes[("POST", "/v1/oauth2/token")] = FakeResponse(
        200, {"access_token": "tok-123"})


# ─── configuration / base URL ───────────────────────────────────────────

def test_is_configured_true(paypal):
    assert paypal.is_configured() is True


def test_is_configured_false_when_disabled(paypal, monkeypatch):
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_ENABLED", False, raising=False)
    assert not paypal.is_configured()


def test_is_configured_false_without_secret(paypal, monkeypatch):
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_CLIENT_SECRET", "", raising=False)
    assert not paypal.is_configured()


def test_base_url_modes(paypal, monkeypatch):
    assert paypal._base() == SANDBOX
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_MODE", "live", raising=False)
    assert paypal._base() == "https://api-m.paypal.com"
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_MODE", None, raising=False)
    assert paypal._base() == SANDBOX  # missing mode defaults to sandbox


def test_missing_credentials_raise_not_configured(paypal, monkeypatch):
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_CLIENT_ID", None, raising=False)
    with pytest.raises(PaymentNotConfigured):
        paypal._token()


def test_supports_auto_recharge_off(paypal):
    assert paypal.supports_auto_recharge is False


# ─── token fetch ────────────────────────────────────────────────────────

def test_token_success_uses_basic_auth(paypal):
    _route_token()
    assert paypal._token() == "tok-123"
    method, url, kwargs = FakeClient.calls[0]
    assert url == f"{SANDBOX}/v1/oauth2/token"
    assert kwargs["auth"] == ("cid", "sec")
    assert kwargs["data"] == {"grant_type": "client_credentials"}


def test_token_http_error_maps_to_payment_error(paypal):
    FakeClient.routes[("POST", "/v1/oauth2/token")] = FakeResponse(401, {"error": "nope"})
    with pytest.raises(PaymentError, match="auth failed"):
        paypal._token()


def test_token_connect_error_maps_to_payment_error(paypal):
    def boom():
        raise httpx.ConnectError("dns down")
    FakeClient.routes[("POST", "/v1/oauth2/token")] = boom
    with pytest.raises(PaymentError, match="auth failed"):
        paypal._token()


# ─── create_checkout ────────────────────────────────────────────────────

def test_create_checkout_success(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders")] = FakeResponse(201, {
        "id": "ORDER-1",
        "links": [
            {"rel": "self", "href": "https://x/self"},
            {"rel": "approve", "href": "https://paypal.test/approve"},
        ],
    })
    result = paypal.create_checkout(
        amount=12.5, currency="eur", team_id=7,
        success_url="https://app/ok", cancel_url="https://app/cancel")
    assert result.provider_ref == "ORDER-1"
    assert result.redirect_url == "https://paypal.test/approve"

    order_call = [c for c in FakeClient.calls if c[1].endswith("/v2/checkout/orders")][0]
    body = order_call[2]["json"]
    assert body["intent"] == "CAPTURE"
    pu = body["purchase_units"][0]
    assert pu["amount"] == {"currency_code": "EUR", "value": "12.50"}
    assert pu["custom_id"] == "7"
    assert body["application_context"]["return_url"] == "https://app/ok"
    assert order_call[2]["headers"]["Authorization"] == "Bearer tok-123"


def test_create_checkout_http_error(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders")] = FakeResponse(400, {"name": "INVALID"})
    with pytest.raises(PaymentError, match="HTTP 400"):
        paypal.create_checkout(amount=5, currency="usd", team_id=1,
                               success_url="s", cancel_url="c")


def test_create_checkout_missing_approve_link(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders")] = FakeResponse(
        201, {"id": "ORDER-2", "links": [{"rel": "self", "href": "x"}]})
    with pytest.raises(PaymentError, match="missing id/approval link"):
        paypal.create_checkout(amount=5, currency="usd", team_id=1,
                               success_url="s", cancel_url="c")


# ─── finalize (capture) ─────────────────────────────────────────────────

def _completed_order(value="30.00", currency="EUR"):
    return {
        "status": "COMPLETED",
        "purchase_units": [{
            "payments": {"captures": [{"amount": {"value": value, "currency_code": currency}}]},
        }],
    }


def test_finalize_captured_paid(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders/ORDER-1/capture")] = FakeResponse(
        201, _completed_order())
    event = paypal.finalize("ORDER-1")
    assert event.status == "paid"
    assert event.provider_ref == "ORDER-1"
    assert event.amount == 30.0
    assert event.currency == "EUR"


def test_finalize_422_falls_back_to_order_read(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders/ORDER-9/capture")] = FakeResponse(
        422, {"name": "ORDER_ALREADY_CAPTURED"})
    FakeClient.routes[("GET", "/v2/checkout/orders/ORDER-9")] = FakeResponse(
        200, _completed_order("10.00", "USD"))
    event = paypal.finalize("ORDER-9")
    assert event.status == "paid"
    assert (event.amount, event.currency) == (10.0, "USD")


def test_finalize_non_completed_is_pending(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders/ORDER-3/capture")] = FakeResponse(
        201, {"status": "PENDING", "purchase_units": [{"amount": {"value": "4.00", "currency_code": "EUR"}}]})
    event = paypal.finalize("ORDER-3")
    assert event.status == "pending"
    assert event.amount == 4.0  # falls back to purchase-unit amount


def test_finalize_http_error(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v2/checkout/orders/ORDER-4/capture")] = FakeResponse(
        500, {"name": "SERVER_ERROR"})
    with pytest.raises(PaymentError, match="HTTP 500"):
        paypal.finalize("ORDER-4")


# ─── webhook parsing ────────────────────────────────────────────────────

def test_parse_webhook_signature_failure_raises(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: False)
    with pytest.raises(PaymentError, match="signature verification failed"):
        paypal.parse_webhook(b"{}", {})


def test_parse_webhook_order_approved_triggers_capture(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: True)
    captured = {}

    def fake_finalize(ref):
        captured["ref"] = ref
        return "EVENT"
    monkeypatch.setattr(paypal, "finalize", fake_finalize)
    body = json.dumps({"event_type": "CHECKOUT.ORDER.APPROVED",
                       "resource": {"id": "ORDER-77"}}).encode()
    assert paypal.parse_webhook(body, {}) == "EVENT"
    assert captured["ref"] == "ORDER-77"


def test_parse_webhook_capture_completed(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: True)
    body = json.dumps({
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "supplementary_data": {"related_ids": {"order_id": "ORDER-88"}},
            "amount": {"value": "55.50", "currency_code": "GBP"},
        },
    }).encode()
    event = paypal.parse_webhook(body, {})
    assert event.provider_ref == "ORDER-88"
    assert event.status == "paid"
    assert (event.amount, event.currency) == (55.5, "GBP")


def test_parse_webhook_capture_without_order_id_ignored(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: True)
    body = json.dumps({"event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {}}).encode()
    assert paypal.parse_webhook(body, {}) is None


def test_parse_webhook_irrelevant_event_ignored(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: True)
    body = json.dumps({"event_type": "BILLING.SUBSCRIPTION.CREATED"}).encode()
    assert paypal.parse_webhook(body, {}) is None


def test_parse_webhook_invalid_json_returns_none(paypal, monkeypatch):
    monkeypatch.setattr(paypal, "_verify_webhook", lambda raw, h: True)
    assert paypal.parse_webhook(b"not json{", {}) is None


# ─── webhook signature verification ─────────────────────────────────────

def _verify_headers():
    return {
        "paypal-transmission-id": "t-id",
        "paypal-transmission-time": "t-time",
        "paypal-cert-url": "https://cert",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "sig",
    }


def test_verify_webhook_missing_webhook_id_raises(paypal, monkeypatch):
    monkeypatch.setattr(rconfig, "PAYMENT_PAYPAL_WEBHOOK_ID", "", raising=False)
    with pytest.raises(PaymentNotConfigured):
        paypal._verify_webhook(b"{}", {})


def test_verify_webhook_success(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v1/notifications/verify-webhook-signature")] = FakeResponse(
        200, {"verification_status": "SUCCESS"})
    raw = json.dumps({"event_type": "X"}).encode()
    assert paypal._verify_webhook(raw, _verify_headers()) is True
    verify_call = [c for c in FakeClient.calls if "verify-webhook-signature" in c[1]][0]
    body = verify_call[2]["json"]
    assert body["webhook_id"] == "wh-1"
    assert body["transmission_id"] == "t-id"
    assert body["webhook_event"] == {"event_type": "X"}


def test_verify_webhook_failure_status(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v1/notifications/verify-webhook-signature")] = FakeResponse(
        200, {"verification_status": "FAILURE"})
    assert paypal._verify_webhook(b"{}", _verify_headers()) is False


def test_verify_webhook_http_error_returns_false(paypal):
    _route_token()
    FakeClient.routes[("POST", "/v1/notifications/verify-webhook-signature")] = FakeResponse(
        400, {"name": "VALIDATION_ERROR"})
    assert paypal._verify_webhook(b"{}", _verify_headers()) is False


def test_verify_webhook_exception_returns_false(paypal):
    def boom():
        raise httpx.ConnectError("down")
    FakeClient.routes[("POST", "/v1/oauth2/token")] = boom
    # Token fetch inside _auth_headers explodes → caught → False.
    assert paypal._verify_webhook(b"{}", _verify_headers()) is False


# ─── amount extraction ──────────────────────────────────────────────────

def test_extract_amount_prefers_captures():
    order = {
        "purchase_units": [{
            "amount": {"value": "1.00", "currency_code": "USD"},
            "payments": {"captures": [{"amount": {"value": "2.00", "currency_code": "EUR"}}]},
        }],
    }
    assert PayPalProvider._extract_amount(order) == (2.0, "EUR")


def test_extract_amount_empty_order():
    assert PayPalProvider._extract_amount({}) == (None, None)
