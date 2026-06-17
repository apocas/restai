from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
import logging
from datetime import datetime, timezone
from typing import List, Optional

from restai.models.models import (
    TeamBalanceUpdate,
    TeamBalanceTopUp,
    TeamBalanceTransaction,
    TeamBalanceTransactionsResponse,
    TeamBranding,
    TeamMemberBudget,
    TeamMemberBudgetUpdate,
    TeamModel,
    TeamModelCreate,
    TeamModelUpdate,
    TeamsResponse,
    User
)
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from restai.models.databasemodels import TeamDatabase, OutputDatabase, ProjectDatabase, UserDatabase, TeamInvitationDatabase, ProjectInvitationDatabase
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import (
    get_current_username,
    get_current_username_platform_admin,
    get_current_username_team_admin,
    get_current_username_team_member,
    check_not_restricted,
    check_user_can_attach_project,
    check_user_can_attach_llm,
    check_user_can_attach_embedding,
)
from restai.constants import ERROR_MESSAGES

router = APIRouter()


def _team_model_with_spending(db_wrapper: DBWrapper, team_id: int) -> TeamModel:
    """Fresh TeamModel for a team, enriched with month-to-date spending/remaining
    when it has a budget cap. Shared by the balance set/top-up endpoints."""
    result = TeamModel.model_validate(db_wrapper.get_team_by_id(team_id))
    if result.budget is not None and result.budget >= 0:
        spending = db_wrapper.get_team_spending(team_id)
        result.spending = spending
        result.remaining = result.budget - spending
    return result


