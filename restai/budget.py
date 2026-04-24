from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func

from restai.database import DBWrapper
from restai.models.databasemodels import ApiKeyDatabase, OutputDatabase
from restai.project import Project


def check_budget(project: Project, db: DBWrapper):
    """Pre-check budget before inference. Raises HTTP 402 if exhausted."""
    team = project.props.team
    if team is not None and team.budget >= 0:
        team_spending = db.get_team_spending(team.id)
        if team.budget - team_spending <= 0:
            # Fire a webhook before we raise so external systems can
            # react (page oncall, top up the budget, etc.). Best-effort —
            # webhook failures must never mask the 402.
            try:
                from restai.webhooks import emit_event
                opts = getattr(getattr(project, "props", None), "options", None)
                opts_dict = opts.model_dump() if hasattr(opts, "model_dump") else (opts or {})
                emit_event(
                    project.props.id, project.props.name, opts_dict,
                    "budget_exceeded",
                    {"team_id": team.id, "team_budget": team.budget, "team_spending": team_spending},
                )
            except Exception:
                pass
            raise HTTPException(status_code=402, detail="Team budget exhausted")


def check_rate_limit(project: Project, db: DBWrapper):
    """Pre-check rate limit before inference. Raises HTTP 429 if exceeded."""
    rate_limit = project.props.options.rate_limit
    if rate_limit is None:
        return
    one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    count = (
        db.db.query(func.count(OutputDatabase.id))
        .filter(
            OutputDatabase.project_id == project.props.id,
            OutputDatabase.date >= one_minute_ago,
        )
        .scalar()
    )
    if count >= rate_limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


def _first_of_next_month(now: datetime) -> datetime:
    """Return the UTC first-of-next-month at 00:00. Monthly quotas roll
    over on calendar boundaries — simplest semantics to reason about
    when a customer asks 'when does my quota reset?'."""
    y, m = now.year, now.month
    if m == 12:
        return datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(y, m + 1, 1, tzinfo=timezone.utc)


def check_api_key_quota(user, db: DBWrapper):
    """If the request authenticated via an API key, enforce that key's
    monthly token quota. No-op for basic/cookie auth (no api_key_id) and
    for keys with `token_quota_monthly = NULL` (unlimited).

    Rolls the counter over lazily: if `quota_reset_at` is in the past,
    zero `tokens_used_this_month` and set a new reset date before
    checking the cap. Cheaper than a scheduled job and bounded to one
    write per key per month."""
    api_key_id = getattr(user, "api_key_id", None)
    if api_key_id is None:
        return
    key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key_id).first()
    if key is None or key.token_quota_monthly is None:
        return

    now = datetime.now(timezone.utc)
    reset_at = key.quota_reset_at
    if reset_at is None or (reset_at.tzinfo is None and reset_at.replace(tzinfo=timezone.utc) <= now) or (reset_at.tzinfo is not None and reset_at <= now):
        key.tokens_used_this_month = 0
        key.quota_reset_at = _first_of_next_month(now)
        db.db.commit()

    if (key.tokens_used_this_month or 0) >= key.token_quota_monthly:
        # Use 429 (same code as rate limit) with a clear detail; receivers
        # don't need to distinguish between "too fast" and "too much".
        raise HTTPException(
            status_code=429,
            detail=(
                f"API key monthly token quota reached "
                f"({key.tokens_used_this_month}/{key.token_quota_monthly}). "
                f"Resets at {key.quota_reset_at.isoformat() if key.quota_reset_at else 'next month'}."
            ),
        )


def record_api_key_tokens(api_key_id: int, tokens: int, db: DBWrapper) -> None:
    """Bump ``tokens_used_this_month`` after a successful inference. Silent
    on unknown key id — the key may have been deleted between auth and
    log write."""
    if not api_key_id or tokens <= 0:
        return
    key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key_id).first()
    if key is None:
        return
    key.tokens_used_this_month = (key.tokens_used_this_month or 0) + int(tokens)
    db.db.commit()
