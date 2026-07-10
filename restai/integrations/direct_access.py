from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import HTTPException

from restai.database import DBWrapper
from restai.limits.budget import enforce_cost_budgets
from restai.models.databasemodels import ApiKeyDatabase, OutputDatabase, TeamDatabase
from restai.models.models import User

# Sentinel: the request didn't authenticate with a team-pinned API key, so
# team resolution should fall through to the legacy first-granting-team loop.
_NOT_PINNED = object()


def _api_key_row(user: User, db: DBWrapper):
    """The ApiKeyDatabase row that authenticated the request, or None."""
    kid = getattr(user, "api_key_id", None)
    if kid is None:
        return None
    return db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == kid).first()


def _budgets_ok(db: DBWrapper, user: User, team) -> bool:
    """True when neither the team nor the caller's per-membership cap is
    exhausted for `team` (api-key cap is checked once up front, not here)."""
    try:
        enforce_cost_budgets(db, user=user, team=team, api_key_row=None)
        return True
    except HTTPException:
        return False


def _resolve_non_pinned(user: User, db: DBWrapper, grants: Callable[[TeamDatabase], bool], not_found: str) -> Optional[int]:
    """Shared non-pinned path: bill the first team that grants the model AND
    has budget headroom (team + caller's per-membership cap). The api-key cost
    cap is global to the key, so it's evaluated once up front and surfaces as a
    402 (not a 403) when exhausted."""
    if user.is_admin:
        return None

    # api-key cost cap (global to the key) — raise 402 before scanning teams.
    api_key_row = _api_key_row(user, db)
    if api_key_row is not None:
        enforce_cost_budgets(db, user=user, api_key_row=api_key_row)

    for team in db.get_teams_for_user(user.id):
        if grants(team) and _budgets_ok(db, user, team):
            return team.id

    raise HTTPException(status_code=403, detail=not_found)


def _pin_api_key_team(user: User, db: DBWrapper, has_access: Callable[[TeamDatabase], bool]):
    """When the request authenticated via an API key that carries a team,
    pin billing to that team deterministically (instead of the order-dependent
    first-granting-team scan). Returns the team_id, or `_NOT_PINNED` when there
    is no key team so the caller falls back to the legacy behavior.

    Admins attribute to the key's team but keep their access/budget bypass;
    non-admins must have model access through that team and stay within every
    applicable cost cap (api-key, per-membership, team)."""
    key_team = getattr(user, "api_key_team_id", None)
    if key_team is None:
        return _NOT_PINNED
    team = db.get_team_by_id(key_team)
    if team is None:
        raise HTTPException(status_code=403, detail="API key team not found")
    if user.is_admin:
        return team.id
    if not has_access(team):
        raise HTTPException(status_code=403, detail="API key's team does not have access to this model")
    enforce_cost_budgets(db, user=user, team=team, api_key_row=_api_key_row(user, db))
    return team.id


def resolve_team_for_llm(user: User, llm_name: str, db: DBWrapper) -> Optional[int]:
    """Returns team_id granting access, None for admin bypass, raises 403 on no access."""
    grants = lambda team: any(l.name == llm_name for l in team.llms)
    pinned = _pin_api_key_team(user, db, grants)
    if pinned is not _NOT_PINNED:
        return pinned
    return _resolve_non_pinned(user, db, grants, "You do not have access to this model")


def resolve_team_for_image_generator(user: User, generator_name: str, db: DBWrapper) -> Optional[int]:
    grants = lambda team: generator_name in [g.generator_name for g in team.image_generators]
    pinned = _pin_api_key_team(user, db, grants)
    if pinned is not _NOT_PINNED:
        return pinned
    return _resolve_non_pinned(user, db, grants, "You do not have access to this image generator")


def resolve_team_for_audio_generator(user: User, generator_name: str, db: DBWrapper) -> Optional[int]:
    grants = lambda team: generator_name in [g.generator_name for g in team.audio_generators]
    pinned = _pin_api_key_team(user, db, grants)
    if pinned is not _NOT_PINNED:
        return pinned
    return _resolve_non_pinned(user, db, grants, "You do not have access to this audio generator")


def resolve_team_for_embedding(user: User, embedding_name: str, db: DBWrapper) -> Optional[int]:
    grants = lambda team: any(e.name == embedding_name for e in team.embeddings)
    pinned = _pin_api_key_team(user, db, grants)
    if pinned is not _NOT_PINNED:
        return pinned
    return _resolve_non_pinned(user, db, grants, "You do not have access to this embedding model")


def log_direct_usage(
    db: DBWrapper,
    user_id: int,
    team_id: Optional[int],
    llm_name: str,
    question: str,
    answer: str,
    input_tokens: int,
    output_tokens: int,
    input_cost: float,
    output_cost: float,
    api_key_id: Optional[int] = None,
):
    entry = OutputDatabase(
        user_id=user_id,
        project_id=None,
        team_id=team_id,
        api_key_id=api_key_id,
        llm=llm_name,
        question=question,
        answer=answer,
        date=datetime.now(timezone.utc),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost=input_cost,
        output_cost=output_cost,
    )
    db.db.add(entry)
    db.db.commit()

    # Count tokens against the API key's monthly quota (parity with the project
    # chat path). No-op for cookie/basic auth or keys without a quota.
    try:
        from restai.limits.budget import record_api_key_tokens
        record_api_key_tokens(api_key_id, (input_tokens or 0) + (output_tokens or 0), db)
    except Exception:
        pass

    # Decrement the team's prepaid wallet by this request's cost (no-op without a wallet).
    try:
        from restai.limits.budget import charge_team_balance
        charge_team_balance(db, team_id, (input_cost or 0.0) + (output_cost or 0.0), actor_user_id=user_id)
    except Exception:
        pass