@router.get("/teams/{team_id}/branding", response_model=TeamBranding)
async def get_team_branding(
    team_id: int = Path(description="Team ID"),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get team branding configuration (public, no auth required)."""
    import json
    team = db_wrapper.get_team_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    try:
        branding_data = json.loads(team.branding) if team.branding else {}
        return TeamBranding(**branding_data)
    except Exception:
        return TeamBranding()


@router.get("/teams", response_model=TeamsResponse)
async def get_teams(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Get all teams the user has access to."""
    try:
        if user.is_admin:
            teams = db_wrapper.get_teams()
        else:
            teams = db_wrapper.get_teams_for_user(user.id)
            
        return {"teams": [TeamModel.model_validate(team) for team in teams]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/teams/{team_id}", response_model=TeamModel)
async def get_team(
    team_id: int = Path(description="Team ID"),
    user: User = Depends(get_current_username_team_member),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Get a specific team by ID."""
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        result = TeamModel.model_validate(team)
        if result.budget >= 0:
            spending = db_wrapper.get_team_spending(team_id)
            result.spending = spending
            result.remaining = result.budget - spending
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams", response_model=TeamModel, status_code=201)
async def create_team(
    team_create: TeamModelCreate,
    user: User = Depends(get_current_username_platform_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Create a new team."""
    check_not_restricted(user)
    try:
        existing_team = db_wrapper.get_team_by_name(team_create.name)
        if existing_team is not None:
            raise HTTPException(status_code=400, detail=ERROR_MESSAGES.TEAM_NAME_TAKEN)
            
        team_data = team_create.model_dump()
        team_data["creator_id"] = user.id

        team = db_wrapper.create_team(TeamModelCreate.model_validate(team_data))

        # Caller is platform admin (auth dep) so per-resource attach gates short-circuit.
        db_wrapper.update_team_members(team, TeamModelUpdate(**team_data), caller=user)
        
        team = db_wrapper.get_team_by_id(team.id)
        return TeamModel.model_validate(team)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/teams/{team_id}", response_model=TeamModel)
async def update_team(
    team_id: int = Path(description="Team ID"),
    team_update: TeamModelUpdate = ...,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Update team details."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        if team_update.name is not None and team_update.name != team.name:
            existing_team = db_wrapper.get_team_by_name(team_update.name)
            if existing_team is not None:
                raise HTTPException(status_code=400, detail=ERROR_MESSAGES.TEAM_NAME_TAKEN)
        
        db_wrapper.update_team(team, team_update)
        
        # resource attach gates fire — without this, a team admin could
        # PATCH `{llms: [team-B-llm]}` and bypass the per-endpoint guards.
        db_wrapper.update_team_members(team, team_update, caller=user)
        
        return TeamModel.model_validate(db_wrapper.get_team_by_id(team_id))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: int = Path(description="Team ID"),
    user: User = Depends(get_current_username_platform_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Delete a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        db_wrapper.delete_team(team)
        return {"deleted": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/users/{username}")
async def add_user_to_team(
    team_id: int = Path(description="Team ID"),
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add a user to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        user_to_add = db_wrapper.get_user_by_username(username)
        if user_to_add is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.add_user_to_team(team, user_to_add)
        return {"added": username, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/users/{username}")
async def remove_user_from_team(
    team_id: int = Path(description="Team ID"),
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove a user from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        user_to_remove = db_wrapper.get_user_by_username(username)
        if user_to_remove is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.remove_user_from_team(team, user_to_remove)
        return {"removed": username, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/admins/{username}")
async def add_admin_to_team(
    team_id: int = Path(description="Team ID"),
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an admin to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        user_to_add = db_wrapper.get_user_by_username(username)
        if user_to_add is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.add_admin_to_team(team, user_to_add)
        return {"added_admin": username, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/admins/{username}")
async def remove_admin_from_team(
    team_id: int = Path(description="Team ID"),
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an admin from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        user_to_remove = db_wrapper.get_user_by_username(username)
        if user_to_remove is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.remove_admin_from_team(team, user_to_remove)
        return {"removed_admin": username, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/projects/{project_id}")
async def add_project_to_team(
    team_id: int = Path(description="Team ID"),
    project_id: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add a project to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        project = db_wrapper.get_project_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)

        check_user_can_attach_project(user, project)

        db_wrapper.add_project_to_team(team, project)
        return {"added_project": project.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/projects/{project_id}")
async def remove_project_from_team(
    team_id: int = Path(description="Team ID"),
    project_id: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove a project from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        project = db_wrapper.get_project_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.remove_project_from_team(team, project)
        return {"removed_project": project.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/llms/{llm_id}")
async def add_llm_to_team(
    team_id: int = Path(description="Team ID"),
    llm_id: int = Path(description="LLM ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an LLM to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        llm = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
        check_user_can_attach_llm(user, llm)
        db_wrapper.add_llm_to_team(team, llm)
        return {"added_llm": llm.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/llms/{llm_id}")
async def remove_llm_from_team(
    team_id: int = Path(description="Team ID"),
    llm_id: int = Path(description="LLM ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an LLM from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        llm = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
        db_wrapper.remove_llm_from_team(team, llm)
        return {"removed_llm": llm.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/embeddings/{embedding_id}")
async def add_embedding_to_team(
    team_id: int = Path(description="Team ID"),
    embedding_id: int = Path(description="Embedding model ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an embedding to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        embedding = db_wrapper.get_embedding_by_id(embedding_id)
        if embedding is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
        check_user_can_attach_embedding(user, embedding)
        db_wrapper.add_embedding_to_team(team, embedding)
        return {"added_embedding": embedding.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/embeddings/{embedding_id}")
async def remove_embedding_from_team(
    team_id: int = Path(description="Team ID"),
    embedding_id: int = Path(description="Embedding model ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an embedding from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        embedding = db_wrapper.get_embedding_by_id(embedding_id)
        if embedding is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
        db_wrapper.remove_embedding_from_team(team, embedding)
        return {"removed_embedding": embedding.name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/teams/{team_id}/transactions")
async def get_team_transactions(
    team_id: int = Path(description="Team ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(100, ge=1, le=100000, description="Pagination end offset"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):

    """Get budget transactions (inference logs) for all projects in a team."""
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        team_project_ids = db_wrapper.db.query(ProjectDatabase.id).filter(
            ProjectDatabase.team_id == team_id
        )

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        base_query = (
            db_wrapper.db.query(
                OutputDatabase,
                ProjectDatabase.name.label("project_name"),
                UserDatabase.username.label("username"),
            )
            .outerjoin(ProjectDatabase, OutputDatabase.project_id == ProjectDatabase.id)
            .outerjoin(UserDatabase, OutputDatabase.user_id == UserDatabase.id)
            .filter(
                or_(
                    OutputDatabase.project_id.in_(team_project_ids),
                    OutputDatabase.team_id == team_id
                ),
                OutputDatabase.date >= month_start
            )
        )

        total = base_query.count()

        rows = (
            base_query
            .order_by(OutputDatabase.date.desc())
            .offset(start)
            .limit(end - start)
            .all()
        )

        transactions = []
        for output, project_name, username in rows:
            input_cost = output.input_cost or 0
            output_cost = output.output_cost or 0
            transactions.append({
                "id": output.id,
                "date": output.date.isoformat() if output.date else None,
                "project": project_name,
                "user": username,
                "llm": output.llm,
                "input_tokens": output.input_tokens or 0,
                "output_tokens": output.output_tokens or 0,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "total_cost": input_cost + output_cost,
                "question": output.question,
                "answer": output.answer,
            })

        return {"transactions": transactions, "total": total}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/teams/{team_id}/balance/transactions", response_model=TeamBalanceTransactionsResponse, tags=["Teams"])
async def get_team_balance_transactions(
    team_id: int = Path(description="Team ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(100, ge=1, le=100000, description="Pagination end offset"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Prepaid-wallet ledger: every balance movement in (top-ups) and out (usage
    debits), newest first. Team admins + platform admins only."""
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        rows, total = db_wrapper.list_balance_transactions(team_id, start, end)
        transactions = [
            TeamBalanceTransaction(
                id=row.id,
                team_id=row.team_id,
                amount=row.amount,
                balance_after=row.balance_after,
                kind=row.kind,
                description=row.description,
                actor_username=actor_username,
                created_at=row.created_at,
            )
            for row, actor_username in rows
        ]
        return TeamBalanceTransactionsResponse(transactions=transactions, total=total)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/teams/{team_id}/analytics", tags=["Statistics"])
async def get_team_analytics(
    team_id: int = Path(description="Team ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year (defaults to current)"),
    month: int = Query(None, ge=1, le=12, description="Month (defaults to current)"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Aggregated usage/cost analytics for a whole team (team admins + platform admins).

    Scope mirrors get_team_spending/get_team_transactions: project-scoped rows for
    the team's projects PLUS direct-access rows (project_id NULL, team_id set), so
    direct-access API usage is fully represented. Costs are pre-computed on each
    OutputDatabase row, so everything is plain SUM/GROUP BY over the selected month.
    """
    import calendar

    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        now = datetime.now(timezone.utc)
        if year is None:
            year = now.year
        if month is None:
            month = now.month
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

        team_project_ids = db_wrapper.db.query(ProjectDatabase.id).filter(
            ProjectDatabase.team_id == team_id
        )
        scope = or_(
            OutputDatabase.project_id.in_(team_project_ids),
            OutputDatabase.team_id == team_id,
        )
        base_filter = [scope, OutputDatabase.date >= start_date, OutputDatabase.date <= end_date]
        cost_expr = func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0.0)
        token_expr = func.coalesce(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens), 0)

        db = db_wrapper.db

        # ---- summary ---------------------------------------------------------
        total_messages = db.query(func.count(OutputDatabase.id)).filter(*base_filter).scalar() or 0
        total_conversations = db.query(func.count(func.distinct(OutputDatabase.chat_id))).filter(
            *base_filter, OutputDatabase.chat_id.isnot(None)
        ).scalar() or 0
        tok = db.query(
            func.coalesce(func.sum(OutputDatabase.input_tokens), 0),
            func.coalesce(func.sum(OutputDatabase.output_tokens), 0),
            func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0.0),
        ).filter(*base_filter).first()
        total_input_tokens = int(tok[0] or 0)
        total_output_tokens = int(tok[1] or 0)
        total_cost = float(tok[2] or 0.0)
        avg_latency = db.query(func.avg(OutputDatabase.latency_ms)).filter(*base_filter).scalar()
        active_users = db.query(func.count(func.distinct(OutputDatabase.user_id))).filter(
            *base_filter, OutputDatabase.user_id.isnot(None)
        ).scalar() or 0
        active_projects = db.query(func.count(func.distinct(OutputDatabase.project_id))).filter(
            *base_filter, OutputDatabase.project_id.isnot(None)
        ).scalar() or 0
        da = db.query(func.count(OutputDatabase.id), cost_expr).filter(
            *base_filter, OutputDatabase.project_id.is_(None)
        ).first()
        direct_access_messages = int(da[0] or 0)
        direct_access_cost = float(da[1] or 0.0)

        summary = {
            "total_messages": total_messages,
            "total_conversations": total_conversations,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "total_cost": round(total_cost, 4),
            "avg_latency_ms": round(avg_latency) if avg_latency else 0,
            "active_users": active_users,
            "active_projects": active_projects,
            "direct_access_messages": direct_access_messages,
            "direct_access_cost": round(direct_access_cost, 4),
        }

        # ---- budget (live current-month, matching the team budget model) -----
        spending_month = float(db_wrapper.get_team_spending(team_id))
        budget_val = team.budget if team.budget is not None else -1.0
        unlimited = budget_val is None or budget_val < 0
        budget = {
            "budget": budget_val,
            "spending_month": round(spending_month, 4),
            "remaining": None if unlimited else round(budget_val - spending_month, 4),
            "unlimited": unlimited,
        }

        # ---- daily -----------------------------------------------------------
        daily_rows = (
            db.query(
                func.date(OutputDatabase.date).label("date"),
                func.coalesce(func.sum(OutputDatabase.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(OutputDatabase.output_tokens), 0).label("output_tokens"),
                cost_expr.label("cost"),
                func.count(OutputDatabase.id).label("messages"),
            )
            .filter(*base_filter)
            .group_by(func.date(OutputDatabase.date))
            .order_by(func.date(OutputDatabase.date))
            .all()
        )
        daily = [{
            "date": str(r.date),
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "tokens": int((r.input_tokens or 0) + (r.output_tokens or 0)),
            "cost": round(float(r.cost or 0), 4),
            "messages": r.messages,
        } for r in daily_rows]

        # ---- per project (direct-access collapses to project=None) -----------
        project_rows = (
            db.query(
                OutputDatabase.project_id,
                ProjectDatabase.name.label("project_name"),
                func.count(OutputDatabase.id).label("messages"),
                token_expr.label("tokens"),
                cost_expr.label("cost"),
            )
            .outerjoin(ProjectDatabase, OutputDatabase.project_id == ProjectDatabase.id)
            .filter(*base_filter)
            .group_by(OutputDatabase.project_id, ProjectDatabase.name)
            .order_by(cost_expr.desc())
            .limit(100)
            .all()
        )
        per_project = [{
            "project_id": r.project_id,
            "project": r.project_name,  # None => direct access (labeled client-side)
            "messages": r.messages,
            "tokens": int(r.tokens or 0),
            "cost": round(float(r.cost or 0), 4),
        } for r in project_rows]

        # ---- per user --------------------------------------------------------
        user_rows = (
            db.query(
                OutputDatabase.user_id,
                UserDatabase.username,
                func.count(OutputDatabase.id).label("messages"),
                token_expr.label("tokens"),
                cost_expr.label("cost"),
            )
            .outerjoin(UserDatabase, OutputDatabase.user_id == UserDatabase.id)
            .filter(*base_filter)
            .group_by(OutputDatabase.user_id, UserDatabase.username)
            .order_by(cost_expr.desc())
            .limit(100)
            .all()
        )
        budgets_map = db_wrapper.get_team_user_budgets_map(team_id)
        per_user = [{
            "user_id": r.user_id,
            "username": r.username,
            "messages": r.messages,
            "tokens": int(r.tokens or 0),
            "cost": round(float(r.cost or 0), 4),
            "budget": budgets_map.get(r.user_id),  # member cap (None = uncapped)
        } for r in user_rows]

        # ---- per LLM ---------------------------------------------------------
        llm_rows = (
            db.query(
                OutputDatabase.llm,
                func.count(OutputDatabase.id).label("messages"),
                token_expr.label("tokens"),
                cost_expr.label("cost"),
            )
            .filter(*base_filter, OutputDatabase.llm.isnot(None))
            .group_by(OutputDatabase.llm)
            .order_by(cost_expr.desc())
            .all()
        )
        per_llm = [{
            "llm": r.llm,
            "messages": r.messages,
            "tokens": int(r.tokens or 0),
            "cost": round(float(r.cost or 0), 4),
        } for r in llm_rows]

        # ---- status breakdown ------------------------------------------------
        status_rows = (
            db.query(OutputDatabase.status, func.count(OutputDatabase.id).label("count"))
            .filter(*base_filter)
            .group_by(OutputDatabase.status)
            .all()
        )
        status_breakdown = [{"status": (r.status or "success"), "count": r.count} for r in status_rows]

        # ---- latency buckets -------------------------------------------------
        LATENCY_BUCKETS = [
            ("0-100ms", 0, 100),
            ("100-500ms", 100, 500),
            ("500ms-2s", 500, 2000),
            ("2-10s", 2000, 10000),
            ("10s+", 10000, None),
        ]
        latency_buckets = []
        for label, lo, hi in LATENCY_BUCKETS:
            q = db.query(func.count(OutputDatabase.id)).filter(
                *base_filter, OutputDatabase.latency_ms.isnot(None), OutputDatabase.latency_ms >= lo
            )
            if hi is not None:
                q = q.filter(OutputDatabase.latency_ms < hi)
            latency_buckets.append({"bucket": label, "count": q.scalar() or 0})

        # ---- hourly ----------------------------------------------------------
        hourly_rows = (
            db.query(
                func.extract("hour", OutputDatabase.date).label("hour"),
                func.count(OutputDatabase.id).label("messages"),
            )
            .filter(*base_filter)
            .group_by(func.extract("hour", OutputDatabase.date))
            .all()
        )
        hourly_map = {int(r.hour): r.messages for r in hourly_rows}
        hourly = [{"hour": h, "messages": hourly_map.get(h, 0)} for h in range(24)]

        return {
            "team": {"id": team.id, "name": team.name},
            "period": {"year": year, "month": month},
            "summary": summary,
            "budget": budget,
            "balance": team.balance,
            "daily": daily,
            "per_project": per_project,
            "per_user": per_user,
            "per_llm": per_llm,
            "status_breakdown": status_breakdown,
            "latency_buckets": latency_buckets,
            "hourly": hourly,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/image_generators/{generator_name}")
async def add_image_generator_to_team(
    team_id: int = Path(description="Team ID"),
    generator_name: str = Path(description="Image generator name"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an image generator to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        db_wrapper.add_image_generator_to_team(team, generator_name)
        return {"added_image_generator": generator_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/image_generators/{generator_name}")
async def remove_image_generator_from_team(
    team_id: int = Path(description="Team ID"),
    generator_name: str = Path(description="Image generator name"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an image generator from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        db_wrapper.remove_image_generator_from_team(team, generator_name)
        return {"removed_image_generator": generator_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/teams/{team_id}/audio_generators/{generator_name}")
async def add_audio_generator_to_team(
    team_id: int = Path(description="Team ID"),
    generator_name: str = Path(description="Audio generator name"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an audio generator to a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        db_wrapper.add_audio_generator_to_team(team, generator_name)
        return {"added_audio_generator": generator_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/teams/{team_id}/audio_generators/{generator_name}")
async def remove_audio_generator_from_team(
    team_id: int = Path(description="Team ID"),
    generator_name: str = Path(description="Audio generator name"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an audio generator from a team."""
    check_not_restricted(user)
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)

        db_wrapper.remove_audio_generator_from_team(team, generator_name)
        return {"removed_audio_generator": generator_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")




@router.post("/teams/{team_id}/invitations", tags=["Teams"])
async def send_team_invitation(
    team_id: int = Path(description="Team ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Invite a user to join a team. Does not disclose whether the user exists."""
    check_not_restricted(user)
    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    # Same response regardless of user existence (don't leak account presence).
    target = db_wrapper.get_user_by_username(username)
    if target is not None:
        team = db_wrapper.get_team_by_id(team_id)
        if team is not None:
            already_member = any(u.id == target.id for u in team.users)
            if not already_member:
                existing = (
                    db_wrapper.db.query(TeamInvitationDatabase)
                    .filter(
                        TeamInvitationDatabase.team_id == team_id,
                        TeamInvitationDatabase.username == username,
                        TeamInvitationDatabase.status == "pending",
                    )
                    .first()
                )
                if existing is None:
                    invite = TeamInvitationDatabase(
                        team_id=team_id,
                        username=username,
                        invited_by=user.id,
                        status="pending",
                        created_at=datetime.now(timezone.utc),
                    )
                    db_wrapper.db.add(invite)
                    db_wrapper.db.commit()

    return {"message": "If the user exists, they will receive the invitation."}


@router.get("/invitations", tags=["Teams"])
async def get_my_invitations(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get pending team and project invitations for the current user."""
    invites = (
        db_wrapper.db.query(TeamInvitationDatabase)
        .options(joinedload(TeamInvitationDatabase.team), joinedload(TeamInvitationDatabase.inviter))
        .filter(
            TeamInvitationDatabase.username == user.username,
            TeamInvitationDatabase.status == "pending",
        )
        .order_by(TeamInvitationDatabase.created_at.desc())
        .all()
    )
    result = []
    for inv in invites:
        team = inv.team
        inviter = inv.inviter
        result.append({
            "id": inv.id,
            "type": "team",
            "team_id": inv.team_id,
            "team_name": team.name if team else "Unknown",
            "invited_by": inviter.username if inviter else "Unknown",
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })

    project_invites = (
        db_wrapper.db.query(ProjectInvitationDatabase)
        .options(joinedload(ProjectInvitationDatabase.project), joinedload(ProjectInvitationDatabase.inviter))
        .filter(
            ProjectInvitationDatabase.username == user.username,
            ProjectInvitationDatabase.status == "pending",
        )
        .order_by(ProjectInvitationDatabase.created_at.desc())
        .all()
    )
    for inv in project_invites:
        project = inv.project
        inviter = inv.inviter
        result.append({
            "id": inv.id,
            "type": "project",
            "project_id": inv.project_id,
            "project_name": project.name if project else "Unknown",
            "invited_by": inviter.username if inviter else "Unknown",
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })
    return result


@router.get("/invitations/count", tags=["Teams"])
async def get_invitation_count(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get the count of pending invitations (team + project) for the current user."""
    from sqlalchemy import func
    team_count = (
        db_wrapper.db.query(func.count(TeamInvitationDatabase.id))
        .filter(
            TeamInvitationDatabase.username == user.username,
            TeamInvitationDatabase.status == "pending",
        )
        .scalar()
    ) or 0
    project_count = (
        db_wrapper.db.query(func.count(ProjectInvitationDatabase.id))
        .filter(
            ProjectInvitationDatabase.username == user.username,
            ProjectInvitationDatabase.status == "pending",
        )
        .scalar()
    ) or 0
    return {"count": team_count + project_count}


@router.post("/invitations/{invitation_id}/accept", tags=["Teams"])
async def accept_invitation(
    invitation_id: int = Path(description="Invitation ID"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Accept a team invitation."""
    invite = (
        db_wrapper.db.query(TeamInvitationDatabase)
        .filter(TeamInvitationDatabase.id == invitation_id)
        .first()
    )
    if invite is None or invite.username != user.username:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")

    team = db_wrapper.get_team_by_id(invite.team_id)
    user_db = db_wrapper.get_user_by_username(user.username)
    if team and user_db and user_db not in team.users:
        team.users.append(user_db)

    invite.status = "accepted"
    db_wrapper.db.commit()

    return {"message": f"Joined team '{team.name if team else ''}'"}


@router.post("/invitations/{invitation_id}/decline", tags=["Teams"])
async def decline_invitation(
    invitation_id: int = Path(description="Invitation ID"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Decline a team invitation."""
    invite = (
        db_wrapper.db.query(TeamInvitationDatabase)
        .filter(TeamInvitationDatabase.id == invitation_id)
        .first()
    )
    if invite is None or invite.username != user.username:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")

    invite.status = "declined"
    db_wrapper.db.commit()

    return {"message": "Invitation declined"}




@router.post("/invitations/projects/{invitation_id}/accept", tags=["Projects"])
async def accept_project_invitation(
    invitation_id: int = Path(description="Invitation ID"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Accept a project invitation."""
    invite = (
        db_wrapper.db.query(ProjectInvitationDatabase)
        .filter(ProjectInvitationDatabase.id == invitation_id)
        .first()
    )
    if invite is None or invite.username != user.username:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")

    project = db_wrapper.get_project_by_id(invite.project_id)
    user_db = db_wrapper.get_user_by_username(user.username)
    if project and user_db and user_db not in project.users:
        project.users.append(user_db)

    invite.status = "accepted"
    db_wrapper.db.commit()

    return {"message": f"Joined project '{project.name if project else ''}'"}


@router.post("/invitations/projects/{invitation_id}/decline", tags=["Projects"])
async def decline_project_invitation(
    invitation_id: int = Path(description="Invitation ID"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Decline a project invitation."""
    invite = (
        db_wrapper.db.query(ProjectInvitationDatabase)
        .filter(ProjectInvitationDatabase.id == invitation_id)
        .first()
    )
    if invite is None or invite.username != user.username:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invitation is no longer pending")

    invite.status = "declined"
    db_wrapper.db.commit()

    return {"message": "Invitation declined"}


def _member_budget_row(db_wrapper, team_id, target):
    cap = db_wrapper.get_team_user_budget(team_id, target.id)
    sp = round(db_wrapper.get_team_user_spending(team_id, target.id), 4)
    return TeamMemberBudget(
        user_id=target.id, username=target.username, budget=cap, spending=sp,
        remaining=(None if cap is None else round(cap - sp, 4)),
    )


@router.get("/teams/{team_id}/members/budgets", response_model=List[TeamMemberBudget], tags=["Teams"])
async def get_team_member_budgets(
    team_id: int = Path(description="Team ID"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Per-member monthly cost caps + month-to-date spend for the whole team
    (team admins + platform admins). One fetch drives the budget chips/dialogs."""
    team = db_wrapper.get_team_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    members = {u.id: u for u in (list(team.users) + list(team.admins))}
    caps = db_wrapper.get_team_user_budgets_map(team_id)
    spend = db_wrapper.get_team_user_spending_map(team_id)
    out = []
    for uid, u in members.items():
        cap = caps.get(uid)
        sp = round(spend.get(uid, 0.0), 4)
        out.append(TeamMemberBudget(
            user_id=uid, username=u.username, budget=cap, spending=sp,
            remaining=(None if cap is None else round(cap - sp, 4)),
        ))
    out.sort(key=lambda m: (m.username or "").lower())
    return out


@router.patch("/teams/{team_id}/members/{username}/budget", response_model=TeamMemberBudget, tags=["Teams"])
async def set_team_member_budget(
    team_id: int = Path(description="Team ID"),
    username: str = Path(description="Member username"),
    body: TeamMemberBudgetUpdate = Body(...),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Set or clear a member's monthly cost cap (team admins + platform admins).
    `budget` null or -1 clears the cap. Validates the target is a team member."""
    check_not_restricted(user)
    team = db_wrapper.get_team_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    target = db_wrapper.get_user_by_username(username)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    member_ids = {u.id for u in (list(team.users) + list(team.admins))}
    if target.id not in member_ids:
        raise HTTPException(status_code=400, detail="User is not a member of this team")
    db_wrapper.set_team_user_budget(team_id, target.id, body.budget)
    return _member_budget_row(db_wrapper, team_id, target)


@router.patch("/teams/{team_id}/balance", response_model=TeamModel, tags=["Teams"])
async def set_team_balance(
    team_id: int = Path(description="Team ID"),
    body: TeamBalanceUpdate = Body(...),
    user: User = Depends(get_current_username_platform_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Set the team's prepaid wallet balance to an absolute value (platform admins
    only — it's real money). Use the topup endpoint to add funds; this is for
    corrections/adjustments."""
    check_not_restricted(user)
    team = db_wrapper.get_team_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    old = float(team.balance) if team.balance is not None else 0.0
    new = float(body.balance)
    delta = new - old
    team.balance = new
    if delta != 0:
        db_wrapper.add_balance_transaction(
            team_id, amount=delta, balance_after=new,
            kind="topup" if delta > 0 else "adjustment",
            description=f"Set to ${new:.2f}", actor_user_id=user.id,
        )
    db_wrapper.db.commit()
    return _team_model_with_spending(db_wrapper, team_id)


@router.post("/teams/{team_id}/balance/topup", response_model=TeamModel, tags=["Teams"])
async def topup_team_balance(
    team_id: int = Path(description="Team ID"),
    body: TeamBalanceTopUp = Body(...),
    user: User = Depends(get_current_username_platform_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Add funds to the team's prepaid wallet (platform admins only — it's real
    money). Additive credit: the first top-up of a team with no wallet (NULL)
    activates it. Records a `topup` ledger row."""
    check_not_restricted(user)
    team = db_wrapper.get_team_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
    current = float(team.balance) if team.balance is not None else 0.0
    amount = float(body.amount)
    new = current + amount
    team.balance = new
    db_wrapper.add_balance_transaction(
        team_id, amount=amount, balance_after=new, kind="topup",
        description=f"Topped up ${amount:.2f}", actor_user_id=user.id,
    )
    db_wrapper.db.commit()
    return _team_model_with_spending(db_wrapper, team_id)