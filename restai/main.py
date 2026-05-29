from pathlib import Path
import warnings
warnings.filterwarnings("ignore", message=".*Accessing the 'model_fields' attribute on the instance is deprecated.*")

from fastapi import FastAPI, Request, Response
from fastapi import Path as PathParam
import logging

from restai import config
import sentry_sdk
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from restai.config import (
    SSO_SECRET_KEY,
    SESSION_COOKIE_SAME_SITE,
    SESSION_COOKIE_SECURE,
    RESTAI_AUTH_SECRET,
    RESTAI_URL,
)
from restai.utils.version import get_version_from_pyproject
from restai.app_setup import (
    register_health_routes,
    register_static_mounts,
    register_routers,
    register_spa,
)
from restai.middleware import register_middleware


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
    from restai.database import open_db_wrapper
    from restai.multiprocessing import get_manager

    try:
        fs_app.state.manager = get_manager()
    except Exception:
        fs_app.state.manager = None

    from restai.settings import ensure_settings_table, seed_defaults
    from restai.database import engine as db_engine
    ensure_settings_table(db_engine)

    from restai.models.databasemodels import TeamImageGeneratorDatabase, TeamAudioGeneratorDatabase, EvalDatasetDatabase, EvalTestCaseDatabase, EvalRunDatabase, EvalResultDatabase, PromptVersionDatabase, GuardEventDatabase, RetrievalEventDatabase, AuditLogDatabase, TeamInvitationDatabase, ImageGeneratorDatabase, SpeechToTextDatabase, ProjectSecretDatabase, ProjectTemplateDatabase, BulkIngestJobDatabase, RoutineExecutionLogDatabase
    TeamImageGeneratorDatabase.__table__.create(db_engine, checkfirst=True)
    TeamAudioGeneratorDatabase.__table__.create(db_engine, checkfirst=True)
    ImageGeneratorDatabase.__table__.create(db_engine, checkfirst=True)
    SpeechToTextDatabase.__table__.create(db_engine, checkfirst=True)
    ProjectSecretDatabase.__table__.create(db_engine, checkfirst=True)
    ProjectTemplateDatabase.__table__.create(db_engine, checkfirst=True)
    BulkIngestJobDatabase.__table__.create(db_engine, checkfirst=True)
    RoutineExecutionLogDatabase.__table__.create(db_engine, checkfirst=True)
    EvalDatasetDatabase.__table__.create(db_engine, checkfirst=True)
    EvalTestCaseDatabase.__table__.create(db_engine, checkfirst=True)
    EvalRunDatabase.__table__.create(db_engine, checkfirst=True)
    EvalResultDatabase.__table__.create(db_engine, checkfirst=True)
    PromptVersionDatabase.__table__.create(db_engine, checkfirst=True)
    GuardEventDatabase.__table__.create(db_engine, checkfirst=True)
    RetrievalEventDatabase.__table__.create(db_engine, checkfirst=True)
    AuditLogDatabase.__table__.create(db_engine, checkfirst=True)
    TeamInvitationDatabase.__table__.create(db_engine, checkfirst=True)
    settings_db_wrapper = open_db_wrapper()
    seed_defaults(settings_db_wrapper)

    fs_app.state.brain = Brain()

    # Idempotent — existing rows keep admin-applied state.
    try:
        from restai.image.registry import seed_local_generators
        seeded = seed_local_generators(settings_db_wrapper)
        if seeded:
            logging.info("Seeded %d local image generator(s)", seeded)
    except Exception as e:
        logging.warning("Failed to seed local image generators: %s", e)

    try:
        from restai.speech_to_text.registry import seed_local_stt_models
        seeded = seed_local_stt_models(settings_db_wrapper)
        if seeded:
            logging.info("Seeded %d local speech-to-text model(s)", seeded)
    except Exception as e:
        logging.warning("Failed to seed local speech-to-text models: %s", e)

    from restai.integrations.oauth import OAuthManager
    config.load_oauth_providers()
    fs_app.state.oauth_manager = OAuthManager(fs_app, db_wrapper=open_db_wrapper())

    from restai.limits.retention import run_retention_cleanup
    run_retention_cleanup(settings_db_wrapper)

    import os as _os
    if _os.environ.get("ANONYMIZED_TELEMETRY", "True").lower() == "true":
        print("Anonymized telemetry is enabled. To opt out, set ANONYMIZED_TELEMETRY=false.")
        import asyncio
        from restai.observability.telemetry import telemetry_loop
        asyncio.create_task(telemetry_loop())

    if not RESTAI_URL:
        logging.warning("RESTAI_URL env var missing. OAUTH auth schemes may not work properly.")

    # JWT signing secret strength check — catches legacy installs / copy-pasted
    # dev secrets. Defaults from `_ensure_env_secret` are 64 url-safe base64 chars.
    _weak_secrets = {"secret", "changeme", "change-me", "default", "password", "restai", "dev"}
    secret_val = (RESTAI_AUTH_SECRET or "").strip()
    fs_app.state.auth_secret_weak = False
    if not secret_val:
        logging.error(
            "SECURITY: RESTAI_AUTH_SECRET is empty. JWTs will fail to sign. "
            "Set a long random value in .env (at least 32 bytes)."
        )
        fs_app.state.auth_secret_weak = True
    elif len(secret_val) < 32:
        logging.warning(
            "SECURITY: RESTAI_AUTH_SECRET is %d chars (recommended ≥32). "
            "Generate a stronger value with `python -c \"import secrets; print(secrets.token_urlsafe(64))\"` "
            "and rotate it.", len(secret_val),
        )
        fs_app.state.auth_secret_weak = True
    elif secret_val.lower() in _weak_secrets:
        logging.warning(
            "SECURITY: RESTAI_AUTH_SECRET matches a known-weak default (%r). "
            "Rotate to a long random value before going to production.", secret_val,
        )
        fs_app.state.auth_secret_weak = True

    # Route registration runs at startup (DB/Brain must be ready first).
    # Order is load-bearing: health + static mounts, then all API routers,
    # then the SPA catch-all LAST so explicit endpoints win route matching.
    register_health_routes(fs_app)
    spa_build_dir = register_static_mounts(fs_app)
    register_routers(fs_app)
    register_spa(fs_app, spa_build_dir)

    yield

    # Docker per-chat / per-project / browser containers are no longer
    # process-managed — `crons/docker_cleanup.py`, `crons/browser_cleanup.py`,
    # and `crons/app_cleanup.py` evict idle containers, so on lifespan
    # shutdown there's nothing for us to stop. (Old behavior nuked all
    # managed containers; that wiped the in-flight work of any sibling
    # worker. Bug, not feature.)


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
from restai.observability.audit import AuditMiddleware
app.add_middleware(AuditMiddleware)


@app.get("/oauth/{provider}/login", tags=["Auth"])
async def oauth_login(provider: str = PathParam(description="OAuth provider name"), request: Request = ...):
    return await request.app.state.oauth_manager.handle_login(request, provider)


@app.get("/oauth/{provider}/callback", tags=["Auth"])
async def oauth_callback(provider: str = PathParam(description="OAuth provider name"), request: Request = ..., response: Response = ...):
    return await request.app.state.oauth_manager.handle_callback(request, provider, response)


# Exception handlers + CORS/security-header middleware.
register_middleware(app)

if config.RESTAI_DEV == True:
    print("Running in development mode!")
