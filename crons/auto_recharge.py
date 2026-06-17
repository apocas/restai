#!/usr/bin/env python3
"""Auto-recharge — cron-friendly script.

For each team with auto-recharge enabled, a saved payment method, and a balance
below its threshold, charge the saved method off-session and credit the wallet.
Stripe-only in v1 (PayPal advertises supports_auto_recharge=False). Runs once
per tick (the runner serialises via a per-job flock) and exits.

Usage:
    uv run python crons/auto_recharge.py
"""
import logging
import uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("restai.payments.auto_recharge")

from restai.settings import ensure_settings_table
from restai.database import open_db_wrapper, engine as db_engine
from restai import payments
from restai.payments import service as payment_service
from restai.payments.base import PaymentError

MAX_FAILURES = 3


def main():
    from restai.observability.cron_log import CronLogger
    cron = CronLogger("auto_recharge")

    ensure_settings_table(db_engine)

    if not payments.payments_enabled():
        cron.finish(items_processed=0)
        return

    db = open_db_wrapper()
    charged = 0
    try:
        due = db.teams_due_for_auto_recharge()
        for cfg, team in due:
            provider = payments.get_provider(cfg.provider)
            if provider is None or not provider.is_configured() or not provider.supports_auto_recharge:
                continue
            if (cfg.failure_count or 0) >= MAX_FAILURES:
                # Too many failures — stop trying until the admin intervenes.
                db.upsert_team_payment_config(team.id, auto_recharge_enabled=False)
                cron.warning(f"Disabled auto-recharge for team {team.name}: {MAX_FAILURES} consecutive failures")
                continue
            if db.has_pending_payment(team.id, "auto_recharge"):
                continue

            currency = db.get_setting_value("currency", "EUR") or "EUR"
            amount = float(cfg.auto_recharge_amount)
            # Pre-create a pending row (in-flight guard); provider_ref is fixed up
            # to the real charge id once we have it.
            row = db.create_payment(
                team_id=team.id, provider=provider.name, kind="auto_recharge",
                provider_ref=f"ar-{team.id}-{uuid.uuid4().hex}", amount=amount,
                currency=currency, actor_user_id=None,
            )
            try:
                event = provider.charge_saved_method(
                    amount=amount, currency=currency,
                    customer_ref=cfg.customer_ref, method_ref=cfg.method_ref,
                )
                row.provider_ref = event.provider_ref or row.provider_ref
                db.db.commit()
                if payment_service.credit_payment(db, row.id, event):
                    db.upsert_team_payment_config(team.id, failure_count=0)
                    charged += 1
                    cron.info(f"Auto-recharged team {team.name} by {amount} {currency}")
            except PaymentError as e:
                payment_service.mark_payment_failed(db, row.id, str(e))
                new_failures = (cfg.failure_count or 0) + 1
                db.upsert_team_payment_config(team.id, failure_count=new_failures)
                cron.error(f"Auto-recharge failed for team {team.name}: {e}")
            except Exception as e:
                payment_service.mark_payment_failed(db, row.id, str(e))
                logger.exception("auto-recharge crashed for team %s", team.id)
                cron.error(f"Auto-recharge crashed for team {team.name}: {e}")

        cron.finish(items_processed=charged)
    except Exception as e:
        cron.error(f"Auto-recharge crashed: {e}", details=__import__("traceback").format_exc())
        cron.finish()
    finally:
        db.db.close()


if __name__ == "__main__":
    main()
