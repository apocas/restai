from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func

from restai.database import DBWrapper
from restai.models.databasemodels import OutputDatabase
from restai.project import Project


def check_budget(project: Project, db: DBWrapper):
    """Pre-check budget before inference. Raises HTTP 402 if exhausted."""
    team = project.props.team
    if team is not None and team.budget >= 0:
        team_spending = db.get_team_spending(team.id)
        if team.budget - team_spending <= 0:
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
