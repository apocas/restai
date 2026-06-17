"""Payment endpoints — team admins top up their wallet via configured providers.

Hosted-redirect checkout: create a provider session → redirect → the provider
webhook (authoritative) credits the wallet; the `/payments/return/{provider}`
handler is a fast fallback that finalizes on the user's return. Crediting is
idempotent (see restai.payments.service)."""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import RedirectResponse

from restai import config
from restai.auth import get_current_username_team_admin, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.constants import ERROR_MESSAGES
from restai.models.models import (
    User, PaymentCheckoutRequest, PaymentRedirectResponse, AutoRechargeUpdate,
    TeamPaymentConfigResponse, SavedMethod, PaymentTransaction, PaymentTransactionsResponse,
)
from restai import payments
from restai.payments import service as payment_service
from restai.payments.base import PaymentError

logger = logging.getLogger(__name__)
router = APIRouter()


def _base_url() -> str:
    base = (config.RESTAI_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="RESTAI_URL is not configured")
    return base


def _spa_wallet_url(team_id, status: str) -> str:
    return f"{(config.RESTAI_URL or '').rstrip('/')}/admin/#/team/{team_id}/wallet?payment={status}"


def _success_url(provider_name: str, team_id: int) -> str:
    base = _base_url()
    if provider_name == "stripe":
        return f"{base}/payments/return/stripe?team_id={team_id}&session_id={{CHECKOUT_SESSION_ID}}"
    return f"{base}/payments/return/{provider_name}?team_id={team_id}"


def _currency(db_wrapper: DBWrapper) -> str:
    return db_wrapper.get_setting_value("currency", "EUR") or "EUR"


def _config_response(db_wrapper: DBWrapper, team_id: int) -> TeamPaymentConfigResponse:
    cfg = db_wrapper.get_team_payment_config(team_id)
    saved = None
    if cfg and cfg.method_ref:
        saved = SavedMethod(provider=cfg.provider, brand=cfg.brand, last4=cfg.last4)
    return TeamPaymentConfigResponse(
        payments_enabled=payments.payments_enabled(),
        providers=payments.enabled_provider_names(),
        auto_recharge_providers=[p.name for p in payments.enabled_providers() if p.supports_auto_recharge],
        currency=_currency(db_wrapper),
        saved_method=saved,
        auto_recharge_enabled=bool(cfg.auto_recharge_enabled) if cfg else False,
        auto_recharge_threshold=cfg.auto_recharge_threshold if cfg else None,
        auto_recharge_amount=cfg.auto_recharge_amount if cfg else None,
    )


