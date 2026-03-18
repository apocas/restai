import logging
from datetime import datetime, timedelta, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
from sqlalchemy import func, or_


logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

@router.get("/statistics/top-projects")
async def get_top_projects_by_tokens(
    limit: int = 10,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
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

        if not user.is_admin:
            query = query.filter(
                or_(
                    ProjectDatabase.id.in_(
                        db_wrapper.db.query(users_projects.c.project_id)
                        .filter(users_projects.c.user_id == user.id)
                    ),
                    ProjectDatabase.public == True
                )
            )

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


def _user_project_filter(user: User, db_wrapper: DBWrapper):
    """Returns a filter condition that limits OutputDatabase rows to projects the user can access."""
    return OutputDatabase.project_id.in_(
        db_wrapper.db.query(ProjectDatabase.id).filter(
            or_(
                ProjectDatabase.id.in_(
                    db_wrapper.db.query(users_projects.c.project_id)
                    .filter(users_projects.c.user_id == user.id)
                ),
                ProjectDatabase.public == True
            )
        )
    )


@router.get("/statistics/summary")
async def get_statistics_summary(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        token_query = db_wrapper.db.query(
            func.coalesce(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0).label("total_cost"),
        )
        if not user.is_admin:
            token_query = token_query.filter(_user_project_filter(user, db_wrapper))
        token_stats = token_query.first()

        if user.is_admin:
            total_projects = db_wrapper.db.query(func.count(ProjectDatabase.id)).scalar() or 0
            total_users = db_wrapper.db.query(func.count(UserDatabase.id)).scalar() or 0
            total_teams = db_wrapper.db.query(func.count(TeamDatabase.id)).scalar() or 0
        else:
            total_projects = db_wrapper.db.query(func.count(ProjectDatabase.id)).filter(
                or_(
                    ProjectDatabase.id.in_(
                        db_wrapper.db.query(users_projects.c.project_id)
                        .filter(users_projects.c.user_id == user.id)
                    ),
                    ProjectDatabase.public == True
                )
            ).scalar() or 0
            total_users = 0
            total_teams = 0

        return {
            "total_tokens": token_stats.total_tokens,
            "total_cost": token_stats.total_cost,
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
    days: int = 30,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            db_wrapper.db.query(
                func.date(OutputDatabase.date).label("date"),
                func.sum(OutputDatabase.input_tokens).label("input_tokens"),
                func.sum(OutputDatabase.output_tokens).label("output_tokens"),
                func.sum(OutputDatabase.input_cost).label("input_cost"),
                func.sum(OutputDatabase.output_cost).label("output_cost"),
            )
            .filter(OutputDatabase.date >= start_date)
        )
        if not user.is_admin:
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
    limit: int = 10,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        query = (
            db_wrapper.db.query(
                OutputDatabase.llm.label("name"),
                func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("total_tokens"),
                func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("total_cost"),
                func.count(OutputDatabase.id).label("request_count"),
            )
        )
        if not user.is_admin:
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