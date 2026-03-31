from pathlib import Path

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Depends, status, Response
from fastapi import Path as PathParam
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
        direct,
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

    # Auto-create new association tables for generators, eval tables, and migrate output table
    from restai.models.databasemodels import TeamImageGeneratorDatabase, TeamAudioGeneratorDatabase, EvalDatasetDatabase, EvalTestCaseDatabase, EvalRunDatabase, EvalResultDatabase, PromptVersionDatabase, GuardEventDatabase, RetrievalEventDatabase, AuditLogDatabase
    from sqlalchemy import inspect as sa_inspect, Column, Integer, ForeignKey, text
    TeamImageGeneratorDatabase.__table__.create(db_engine, checkfirst=True)
    TeamAudioGeneratorDatabase.__table__.create(db_engine, checkfirst=True)
    EvalDatasetDatabase.__table__.create(db_engine, checkfirst=True)
    EvalTestCaseDatabase.__table__.create(db_engine, checkfirst=True)
    EvalRunDatabase.__table__.create(db_engine, checkfirst=True)
    EvalResultDatabase.__table__.create(db_engine, checkfirst=True)
    PromptVersionDatabase.__table__.create(db_engine, checkfirst=True)
    GuardEventDatabase.__table__.create(db_engine, checkfirst=True)
    RetrievalEventDatabase.__table__.create(db_engine, checkfirst=True)
    AuditLogDatabase.__table__.create(db_engine, checkfirst=True)
    inspector = sa_inspect(db_engine)
    if "output" in inspector.get_table_names():
        output_cols = {c["name"] for c in inspector.get_columns("output")}
        if "team_id" not in output_cols:
            with db_engine.begin() as conn:
                conn.execute(text("ALTER TABLE output ADD COLUMN team_id INTEGER"))
    settings_db_wrapper = get_db_wrapper()
    seed_defaults(settings_db_wrapper)
    load_settings(settings_db_wrapper)

    if not RESTAI_URL:
      logging.warning("RESTAI_URL env var missing. OAUTH auth schemes may not work properly.")

    @fs_app.get("/", tags=["Health"])
    async def get():
        """Root endpoint."""
        return "RESTai, so many 'A's and 'I's, so little time..."

    @fs_app.get("/version", tags=["Health"])
    async def get_version():
        """Get the current RESTai version."""
        return {
            "version": fs_app.version,
        }

    @fs_app.get("/health/live", tags=["Health"])
    async def health_live():
        """Liveness probe. Returns 200 if the service is running."""
        return {"status": "ok"}

    @fs_app.get("/health/ready", tags=["Health"])
    async def health_ready():
        """Readiness probe. Checks database and Redis connectivity."""
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

    @fs_app.get("/setup", tags=["Health"])
    async def get_setup():
        """Get platform setup information including SSO providers and feature flags."""
        sso_list = []
        if isinstance(config.OAUTH_PROVIDERS, dict):
            sso_list = list(config.OAUTH_PROVIDERS.keys())
        elif isinstance(config.OAUTH_PROVIDERS, (list, tuple)):
            sso_list = list(config.OAUTH_PROVIDERS)
        else:
            sso_list = []
        sso_provider_names = {}
        for provider in sso_list:
            if provider == "oidc":
                sso_provider_names[provider] = config.OAUTH_PROVIDER_NAME or "SSO"
            else:
                sso_provider_names[provider] = provider.capitalize()

        return {
            "sso": sso_list,
            "sso_provider_names": sso_provider_names,
            "proxy": bool(config.PROXY_URL),
            "gpu": config.RESTAI_GPU,
            "app_name": config.RESTAI_NAME,
            "hide_branding": config.HIDE_BRANDING,
            "proxy_url": config.PROXY_URL or "",
            "currency": config.CURRENCY or "EUR",
            "auth_disable_local": config.RESTAI_AUTH_DISABLE_LOCAL,
            "mcp": config.RESTAI_MCP,
        }

    @fs_app.get("/info", tags=["Health"])
    async def get_info(
        _: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
        """Get platform information including available LLMs, embeddings, and loaders."""
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

    fs_app.include_router(llms.router, tags=["LLMs"])
    fs_app.include_router(embeddings.router, tags=["Embeddings"])
    fs_app.include_router(projects.router)
    fs_app.include_router(tools.router, tags=["Tools"])
    fs_app.include_router(users.router, tags=["Users"])
    fs_app.include_router(proxy.router, tags=["Proxy"])
    fs_app.include_router(statistics.router, tags=["Statistics"])
    fs_app.include_router(auth.router, tags=["Auth"])
    fs_app.include_router(teams.router, tags=["Teams"])
    fs_app.include_router(settings.router, tags=["Settings"])
    fs_app.include_router(direct.router, tags=["Direct Access"])

    from restai.routers import evals
    fs_app.include_router(evals.router)

    if config.RESTAI_GPU == True:
        fs_app.include_router(image.router, tags=["Image"])
        fs_app.include_router(audio.router, tags=["Audio"])

    if config.RESTAI_MCP:
        from restai.mcp import create_mcp_server
        mcp_server = create_mcp_server(fs_app)
        fs_app.mount("/mcp", mcp_server.http_app(transport="sse"))
        logging.info("MCP server enabled at /mcp/sse")

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

OPENAPI_TAGS = [
    {"name": "Projects", "description": "Create and manage AI projects (RAG, inference, agent, vision, block)"},
    {"name": "Knowledge", "description": "Manage embeddings and knowledge base for RAG projects"},
    {"name": "Chat", "description": "Chat and question endpoints for interacting with projects"},
    {"name": "Teams", "description": "Manage teams, members, admins, and resource access"},
    {"name": "Users", "description": "User management and API key management"},
    {"name": "LLMs", "description": "Register and configure Large Language Model providers"},
    {"name": "Embeddings", "description": "Register and configure embedding model providers"},
    {"name": "Tools", "description": "Text classification, MCP server probing, Ollama model management"},
    {"name": "Proxy", "description": "LiteLLM proxy key management"},
    {"name": "Statistics", "description": "Platform usage statistics and analytics"},
    {"name": "Auth", "description": "Authentication, login, logout, and session management"},
    {"name": "Settings", "description": "Platform settings (admin only)"},
    {"name": "Image", "description": "GPU-accelerated image generation"},
    {"name": "Audio", "description": "GPU-accelerated audio transcription"},
    {"name": "Direct Access", "description": "OpenAI-compatible direct access to LLMs, image and audio generators"},
    {"name": "Health", "description": "Health checks and system information"},
]

app = FastAPI(
    title=config.RESTAI_NAME,
    description="""RESTai is an AIaaS (AI as a Service) platform. Create AI projects and consume them via REST API.

Supports multiple project types: **RAG**, **Inference**, **Agent**, and **Block**.

## Authentication

All endpoints require authentication via one of:
- **JWT Cookie** (`restai_token`)
- **Bearer API Key** (`Authorization: Bearer <key>`)
- **Basic Auth** (`Authorization: Basic <credentials>`)
""",
    version=get_version_from_pyproject(),
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    contact={"name": "RESTai", "url": "https://github.com/apocas/restai"},
    license_info={"name": "Apache 2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
)

oauth_manager = OAuthManager(app, db_wrapper=get_db_wrapper())
app.state.oauth_manager = oauth_manager

# Always add SessionMiddleware so SSO can be enabled at runtime via settings
app.add_middleware(
    SessionMiddleware,
    secret_key=SSO_SECRET_KEY,
    session_cookie="oui-session",
    same_site=SESSION_COOKIE_SAME_SITE,
    https_only=SESSION_COOKIE_SECURE,
)

# Audit log middleware — records all mutation requests
from restai.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)


@app.get("/oauth/{provider}/login", tags=["Auth"])
async def oauth_login(provider: str = PathParam(description="OAuth provider name"), request: Request = ...):
    """Initiate OAuth login flow for the specified provider."""
    return await oauth_manager.handle_login(request, provider)


@app.get("/oauth/{provider}/callback", tags=["Auth"])
async def oauth_callback(provider: str = PathParam(description="OAuth provider name"), request: Request = ..., response: Response = ...):
    """Handle OAuth callback from the specified provider."""
    return await oauth_manager.handle_callback(request, provider, response)

    

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logging.error(f"{request}: {exc_str}")
    content = {"detail": exc_str}
    return JSONResponse(
        content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")
    return JSONResponse(
        content={"detail": "Internal server error"},
        status_code=500
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
