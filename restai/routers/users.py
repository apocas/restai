from fastapi import APIRouter
import uuid
from unidecode import unidecode
from fastapi import Depends, HTTPException, Request
import traceback
import re
import logging
from datetime import timedelta
import secrets
from fastapi.responses import RedirectResponse
from restai import config
from restai.models.models import User, UserCreate, UserLogin, UserUpdate, UsersResponse
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import (
    create_access_token,
    get_current_username_admin,
    get_current_username_user,
)
from ssl import CERT_REQUIRED, PROTOCOL_TLS
from ldap3 import Server, Connection, NONE, Tls
from ldap3.utils.conv import escape_filter_chars

router = APIRouter()

def sanitize_user(user: User) -> User:
    if hasattr(user, 'model_dump'):
        user_dict = user.model_dump()
    else:
        user_dict = User.model_validate(user).model_dump()
    
    if "api_key" in user_dict:
        user_dict["api_key"] = None
        
    return User.model_validate(user_dict)


@router.post("/ldap")
async def ldap_auth(request: Request, form_data: UserLogin, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    ENABLE_LDAP = config.ENABLE_LDAP
    LDAP_SERVER_HOST = config.LDAP_SERVER_HOST
    LDAP_SERVER_PORT = config.LDAP_SERVER_PORT
    LDAP_ATTRIBUTE_FOR_MAIL = config.LDAP_ATTRIBUTE_FOR_MAIL
    LDAP_ATTRIBUTE_FOR_USERNAME = config.LDAP_ATTRIBUTE_FOR_USERNAME
    LDAP_SEARCH_BASE = config.LDAP_SEARCH_BASE
    LDAP_SEARCH_FILTERS = config.LDAP_SEARCH_FILTERS
    LDAP_APP_DN = config.LDAP_APP_DN
    LDAP_APP_PASSWORD = config.LDAP_APP_PASSWORD
    LDAP_USE_TLS = config.LDAP_USE_TLS
    LDAP_CA_CERT_FILE = config.LDAP_CA_CERT_FILE
    LDAP_CIPHERS = (
        config.LDAP_CIPHERS
        if config.LDAP_CIPHERS
        else "ALL"
    )

    if not ENABLE_LDAP:
        raise HTTPException(400, detail="LDAP authentication is not enabled")

    try:
        tls = Tls(
            validate=CERT_REQUIRED,
            version=PROTOCOL_TLS,
            ca_certs_file=LDAP_CA_CERT_FILE,
            ciphers=LDAP_CIPHERS,
        )
    except Exception as e:
        logging.exception(e)
        raise HTTPException(400, detail=str(e))

    try:
        server = Server(
            host=LDAP_SERVER_HOST,
            port=LDAP_SERVER_PORT,
            get_info=NONE,
            use_ssl=LDAP_USE_TLS,
            tls=tls,
        )
        connection_app = Connection(
            server,
            LDAP_APP_DN,
            LDAP_APP_PASSWORD,
            auto_bind="NONE",
            authentication="SIMPLE",
        )
        if not connection_app.bind():
            raise HTTPException(400, detail="Application account bind failed")

        search_success = connection_app.search(
            search_base=LDAP_SEARCH_BASE,
            search_filter=f"(&({LDAP_ATTRIBUTE_FOR_USERNAME}={escape_filter_chars(form_data.user.lower())}){LDAP_SEARCH_FILTERS})",
            attributes=[
                f"{LDAP_ATTRIBUTE_FOR_USERNAME}",
                f"{LDAP_ATTRIBUTE_FOR_MAIL}",
                "cn",
            ],
        )

        if not search_success:
            raise HTTPException(400, detail="User not found in the LDAP server")

        entry = connection_app.entries[0]
        username = str(entry[f"{LDAP_ATTRIBUTE_FOR_USERNAME}"]).lower()
        mail = str(entry[f"{LDAP_ATTRIBUTE_FOR_MAIL}"])
        if not mail or mail == "" or mail == "[]":
            raise HTTPException(400, f"User {form_data.user} does not have mail.")
        cn = str(entry["cn"])
        user_dn = entry.entry_dn

        if username == form_data.user.lower():
            connection_user = Connection(
                server,
                user_dn,
                form_data.password,
                auto_bind="NONE",
                authentication="SIMPLE",
            )
            if not connection_user.bind():
                raise HTTPException(400, f"Authentication failed for {form_data.user}")


            user = db_wrapper.get_user_by_username(mail)
            if user is None:
                user = db_wrapper.create_user(mail, None, False, False)
                db_wrapper.db.commit()

            new_token = create_access_token(
                data={"username": user.username}, expires_delta=timedelta(minutes=1440)
            )

            response = RedirectResponse("./admin")
            response.set_cookie(
                key="restai_token", value=new_token, samesite="strict", expires=86400
            )

            return response
        else:
            raise HTTPException(
                400,
                f"User {form_data.user} does not match the record. Search result: {str(entry[f'{LDAP_ATTRIBUTE_FOR_USERNAME}'])}",
            )
    except Exception as e:
        raise HTTPException(400, detail=str(e))


@router.get("/users/{username}", response_model=User)
async def route_get_user_details(
    username: str,
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        user_model = User.model_validate(db_wrapper.get_user_by_username(username))
        return sanitize_user(user_model)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/users/{username}/apikey")
async def route_get_user_apikey(
    username: str,
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        apikey = uuid.uuid4().hex + secrets.token_urlsafe(32)
        db_wrapper.update_user(user, UserUpdate(api_key=apikey))
        return {"api_key": apikey}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users", response_model=UsersResponse)
async def route_get_users(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    users = db_wrapper.get_users()
    users_final = [sanitize_user(User.model_validate(user)) for user in users]

    return {"users": users_final}


@router.post("/users")
async def route_create_user(
    user_create: UserCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        user_create.username = unidecode(
            user_create.username.strip().lower().replace(" ", ".")
        )
        user_create.username = re.sub(r"[^\w\-.@]+", "", user_create.username)

        db_wrapper.create_user(
            user_create.username,
            user_create.password,
            user_create.is_admin,
            user_create.is_private,
        )
        return {"username": user_create.username}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail="Failed to create user " + user_create.username
        )


@router.patch("/users/{username}", response_model=User)
async def route_update_user(
    username: str,
    user_update: UserUpdate,
    user: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        user_to_update = db_wrapper.get_user_by_username(username)
        if user_to_update is None:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.is_admin and user_update.is_admin is True:
            raise HTTPException(status_code=403, detail="Insuficient permissions")

        db_wrapper.update_user(user_to_update, user_update)

        if user_update.projects is not None:
            user_to_update.projects = []

            for project in user_update.projects:
                project_db = db_wrapper.get_project_by_name(project)
                if project_db is not None:
                    user_to_update.projects.append(project_db)
            db_wrapper.db.commit()
        return sanitize_user(user_to_update)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{username}")
async def route_delete_user(
    username: str,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        user_link = db_wrapper.get_user_by_username(username)
        if user_link is None:
            raise HTTPException(status_code=404, detail="User not found")
        db_wrapper.delete_user(user_link)
        return {"deleted": username}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
