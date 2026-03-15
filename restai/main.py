from pathlib import Path

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Depends, status, Response
import logging
import sys

from fastmcp import FastMCP
from restai import config
import sentry_sdk
from contextlib import asynccontextmanager
from restai.database import get_db_wrapper
from restai.oauth import OAuthManager
from starlette.middleware.sessions import SessionMiddleware
from restai.config import (
    OAUTH_PROVIDERS,
    SSO_SECRET_KEY,
    SESSION_COOKIE_SAME_SITE,
    SESSION_COOKIE_SECURE,
    RESTAI_AUTH_SECRET,
    RESTAI_URL
)
from restai.utils.version import get_version_from_pyproject

PROJECT_ROOT = Path(__file__).parent.parent
FRONTEND_BUILD_DIR = PROJECT_ROOT / "frontend" / "build"

@asynccontextmanager
async def lifespan(fs_app: FastAPI):
    print(
        r"""
       ___ ___ ___ _____ _   ___      _.--'"'.
      | _ \ __/ __|_   _/_\ |_ _|    (  ( (   )
      |   / _|\__ \ | |/ _ \ | |     (o)_    ) )
      |_|_\___|___/ |_/_/ \_\___|        (o)_.'
                                  
        """
    )
    from restai.brain import Brain
    from restai.database import get_db_wrapper, DBWrapper
    from restai.auth import get_current_username
    from restai.routers import (
        llms,
        projects,
        tools,
        users,
        image,
        audio,
        embeddings,
        proxy,
        statistics,
        auth,
        teams,
        settings,
    )
    from restai.models.models import User
    from restai.models.databasemodels import ProjectDatabase
    from restai.multiprocessing import get_manager
    from modules.loaders import LOADERS

    fs_app.state.manager = get_manager()
    fs_app.state.brain = Brain()

    from restai.settings import ensure_settings_table, seed_defaults, load_settings
    from restai.database import engine as db_engine
    ensure_settings_table(db_engine)
    settings_db_wrapper = get_db_wrapper()
    seed_defaults(settings_db_wrapper)
    load_settings(settings_db_wrapper)

    if not RESTAI_URL:
      logging.warning("RESTAI_URL env var missing. OAUTH auth schemes may not work properly.")

    @fs_app.get("/")
    async def get():
        return "RESTai, so many 'A's and 'I's, so little time..."

    @fs_app.get("/version")
    async def get_version():
        return {
            "version": fs_app.version,
        }

    @fs_app.get("/health/live")
    async def health_live():
        return {"status": "ok"}

    @fs_app.get("/health/ready")
    async def health_ready():
        health = {"status": "ok"}
        try:
            from sqlalchemy import text
            db_check = get_db_wrapper()
            db_check.db.execute(text("SELECT 1"))
            db_check.db.close()
            health["database"] = "ok"
        except Exception:
            health["database"] = "error"
            health["status"] = "degraded"

        if config.REDIS_HOST:
            try:
                import redis
                r = redis.Redis(
                    host=config.REDIS_HOST,
                    port=int(config.REDIS_PORT or 6379),
                    socket_connect_timeout=2,
                )
                r.ping()
                r.close()
                health["redis"] = "ok"
            except Exception:
                health["redis"] = "error"
                health["status"] = "degraded"

        if health["status"] != "ok":
            return JSONResponse(content=health, status_code=503)
        return health

    @fs_app.get("/setup")
    async def get_setup():
        sso_list = []
        if isinstance(config.OAUTH_PROVIDERS, dict):
            sso_list = list(config.OAUTH_PROVIDERS.keys())
        elif isinstance(config.OAUTH_PROVIDERS, (list, tuple)):
            sso_list = list(config.OAUTH_PROVIDERS)
        else:
            sso_list = []
        return {
            "sso": sso_list,
            "proxy": bool(config.PROXY_URL),
            "gpu": config.RESTAI_GPU,
            "app_name": config.RESTAI_NAME,
            "hide_branding": config.HIDE_BRANDING,
            "proxy_url": config.PROXY_URL or "",
        }

    @fs_app.get("/info")
    async def get_info(
        _: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
        from restai.vectordb.tools import get_available_vectorstores

        output = {
            "version": fs_app.version,
            "loaders": list(LOADERS.keys()),
            "embeddings": [],
            "llms": [],
            "vectorstores": get_available_vectorstores(),
        }

        db_llms = db_wrapper.get_llms()
        for llm in db_llms:
            output["llms"].append(
                {
                    "name": llm.name,
                    "privacy": llm.privacy,
                    "description": llm.description,
                    "type": llm.type,
                }
            )

        db_embeddings = db_wrapper.get_embeddings()
        for embedding in db_embeddings:
            output["embeddings"].append(
                {
                    "name": embedding.name,
                    "privacy": embedding.privacy,
                    "description": embedding.description,
                }
            )
        return output

    try:
            fs_app.mount(
                "/admin/static",
                StaticFiles(directory=str(FRONTEND_BUILD_DIR / "static")),
                name="static_assets",
            )
            fs_app.mount(
                "/admin/assets",
                StaticFiles(directory=str(FRONTEND_BUILD_DIR / "assets")),
                name="static_images",
            )

            # SPA catch-all route for /admin/* - must be defined after static mounts
            @fs_app.get("/admin/{full_path:path}")
            async def serve_spa(full_path: str):
                """Serve index.html for all /admin/* routes to support SPA routing"""
                index_file = FRONTEND_BUILD_DIR / "index.html"
                if index_file.exists():
                    return FileResponse(str(index_file))
                return JSONResponse(status_code=404, content={"detail": "Frontend not found"})
    except Exception as e:
        print(e)
        print("Admin frontend not available.")

    fs_app.include_router(llms.router)
    fs_app.include_router(embeddings.router)
    fs_app.include_router(projects.router)
    fs_app.include_router(tools.router)
    fs_app.include_router(users.router)
    fs_app.include_router(proxy.router)
    fs_app.include_router(statistics.router)
    fs_app.include_router(auth.router)
    fs_app.include_router(teams.router)
    fs_app.include_router(settings.router)

    if config.RESTAI_GPU == True:
        fs_app.include_router(image.router)
        fs_app.include_router(audio.router)

    # Initialize MCP server if enabled
    if config.MCP_SERVER:
        print("MCP server starting...")
        from restai.mcp_server import create_mcp_server
        from restai.auth import get_current_username
        from restai.database import get_db_wrapper
        from fastapi import Request, HTTPException, status
        from restai.models.models import User
        from fastapi.responses import JSONResponse
        from starlette.types import ASGIApp, Receive, Scope, Send

        # Create MCP server that exposes projects as tools
        mcp = create_mcp_server(fs_app, fs_app.state.brain)

        # Custom ASGI middleware for authentication
        class MCPAuthMiddleware:
            def __init__(self, app: ASGIApp):
                self.app = app
            async def __call__(self, scope: Scope, receive: Receive, send: Send):
                if scope["type"] == "http":
                    request = Request(scope, receive=receive)
                    try:
                        user = await get_current_username(request, db_wrapper=get_db_wrapper())
                        scope["state"] = getattr(scope, "state", {})
                        scope["state"]["user"] = user
                    except HTTPException:
                        response = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Unauthorized"})
                        await response(scope, receive, send)
                        return
                await self.app(scope, receive, send)

        # Get the ASGI app from FastMCP and wrap with authentication middleware
        mcp_asgi_app = mcp.http_app()
        mcp_with_auth = MCPAuthMiddleware(mcp_asgi_app)

        # Mount the MCP server endpoints
        fs_app.mount("/mcp", mcp_with_auth)

    # Start Telegram pollers for all projects with a token
    import json as _json
    from restai.telegram import start_poller, stop_all_pollers

    tg_db_wrapper = get_db_wrapper()
    all_projects = tg_db_wrapper.db.query(ProjectDatabase).all()
    for proj in all_projects:
        opts = _json.loads(proj.options) if proj.options else {}
        token = opts.get("telegram_token")
        if token:
            try:
                start_poller(proj.id, token, fs_app)
            except Exception as e:
                logging.warning(f"Failed to start Telegram poller for project {proj.id}: {e}")
    tg_db_wrapper.db.close()

    yield

    # Shutdown: stop all Telegram pollers
    stop_all_pollers()


logging.basicConfig(level=config.LOG_LEVEL)

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        traces_sample_rate=1.0,
        enable_tracing=True,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title=config.RESTAI_NAME,
    version=get_version_from_pyproject(),
    lifespan=lifespan,
)

oauth_manager = OAuthManager(app, db_wrapper=get_db_wrapper())

if len(OAUTH_PROVIDERS) > 0:
    app.add_middleware(
        SessionMiddleware,
        secret_key=SSO_SECRET_KEY,
        session_cookie="oui-session",
        same_site=SESSION_COOKIE_SAME_SITE,
        https_only=SESSION_COOKIE_SECURE,
    )


@app.get("/oauth/{provider}/login")
async def oauth_login(provider: str, request: Request):
    return await oauth_manager.handle_login(request, provider)


@app.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, response: Response):
    return await oauth_manager.handle_callback(request, provider, response)

    

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logging.error(f"{request}: {exc_str}")
    content = {"status_code": 10422, "message": exc_str, "data": None}
    return JSONResponse(
        content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )

if config.RESTAI_DEV == True:
    print("Running in development mode!")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
