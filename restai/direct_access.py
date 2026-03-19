from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from restai.database import DBWrapper
from restai.models.databasemodels import OutputDatabase
from restai.models.models import User


def resolve_team_for_llm(user: User, llm_name: str, db: DBWrapper) -> Optional[int]:
    """Resolve which team grants the user access to an LLM.

    Returns:
        None  - admin bypass (no team_id needed)
        int   - team_id that grants access
    Raises:
        HTTPException 403 if no access
    """
    if user.is_admin:
        return None

    teams = db.get_teams_for_user(user.id)
    for team in teams:
        for llm in team.llms:
            if llm.name == llm_name:
                # Check team budget
                if team.budget >= 0:
                    spending = db.get_team_spending(team.id)
                    if team.budget - spending <= 0:
                        continue
                return team.id

    raise HTTPException(status_code=403, detail="You do not have access to this model")


def resolve_team_for_image_generator(user: User, generator_name: str, db: DBWrapper) -> Optional[int]:
    """Resolve which team grants the user access to an image generator."""
    if user.is_admin:
        return None

    teams = db.get_teams_for_user(user.id)
    for team in teams:
        gen_names = [g.generator_name for g in team.image_generators]
        if generator_name in gen_names:
            if team.budget >= 0:
                spending = db.get_team_spending(team.id)
                if team.budget - spending <= 0:
                    continue
            return team.id

    raise HTTPException(status_code=403, detail="You do not have access to this image generator")


def resolve_team_for_audio_generator(user: User, generator_name: str, db: DBWrapper) -> Optional[int]:
    """Resolve which team grants the user access to an audio generator."""
    if user.is_admin:
        return None

    teams = db.get_teams_for_user(user.id)
    for team in teams:
        gen_names = [g.generator_name for g in team.audio_generators]
        if generator_name in gen_names:
            if team.budget >= 0:
                spending = db.get_team_spending(team.id)
                if team.budget - spending <= 0:
                    continue
            return team.id

    raise HTTPException(status_code=403, detail="You do not have access to this audio generator")


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
):
    """Log direct access usage to OutputDatabase with project_id=NULL."""
    entry = OutputDatabase(
        user_id=user_id,
        project_id=None,
        team_id=team_id,
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
