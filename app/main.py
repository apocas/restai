from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Depends, status
import logging
from app import config
import sentry_sdk

print("""
  ___ ___ ___ _____ _   ___      _.--'"'.
 | _ \ __/ __|_   _/_\ |_ _|    (  ( (   )
 |   / _|\__ \ | |/ _ \ | |     (o)_    ) )
 |_|_\___|___/ |_/_/ \_\___|        (o)_.'
                            
""")

from modules.loaders import LOADERS
from modules.embeddings import EMBEDDINGS
from app.models.models import User
from app.database import get_db_wrapper, DBWrapper
from app.brain import Brain
from app.auth import get_current_username
from app.routers import llms, projects, tools, users, image
from app import config

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        traces_sample_rate=1.0,
        enable_tracing=True,
        profiles_sample_rate=1.0
    )

app = FastAPI(
    title="RestAI",
    description="RestAI is an AIaaS (AI as a Service) open-source platform. Built on top of Llamaindex, Langchain and Transformers. Supports any public LLM supported by LlamaIndex and any local LLM suported by Ollama. Precise embeddings usage and tuning.",
    version="5.0.2",
    contact={
        "name": "Pedro Dias",
        "url": "https://github.com/apocas/restai",
        "email": "petermdias@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
    logging.error(f"{request}: {exc_str}")
    content = {'status_code': 10422, 'message': exc_str, 'data': None}
    return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


if config.RESTAI_DEV:
    print("Running in development mode!")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

brain = Brain()

app.state.brain = brain

app.include_router(llms.router)
app.include_router(projects.router)
app.include_router(tools.router)
app.include_router(users.router)

if config.RESTAI_GPU:
    app.include_router(image.router)


@app.get("/")
async def get(request: Request):
    return "RESTAI, so many 'A's and 'I's, so little time..."


@app.get("/version")
async def get_version():
    return {
        "version": app.version,
    }


@app.get("/info")
async def get_info(_: User = Depends(get_current_username), db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    output = {
        "version": app.version,
        "loaders": list(LOADERS.keys()),
        "embeddings": [],
        "llms": []
    }

    llms = db_wrapper.get_llms()
    for llm in llms:
        output["llms"].append({
            "name": llm.name,
            "privacy": llm.privacy,
            "description": llm.description,
            "type": llm.type
        })

    for embedding in EMBEDDINGS:
        _, _, privacy, description, _ = EMBEDDINGS[embedding]
        output["embeddings"].append({
            "name": embedding,
            "privacy": privacy,
            "description": description
        })
    return output


try:
    app.mount("/admin/", StaticFiles(directory="frontend/html/",
                                     html=True), name="static_admin")
    app.mount(
        "/admin/static/js",
        StaticFiles(
            directory="frontend/html/static/js"),
        name="static_js")
    app.mount(
        "/admin/static/css",
        StaticFiles(
            directory="frontend/html/static/css"),
        name="static_css")
    app.mount(
        "/admin/static/media",
        StaticFiles(
            directory="frontend/html/static/media"),
        name="static_media")
except BaseException:
    print("Admin frontend not available.")
