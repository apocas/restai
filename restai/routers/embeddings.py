import json
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Request
import traceback
import logging
from restai import config
from restai.models.databasemodels import EmbeddingDatabase
from restai.models.models import EmbeddingModel, User, EmbeddingUpdate
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username, get_current_username_admin
from modules.embeddings import EMBEDDINGS

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/embeddings/{embedding_name}", response_model=EmbeddingModel)
async def api_get_embedding(embedding_name: str,
                      _: User = Depends(get_current_username),
                      db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    if embedding_name in EMBEDDINGS:
        _, _, privacy, description, _ = EMBEDDINGS[embedding_name]
        return EmbeddingModel(name=embedding_name, class_name="LangChain", options="{}", privacy=privacy, description=description)
  
    try:
        llm = EmbeddingModel.model_validate(db_wrapper.get_embedding_by_name(embedding_name))
        if llm.options is not None:
            options = json.loads(llm.options)
            if 'api_key' in options:
                options["api_key"] = "********"
                llm.options = json.dumps(options)
            return llm
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/embeddings", response_model=list[EmbeddingModel])
async def api_get_embeddings(
        _: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    embeddings: list[Optional[EmbeddingModel]] = [EmbeddingModel.model_validate(embedding) for embedding in db_wrapper.get_embeddings()]
    for embedding in embeddings:
        if embedding.options is not None:
            options = json.loads(embedding.options)
            if 'api_key' in options:
                options["api_key"] = "********"
                embedding.options = json.dumps(options)
    
    for embedding in EMBEDDINGS:
        _, _, privacy, description, dimension = EMBEDDINGS[embedding]
        embeddings.append(EmbeddingModel(name=embedding, class_name="LangChain", options="{}", privacy=privacy, description=description, dimension=dimension))
    
    return embeddings


@router.post("/embeddings")
async def api_create_embeddings(embeddingc: EmbeddingModel,
                         _: User = Depends(get_current_username_admin),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        embedding: EmbeddingDatabase = db_wrapper.create_embedding(embeddingc.name, embeddingc.class_name, embeddingc.options, embeddingc.privacy, embeddingc.description, embeddingc.dimension)
        return embedding
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create Embedding ' + embeddingc.name)


@router.patch("/embeddings/{embedding_name}")
async def api_edit_embedding(request: Request,
                           embedding_name: str,
                           embeddingUpdate: EmbeddingUpdate,
                           _: User = Depends(get_current_username_admin),
                           db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        embedding: Optional[EmbeddingDatabase] = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise Exception("Embedding not found")
        if db_wrapper.update_embedding(embedding, embeddingUpdate):
            return {"embedding": embedding_name}
        else:
            raise HTTPException(
                status_code=404, detail='Embedding not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.delete("/embeddings/{embedding_name}")
async def api_delete_embedding(embedding_name: str,
                         _: User = Depends(get_current_username_admin),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    try:
        embedding: Optional[EmbeddingDatabase] = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise Exception("Embedding not found")
        db_wrapper.delete_embedding(embedding)
        return {"deleted": embedding_name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
