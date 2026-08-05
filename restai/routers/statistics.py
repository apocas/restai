import logging
from datetime import datetime, timedelta, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from restai import config
from restai.auth import (
    get_current_username,
    get_current_username_admin,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import (
    User,
)
from restai.models.databasemodels import OutputDatabase, ProjectDatabase, UserDatabase, TeamDatabase, users_projects
from sqlalchemy import and_, func, or_, true


logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

@router.get("/statistics/top-projects")
async def get_top_projects_by_tokens(
    limit: int = Query(10, ge=1, le=1000, description="Maximum number of projects to return"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get projects ranked by total token consumption."""
    try:
        query = (
            db_wrapper.db.query(
                ProjectDatabase,
                func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("total_tokens"),
                func.sum(OutputDatabase.input_tokens).label("input_tokens"),
                func.sum(OutputDatabase.output_tokens).label("output_tokens"),
                func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("total_cost")
            )
            .join(OutputDatabase, ProjectDatabase.id == OutputDatabase.project_id)
        )

        query = query.filter(_visible_project_predicate(user, db_wrapper))

        top_projects = (
            query
            .group_by(ProjectDatabase.id)
            .order_by(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).desc())
            .limit(limit)
            .all()
        )

        return {
            "projects": [
                {
                    "id": project.ProjectDatabase.id,
                    "name": project.ProjectDatabase.name,
                    "type": project.ProjectDatabase.type,
                    "llm": project.ProjectDatabase.llm,
                    "total_tokens": project.total_tokens,
                    "input_tokens": project.input_tokens,
                    "output_tokens": project.output_tokens,
                    "total_cost": project.total_cost
                }
                for project in top_projects
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


def _visible_project_predicate(user: User, db_wrapper: DBWrapper):
    """SQL predicate for the projects `user` may see in aggregate statistics.

    Mirrors `auth.get_current_username_project`: direct membership, OR any
    project in a team the user administers, OR a public project in one of their
    teams. Then — for every caller including admins — narrowed by the presented
    credential's own project scope.

    Both halves have been wrong here before. The team constraint was missing, so
    `public == True` alone leaked names and spend across tenants. And the whole
    filter used to sit behind `if not user.is_admin`, which meant a key minted
    `read_only=True, allowed_projects=[one]` — exactly what mobile pairing hands
    to a phone — returned every project on the platform whenever its owner was
    an admin. `has_api_key_project_access` (models.py) is deliberately NOT
    short-circuited on is_admin for that reason; this router simply never
    consulted it.
    """
    member = ProjectDatabase.id.in_(
        db_wrapper.db.query(users_projects.c.project_id)
        .filter(users_projects.c.user_id == user.id)
    )
    team_ids = {t.id for t in (user.teams or [])}
    admin_team_ids = {t.id for t in (user.admin_teams or [])}

    if user.is_admin:
        visible = true()
    else:
        clauses = [member]
        if admin_team_ids:
            # Team admins reach every project in their teams, public or not —
            # matching get_current_username_project, which this used to be
            # stricter than (team admins under-counted their own dashboards).
            clauses.append(ProjectDatabase.team_id.in_(admin_team_ids))
        if team_ids:
            clauses.append(
                and_(ProjectDatabase.public == True, ProjectDatabase.team_id.in_(team_ids))
            )
        visible = or_(*clauses) if len(clauses) > 1 else clauses[0]

    # The credential's advertised scope binds regardless of who owns it.
    if user.api_key_allowed_projects is not None:
        visible = and_(visible, ProjectDatabase.id.in_(user.api_key_allowed_projects))
    return visible


def _user_project_filter(user: User, db_wrapper: DBWrapper):
    """Returns a filter condition that limits OutputDatabase rows to projects the user can access."""
    return OutputDatabase.project_id.in_(
        db_wrapper.db.query(ProjectDatabase.id).filter(
            _visible_project_predicate(user, db_wrapper)
        )
    )


@router.get("/statistics/summary")
async def get_statistics_summary(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get platform-wide usage summary (tokens, costs, counts)."""
    try:
        token_query = db_wrapper.db.query(
            func.coalesce(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0).label("total_cost"),
            func.avg(OutputDatabase.latency_ms).label("avg_latency_ms"),
        )
        token_query = token_query.filter(_user_project_filter(user, db_wrapper))
        token_stats = token_query.first()

        # The predicate is `true()` for an unscoped admin, so one filtered count
        # covers both cases — and a project-scoped key is narrowed even when its
        # owner is an admin.
        total_projects = db_wrapper.db.query(func.count(ProjectDatabase.id)).filter(
            _visible_project_predicate(user, db_wrapper)
        ).scalar() or 0

        # Platform-wide rosters are not project-scoped, so a narrowed key must
        # not see them either.
        if user.is_admin and user.api_key_allowed_projects is None:
            total_users = db_wrapper.db.query(func.count(UserDatabase.id)).scalar() or 0
            total_teams = db_wrapper.db.query(func.count(TeamDatabase.id)).scalar() or 0
        else:
            total_users = 0
            total_teams = 0

        return {
            "total_tokens": token_stats.total_tokens,
            "total_cost": token_stats.total_cost,
            "avg_latency_ms": round(token_stats.avg_latency_ms) if token_stats.avg_latency_ms else 0,
            "total_projects": total_projects,
            "total_users": total_users,
            "total_teams": total_teams,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics/daily-tokens")
async def get_daily_tokens(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get daily token consumption over a time period."""
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            db_wrapper.db.query(
                func.date(OutputDatabase.date).label("date"),
                func.sum(OutputDatabase.input_tokens).label("input_tokens"),
                func.sum(OutputDatabase.output_tokens).label("output_tokens"),
                func.sum(OutputDatabase.input_cost).label("input_cost"),
                func.sum(OutputDatabase.output_cost).label("output_cost"),
                func.avg(OutputDatabase.latency_ms).label("avg_latency_ms"),
            )
            .filter(OutputDatabase.date >= start_date)
        )
        query = query.filter(_user_project_filter(user, db_wrapper))

        daily = (
            query
            .group_by(func.date(OutputDatabase.date))
            .order_by(func.date(OutputDatabase.date))
            .all()
        )

        return {
            "tokens": [
                {
                    "date": str(row.date),
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "input_cost": row.input_cost or 0,
                    "output_cost": row.output_cost or 0,
                    "avg_latency_ms": round(row.avg_latency_ms) if row.avg_latency_ms else 0,
                }
                for row in daily
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics/top-llms")
async def get_top_llms(
    limit: int = Query(10, ge=1, le=1000, description="Maximum number of LLMs to return"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get LLMs ranked by total token consumption."""
    try:
        query = (
            db_wrapper.db.query(
                OutputDatabase.llm.label("name"),
                func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("total_tokens"),
                func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("total_cost"),
                func.count(OutputDatabase.id).label("request_count"),
            )
        )
        query = query.filter(_user_project_filter(user, db_wrapper))

        top = (
            query
            .group_by(OutputDatabase.llm)
            .order_by(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).desc())
            .limit(limit)
            .all()
        )

        return {
            "llms": [
                {
                    "name": row.name,
                    "total_tokens": row.total_tokens or 0,
                    "total_cost": row.total_cost or 0,
                    "request_count": row.request_count or 0,
                }
                for row in top
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics/users", tags=["Statistics"])
async def get_top_users(
    limit: int = Query(10, ge=1, le=100, description="Max users to return"),
    user: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get users ranked by token consumption (admin only)."""
    rows = (
        db_wrapper.db.query(
            OutputDatabase.user_id,
            UserDatabase.username,
            func.count(OutputDatabase.id).label("requests"),
            func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("total_tokens"),
            func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("total_cost"),
        )
        .join(UserDatabase, OutputDatabase.user_id == UserDatabase.id)
        .group_by(OutputDatabase.user_id, UserDatabase.username)
        .order_by(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).desc())
        .limit(limit)
        .all()
    )
    return {
        "users": [
            {
                "user_id": r.user_id,
                "username": r.username,
                "requests": r.requests,
                "total_tokens": r.total_tokens or 0,
                "total_cost": round(r.total_cost or 0, 4),
            }
            for r in rows
        ]
    }


@router.get("/statistics/users/{userID}", tags=["Statistics"])
async def get_user_activity(
    userID: int,
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get detailed activity for a specific user."""
    if not user.is_admin and user.id != userID:
        raise HTTPException(status_code=403, detail="Access denied")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    base_filter = [OutputDatabase.user_id == userID, OutputDatabase.date >= since]

    total_requests = db_wrapper.db.query(func.count(OutputDatabase.id)).filter(*base_filter).scalar() or 0
    total_tokens = db_wrapper.db.query(
        func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens)
    ).filter(*base_filter).scalar() or 0
    total_cost = db_wrapper.db.query(
        func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost)
    ).filter(*base_filter).scalar() or 0
    avg_latency = db_wrapper.db.query(func.avg(OutputDatabase.latency_ms)).filter(*base_filter).scalar()
    total_conversations = db_wrapper.db.query(
        func.count(func.distinct(OutputDatabase.chat_id))
    ).filter(*base_filter, OutputDatabase.chat_id.isnot(None)).scalar() or 0

    daily_rows = (
        db_wrapper.db.query(
            func.date(OutputDatabase.date).label("date"),
            func.count(OutputDatabase.id).label("requests"),
            func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("tokens"),
        )
        .filter(*base_filter)
        .group_by(func.date(OutputDatabase.date))
        .order_by(func.date(OutputDatabase.date))
        .all()
    )

    project_rows = (
        db_wrapper.db.query(
            OutputDatabase.project_id,
            ProjectDatabase.name,
            func.count(OutputDatabase.id).label("requests"),
            func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("tokens"),
        )
        .join(ProjectDatabase, OutputDatabase.project_id == ProjectDatabase.id)
        .filter(*base_filter)
        .group_by(OutputDatabase.project_id, ProjectDatabase.name)
        .order_by(func.count(OutputDatabase.id).desc())
        .limit(10)
        .all()
    )

    hourly_rows = (
        db_wrapper.db.query(
            func.extract("hour", OutputDatabase.date).label("hour"),
            func.count(OutputDatabase.id).label("requests"),
        )
        .filter(*base_filter)
        .group_by(func.extract("hour", OutputDatabase.date))
        .all()
    )
    hourly_map = {int(r.hour): r.requests for r in hourly_rows}

    return {
        "summary": {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4),
            "avg_latency_ms": round(avg_latency) if avg_latency else 0,
            "total_conversations": total_conversations,
        },
        "daily": [{"date": r.date, "requests": r.requests, "tokens": r.tokens or 0} for r in daily_rows],
        "top_projects": [
            {"project_id": r.project_id, "project_name": r.name, "requests": r.requests, "tokens": r.tokens or 0}
            for r in project_rows
        ],
        "hourly": [{"hour": h, "requests": hourly_map.get(h, 0)} for h in range(24)],
    }