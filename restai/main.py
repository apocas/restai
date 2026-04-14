from pathlib import Path
import warnings
warnings.filterwarnings("ignore", message=".*Accessing the 'model_fields' attribute on the instance is deprecated.*")

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Request, Depends, status, Response
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

# When installed from PyPI, frontend may be bundled inside the package
if not FRONTEND_BUILD_DIR.exists():
    _pkg_frontend = Path(__file__).parent.parent / "frontend" / "build"
    if _pkg_frontend.exists():
        FRONTEND_BUILD_DIR = _pkg_frontend

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
        widgets,
        search,
    )
    from restai.models.models import User
    from restai.models.databasemodels import ProjectDatabase
    from restai.multiprocessing import get_manager
    from modules.loaders import LOADERS

    try:
        fs_app.state.manager = get_manager()
    except Exception:
        fs_app.state.manager = None

    from restai.settings import ensure_settings_table, seed_defaults, load_settings
    from restai.database import engine as db_engine
    ensure_settings_table(db_engine)

    # Auto-create new association tables for generators, eval tables, and migrate output table
    from restai.models.databasemodels import TeamImageGeneratorDatabase, TeamAudioGeneratorDatabase, EvalDatasetDatabase, EvalTestCaseDatabase, EvalRunDatabase, EvalResultDatabase, PromptVersionDatabase, GuardEventDatabase, RetrievalEventDatabase, AuditLogDatabase, TeamInvitationDatabase
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
    TeamInvitationDatabase.__table__.create(db_engine, checkfirst=True)
    settings_db_wrapper = get_db_wrapper()
    seed_defaults(settings_db_wrapper)
    load_settings(settings_db_wrapper)

    fs_app.state.brain = Brain()

    from restai.oauth import OAuthManager
    config.load_oauth_providers()
    fs_app.state.oauth_manager = OAuthManager(fs_app, db_wrapper=get_db_wrapper())

    # Run data retention cleanup on startup
    from restai.retention import run_retention_cleanup
    run_retention_cleanup(settings_db_wrapper)

    # Anonymized telemetry
    import os as _os
    if _os.environ.get("ANONYMIZED_TELEMETRY", "True").lower() == "true":
        print("Anonymized telemetry is enabled. To opt out, set ANONYMIZED_TELEMETRY=false.")
        import asyncio
        from restai.telemetry import telemetry_loop
        asyncio.create_task(telemetry_loop())

    if not RESTAI_URL:
      logging.warning("RESTAI_URL env var missing. OAUTH auth schemes may not work properly.")

    @fs_app.get("/", tags=["Health"])
    async def get():
        """Root endpoint — redirect to admin UI."""
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/admin")

    @fs_app.get("/version", tags=["Health"])
    async def get_version(_: User = Depends(get_current_username)):
        """Get the current RESTai version."""
        return {
            "version": fs_app.version,
            "telemetry": _os.environ.get("ANONYMIZED_TELEMETRY", "True").lower() == "true",
        }

    _update_cache = {"data": None, "ts": 0}

    @fs_app.get("/version/check", tags=["Health"])
    async def check_for_update(_: User = Depends(get_current_username)):
        """Check GitHub for a newer release. Cached for 1 hour."""
        import time as _time
        import httpx
        from packaging.version import parse as parse_version

        current = fs_app.version
        now = _time.time()

        # Return cached result if fresh (1 hour)
        if _update_cache["data"] and (now - _update_cache["ts"]) < 3600:
            return _update_cache["data"]

        result = {
            "current": current,
            "latest": current,
            "update_available": False,
            "latest_url": "https://github.com/apocas/restai/releases",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/repos/apocas/restai/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tag = data.get("tag_name", "").lstrip("v")
                    if tag:
                        result["latest"] = tag
                        result["latest_url"] = data.get("html_url", result["latest_url"])
                        result["update_available"] = parse_version(tag) > parse_version(current)
        except Exception:
            pass

        _update_cache["data"] = result
        _update_cache["ts"] = now
        return result

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
    async def get_setup(
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
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

        _sv = db_wrapper.get_setting_value
        return {
            "sso": sso_list,
            "sso_provider_names": sso_provider_names,
            "proxy": bool(_sv("proxy_url")),
            "gpu": config.RESTAI_GPU,
            "app_name": _sv("app_name", "RESTai"),
            "hide_branding": _sv("hide_branding", "false").lower() in ("true", "1"),
            "proxy_url": _sv("proxy_url", ""),
            "currency": _sv("currency", "EUR"),
            "auth_disable_local": _sv("auth_disable_local", "false").lower() in ("true", "1"),
            "mcp": config.RESTAI_MCP,
            "enforce_2fa": _sv("enforce_2fa", "false").lower() in ("true", "1"),
        }

    @fs_app.get("/info", tags=["Health"])
    async def get_info(
        user: User = Depends(get_current_username),
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
            "system_llm_configured": bool(getattr(db_wrapper.get_setting("system_llm"), "value", None)),
        }

        # Filter LLMs and embeddings by team access for non-admin users
        allowed_llm_names = None
        allowed_emb_names = None
        if not user.is_admin:
            allowed_llm_names = set()
            allowed_emb_names = set()
            for team in user.teams:
                for llm in (team.llms if hasattr(team, 'llms') and team.llms else []):
                    allowed_llm_names.add(llm.name if hasattr(llm, 'name') else llm)
                for emb in (team.embeddings if hasattr(team, 'embeddings') and team.embeddings else []):
                    allowed_emb_names.add(emb.name if hasattr(emb, 'name') else emb)

        db_llms = db_wrapper.get_llms()
        for llm in db_llms:
            if allowed_llm_names is not None and llm.name not in allowed_llm_names:
                continue
            output["llms"].append(
                {
                    "id": llm.id,
                    "name": llm.name,
                    "privacy": llm.privacy,
                    "description": llm.description,
                }
            )

        db_embeddings = db_wrapper.get_embeddings()
        for embedding in db_embeddings:
            if allowed_emb_names is not None and embedding.name not in allowed_emb_names:
                continue
            output["embeddings"].append(
                {
                    "id": embedding.id,
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
                """Serve static files if they exist, otherwise index.html for SPA routing."""
                # Serve actual files (manifest.json, favicon.ico, etc.)
                file_path = (FRONTEND_BUILD_DIR / full_path).resolve()
                build_root = FRONTEND_BUILD_DIR.resolve()
                # Prevent directory traversal — resolved path must stay inside build dir
                if full_path and str(file_path).startswith(str(build_root) + "/") and file_path.is_file():
                    return FileResponse(str(file_path))
                index_file = build_root / "index.html"
                if index_file.exists():
                    return FileResponse(str(index_file))
                return JSONResponse(status_code=404, content={"detail": "Frontend not found"})
    except Exception as e:
        print(e)
        print("Admin frontend not available.")

    # Widget JS endpoint
    WIDGET_DIR = Path(__file__).parent / "widget"
    if WIDGET_DIR.exists():
        @fs_app.get("/widget/chat.js")
        async def serve_widget_js():
            widget_file = WIDGET_DIR / "chat.js"
            if widget_file.exists():
                return FileResponse(str(widget_file), media_type="application/javascript")
            return JSONResponse(status_code=404, content={"detail": "Widget not found"})

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
    fs_app.include_router(widgets.router, tags=["Widget"])
    fs_app.include_router(search.router, tags=["Search"])

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

    yield

    # Shutdown: clean up Docker containers
    fs_app.state.brain.shutdown_docker_manager()


logging.basicConfig(level=config.LOG_LEVEL)

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        traces_sample_rate=1.0,
        enable_tracing=True,
        profiles_sample_rate=1.0,
    )

OPENAPI_TAGS = [
    {"name": "Projects", "description": "Create and manage AI projects (RAG, agent, block)"},
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

Supports multiple project types: **RAG**, **Agent**, and **Block**.

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
    return await request.app.state.oauth_manager.handle_login(request, provider)


@app.get("/oauth/{provider}/callback", tags=["Auth"])
async def oauth_callback(provider: str = PathParam(description="OAuth provider name"), request: Request = ..., response: Response = ...):
    """Handle OAuth callback from the specified provider."""
    return await request.app.state.oauth_manager.handle_callback(request, provider, response)

    

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    response = JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 401:
        response.delete_cookie(key="restai_token")
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logging.error(f"{request}: {exc_str}")
    # Extract clean user-facing messages from validation errors
    messages = []
    for err in exc.errors():
        msg = err.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        messages.append(msg)
    detail = "; ".join(messages) if messages else exc_str
    return JSONResponse(
        content={"detail": detail}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
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

# CORS — only allow wildcard origins for widget endpoints (cross-origin
# chat API calls from embedded widgets on third-party sites). All other
# endpoints use same-origin only.
_WIDGET_CORS_PATHS = ("/widget/",)
_CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Accept, X-Widget-Key, X-Widget-Context",
    "Access-Control-Max-Age": "86400",
}


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    path = request.url.path
    is_widget = any(path.startswith(p) for p in _WIDGET_CORS_PATHS)
    origin = request.headers.get("origin")

    # Handle preflight OPTIONS
    if request.method == "OPTIONS" and is_widget and origin:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                **_CORS_HEADERS,
            },
        )

    response = await call_next(request)

    # Add CORS headers only for widget endpoints
    if is_widget and origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        for k, v in _CORS_HEADERS.items():
            response.headers[k] = v

    return response
