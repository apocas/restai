"""Centralised, idempotent crediting — every provider funnels through here.

A successful payment becomes a wallet `topup` ledger row + a balance bump, exactly
like `topup_team_balance` (restai/routers/teams.py). Idempotency is enforced by an
atomic `UPDATE ... WHERE status='pending'` claim so a webhook and a return-page
finalize for the same payment can never double-credit."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from restai.models.databasemodels import PaymentTransactionDatabase
from restai.payments.base import PaymentEvent

logger = logging.getLogger(__name__)


def credit_payment(db, payment_id: int, event: PaymentEvent) -> bool:
    """Credit the team wallet for a completed payment. Returns True iff this call
    is the one that actually credited (idempotent — later calls return False)."""
    if event.status != "paid":
        return False

    now = datetime.now(timezone.utc)
    # Atomic claim: only the txn that flips pending->completed proceeds to credit.
    claimed = (
        db.db.query(PaymentTransactionDatabase)
        .filter(PaymentTransactionDatabase.id == payment_id,
                PaymentTransactionDatabase.status == "pending")
        .update({"status": "completed", "completed_at": now}, synchronize_session=False)
    )
    if not claimed:
        db.db.rollback()
        return False

    row = db.db.query(PaymentTransactionDatabase).filter(
        PaymentTransactionDatabase.id == payment_id).first()
    team = db.get_team_by_id(row.team_id)
    if team is None:
        db.db.commit()
        return False

    amount = event.amount if event.amount is not None else row.amount
    current = float(team.balance) if team.balance is not None else 0.0
    new = current + float(amount)
    team.balance = new
    btx = db.add_balance_transaction(
        row.team_id, amount=float(amount), balance_after=new, kind="topup",
        description=f"{row.provider.capitalize()} payment", actor_user_id=row.actor_user_id,
    )
    db.db.flush()
    row.balance_transaction_id = btx.id
    if event.amount is not None:
        row.amount = float(event.amount)
    db.db.commit()

    # Persist the saved card if the provider returned one (save-on-top-up).
    if event.method_ref:
        try:
            record_saved_method(db, row.team_id, row.provider, event)
        except Exception:
            logger.exception("failed to record saved method for team %s", row.team_id)
    return True


def complete_setup(db, payment_id: int, event: PaymentEvent) -> bool:
    """Finalize a save-a-card (setup) payment: mark completed + persist the saved
    method. No balance change. Idempotent via the atomic claim."""
    if event.status != "paid":
        return False
    now = datetime.now(timezone.utc)
    claimed = (
        db.db.query(PaymentTransactionDatabase)
        .filter(PaymentTransactionDatabase.id == payment_id,
                PaymentTransactionDatabase.status == "pending")
        .update({"status": "completed", "completed_at": now}, synchronize_session=False)
    )
    if not claimed:
        db.db.rollback()
        return False
    row = db.db.query(PaymentTransactionDatabase).filter(
        PaymentTransactionDatabase.id == payment_id).first()
    db.db.commit()
    if event.method_ref:
        try:
            record_saved_method(db, row.team_id, row.provider, event)
        except Exception:
            logger.exception("failed to record saved method for team %s", row.team_id)
    return True


def record_saved_method(db, team_id: int, provider: str, event: PaymentEvent) -> None:
    """Store the reusable payment method (for auto-recharge)."""
    db.upsert_team_payment_config(
        team_id,
        provider=provider,
        customer_ref=event.customer_ref,
        method_ref=event.method_ref,
        brand=event.brand,
        last4=event.last4,
    )


def mark_payment_failed(db, payment_id: int, error: str) -> None:
    row = db.db.query(PaymentTransactionDatabase).filter(
        PaymentTransactionDatabase.id == payment_id,
        PaymentTransactionDatabase.status == "pending",
    ).first()
    if row is None:
        return
    row.status = "failed"
    row.error = (error or "")[:2000]
    db.db.commit()
