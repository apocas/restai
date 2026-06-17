"""Stripe provider — hosted Checkout for top-ups + saved cards for auto-recharge.

Reads credentials from the live GUI settings (config read-through) on every call,
so multi-worker config changes take effect immediately. Uses the official
``stripe`` SDK; the api_key is passed per call (no global mutation)."""
from __future__ import annotations

import logging
from typing import Optional

import stripe

import restai.config as _cfg
from restai.payments.base import (
    CheckoutResult, PaymentEvent, PaymentProvider, PaymentError, PaymentNotConfigured,
)

logger = logging.getLogger(__name__)


def _cents(amount: float) -> int:
    return int(round(float(amount) * 100))


class StripeProvider(PaymentProvider):
    name = "stripe"
    supports_auto_recharge = True

    def _secret(self) -> str:
        key = _cfg.PAYMENT_STRIPE_SECRET_KEY
        if not key:
            raise PaymentNotConfigured("Stripe secret key is not configured")
        return key

    def is_configured(self) -> bool:
        return bool(_cfg.PAYMENT_STRIPE_ENABLED and _cfg.PAYMENT_STRIPE_SECRET_KEY)

    def create_checkout(self, *, amount, currency, team_id, success_url, cancel_url,
                        save_method=False) -> CheckoutResult:
        params = dict(
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "product_data": {"name": "Wallet top-up"},
                    "unit_amount": _cents(amount),
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"team_id": str(team_id), "kind": "topup"},
        )
        if save_method:
            params["customer_creation"] = "always"
            params["payment_intent_data"] = {"setup_future_usage": "off_session"}
        try:
            session = stripe.checkout.Session.create(api_key=self._secret(), **params)
        except stripe.error.StripeError as e:
            raise PaymentError(f"Stripe checkout failed: {getattr(e, 'user_message', None) or str(e)}")
        return CheckoutResult(provider_ref=session.id, redirect_url=session.url)

    def create_setup(self, *, team_id, success_url, cancel_url) -> CheckoutResult:
        secret = self._secret()
        try:
            customer = stripe.Customer.create(api_key=secret, metadata={"team_id": str(team_id)})
            session = stripe.checkout.Session.create(
                api_key=secret, mode="setup", customer=customer.id,
                success_url=success_url, cancel_url=cancel_url,
                metadata={"team_id": str(team_id), "kind": "setup"},
            )
        except stripe.error.StripeError as e:
            raise PaymentError(f"Stripe setup failed: {getattr(e, 'user_message', None) or str(e)}")
        return CheckoutResult(provider_ref=session.id, redirect_url=session.url)

    def finalize(self, provider_ref: str) -> PaymentEvent:
        try:
            session = stripe.checkout.Session.retrieve(
                provider_ref, api_key=self._secret(),
                expand=["payment_intent.payment_method", "setup_intent.payment_method"],
            )
        except stripe.error.StripeError as e:
            raise PaymentError(f"Stripe retrieve failed: {getattr(e, 'user_message', None) or str(e)}")
        return self._event_from_session(session)

    def parse_webhook(self, raw_body: bytes, headers) -> Optional[PaymentEvent]:
        secret = _cfg.PAYMENT_STRIPE_WEBHOOK_SECRET
        if not secret:
            raise PaymentNotConfigured("Stripe webhook secret is not configured")
        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature")
        try:
            event = stripe.Webhook.construct_event(raw_body, sig, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            raise PaymentError(f"Stripe webhook signature verification failed: {e}")
        if event["type"] not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
            return None
        # The webhook payload isn't expanded — re-retrieve to resolve the card.
        return self.finalize(event["data"]["object"]["id"])

    def charge_saved_method(self, *, amount, currency, customer_ref, method_ref) -> PaymentEvent:
        try:
            pi = stripe.PaymentIntent.create(
                api_key=self._secret(),
                amount=_cents(amount), currency=currency.lower(),
                customer=customer_ref, payment_method=method_ref,
                off_session=True, confirm=True,
                metadata={"kind": "auto_recharge"},
            )
        except stripe.error.StripeError as e:
            raise PaymentError(f"Stripe auto-recharge failed: {getattr(e, 'user_message', None) or str(e)}")
        if pi.status != "succeeded":
            raise PaymentError(f"Stripe PaymentIntent not succeeded (status={pi.status})")
        return PaymentEvent(provider_ref=pi.id, status="paid",
                            amount=(pi.amount or 0) / 100, currency=(pi.currency or currency).upper())

    @staticmethod
    def _card_bits(pm) -> tuple[Optional[str], Optional[str]]:
        card = getattr(pm, "card", None) if pm else None
        if not card:
            return None, None
        return getattr(card, "brand", None), getattr(card, "last4", None)

    def _event_from_session(self, session) -> PaymentEvent:
        complete = session.status == "complete"
        if session.mode == "setup":
            si = session.setup_intent
            pm = getattr(si, "payment_method", None) if si else None
            brand, last4 = self._card_bits(pm)
            return PaymentEvent(
                provider_ref=session.id,
                status="paid" if complete else "pending",
                kind="setup",
                customer_ref=session.customer,
                method_ref=getattr(pm, "id", None),
                brand=brand, last4=last4,
            )
        paid = session.payment_status == "paid"
        pi = session.payment_intent
        pm = getattr(pi, "payment_method", None) if pi else None
        brand, last4 = self._card_bits(pm)
        return PaymentEvent(
            provider_ref=session.id,
            status="paid" if paid else "pending",
            amount=(session.amount_total or 0) / 100,
            currency=(session.currency or "").upper() or None,
            kind="topup",
            customer_ref=session.customer,
            method_ref=getattr(pm, "id", None),
            brand=brand, last4=last4,
        )
