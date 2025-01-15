from fastapi import APIRouter
import copy
import uuid
from unidecode import unidecode
from fastapi import Depends, HTTPException, Request
import traceback
import re
import jwt
import logging
from datetime import timedelta
import secrets
from fastapi.responses import RedirectResponse
from app import config
from app.models.models import Team, User, UserBase, UserCreate, UserUpdate, UsersResponse
from app.database import get_db_wrapper, DBWrapper
from app.auth import create_access_token, get_current_username, get_current_username_admin, get_current_username_superadmin, get_current_username_user, get_team, user_is_admin_team

router = APIRouter()


@router.get("/sso")
async def get_sso(request: Request, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    params = dict(request.query_params)

    if "jwt" not in params:
        raise HTTPException(
            status_code=400, detail="Missing JWT token")

    try:
        data = jwt.decode(params["jwt"], config.RESTAI_SSO_SECRET, algorithms=[config.RESTAI_SSO_ALG])
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    user = db_wrapper.get_user_by_username(data["preferred_username"])
    if user is None:
        user = db_wrapper.create_user(data["preferred_username"], None, False, False)
        user.sso = config.RESTAI_SSO_CALLBACK
        db_wrapper.db.commit()

    new_token = create_access_token(
        data={"username": user.username}, expires_delta=timedelta(minutes=1440))

    response = RedirectResponse("./admin")
    response.set_cookie(key="restai_token", value=new_token, samesite="strict", expires=86400)

    return response


@router.get("/users/{username}/sso")
async def route_get_user(username: str, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            return {"sso": config.RESTAI_SSO_CALLBACK}
        return {"sso": user.sso}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/users/{username}", response_model=UserBase)
async def route_get_user(username: str,
                         _: User = Depends(get_current_username_user),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        user_db = db_wrapper.get_user_by_username(username)
        
        if not user_db:
            raise Exception("User not found")
        
        user_model = UserBase(
            id=user_db.id,
            username=user_db.username,
            superadmin=user_db.superadmin,
            is_private=user_db.is_private,
            projects=user_db.projects,
            sso=user_db.sso,
            teams=user_db.teams
        )
        
        return user_model
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.post("/users/{username}/apikey")
async def route_get_user(username: str,
                         _: User = Depends(get_current_username_user),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            raise Exception("User not found")

        apikey = uuid.uuid4().hex + secrets.token_urlsafe(32)
        db_wrapper.update_user(user, UserUpdate(api_key=apikey))
        return {"api_key": apikey}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/users", response_model=UsersResponse)
async def route_get_users(
        user: User = Depends(get_current_username_admin),
        team: Team = Depends(get_team),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    users = []
    users_final = []
    
    if user.superadmin:
        users = db_wrapper.get_users()
    else:
        if user_is_admin_team(team.id, user):
            db_wrapper.get_users_team(team.id)
        else:
            raise HTTPException(
                status_code=401,
                detail="Insufficient permissions"
            )
        
    for user_model in users:
        user_model_copy = copy.deepcopy(User.model_validate(user_model))
        del user_model_copy.api_key
        users_final.append(user_model_copy)

    return {"users": users_final}


@router.post("/users")
async def route_create_user(user_create: UserCreate,
                            user: User = Depends(get_current_username_admin),
                            db_wrapper: DBWrapper = Depends(get_db_wrapper)):

    if user_is_admin_team(user_create.team_id, user):
        try:
            user_create.username = unidecode(user_create.username.strip().lower().replace(" ", "."))
            user_create.username = re.sub(r'[^\w\-.@]+', '', user_create.username)

            db_wrapper.create_user(
                user_create.username,
                user_create.password,
                user_create.superadmin,
                user_create.is_private)
            return {"username": user_create.username}
        except Exception as e:
            logging.error(e)
            traceback.print_tb(e.__traceback__)
            raise HTTPException(
                status_code=500,
                detail='Failed to create user ' + user_create.username)
    else:
        raise HTTPException(
            status_code=401,
            detail="Insufficient permissions"
        )


@router.patch("/users/{username}", response_model=User)
async def route_update_user(
        username: str,
        user_update: UserUpdate,
        user: User = Depends(get_current_username_superadmin),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        user_to_update = db_wrapper.get_user_by_username(username)
        if user_to_update is None:
            raise Exception("User not found")

        if not user.superadmin and user_update.superadmin is True:
            raise Exception("Insuficient permissions")

        db_wrapper.update_user(user_to_update, user_update)

        if user_update.projects is not None:
            user_to_update.projects = []

            for project in user_update.projects:
                project_db = db_wrapper.get_project_by_name(project)
                if project_db is not None:
                    user_to_update.projects.append(project_db)
            db_wrapper.db.commit()
        return user_to_update
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.delete("/users/{username}")
async def route_delete_user(username: str,
                            _: User = Depends(get_current_username_superadmin),
                            db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        user_link = db_wrapper.get_user_by_username(username)
        if user_link is None:
            raise Exception("User not found")
        db_wrapper.delete_user(user_link)
        return {"deleted": username}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
