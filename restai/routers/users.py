from fastapi import APIRouter
import traceback
import uuid
from unidecode import unidecode
from fastapi import Depends, HTTPException, Path, Request
import re
import logging
from datetime import timedelta
import secrets
from fastapi.responses import RedirectResponse
from restai import config
from restai.models.models import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    TOTPSetupResponse,
    TOTPEnableRequest,
    TOTPDisableRequest,
    User,
    UserCreate,
    UserLogin,
    UserUpdate,
    UsersResponse,
    LimitedUser,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.databasemodels import UserDatabase, ProjectDatabase, TeamDatabase, users_projects, teams_users, teams_admins
from restai.auth import (
    create_access_token,
    get_current_username,
    get_current_username_admin,
    get_current_username_user,
)
from ssl import CERT_REQUIRED, PROTOCOL_TLS
from ldap3 import Server, Connection, NONE, Tls
from ldap3.utils.conv import escape_filter_chars
from restai.utils.crypto import encrypt_api_key, hash_api_key, encrypt_totp_secret, decrypt_totp_secret, generate_recovery_codes, hash_recovery_code

router = APIRouter()


@router.post("/ldap")
async def ldap_auth(request: Request, form_data: UserLogin, db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Authenticate via LDAP and create session."""
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
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(400, detail="LDAP authentication failed")

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
                user = db_wrapper.create_user(mail, None, False, False, restricted=config.SSO_AUTO_RESTRICTED)
                db_wrapper.db.commit()
                if config.SSO_AUTO_TEAM_ID:
                    try:
                        team = db_wrapper.get_team_by_id(int(config.SSO_AUTO_TEAM_ID))
                        if team:
                            db_wrapper.add_user_to_team(team, user)
                    except (ValueError, TypeError):
                        pass

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
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(400, detail="LDAP authentication failed")


@router.get("/users/{username}", response_model=User)
async def route_get_user_details(
    username: str = Path(description="Username"),
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get user details by username."""
    try:
        user_db = db_wrapper.get_user_by_username(username)
        user_model = User.model_validate(user_db)
        return user_model
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{username}/apikeys", response_model=ApiKeyCreatedResponse, status_code=201)
async def route_create_user_apikey(
    username: str = Path(description="Username"),
    body: ApiKeyCreate = ApiKeyCreate(),
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new API key for a user."""
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        plaintext = uuid.uuid4().hex + secrets.token_urlsafe(32)
        encrypted = encrypt_api_key(plaintext)
        key_hash = hash_api_key(plaintext)
        key_prefix = plaintext[:8]

        allowed_projects_json = None
        if body.allowed_projects is not None:
            import json
            allowed_projects_json = json.dumps(body.allowed_projects)

        api_key_row = db_wrapper.create_api_key(
            user_id=user.id,
            encrypted_key=encrypted,
            key_hash=key_hash,
            key_prefix=key_prefix,
            description=body.description,
            allowed_projects=allowed_projects_json,
            read_only=body.read_only,
        )
        return ApiKeyCreatedResponse(
            id=api_key_row.id,
            api_key=plaintext,
            key_prefix=key_prefix,
            description=api_key_row.description,
            created_at=api_key_row.created_at,
            allowed_projects=body.allowed_projects,
            read_only=body.read_only,
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{username}/apikeys", response_model=list[ApiKeyResponse])
async def route_list_user_apikeys(
    username: str = Path(description="Username"),
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all API keys for a user."""
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        keys = db_wrapper.get_api_keys_for_user(user.id)
        return [ApiKeyResponse.model_validate(k) for k in keys]
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{username}/apikeys/{key_id}")
async def route_delete_user_apikey(
    username: str = Path(description="Username"),
    key_id: int = Path(description="API key ID"),
    _: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an API key."""
    try:
        user = db_wrapper.get_user_by_username(username)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        deleted = db_wrapper.delete_api_key(key_id, user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="API key not found")
        return {"deleted": key_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users", response_model=UsersResponse)
async def route_get_users(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all users. Admins see all, others see team members only."""
    # If user is admin, return all users
    if user.is_admin:
        users = db_wrapper.get_users()
        users_final = [User.model_validate(user_obj) for user_obj in users]
    # For regular users, only return users from their teams
    else:
        # Get the set of unique users from all teams the current user belongs to
        team_users = set()
        for team in user.teams:
            # Add all users from this team to our set
            for team_user in team.users:
                team_users.add(team_user.id)
        
        # Get all users and filter by the team user IDs
        users = db_wrapper.get_users()
        team_users_list = []
        for user_obj in users:
            if user_obj.id in team_users:
                team_users_list.append(user_obj)
        
        # Convert to LimitedUser objects
        users_final = []
        for user_obj in team_users_list:
            user_model = User.model_validate(user_obj)
            limited_user = LimitedUser(
                id=user_model.id,
                username=user_model.username
            )
            users_final.append(limited_user)

    return {"users": users_final}


@router.post("/users", status_code=201)
async def route_create_user(
    user_create: UserCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Create a new user (admin only)."""
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
            user_create.is_restricted,
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
    username: str = Path(description="Username"),
    user_update: UserUpdate = ...,
    user: User = Depends(get_current_username_user),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update user properties."""
    try:
        if user.is_restricted and not user.is_admin:
            raise HTTPException(status_code=403, detail="Restricted users cannot edit their profile")

        user_to_update = db_wrapper.get_user_by_username(username)
        if user_to_update is None:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.is_admin and user_update.is_admin is True:
            raise HTTPException(status_code=403, detail="Insuficient permissions")

        if user_update.is_private is not None and user_update.is_private != user_to_update.is_private:
            can_change = user.is_admin
            if not can_change:
                caller_db = db_wrapper.get_user_by_username(user.username)
                for team in caller_db.admin_teams:
                    if user_to_update in team.users or user_to_update in team.admins:
                        can_change = True
                        break
            if not can_change:
                raise HTTPException(status_code=403, detail="Only platform admins or team admins can modify user privacy setting")

        if not user.is_admin and user_update.is_restricted is not None:
            raise HTTPException(status_code=403, detail="Only admins can modify restriction settings")

        if not user.is_admin and user_update.projects is not None:
            raise HTTPException(status_code=403, detail="Only admins can modify project assignments")

        db_wrapper.update_user(user_to_update, user_update)

        if user_update.projects is not None:
            user_to_update.projects = []

            for project in user_update.projects:
                project_db = db_wrapper.get_project_by_name(project)
                if project_db is not None:
                    user_to_update.projects.append(project_db)
            db_wrapper.db.commit()
        return User.model_validate(user_to_update)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{username}")
async def route_delete_user(
    username: str = Path(description="Username"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a user (admin only)."""
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


# --- TOTP 2FA Endpoints ---

@router.get("/users/{username}/totp/status")
async def totp_status(
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Check if 2FA is enabled for a user."""
    if not user.is_admin and user.username != username:
        raise HTTPException(status_code=403, detail="Access denied")
    user_db = db_wrapper.get_user_by_username(username)
    if user_db is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "enabled": bool(user_db.totp_enabled),
        "enforced": bool(getattr(config, "ENFORCE_2FA", False)),
    }


@router.post("/users/{username}/totp/setup", response_model=TOTPSetupResponse)
async def totp_setup(
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Generate a new TOTP secret and recovery codes. Does NOT enable 2FA yet — call /enable with a valid code to activate."""
    import pyotp
    import json

    if not user.is_admin and user.username != username:
        raise HTTPException(status_code=403, detail="Access denied")
    user_db = db_wrapper.get_user_by_username(username)
    if user_db is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate secret and recovery codes
    secret = pyotp.random_base32()
    app_name = getattr(config, "RESTAI_NAME", "RESTai") or "RESTai"
    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(username, issuer_name=app_name)
    recovery_codes = generate_recovery_codes()

    # Store encrypted secret and hashed recovery codes (but don't enable yet)
    user_db.totp_secret = encrypt_totp_secret(secret)
    user_db.totp_recovery_codes = json.dumps([hash_recovery_code(c) for c in recovery_codes])
    db_wrapper.db.commit()

    return TOTPSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        recovery_codes=recovery_codes,
    )


@router.post("/users/{username}/totp/enable")
async def totp_enable(
    body: TOTPEnableRequest,
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Activate 2FA by confirming a valid TOTP code from the authenticator app."""
    import pyotp

    if not user.is_admin and user.username != username:
        raise HTTPException(status_code=403, detail="Access denied")
    user_db = db_wrapper.get_user_by_username(username)
    if user_db is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user_db.totp_secret:
        raise HTTPException(status_code=400, detail="Run /totp/setup first")

    secret = decrypt_totp_secret(user_db.totp_secret)
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    user_db.totp_enabled = True
    db_wrapper.db.commit()
    return {"message": "2FA enabled successfully."}


@router.post("/users/{username}/totp/disable")
async def totp_disable(
    body: TOTPDisableRequest,
    username: str = Path(description="Username"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Disable 2FA. Requires password confirmation. Blocked if admin enforces 2FA."""
    from restai.database import verify_password

    if not user.is_admin and user.username != username:
        raise HTTPException(status_code=403, detail="Access denied")

    if getattr(config, "ENFORCE_2FA", False):
        raise HTTPException(status_code=403, detail="2FA is enforced by the administrator and cannot be disabled")

    user_db = db_wrapper.get_user_by_username(username)
    if user_db is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(body.password, user_db.hashed_password):
        raise HTTPException(status_code=403, detail="Invalid password")

    user_db.totp_enabled = False
    user_db.totp_secret = None
    user_db.totp_recovery_codes = None
    db_wrapper.db.commit()
    return {"message": "2FA disabled successfully."}


@router.get("/permissions/matrix", tags=["Admin"])
async def get_permission_matrix(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return the users x projects permission matrix.

    Admins see everything. Team leaders see only users and projects
    belonging to their teams. Regular users get 403.
    """
    admin_team_ids = {t.id for t in (user.admin_teams or [])}

    if not user.is_admin and not admin_team_ids:
        raise HTTPException(status_code=403, detail="Forbidden")

    if user.is_admin:
        all_users = (
            db_wrapper.db.query(UserDatabase)
            .order_by(UserDatabase.username)
            .all()
        )
        all_projects = (
            db_wrapper.db.query(ProjectDatabase)
            .outerjoin(TeamDatabase, ProjectDatabase.team_id == TeamDatabase.id)
            .order_by(ProjectDatabase.name)
            .all()
        )
        rows = db_wrapper.db.query(users_projects).all()
    else:
        # Team leader: filter to their teams
        all_projects = (
            db_wrapper.db.query(ProjectDatabase)
            .outerjoin(TeamDatabase, ProjectDatabase.team_id == TeamDatabase.id)
            .filter(ProjectDatabase.team_id.in_(admin_team_ids))
            .order_by(ProjectDatabase.name)
            .all()
        )
        project_ids = {p.id for p in all_projects}

        # Users who belong to those teams (members + admins, single query via union)
        from sqlalchemy import union
        members_q = db_wrapper.db.query(teams_users.c.user_id).filter(teams_users.c.team_id.in_(admin_team_ids))
        admins_q = db_wrapper.db.query(teams_admins.c.user_id).filter(teams_admins.c.team_id.in_(admin_team_ids))
        team_user_ids = {r[0] for r in members_q.union(admins_q).all()}

        all_users = (
            db_wrapper.db.query(UserDatabase)
            .filter(UserDatabase.id.in_(team_user_ids))
            .order_by(UserDatabase.username)
            .all()
        )

        rows = (
            db_wrapper.db.query(users_projects)
            .filter(users_projects.c.project_id.in_(project_ids))
            .filter(users_projects.c.user_id.in_(team_user_ids))
            .all()
        )

    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "is_admin": bool(u.is_admin),
                "is_restricted": bool(getattr(u, "is_restricted", False)),
            }
            for u in all_users
        ],
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "team_id": p.team_id,
                "team_name": p.team.name if p.team else None,
            }
            for p in all_projects
        ],
        "assignments": [
            {"user_id": row.user_id, "project_id": row.project_id} for row in rows
        ],
    }
