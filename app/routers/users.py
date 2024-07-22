from fastapi import APIRouter
import copy
import uuid
from starlette.requests import Request
from unidecode import unidecode
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from fastapi import HTTPException, Request
import traceback
import re
import jwt
import logging
from datetime import timedelta
import secrets
from fastapi.responses import RedirectResponse
from app import config

from app.models.models import User, UserCreate, UserUpdate, UsersResponse
from app.database import dbc, get_db
from app.auth import create_access_token, get_current_username_admin, get_current_username_user

router = APIRouter()

@router.get("/sso")
async def get_sso(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)

    if "jwt" not in params:
        raise HTTPException(
            status_code=400, detail="Missing JWT token")

    try:
        data = jwt.decode(params["jwt"], config.RESTAI_SSO_SECRET, algorithms=[config.RESTAI_SSO_ALG])
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    user = dbc.get_user_by_username(db, data["preferred_username"])
    if user is None:
        user = dbc.create_user(db,
                               data["preferred_username"], None,
                               False,
                               False)
        user.sso = config.RESTAI_SSO_CALLBACK
        db.commit()

    new_token = create_access_token(
        data={"username": user.username}, expires_delta=timedelta(minutes=1440))

    response = RedirectResponse("./admin")
    response.set_cookie(key="restai_token", value=new_token, samesite="strict", expires=86400)

    return response


@router.get("/users/{username}/sso")
async def get_user(username: str, db: Session = Depends(get_db)):
    try:
        user = dbc.get_user_by_username(db, username)
        if user is None:
            return {"sso": config.RESTAI_SSO_CALLBACK}
        return {"sso": user.sso}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/users/{username}", response_model=User)
async def get_user(username: str, user: User = Depends(get_current_username_user), db: Session = Depends(get_db)):
    try:
        user_model = User.model_validate(
            dbc.get_user_by_username(db, username))
        user_model_copy = copy.deepcopy(user_model)
        del user_model_copy.api_key
        return user_model
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.post("/users/{username}/apikey")
async def get_user(username: str, user: User = Depends(get_current_username_user), db: Session = Depends(get_db)):
    try:
        useru = dbc.get_user_by_username(db, username)
        if useru is None:
            raise Exception("User not found")

        apikey = uuid.uuid4().hex + secrets.token_urlsafe(32)
        dbc.update_user(db, useru, UserUpdate(api_key=apikey))
        return {"api_key": apikey}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/users", response_model=UsersResponse)
async def get_users(
        user: User = Depends(get_current_username_admin),
        db: Session = Depends(get_db)):
    users = dbc.get_users(db)
    users_final = []

    for user_model in users:
        user_model_copy = copy.deepcopy(User.model_validate(user_model))
        del user_model_copy.api_key
        users_final.append(user_model_copy)

    return {"users": users_final}
  
@router.post("/users", response_model=User)
async def create_user(userc: UserCreate,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        userc.username = unidecode(
            userc.username.strip().lower().replace(" ", "."))
        userc.username = re.sub(r'[^\w\-.@]+', '', userc.username)

        user = dbc.create_user(db,
                               userc.username,
                               userc.password,
                               userc.is_admin,
                               userc.is_private)
        user_model_copy = copy.deepcopy(user)
        user_model_copy.api_key = None
        user_model_copy.id = None
        user_model_copy.projects = []
        return user_model_copy
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create user ' + userc.username)


@router.patch("/users/{username}", response_model=User)
async def update_user(
        username: str,
        userc: UserUpdate,
        user: User = Depends(get_current_username_user),
        db: Session = Depends(get_db)):
    try:
        useru = dbc.get_user_by_username(db, username)
        if useru is None:
            raise Exception("User not found")

        if not user.is_admin and userc.is_admin is True:
            raise Exception("Insuficient permissions")

        dbc.update_user(db, useru, userc)

        if userc.projects is not None:
            useru.projects = []
            
            for project in userc.projects:
                projectdb = dbc.get_project_by_name(db, project)
                
                if projectdb is not None:
                    useru.projects.append(projectdb)
            db.commit()
        return useru
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.delete("/users/{username}")
async def delete_user(username: str,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        userl = dbc.get_user_by_username(db, username)
        if userl is None:
            raise Exception("User not found")
        dbc.delete_user(db, userl)
        return {"deleted": username}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))