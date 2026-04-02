from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
import logging
from datetime import datetime, timezone
from typing import List, Optional

from restai.models.models import (
    TeamBranding,
    TeamModel,
    TeamModelCreate,
    TeamModelUpdate,
    TeamsResponse,
    User
)
from sqlalchemy import or_
from restai.models.databasemodels import TeamDatabase, OutputDatabase, ProjectDatabase, UserDatabase, TeamInvitationDatabase
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import (
    get_current_username,
    get_current_username_platform_admin,
    get_current_username_team_admin,
    get_current_username_team_member
)
from restai.constants import ERROR_MESSAGES

router = APIRouter()


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
    """Get all teams the user has access to.
    
    - Platform admins see all teams
    - Regular users see teams they are members of
    """
    try:
        if user.is_admin:
            # Platform admins see all teams
            teams = db_wrapper.get_teams()
        else:
            # Regular users see teams they are members of
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
    """Get a specific team by ID.
    
    User must be a member or admin of the team, or a platform admin.
    """
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
    """Create a new team.
    
    Only platform admins can create teams.
    """
    try:
        # Check if team name already exists
        existing_team = db_wrapper.get_team_by_name(team_create.name)
        if existing_team is not None:
            raise HTTPException(status_code=400, detail=ERROR_MESSAGES.TEAM_NAME_TAKEN)
            
        # Create new team
        team_data = team_create.model_dump()
        team_data["creator_id"] = user.id  # Set the creator to the current user
        
        team = db_wrapper.create_team(TeamModelCreate.model_validate(team_data))
        
        # Process team relationships (users, admins, LLMs, embeddings, projects)
        # Since TeamModelCreate and TeamModelUpdate have the same fields for these relationships,
        # we can reuse the update_team_members method
        db_wrapper.update_team_members(team, TeamModelUpdate(**team_data))
        
        # Get the refreshed team with all relationships
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
    """Update team details.
    
    Only team admins and platform admins can update team details.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        # If changing name, check if new name is available
        if team_update.name is not None and team_update.name != team.name:
            existing_team = db_wrapper.get_team_by_name(team_update.name)
            if existing_team is not None:
                raise HTTPException(status_code=400, detail=ERROR_MESSAGES.TEAM_NAME_TAKEN)
        
        # Update base team properties
        db_wrapper.update_team(team, team_update)
        
        # Update team members and resources
        db_wrapper.update_team_members(team, team_update)
        
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
    """Delete a team.
    
    Only platform admins can delete teams.
    """
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
    """Add a user to a team.
    
    Only team admins and platform admins can add users to a team.
    """
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
    """Remove a user from a team.
    
    Only team admins and platform admins can remove users from a team.
    """
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
    """Add an admin to a team.
    
    Only team admins and platform admins can add admins to a team.
    """
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
    """Remove an admin from a team.
    
    Only team admins and platform admins can remove admins from a team.
    """
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
    """Add a project to a team.
    
    Only team admins and platform admins can add projects to a team.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        project = db_wrapper.get_project_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
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
    """Remove a project from a team.
    
    Only team admins and platform admins can remove projects from a team.
    """
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
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        llm = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
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
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
        embedding = db_wrapper.get_embedding_by_id(embedding_id)
        if embedding is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
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

@router.post("/teams/{team_id}/image_generators/{generator_name}")
async def add_image_generator_to_team(
    team_id: int = Path(description="Team ID"),
    generator_name: str = Path(description="Image generator name"),
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an image generator to a team."""
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


# ── Team Invitations ─────────────────────────────────────────────────────


@router.post("/teams/{team_id}/invitations", tags=["Teams"])
async def send_team_invitation(
    team_id: int = Path(description="Team ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Invite a user to join a team. Does not disclose whether the user exists."""
    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    # Always return the same message regardless of whether user exists
    target = db_wrapper.get_user_by_username(username)
    if target is not None:
        team = db_wrapper.get_team_by_id(team_id)
        if team is not None:
            # Check not already a member
            already_member = any(u.id == target.id for u in team.users)
            if not already_member:
                # Check no pending invite exists
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
    """Get pending team invitations for the current user."""
    invites = (
        db_wrapper.db.query(TeamInvitationDatabase)
        .filter(
            TeamInvitationDatabase.username == user.username,
            TeamInvitationDatabase.status == "pending",
        )
        .order_by(TeamInvitationDatabase.created_at.desc())
        .all()
    )
    result = []
    for inv in invites:
        team = db_wrapper.get_team_by_id(inv.team_id)
        inviter = db_wrapper.get_user_by_id(inv.invited_by) if inv.invited_by else None
        result.append({
            "id": inv.id,
            "team_id": inv.team_id,
            "team_name": team.name if team else "Unknown",
            "invited_by": inviter.username if inviter else "Unknown",
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        })
    return result


@router.get("/invitations/count", tags=["Teams"])
async def get_invitation_count(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get the count of pending invitations for the current user."""
    from sqlalchemy import func
    count = (
        db_wrapper.db.query(func.count(TeamInvitationDatabase.id))
        .filter(
            TeamInvitationDatabase.username == user.username,
            TeamInvitationDatabase.status == "pending",
        )
        .scalar()
    ) or 0
    return {"count": count}


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

    # Add user to team
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