from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func

from restai.database import DBWrapper
from restai.models.databasemodels import ApiKeyDatabase, OutputDatabase
from restai.project import Project


# Scope-specific 402 messages. "Team budget exhausted" is preserved verbatim
# for back-compat (existing tests / clients key on it).
_BUDGET_DETAIL = {
    "project": "Project budget exhausted",
    "api_key": "API key cost budget exhausted",
    "user_in_team": "Your personal budget for this team is exhausted",
    "team": "Team budget exhausted",
    "balance": "Team balance depleted",
}


def _emit_budget_webhook(project, scope, cap, spent, team_id=None):
    """Best-effort budget_exceeded webhook. Never masks the 402. Only meaningful
    when a project is in scope (emit_event needs project options); direct-access
    paths (project=None) skip it."""
    if project is None:
        return
    try:
        from restai.comms.webhooks import emit_event
        opts = getattr(getattr(project, "props", None), "options", None)
        opts_dict = opts.model_dump() if hasattr(opts, "model_dump") else (opts or {})
        emit_event(
            project.props.id, project.props.name, opts_dict,
            "budget_exceeded",
            {"scope": scope, "budget": cap, "spending": spent, "team_id": team_id},
        )
    except Exception:
        pass


def enforce_cost_budgets(db: DBWrapper, *, project=None, user=None, team=None, api_key_row=None):
    """Single entrypoint for the unified cost-budget model. Evaluates every
    applicable monthly cost cap (project → api-key → user-in-team → team) vs its
    month-to-date spend and raises HTTPException(402) on the FIRST exhausted scope.

    Caps are skipped when unset (None or < 0). Platform admins bypass all cost
    caps (consistent with prior behavior). `team` may be a TeamModel or a
    TeamDatabase (both expose .id / .budget); when omitted it falls back to the
    project's team."""
    if user is not None and getattr(user, "is_admin", False):
        return

    if team is None and project is not None:
        team = getattr(project.props, "team", None)

    def _exhausted(cap, spent):
        return cap is not None and cap >= 0 and (cap - spent) <= 0

    # 0. team balance — the hard prepaid wallet. NULL = no wallet (skip); a
    # depleted wallet (<= 0) stops ALL usage (highest-priority gate). This is a
    # real-money constraint, distinct from the soft `budget` cap below.
    if team is not None:
        bal = getattr(team, "balance", None)
        if bal is not None and bal <= 0:
            _emit_budget_webhook(project, "balance", bal, bal, team_id=team.id)
            raise HTTPException(status_code=402, detail=_BUDGET_DETAIL["balance"])

    # 1. project
    if project is not None:
        cap = getattr(getattr(project.props, "options", None), "budget", None)
        if cap is not None and cap >= 0:
            spent = db.spend_for(project_id=project.props.id)
            if _exhausted(cap, spent):
                _emit_budget_webhook(project, "project", cap, spent)
                raise HTTPException(status_code=402, detail=_BUDGET_DETAIL["project"])

    # 2. api-key (cost cap; distinct from the token quota)
    if api_key_row is not None:
        cap = getattr(api_key_row, "cost_budget_monthly", None)
        if cap is not None and cap >= 0:
            spent = db.spend_for(api_key_id=api_key_row.id)
            if _exhausted(cap, spent):
                _emit_budget_webhook(project, "api_key", cap, spent)
                raise HTTPException(status_code=402, detail=_BUDGET_DETAIL["api_key"])

    # 3. user-in-team
    if team is not None and user is not None:
        cap = db.get_team_user_budget(team.id, user.id)
        if cap is not None:
            spent = db.get_team_user_spending(team.id, user.id)
            if _exhausted(cap, spent):
                _emit_budget_webhook(project, "user_in_team", cap, spent, team_id=team.id)
                raise HTTPException(status_code=402, detail=_BUDGET_DETAIL["user_in_team"])

    # 4. team
    if team is not None and team.budget is not None and team.budget >= 0:
        spent = db.get_team_spending(team.id)
        if _exhausted(team.budget, spent):
            _emit_budget_webhook(project, "team", team.budget, spent, team_id=team.id)
            raise HTTPException(status_code=402, detail=_BUDGET_DETAIL["team"])


def check_budget(project: Project, db: DBWrapper):
    """Back-compat shim — project-path team+project+user cost budgets.

    Kept so existing importers (app/validate.py, app/generate.py) keep working;
    chat_main now calls enforce_cost_budgets directly (it also passes the user +
    api key). Resolves the user/api-key from the project context is not possible
    here, so this only enforces project + team scope."""
    enforce_cost_budgets(db, project=project, team=project.props.team)


def check_rate_limit(project: Project, db: DBWrapper):
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
    y, m = now.year, now.month
    if m == 12:
        return datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(y, m + 1, 1, tzinfo=timezone.utc)


def check_api_key_quota(user, db: DBWrapper):
    """If the request authenticated via an API key, enforce that key's
    monthly token quota. No-op for basic/cookie auth (no api_key_id) and
    for keys with `token_quota_monthly = NULL` (unlimited).

    Rolls the counter over lazily on first check after `quota_reset_at`."""
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
        raise HTTPException(
            status_code=429,
            detail=(
                f"API key monthly token quota reached "
                f"({key.tokens_used_this_month}/{key.token_quota_monthly}). "
                f"Resets at {key.quota_reset_at.isoformat() if key.quota_reset_at else 'next month'}."
            ),
        )


def record_api_key_tokens(api_key_id: int, tokens: int, db: DBWrapper) -> None:
    if not api_key_id or tokens <= 0:
        return
    key = db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == api_key_id).first()
    if key is None:
        return
    key.tokens_used_this_month = (key.tokens_used_this_month or 0) + int(tokens)
    db.db.commit()


def charge_team_balance(db: DBWrapper, team_id, amount: float, actor_user_id=None) -> None:
    """Decrement a team's prepaid wallet by `amount` (the inference cost), clamped
    at 0, and record the movement in the ledger. No-op when there's no team, a
    non-positive amount, or the team has no wallet (balance is NULL). Called after
    each inference is logged — the request that crosses zero is absorbed; the next
    one is blocked by enforce_cost_budgets. The debit row + balance update commit
    atomically, so the ledger always reconciles with teams.balance."""
    if team_id is None or amount is None or amount <= 0:
        return
    team = db.get_team_by_id(team_id)
    if team is None or team.balance is None:
        return
    before = float(team.balance)
    after = max(0.0, before - float(amount))
    applied = before - after  # actual amount removed (clamped at 0 on overspend)
    if applied <= 0:
        return  # wallet already empty — nothing moved, no ledger noise
    team.balance = after
    db.add_balance_transaction(team_id, amount=-applied, balance_after=after,
                               kind="usage", actor_user_id=actor_user_id)
    db.db.commit()
