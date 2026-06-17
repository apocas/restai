"""DBWrapper payment methods (mixin).

Payment audit/idempotency rows (`payment_transactions`) and per-team saved
method + auto-recharge rule (`team_payment_config`). Crediting itself lives in
`restai.payments.service`; these are the persistence helpers it builds on.
"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from restai.models.databasemodels import (
    PaymentTransactionDatabase, TeamPaymentConfigDatabase, TeamDatabase,
)


class PaymentMixin:
    __slots__ = ()

    def create_payment(self, *, team_id: int, provider: str, kind: str, provider_ref: str,
                       amount: float, currency: str,
                       actor_user_id: Optional[int] = None) -> PaymentTransactionDatabase:
        row = PaymentTransactionDatabase(
            team_id=team_id, provider=provider, kind=kind, provider_ref=provider_ref,
            amount=float(amount), currency=currency, status="pending",
            actor_user_id=actor_user_id, created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def get_payment(self, provider: str, provider_ref: str) -> Optional[PaymentTransactionDatabase]:
        return (
            self.db.query(PaymentTransactionDatabase)
            .filter(PaymentTransactionDatabase.provider == provider,
                    PaymentTransactionDatabase.provider_ref == provider_ref)
            .first()
        )

    def get_payment_by_id(self, payment_id: int) -> Optional[PaymentTransactionDatabase]:
        return (
            self.db.query(PaymentTransactionDatabase)
            .filter(PaymentTransactionDatabase.id == payment_id)
            .first()
        )

    def has_pending_payment(self, team_id: int, kind: str) -> bool:
        return self.db.query(PaymentTransactionDatabase.id).filter(
            PaymentTransactionDatabase.team_id == team_id,
            PaymentTransactionDatabase.kind == kind,
            PaymentTransactionDatabase.status == "pending",
        ).first() is not None

    def list_payments(self, team_id: int, start: int, end: int) -> Tuple[list, int]:
        base = self.db.query(PaymentTransactionDatabase).filter(
            PaymentTransactionDatabase.team_id == team_id)
        total = base.count()
        rows = (
            base.order_by(PaymentTransactionDatabase.created_at.desc(),
                          PaymentTransactionDatabase.id.desc())
            .offset(start).limit(end - start).all()
        )
        return rows, total

    def get_team_payment_config(self, team_id: int) -> Optional[TeamPaymentConfigDatabase]:
        return (
            self.db.query(TeamPaymentConfigDatabase)
            .filter(TeamPaymentConfigDatabase.team_id == team_id)
            .first()
        )

    def upsert_team_payment_config(self, team_id: int, **fields) -> TeamPaymentConfigDatabase:
        row = self.get_team_payment_config(team_id)
        if row is None:
            row = TeamPaymentConfigDatabase(team_id=team_id)
            self.db.add(row)
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return row

    def clear_saved_method(self, team_id: int) -> None:
        row = self.get_team_payment_config(team_id)
        if row is None:
            return
        row.provider = None
        row.customer_ref = None
        row.method_ref = None
        row.brand = None
        row.last4 = None
        row.auto_recharge_enabled = False
        row.failure_count = 0
        row.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def teams_due_for_auto_recharge(self) -> List[Tuple[TeamPaymentConfigDatabase, TeamDatabase]]:
        """(config, team) pairs with auto-recharge on, a saved method, and balance
        below threshold. The cron filters further (in-flight guard, provider)."""
        rows = (
            self.db.query(TeamPaymentConfigDatabase, TeamDatabase)
            .join(TeamDatabase, TeamPaymentConfigDatabase.team_id == TeamDatabase.id)
            .filter(
                TeamPaymentConfigDatabase.auto_recharge_enabled.is_(True),
                TeamPaymentConfigDatabase.method_ref.isnot(None),
                TeamPaymentConfigDatabase.auto_recharge_threshold.isnot(None),
                TeamPaymentConfigDatabase.auto_recharge_amount.isnot(None),
                TeamDatabase.balance.isnot(None),
                TeamDatabase.balance < TeamPaymentConfigDatabase.auto_recharge_threshold,
            )
            .all()
        )
        return rows
