"""PayPal provider — hosted Orders v2 checkout for one-time top-ups.

v1 is manual-top-up only: PayPal off-session/reference transactions require
special merchant approval, so ``supports_auto_recharge`` stays False and the
save-a-card / auto-recharge methods inherit the "unsupported" defaults.

Raw REST via ``httpx`` (no SDK). Credentials read from live GUI settings."""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

import restai.config as _cfg
from restai.payments.base import (
    CheckoutResult, PaymentEvent, PaymentProvider, PaymentError, PaymentNotConfigured,
)

logger = logging.getLogger(__name__)


class PayPalProvider(PaymentProvider):
    name = "paypal"
    supports_auto_recharge = False

    def _base(self) -> str:
        mode = (_cfg.PAYMENT_PAYPAL_MODE or "sandbox").lower()
        return "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"

    def _creds(self) -> tuple[str, str]:
        cid, secret = _cfg.PAYMENT_PAYPAL_CLIENT_ID, _cfg.PAYMENT_PAYPAL_CLIENT_SECRET
        if not cid or not secret:
            raise PaymentNotConfigured("PayPal credentials are not configured")
        return cid, secret

    def is_configured(self) -> bool:
        return bool(_cfg.PAYMENT_PAYPAL_ENABLED and _cfg.PAYMENT_PAYPAL_CLIENT_ID
                    and _cfg.PAYMENT_PAYPAL_CLIENT_SECRET)

    def _token(self) -> str:
        cid, secret = self._creds()
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{self._base()}/v1/oauth2/token", auth=(cid, secret),
                           data={"grant_type": "client_credentials"},
                           headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.json()["access_token"]
        except httpx.HTTPError as e:
            raise PaymentError(f"PayPal auth failed: {e}")

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def create_checkout(self, *, amount, currency, team_id, success_url, cancel_url,
                        save_method=False) -> CheckoutResult:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {"currency_code": currency.upper(), "value": f"{float(amount):.2f}"},
                "custom_id": str(team_id),
                "description": "Wallet top-up",
            }],
            "application_context": {
                "return_url": success_url,
                "cancel_url": cancel_url,
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
            },
        }
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{self._base()}/v2/checkout/orders", json=body, headers=self._auth_headers())
            if r.status_code >= 400:
                raise PaymentError(f"PayPal order failed (HTTP {r.status_code}): {r.text[:300]}")
            data = r.json()
        except httpx.HTTPError as e:
            raise PaymentError(f"PayPal order request failed: {e}")
        order_id = data.get("id")
        approve = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
        if not order_id or not approve:
            raise PaymentError("PayPal order missing id/approval link")
        return CheckoutResult(provider_ref=order_id, redirect_url=approve)

    def finalize(self, provider_ref: str) -> PaymentEvent:
        headers = self._auth_headers()
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{self._base()}/v2/checkout/orders/{provider_ref}/capture", headers=headers)
                if r.status_code == 422:
                    # Already captured (e.g. webhook beat the return) — read the order.
                    r = c.get(f"{self._base()}/v2/checkout/orders/{provider_ref}", headers=headers)
                if r.status_code >= 400:
                    raise PaymentError(f"PayPal capture failed (HTTP {r.status_code}): {r.text[:300]}")
                data = r.json()
        except httpx.HTTPError as e:
            raise PaymentError(f"PayPal capture request failed: {e}")
        amount, currency = self._extract_amount(data)
        return PaymentEvent(
            provider_ref=provider_ref,
            status="paid" if data.get("status") == "COMPLETED" else "pending",
            amount=amount, currency=currency,
        )

    def parse_webhook(self, raw_body: bytes, headers) -> Optional[PaymentEvent]:
        if not self._verify_webhook(raw_body, headers):
            raise PaymentError("PayPal webhook signature verification failed")
        try:
            event = json.loads(raw_body or b"{}")
        except Exception:
            return None
        etype = event.get("event_type")
        resource = event.get("resource", {}) or {}
        if etype == "CHECKOUT.ORDER.APPROVED":
            # Capture server-side even if the buyer never returns to the app.
            return self.finalize(resource.get("id"))
        if etype == "PAYMENT.CAPTURE.COMPLETED":
            order_id = (resource.get("supplementary_data", {})
                        .get("related_ids", {}).get("order_id"))
            if not order_id:
                return None
            amt = resource.get("amount", {}) or {}
            return PaymentEvent(provider_ref=order_id, status="paid",
                                amount=float(amt.get("value", 0) or 0),
                                currency=amt.get("currency_code"))
        return None

    def _verify_webhook(self, raw_body: bytes, headers) -> bool:
        webhook_id = _cfg.PAYMENT_PAYPAL_WEBHOOK_ID
        if not webhook_id:
            raise PaymentNotConfigured("PayPal webhook ID is not configured")
        try:
            body = {
                "transmission_id": headers.get("paypal-transmission-id"),
                "transmission_time": headers.get("paypal-transmission-time"),
                "cert_url": headers.get("paypal-cert-url"),
                "auth_algo": headers.get("paypal-auth-algo"),
                "transmission_sig": headers.get("paypal-transmission-sig"),
                "webhook_id": webhook_id,
                "webhook_event": json.loads(raw_body or b"{}"),
            }
            with httpx.Client(timeout=30) as c:
                r = c.post(f"{self._base()}/v1/notifications/verify-webhook-signature",
                           json=body, headers=self._auth_headers())
            if r.status_code >= 400:
                logger.warning("PayPal verify-webhook-signature HTTP %s: %s", r.status_code, r.text[:200])
                return False
            return r.json().get("verification_status") == "SUCCESS"
        except Exception as e:
            logger.warning("PayPal webhook verification error: %s", e)
            return False

    @staticmethod
    def _extract_amount(order: dict) -> tuple[Optional[float], Optional[str]]:
        for pu in order.get("purchase_units", []) or []:
            captures = (pu.get("payments", {}) or {}).get("captures", []) or []
            for cap in captures:
                amt = cap.get("amount", {}) or {}
                if "value" in amt:
                    return float(amt["value"]), amt.get("currency_code")
            amt = pu.get("amount", {}) or {}
            if "value" in amt:
                return float(amt["value"]), amt.get("currency_code")
        return None, None
