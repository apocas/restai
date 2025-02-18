import base64
import json
import logging
import os
import re
import traceback
import urllib.parse
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    BackgroundTasks,
    Query,
)
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
import requests
from unidecode import unidecode
from restai import config
from restai.auth import (
    get_current_username,
    get_current_username_admin,
    get_current_username_project,
    get_current_username_project_public,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.helper import chat_main, question_main
from restai.loaders.url import SeleniumWebReader
from restai.models.models import (
    FindModel,
    IngestResponse,
    KeyCreate,
    ProjectModel,
    ProjectModelCreate,
    ProjectModelUpdate,
    ProjectsResponse,
    QuestionModel,
    ChatModel,
    TextIngestModel,
    URLIngestModel,
    User,
)
from restai.project import Project
from restai.vectordb import tools
from restai.vectordb.tools import (
    find_file_loader,
    extract_keywords_for_metadata,
    index_documents_classic,
    index_documents_docling,
)
from modules.embeddings import EMBEDDINGS
from restai.models.databasemodels import OutputDatabase
import datetime
from sqlalchemy import func
import calendar

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()



@router.post("/proxy/keys")
async def route_create_key(
    key_create: KeyCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + '/key/generate'
    headers = {
        'Authorization': 'Bearer ' + config.PROXY_KEY,
        'Content-Type': 'application/json'
    }
    data = {
        "models": key_create.models,
        "metadata": {"user": key_create.user}
    }

    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        data = response.json()
        return {"key": data["key"], "models": data["models"]}
    else:
        return {"error": "Failed to generate new key"}
    

@router.get("/proxy/keys")
async def route_get_keys(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + '/user/info'
    headers = {
        'Authorization': 'Bearer ' + config.PROXY_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["keys"]:
            output.append({"key": key["key_name"], "models": key["models"]})
        return {"keys": output}
    else:
        return {"error": "Failed to list keys"}
    

@router.get("/proxy/models")
async def route_create_key(
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    url = config.PROXY_URL + '/models'
    headers = {
        'Authorization': 'Bearer ' + config.PROXY_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        output = []
        for key in data["data"]:
            output.append({"model": key["id"]})
        return {"models": output}
    else:
        return {"error": "Failed to list keys"}