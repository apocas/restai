import base64
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic
import jwt
from app.config import RESTAI_AUTH_SECRET, RESTAI_AUTH_DISABLE_LOCAL
from app.database import get_db_wrapper, pwd_context, DBWrapper
from app.models.databasemodels import ProjectDatabase
from app.models.models import User

security: HTTPBasic = HTTPBasic()


def create_access_token(data: dict[str, str | datetime], expires_delta: Optional[timedelta] = None):
    to_encode: dict[str, str | datetime] = data.copy()
    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire: datetime = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(
        to_encode, RESTAI_AUTH_SECRET, algorithm="HS512")
    return encoded_jwt


def get_current_username(
        request: Request,
        db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    auth_header = request.headers.get('Authorization')
    auth_cookie = request.cookies.get("restai_token")
    
    if auth_cookie:
        try:
            data = jwt.decode(auth_cookie, RESTAI_AUTH_SECRET, algorithms=["HS512"])

            user = db_wrapper.get_user_by_username(data["username"])

            return User.model_validate(user)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )
    elif auth_header:
        temp_bearer_token = auth_header.split(" ")[1]
        
        if "Bearer" in auth_header:            
            user = db_wrapper.get_user_by_apikey(temp_bearer_token)

            if user is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid key"
                )

            return User.model_validate(user)
        elif "Basic" in auth_header:
            try:
                credentials_b64 = base64.b64decode(temp_bearer_token).decode('utf-8')
                username, password = credentials_b64.split(':', 1)
                credentials = {
                    'username': username,
                    'password': password
                }
                
                if RESTAI_AUTH_DISABLE_LOCAL or not credentials or ("username" not in credentials or "password" not in credentials):
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid credentials"
                    )
                
                user = db_wrapper.get_user_by_username(credentials["username"])

                if user is None or user.sso:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid credentials"
                    )

                is_correct_username = credentials["username"] == user.username
                is_correct_password = pwd_context.verify(
                    credentials["password"], user.hashed_password)

                if not (is_correct_username and is_correct_password):
                    raise HTTPException(
                        status_code=401,
                        detail="Incorrect email or password",
                        headers={"WWW-Authenticate": "Basic"},
                    )

                return User.model_validate(user)
                
            except Exception:
                pass  


def get_current_username_admin(user: User = Depends(get_current_username)):
    if not user.is_admin:
        raise HTTPException(
            status_code=401,
            detail="Insufficient permissions",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_username_project(projectName: str, user: User = Depends(get_current_username)):
    found: bool = user.is_admin

    if not found:
        for project in user.projects:
            if project.name == projectName:
                found = True
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )
    return user


def get_current_username_project_public(
        projectName: str,
        user: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)
):
    found = False
    if not user.is_admin:
        for project in user.projects:
            if project.name == projectName:
                found = True
                user.level = "own"
    else:
        found = True
        user.level = "own"

    p: Optional[ProjectDatabase] = db_wrapper.get_project_by_name(projectName)
    if found == False and (p is not None and p.public):
        found = True
        user.level = "public"

    if not found:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )
    return user


def get_current_username_user(username: str, user: User = Depends(get_current_username)):
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
