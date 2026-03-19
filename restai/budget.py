from fastapi import HTTPException
from restai.database import DBWrapper
from restai.project import Project


def check_budget(project: Project, db: DBWrapper):
    """Pre-check budget before inference. Raises HTTP 402 if exhausted."""
    team = project.props.team
    if team is not None and team.budget >= 0:
        team_spending = db.get_team_spending(team.id)
        if team.budget - team_spending <= 0:
            raise HTTPException(status_code=402, detail="Team budget exhausted")
