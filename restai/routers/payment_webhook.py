"""Payment provider webhooks — the authoritative crediting path.

`POST /webhooks/payments/{provider}` is public + signature-verified (verification
lives in each provider's `parse_webhook`). Mirrors the WhatsApp webhook: read the
raw body first, verify, then do the heavy work in a BackgroundTask and return 200
fast so the provider doesn't retry."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException

from restai.database import open_db_wrapper
from restai import payments
from restai.payments import service as payment_service
from restai.payments.base import PaymentError, PaymentNotConfigured

logger = logging.getLogger(__name__)
router = APIRouter()


def _process_event(provider_name: str, provider_ref: str, kind: str, event_dict: dict) -> None:
    """Background worker — credit/setup against a fresh DB session. Never raises."""
    from restai.payments.base import PaymentEvent
    db = open_db_wrapper()
    try:
        event = PaymentEvent(**event_dict)
        row = db.get_payment(provider_name, provider_ref)
        if row is None:
            logger.info("payment webhook: no local row for %s ref=%s", provider_name, provider_ref)
            return
        if row.status != "pending":
            return
        if row.kind == "setup":
            payment_service.complete_setup(db, row.id, event)
        else:
            payment_service.credit_payment(db, row.id, event)
    except Exception:
        logger.exception("payment webhook processing failed (%s)", provider_name)
    finally:
        db.close()


@router.post("/webhooks/payments/{provider}", tags=["Payments"])
async def receive_payment_webhook(provider: str, request: Request, background_tasks: BackgroundTasks):
    prov = payments.get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="Unknown provider")
    raw = await request.body()
    try:
        event = prov.parse_webhook(raw, request.headers)
    except PaymentNotConfigured as e:
        logger.warning("payment webhook %s not configured: %s", provider, e)
        raise HTTPException(status_code=503, detail="provider not configured")
    except PaymentError as e:
        logger.warning("payment webhook %s rejected: %s", provider, e)
        raise HTTPException(status_code=401, detail="signature mismatch")

    if event is None or event.status != "paid":
        return {"status": "ignored"}

    background_tasks.add_task(
        _process_event, prov.name, event.provider_ref, event.kind, event.__dict__,
    )
    return {"status": "ok"}
