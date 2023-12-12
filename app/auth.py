import secrets
from typing import Annotated
from fastapi import Depends, HTTPException

from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.database import dbc, get_db, pwd_context
from app.models import User


security = HTTPBasic()


def get_current_username(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    user = dbc.get_user_by_username(db, credentials.username)

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
