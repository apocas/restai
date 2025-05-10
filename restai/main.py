from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Depends, status, Response
import logging

from fastmcp import FastMCP
from restai import config
import sentry_sdk
from contextlib import asynccontextmanager
from restai.database import get_db_wrapper
from restai.oauth import OAuthManager
from starlette.middleware.sessions import SessionMiddleware
from restai.config import (
    OAUTH_PROVIDERS,
    SECRET_KEY,
    SESSION_COOKIE_SAME_SITE,
    SESSION_COOKIE_SECURE,
)

@asynccontextmanager
async def lifespan(fs_app: FastAPI):
    print(
        """
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
    )
    from restai.models.models import User
    from restai.multiprocessing import get_manager
    from modules.loaders import LOADERS
    from modules.embeddings import EMBEDDINGS

    fs_app.state.manager = get_manager()
    fs_app.state.brain = Brain()

    @fs_app.get("/")
    async def get():
        return "RESTai, so many 'A's and 'I's, so little time..."

    @fs_app.get("/version")
    async def get_version():
        return {
            "version": fs_app.version,
        }

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
        }

    @fs_app.get("/info")
    async def get_info(
        _: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper),
    ):
        output = {
            "version": fs_app.version,
            "loaders": list(LOADERS.keys()),
            "embeddings": [],
            "llms": [],
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

        for embedding in EMBEDDINGS:
            _, _, privacy, description, _ = EMBEDDINGS[embedding]
            output["embeddings"].append(
                {"name": embedding, "privacy": privacy, "description": description}
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
            "/admin/",
            StaticFiles(directory="frontend/build/", html=True),
            name="static_admin",
        )
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

    if config.RESTAI_GPU == True:
        fs_app.include_router(image.router)
        fs_app.include_router(audio.router)

    yield


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        traces_sample_rate=1.0,
        enable_tracing=True,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title=config.RESTAI_NAME,
    version="5.0.3",
    lifespan=lifespan,
)

oauth_manager = OAuthManager(app, db_wrapper=get_db_wrapper())

if len(OAUTH_PROVIDERS) > 0:
    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
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

if config.MCP_SERVER:
    print("MCP server starting...")
    #mcp = FastMCP.from_fastapi(app=app)
    #mcp.run()
    

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
