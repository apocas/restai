"""Payment provider registry.

Add a provider by implementing ``PaymentProvider`` and registering it in
``PROVIDERS``. Everything else (settings, routers, webhook, crediting, cron)
is provider-agnostic.
"""
from __future__ import annotations

from typing import List, Optional

import restai.config as _cfg
from restai.payments.base import PaymentProvider, PaymentError, PaymentNotConfigured
from restai.payments.stripe_provider import StripeProvider
from restai.payments.paypal_provider import PayPalProvider

PROVIDERS = {
    "stripe": StripeProvider(),
    "paypal": PayPalProvider(),
}


def payments_enabled() -> bool:
    return bool(_cfg.PAYMENT_ENABLED)


def get_provider(name: str) -> Optional[PaymentProvider]:
    return PROVIDERS.get((name or "").lower())


def enabled_providers() -> List[PaymentProvider]:
    """Providers that are both enabled and fully configured (and payments on)."""
    if not payments_enabled():
        return []
    return [p for p in PROVIDERS.values() if p.is_configured()]


def enabled_provider_names() -> List[str]:
    return [p.name for p in enabled_providers()]


__all__ = [
    "PROVIDERS", "PaymentProvider", "PaymentError", "PaymentNotConfigured",
    "payments_enabled", "get_provider", "enabled_providers", "enabled_provider_names",
]
