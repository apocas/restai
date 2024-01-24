from datetime import timedelta, timezone
import datetime
import os
from typing import Union
from fastapi import Depends, HTTPException, Request

from fastapi.security import HTTPBasic, HTTPBasicCredentials
import jwt
from sqlalchemy.orm import Session

from app.database import dbc, get_db, pwd_context
from app.models import User


security = HTTPBasic()


def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, os.environ["RESTAI_AUTH_SECRET"], algorithm="HS512")
    return encoded_jwt


def get_current_username(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    auth_header = request.headers.get('Authorization')
    bearer_token = None
    if auth_header:
        temp_bearer_token = auth_header.split(" ")[1]
        if "Bearer" in temp_bearer_token:
            bearer_token = temp_bearer_token.split(" ")[1]

    jwt_token = request.cookies.get("restai_token")

    if bearer_token:
        user = dbc.get_user_by_apikey(db, bearer_token)
        return User.model_validate(user)
    elif jwt_token:
        try:
            data = jwt.decode(jwt_token, os.environ["RESTAI_SSO_SECRET"], algorithms=[
                              os.environ.get("RESTAI_SSO_ALG") or "HS512"])

            user = dbc.get_user_by_username(db, data["preferred_username"])

            return User.model_validate(user)
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
    else:
        user = dbc.get_user_by_username(db, credentials.username)

        if user.sso:
            raise HTTPException(
                status_code=401,
                detail="SSO user"
            )

        if user is not None:
            is_correct_username = credentials.username == user.username
            is_correct_password = pwd_context.verify(
                credentials.password, user.hashed_password)
        else:
            is_correct_username = False
            is_correct_password = False

        if not (is_correct_username and is_correct_password):
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        return User.model_validate(user)


def get_current_username_admin(
    user: User = Depends(get_current_username)
):
    if not (user.is_admin):
        raise HTTPException(
            status_code=401,
            detail="Insuficient permissions",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_username_project(
    projectName: str,
    user: User = Depends(get_current_username)
):
    found = False
    if not user.is_admin:
        for project in user.projects:
            if project.name == projectName:
                found = True
    else:
        found = True

    if not found:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )
    return user


def get_current_username_user(
    username: str,
    user: User = Depends(get_current_username)
):
    found = False
    if not user.is_admin:
        if user.username == username:
            found = True
    else:
        found = True

    if not found:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    return user
