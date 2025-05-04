from fastapi import APIRouter, Depends, HTTPException, Request
import traceback
import logging
from datetime import datetime
from typing import List, Optional

from restai.models.models import (
    TeamModel, 
    TeamModelCreate, 
    TeamModelUpdate, 
    TeamsResponse,
    User
)
from restai.models.databasemodels import TeamDatabase
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import (
    get_current_username,
    get_current_username_platform_admin,
    get_current_username_team_admin,
    get_current_username_team_member
)
from restai.constants import ERROR_MESSAGES

router = APIRouter()

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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/teams/{team_id}", response_model=TeamModel)
async def get_team(
    team_id: int,
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
            
        return TeamModel.model_validate(team)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams", response_model=TeamModel)
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/teams/{team_id}", response_model=TeamModel)
async def update_team(
    team_id: int,
    team_update: TeamModelUpdate,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: int,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams/{team_id}/users/{username}")
async def add_user_to_team(
    team_id: int,
    username: str,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}/users/{username}")
async def remove_user_from_team(
    team_id: int,
    username: str,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams/{team_id}/admins/{username}")
async def add_admin_to_team(
    team_id: int,
    username: str,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}/admins/{username}")
async def remove_admin_from_team(
    team_id: int,
    username: str,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams/{team_id}/projects/{project_id}")
async def add_project_to_team(
    team_id: int,
    project_id: int,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}/projects/{project_id}")
async def remove_project_from_team(
    team_id: int,
    project_id: int,
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
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams/{team_id}/llms/{llm_name}")
async def add_llm_to_team(
    team_id: int,
    llm_name: str,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an LLM to a team.
    
    Only team admins and platform admins can add LLMs to a team.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        llm = db_wrapper.get_llm_by_name(llm_name)
        if llm is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.add_llm_to_team(team, llm)
        return {"added_llm": llm_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}/llms/{llm_name}")
async def remove_llm_from_team(
    team_id: int,
    llm_name: str,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an LLM from a team.
    
    Only team admins and platform admins can remove LLMs from a team.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        llm = db_wrapper.get_llm_by_name(llm_name)
        if llm is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.remove_llm_from_team(team, llm)
        return {"removed_llm": llm_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/teams/{team_id}/embeddings/{embedding_name}")
async def add_embedding_to_team(
    team_id: int,
    embedding_name: str,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Add an embedding to a team.
    
    Only team admins and platform admins can add embeddings to a team.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        embedding = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.add_embedding_to_team(team, embedding)
        return {"added_embedding": embedding_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/teams/{team_id}/embeddings/{embedding_name}")
async def remove_embedding_from_team(
    team_id: int,
    embedding_name: str,
    user: User = Depends(get_current_username_team_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    """Remove an embedding from a team.
    
    Only team admins and platform admins can remove embeddings from a team.
    """
    try:
        team = db_wrapper.get_team_by_id(team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.TEAM_NOT_FOUND)
            
        embedding = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise HTTPException(status_code=404, detail=ERROR_MESSAGES.NOT_FOUND)
            
        db_wrapper.remove_embedding_from_team(team, embedding)
        return {"removed_embedding": embedding_name, "team": team.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))