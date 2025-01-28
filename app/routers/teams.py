from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.databasemodels import TeamDatabase, UserDatabase
from app.database import get_db_wrapper, DBWrapper
from app.auth import get_current_username, get_current_username_admin, get_current_username_superadmin, user_is_admin_team, user_is_team_member
from app.models.models import TeamCreate, TeamUpdate, Team, User, UserBase

router = APIRouter()

@router.post("/teams", response_model=Team)
async def create_team(team: TeamCreate, _: User = Depends(get_current_username_superadmin), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    db = db_wrapper.db
    db_team = db.query(TeamDatabase).filter(TeamDatabase.name == team.name).first()
    if db_team:
        raise HTTPException(status_code=400, detail="Team already exists")
    new_team = TeamDatabase(name=team.name, description=team.description)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return new_team

@router.get("/teams", response_model=list[Team])
async def list_teams(user: User = Depends(get_current_username), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    db = db_wrapper.db
    
    teams = db.query(TeamDatabase).all()
    if user.superadmin:
        return teams
    else:
        teams_output = []
        for team in teams:
            if user_is_team_member(team.id, user):
                teams_output.append(team)
        return teams_output

@router.get("/teams/{team_id}", response_model=Team)
async def get_team(team_id: int, user: User = Depends(get_current_username), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    if user_is_team_member(team_id, user):
        db = db_wrapper.db
        team = db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        else:
            return team
    else:
        raise HTTPException(status_code=403, detail="Not a member")
    


@router.patch("/teams/{team_id}", response_model=Team)
async def update_team(team_id: int, team: TeamUpdate, user: User = Depends(get_current_username_admin), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    if user_is_admin_team(team_id, user):
        db = db_wrapper.db
        db_team = db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
        if not db_team:
            raise HTTPException(status_code=404, detail="Team not found")
        if team.name is not None:
            db_team.name = team.name
        if team.description is not None:
            db_team.description = team.description
        db.commit()
        db.refresh(db_team)
        return db_team
    else:
        raise HTTPException(status_code=403, detail="Not an admin")

@router.delete("/teams/{team_id}", response_model=Team)
async def delete_team(team_id: int, _: User = Depends(get_current_username_superadmin), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    db = db_wrapper.db
    db_team = db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(db_team)
    db.commit()
    return db_team