@router.post("/teams/{team_id}/balance/checkout", response_model=PaymentRedirectResponse, tags=["Payments"])
async def create_checkout(
    team_id: int = Path(description="Team ID"),
    body: PaymentCheckoutRequest = Body(...),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Start a hosted top-up checkout. Team admins only."""
    check_not_restricted(user)
    if not payments.payments_enabled():
        raise HTTPException(status_code=400, detail="Payments are not enabled")
    provider = payments.get_provider(body.provider)
    if provider is None or not provider.is_configured():
        raise HTTPException(status_code=400, detail="Payment provider not available")
    if body.save_method and not provider.supports_auto_recharge:
        raise HTTPException(status_code=400, detail=f"{provider.name} cannot save a payment method")
    if db_wrapper.get_team_by_id(team_id) is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

    currency = _currency(db_wrapper)
    try:
        result = provider.create_checkout(
            amount=body.amount, currency=currency, team_id=team_id,
            success_url=_success_url(provider.name, team_id),
            cancel_url=_spa_wallet_url(team_id, "cancel"),
            save_method=body.save_method,
        )
    except PaymentError as e:
        raise HTTPException(status_code=502, detail=str(e))
    db_wrapper.create_payment(
        team_id=team_id, provider=provider.name, kind="topup",
        provider_ref=result.provider_ref, amount=body.amount, currency=currency,
        actor_user_id=user.id,
    )
    return PaymentRedirectResponse(redirect_url=result.redirect_url, provider_ref=result.provider_ref)


@router.post("/teams/{team_id}/payment/setup", response_model=PaymentRedirectResponse, tags=["Payments"])
async def setup_payment_method(
    team_id: int = Path(description="Team ID"),
    provider_name: str = Query("stripe", alias="provider", description="Provider to save a card with"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Start a save-a-card flow for auto-recharge (Stripe only). Team admins only."""
    check_not_restricted(user)
    if not payments.payments_enabled():
        raise HTTPException(status_code=400, detail="Payments are not enabled")
    provider = payments.get_provider(provider_name)
    if provider is None or not provider.is_configured() or not provider.supports_auto_recharge:
        raise HTTPException(status_code=400, detail="Provider cannot save a payment method")
    if db_wrapper.get_team_by_id(team_id) is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    try:
        result = provider.create_setup(
            team_id=team_id,
            success_url=_success_url(provider.name, team_id),
            cancel_url=_spa_wallet_url(team_id, "cancel"),
        )
    except PaymentError as e:
        raise HTTPException(status_code=502, detail=str(e))
    db_wrapper.create_payment(
        team_id=team_id, provider=provider.name, kind="setup",
        provider_ref=result.provider_ref, amount=0.0, currency=_currency(db_wrapper),
        actor_user_id=user.id,
    )
    return PaymentRedirectResponse(redirect_url=result.redirect_url, provider_ref=result.provider_ref)


@router.get("/payments/return/{provider}", include_in_schema=False)
async def payment_return(provider: str, request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Provider return URL — finalize (capture/retrieve) then redirect to the SPA.
    Public + idempotent: finalize verifies status with the provider, so a stray
    ref credits nothing. The webhook remains the authoritative path."""
    params = request.query_params
    team_id = params.get("team_id")
    ref = params.get("session_id") or params.get("token")
    prov = payments.get_provider(provider)
    status = "success"
    try:
        if prov and ref:
            row = db_wrapper.get_payment(prov.name, ref)
            if row is not None and row.status == "pending":
                event = prov.finalize(ref)
                if event.status == "paid":
                    if row.kind == "setup":
                        payment_service.complete_setup(db_wrapper, row.id, event)
                    else:
                        payment_service.credit_payment(db_wrapper, row.id, event)
                else:
                    status = "pending"
    except Exception:
        logger.exception("payment return finalize failed (provider=%s)", provider)
        status = "error"
    return RedirectResponse(_spa_wallet_url(team_id, status), status_code=303)


@router.get("/teams/{team_id}/payment", response_model=TeamPaymentConfigResponse, tags=["Payments"])
async def get_team_payment(
    team_id: int = Path(description="Team ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Team payment state: enabled providers, saved method, auto-recharge rule."""
    if db_wrapper.get_team_by_id(team_id) is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    return _config_response(db_wrapper, team_id)


@router.put("/teams/{team_id}/payment/auto-recharge", response_model=TeamPaymentConfigResponse, tags=["Payments"])
async def set_auto_recharge(
    team_id: int = Path(description="Team ID"),
    body: AutoRechargeUpdate = Body(...),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Configure the auto-recharge rule. Enabling requires a saved method on a
    provider that supports off-session charging."""
    check_not_restricted(user)
    if db_wrapper.get_team_by_id(team_id) is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    cfg = db_wrapper.get_team_payment_config(team_id)
    if body.enabled:
        if cfg is None or not cfg.method_ref:
            raise HTTPException(status_code=400, detail="Save a payment method first")
        prov = payments.get_provider(cfg.provider)
        if prov is None or not prov.supports_auto_recharge:
            raise HTTPException(status_code=400, detail="Saved provider does not support auto-recharge")
        if body.threshold is None or body.amount is None:
            raise HTTPException(status_code=400, detail="threshold and amount are required")
    db_wrapper.upsert_team_payment_config(
        team_id,
        auto_recharge_enabled=bool(body.enabled),
        auto_recharge_threshold=body.threshold,
        auto_recharge_amount=body.amount,
        failure_count=0,
    )
    return _config_response(db_wrapper, team_id)


@router.delete("/teams/{team_id}/payment/method", response_model=TeamPaymentConfigResponse, tags=["Payments"])
async def delete_payment_method(
    team_id: int = Path(description="Team ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Remove the saved payment method (also disables auto-recharge)."""
    check_not_restricted(user)
    db_wrapper.clear_saved_method(team_id)
    return _config_response(db_wrapper, team_id)


@router.get("/teams/{team_id}/payments", response_model=PaymentTransactionsResponse, tags=["Payments"])
async def list_team_payments(
    team_id: int = Path(description="Team ID"),
    start: int = Query(0, ge=0, le=100000),
    end: int = Query(50, ge=1, le=100000),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Payment history (audit) for the team's wallet."""
    rows, total = db_wrapper.list_payments(team_id, start, end)
    txs = [
        PaymentTransaction(
            id=r.id, provider=r.provider, kind=r.kind, amount=r.amount,
            currency=r.currency, status=r.status, created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]
    return PaymentTransactionsResponse(transactions=txs, total=total)
