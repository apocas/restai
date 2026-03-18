from fastapi import HTTPException
from restai.database import DBWrapper
from restai.project import Project
from restai.models.models import User
import json


def check_budget(user: User, project: Project, db: DBWrapper):
    """Pre-check budget before inference. Raises HTTP 402 if exhausted."""
    # Check user credit
    options = user.options
    if isinstance(options, str):
        try:
            options_dict = json.loads(options)
            credit = options_dict.get("credit", -1.0)
        except json.JSONDecodeError:
            credit = -1.0
    else:
        credit = options.credit

    if credit >= 0:
        spending = db.get_user_spending(user.id)
        remaining = credit - spending
        if remaining <= 0:
            raise HTTPException(status_code=402, detail="User budget exhausted")

    # Check team budget
    team = project.props.team
    if team is not None and team.budget >= 0:
        team_spending = db.get_team_spending(team.id)
        team_remaining = team.budget - team_spending
        if team_remaining <= 0:
            raise HTTPException(status_code=402, detail="Team budget exhausted")
