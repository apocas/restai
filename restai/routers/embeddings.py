import json
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Path, Request
import logging
from restai import config
from restai.models.databasemodels import EmbeddingDatabase, ProjectDatabase
from restai.models.models import EmbeddingModel, User, EmbeddingUpdate
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username, get_current_username_admin

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/embeddings/{embedding_name}", response_model=EmbeddingModel)
async def api_get_embedding(embedding_name: str = Path(description="Embedding model name"),
                      _: User = Depends(get_current_username),
                      db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Get embedding model configuration by name."""
    try:
        llm = EmbeddingModel.model_validate(db_wrapper.get_embedding_by_name(embedding_name))
        if llm.options is not None:
            options = json.loads(llm.options)
            if 'api_key' in options:
                options["api_key"] = "********"
                llm.options = json.dumps(options)
            return llm
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(
            status_code=404, detail="Embedding not found")


@router.get("/embeddings", response_model=list[EmbeddingModel])
async def api_get_embeddings(
        user: User = Depends(get_current_username),
        db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """List registered embedding models. Non-admin users only see embeddings accessible via their teams."""
    all_embeddings = db_wrapper.get_embeddings()

    if not user.is_admin:
        allowed_names = set()
        for team in user.teams:
            for emb in (team.embeddings if hasattr(team, 'embeddings') and team.embeddings else []):
                allowed_names.add(emb.name if hasattr(emb, 'name') else emb)
        all_embeddings = [e for e in all_embeddings if e.name in allowed_names]

    embeddings: list[Optional[EmbeddingModel]] = [EmbeddingModel.model_validate(embedding) for embedding in all_embeddings]
    for embedding in embeddings:
        if embedding.options is not None:
            options = json.loads(embedding.options)
            if 'api_key' in options:
                options["api_key"] = "********"
                embedding.options = json.dumps(options)

    return embeddings


@router.post("/embeddings", status_code=201)
async def api_create_embeddings(embeddingc: EmbeddingModel,
                         _: User = Depends(get_current_username_admin),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Register a new embedding model provider (admin only)."""
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
                           embedding_name: str = Path(description="Embedding model name"),
                           embeddingUpdate: EmbeddingUpdate = ...,
                           _: User = Depends(get_current_username_admin),
                           db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Update embedding model configuration (admin only)."""
    try:
        embedding: Optional[EmbeddingDatabase] = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise HTTPException(status_code=404, detail="Embedding not found")
        if db_wrapper.update_embedding(embedding, embeddingUpdate):
            return {"embedding": embedding_name}
        else:
            raise HTTPException(
                status_code=404, detail='Embedding not found')
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(
            status_code=500, detail="Internal server error")


@router.delete("/embeddings/{embedding_name}")
async def api_delete_embedding(embedding_name: str = Path(description="Embedding model name"),
                         _: User = Depends(get_current_username_admin),
                         db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    """Delete an embedding model provider (admin only)."""
    try:
        embedding: Optional[EmbeddingDatabase] = db_wrapper.get_embedding_by_name(embedding_name)
        if embedding is None:
            raise HTTPException(status_code=404, detail="Embedding not found")

        projects_using = db_wrapper.db.query(ProjectDatabase).filter(
            ProjectDatabase.embeddings == embedding_name
        ).all()
        if projects_using:
            names = [p.name for p in projects_using]
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete embedding '{embedding_name}': used by projects: {', '.join(names)}"
            )

        db_wrapper.delete_embedding(embedding)
        return {"deleted": embedding_name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(
            status_code=500, detail="Internal server error")
