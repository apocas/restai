"""Pluggable payment-provider interface.

Each provider (Stripe, PayPal, ...) is a self-contained implementation of
``PaymentProvider``. The platform admin configures credentials in Settings; team
admins top up their wallet through whichever providers are enabled. Crediting is
always centralised in ``restai.payments.service`` so every provider funnels into
the same idempotent ledger path.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class PaymentError(Exception):
    """Provider-side failure with a message safe to surface to the caller."""


class PaymentNotConfigured(PaymentError):
    """Provider is not enabled / missing credentials."""


class AutoRechargeUnsupported(PaymentError):
    """Provider cannot charge a saved method off-session (e.g. PayPal in v1)."""


@dataclass
class CheckoutResult:
    provider_ref: str
    redirect_url: str


@dataclass
class PaymentEvent:
    """Normalised outcome of a webhook / finalize / off-session charge."""
    provider_ref: str
    status: str  # paid | pending | failed | canceled | ignored
    amount: Optional[float] = None  # provider-confirmed amount, major units
    currency: Optional[str] = None
    kind: str = "topup"  # topup | setup
    customer_ref: Optional[str] = None
    method_ref: Optional[str] = None
    brand: Optional[str] = None
    last4: Optional[str] = None


class PaymentProvider(ABC):
    name: str = ""
    supports_auto_recharge: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def create_checkout(self, *, amount: float, currency: str, team_id: int,
                        success_url: str, cancel_url: str,
                        save_method: bool = False) -> CheckoutResult:
        """Create a hosted checkout for a one-time top-up. Returns the provider
        reference (session/order id) + the URL to redirect the user to."""

    @abstractmethod
    def finalize(self, provider_ref: str) -> PaymentEvent:
        """Retrieve/capture a checkout by reference — the return-page fallback
        for when the webhook hasn't landed yet. Idempotent on the provider side."""

    @abstractmethod
    def parse_webhook(self, raw_body: bytes, headers) -> Optional[PaymentEvent]:
        """Verify the webhook signature and return a normalised event, or None
        when the event isn't relevant. Raise PaymentError on signature failure."""

    def create_setup(self, *, team_id: int, success_url: str, cancel_url: str) -> CheckoutResult:
        """Start a save-a-card flow (for auto-recharge). Default: unsupported."""
        raise AutoRechargeUnsupported(f"{self.name} does not support saving a payment method")

    def charge_saved_method(self, *, amount: float, currency: str, customer_ref: str,
                            method_ref: str) -> PaymentEvent:
        """Charge a previously saved method off-session (auto-recharge)."""
        raise AutoRechargeUnsupported(f"{self.name} does not support auto-recharge")
