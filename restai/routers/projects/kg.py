import base64
import json
import logging
from typing import Optional
import os
import re
import traceback
from pathlib import Path
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Path as PathParam,
    Request,
    UploadFile,
    BackgroundTasks,
    Query,
)
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import Document
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from unidecode import unidecode
from restai import config
from restai.auth import (
    get_current_username,
    get_current_username_project,
    get_current_username_project_public,
    check_not_restricted,
    check_user_can_use_mcp_host,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.helper import chat_main
from restai.loaders.url import SeleniumWebReader
from restai.models.models import (
    FindModel,
    IngestResponse,
    ProjectModel,
    ProjectModelCreate,
    ProjectModelUpdate,
    ProjectResponse,
    ProjectsResponse,
    ProjectCommentCreate,
    ProjectCommentUpdate,
    ChatModel,
    TextIngestModel,
    URLIngestModel,
    User,
    WidgetCreate,
    WidgetUpdate,
    WidgetConfig,
    WidgetResponse,
    WidgetCreatedResponse,
    BlockGenerateRequest,
    SystemPromptGenerateRequest,
    ProjectToolUpdate,
    RoutineCreate,
    RoutineUpdate,
    validate_safe_name,
)
import uuid
import secrets
from restai.utils.crypto import encrypt_api_key, hash_api_key, encrypt_field
from restai.brain import Brain
from restai.project import Project
from restai.vectordb import tools
from restai.integrations.knowledge_graph import extract_and_persist_safe
from restai.vectordb.tools import (
    find_file_loader,
    extract_keywords_for_metadata,
    index_documents_classic,
    index_documents_docling,
)
from restai.models.databasemodels import OutputDatabase, ProjectDatabase, ProjectInvitationDatabase
from restai.settings import mask_key
import datetime
from sqlalchemy import func, Integer, case
import calendar
import tempfile
import shutil

from restai.routers.projects._common import (
    router,
    get_project,
    _mask_sync_sources,
    _SENSITIVE_OPTION_KEYS,
)

@router.get("/projects/{projectID}/kg/entities", tags=["Knowledge Graph"])
async def kg_list_entities(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    type: Optional[str] = Query(None, description="Filter by entity type (PERSON, ORG, LOC, MISC)"),
    search: Optional[str] = Query(None, description="Substring search on entity name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List entities in a project's knowledge graph."""
    from restai.models.databasemodels import KGEntityDatabase

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Knowledge graph is only available for RAG projects.")

    q = db_wrapper.db.query(KGEntityDatabase).filter(KGEntityDatabase.project_id == projectID)
    if type:
        q = q.filter(KGEntityDatabase.entity_type == type)
    if search:
        q = q.filter(KGEntityDatabase.normalized.ilike(f"%{search.lower()}%"))
    total = q.count()
    rows = q.order_by(KGEntityDatabase.mention_count.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "normalized": e.normalized,
                "entity_type": e.entity_type,
                "mention_count": e.mention_count,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in rows
        ],
    }


@router.get("/projects/{projectID}/kg/entities/{entity_id}", tags=["Knowledge Graph"])
async def kg_get_entity(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    entity_id: int = PathParam(description="Entity ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get one entity with all its mentions and related entities."""
    from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase, KGEntityRelationshipDatabase

    entity = (
        db_wrapper.db.query(KGEntityDatabase)
        .filter(KGEntityDatabase.id == entity_id, KGEntityDatabase.project_id == projectID)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    mentions = (
        db_wrapper.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id == entity_id)
        .all()
    )
    edges = (
        db_wrapper.db.query(KGEntityRelationshipDatabase)
        .filter(
            (KGEntityRelationshipDatabase.from_entity_id == entity_id)
            | (KGEntityRelationshipDatabase.to_entity_id == entity_id)
        )
        .all()
    )
    related_ids = set()
    for edge in edges:
        if edge.from_entity_id != entity_id:
            related_ids.add(edge.from_entity_id)
        if edge.to_entity_id != entity_id:
            related_ids.add(edge.to_entity_id)
    related_entities = (
        db_wrapper.db.query(KGEntityDatabase).filter(KGEntityDatabase.id.in_(related_ids)).all()
        if related_ids else []
    )
    related_map = {r.id: r for r in related_entities}

    return {
        "id": entity.id,
        "name": entity.name,
        "normalized": entity.normalized,
        "entity_type": entity.entity_type,
        "mention_count": entity.mention_count,
        "mentions": [
            {"source": m.source, "mention_count": m.mention_count}
            for m in mentions
        ],
        "related": [
            {
                "id": eid,
                "name": related_map[eid].name,
                "entity_type": related_map[eid].entity_type,
                "weight": next(
                    (e.weight for e in edges if e.from_entity_id == eid or e.to_entity_id == eid),
                    1,
                ),
            }
            for eid in related_ids if eid in related_map
        ],
    }


@router.patch("/projects/{projectID}/kg/entities/{entity_id}", tags=["Knowledge Graph"])
async def kg_update_entity(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    entity_id: int = PathParam(description="Entity ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Rename an entity (update display name only — normalized name is derived)."""
    check_not_restricted(user)
    from restai.models.databasemodels import KGEntityDatabase
    from restai.integrations.knowledge_graph import normalize_entity_name

    new_name = (body.get("name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name is required")

    entity = (
        db_wrapper.db.query(KGEntityDatabase)
        .filter(KGEntityDatabase.id == entity_id, KGEntityDatabase.project_id == projectID)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    entity.name = new_name[:255]
    entity.normalized = normalize_entity_name(new_name)[:255]
    entity.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db_wrapper.db.commit()
    return {"id": entity.id, "name": entity.name, "normalized": entity.normalized}


@router.delete("/projects/{projectID}/kg/entities/{entity_id}", status_code=204, tags=["Knowledge Graph"])
async def kg_delete_entity(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    entity_id: int = PathParam(description="Entity ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an entity and all its mentions/relationships."""
    check_not_restricted(user)
    from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase, KGEntityRelationshipDatabase

    entity = (
        db_wrapper.db.query(KGEntityDatabase)
        .filter(KGEntityDatabase.id == entity_id, KGEntityDatabase.project_id == projectID)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    db_wrapper.db.query(KGEntityMentionDatabase).filter(KGEntityMentionDatabase.entity_id == entity_id).delete()
    db_wrapper.db.query(KGEntityRelationshipDatabase).filter(
        (KGEntityRelationshipDatabase.from_entity_id == entity_id)
        | (KGEntityRelationshipDatabase.to_entity_id == entity_id)
    ).delete(synchronize_session=False)
    db_wrapper.db.delete(entity)
    db_wrapper.db.commit()


@router.post("/projects/{projectID}/kg/entities/{entity_id}/merge", tags=["Knowledge Graph"])
async def kg_merge_entity(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    entity_id: int = PathParam(description="Source entity ID (will be deleted)"),
    body: dict = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Merge this entity (source) INTO the target entity. Source is deleted."""
    check_not_restricted(user)
    from restai.integrations.knowledge_graph import merge_entities

    target_id = body.get("target_id")
    if not target_id or not isinstance(target_id, int):
        raise HTTPException(status_code=400, detail="target_id (int) is required")

    success = merge_entities(db_wrapper, primary_id=target_id, secondary_id=entity_id)
    if not success:
        raise HTTPException(status_code=400, detail="Merge failed (entities not found, same id, or different projects)")
    return {"merged_into": target_id}


@router.get("/projects/{projectID}/kg/duplicates", tags=["Knowledge Graph"])
async def kg_find_duplicates(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    threshold: float = Query(0.85, ge=0.5, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List potential duplicate entity pairs based on name similarity."""
    from restai.integrations.knowledge_graph import compute_potential_duplicates
    return {"candidates": compute_potential_duplicates(db_wrapper, projectID, threshold=threshold, limit=limit)}


@router.get("/projects/{projectID}/kg/graph", tags=["Knowledge Graph"])
async def kg_get_graph(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    type: Optional[str] = Query(None, description="Filter nodes by entity type"),
    limit: int = Query(100, ge=1, le=500, description="Max number of top entities to include"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return nodes and edges for knowledge graph visualization."""
    from restai.models.databasemodels import KGEntityDatabase, KGEntityRelationshipDatabase

    q = db_wrapper.db.query(KGEntityDatabase).filter(KGEntityDatabase.project_id == projectID)
    if type:
        q = q.filter(KGEntityDatabase.entity_type == type)
    top_entities = q.order_by(KGEntityDatabase.mention_count.desc()).limit(limit).all()
    entity_ids = {e.id for e in top_entities}

    nodes = [
        {
            "id": e.id,
            "label": e.name,
            "type": e.entity_type,
            "mention_count": e.mention_count,
        }
        for e in top_entities
    ]
    edges_q = (
        db_wrapper.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == projectID)
        .all()
    )
    edges = [
        {"from": e.from_entity_id, "to": e.to_entity_id, "weight": e.weight}
        for e in edges_q
        if e.from_entity_id in entity_ids and e.to_entity_id in entity_ids
    ]
    return {"nodes": nodes, "edges": edges}


@router.post("/projects/{projectID}/kg/query", tags=["Knowledge Graph"])
async def kg_query(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    body: dict = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Natural language query against the knowledge graph."""
    import re as _re
    from restai.integrations.knowledge_graph import find_entities_in_text, normalize_entity_name
    from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Only available for RAG projects.")
    if not project.props.options.enable_knowledge_graph:
        raise HTTPException(status_code=400, detail="Knowledge graph is not enabled for this project.")

    brain = request.app.state.brain

    # Match question against entities already in the project graph; NER is supplementary.
    project_entities = (
        db_wrapper.db.query(KGEntityDatabase)
        .filter(KGEntityDatabase.project_id == projectID)
        .all()
    )

    if not project_entities:
        return {
            "answer": "This project's knowledge graph is empty. Ingest some documents (with knowledge graph enabled) or click Rebuild Graph first.",
            "entities_matched": [],
            "sources": [],
            "source_count": 0,
        }

    question_lower = " " + _re.sub(r"[^\w\s]", " ", question.lower()) + " "
    matched_entities = []
    for ent in project_entities:
        norm = ent.normalized or ""
        if not norm:
            continue
        # Word-boundary substring match — avoids "ace" inside "place".
        if f" {norm} " in question_lower:
            matched_entities.append(ent)

    # Supplement with NER hits for near-matches not in the DB by exact form.
    try:
        ner_hits = find_entities_in_text(question, brain)
        if ner_hits:
            ner_normalized = {normalize_entity_name(name) for name, _ in ner_hits}
            already_matched_ids = {e.id for e in matched_entities}
            extra = (
                db_wrapper.db.query(KGEntityDatabase)
                .filter(
                    KGEntityDatabase.project_id == projectID,
                    KGEntityDatabase.normalized.in_(list(ner_normalized)),
                )
                .all()
            )
            for e in extra:
                if e.id not in already_matched_ids:
                    matched_entities.append(e)
    except Exception as e:
        logging.warning("NER fallback failed in kg/query: %s", e)

    if not matched_entities:
        sample = [e.name for e in project_entities[:10]]
        return {
            "answer": (
                "I couldn't match any entities from your question against this project's knowledge graph. "
                f"Try mentioning one of these entities by name: {', '.join(sample)}"
                + ("..." if len(project_entities) > 10 else "")
            ),
            "entities_matched": [],
            "sources": [],
            "source_count": 0,
        }

    matched_entity_ids = [e.id for e in matched_entities]
    matched_sources = list({
        m.source for m in db_wrapper.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id.in_(matched_entity_ids))
        .all()
    })

    if not matched_sources:
        return {
            "answer": "Found matching entities but no source documents.",
            "entities_matched": [e.name for e in matched_entities],
            "sources": [],
            "source_count": 0,
        }

    context_parts = []
    for src in matched_sources[:10]:
        try:
            chunk_data = project.vector.find_source(src)
            for doc_text in (chunk_data.get("documents") or [])[:5]:
                context_parts.append(f"[Source: {src}]\n{doc_text}")
        except Exception:
            pass

    if not context_parts:
        return {
            "answer": "No content could be retrieved for the matched entities.",
            "entities_matched": [e.name for e in matched_entities],
            "sources": matched_sources,
            "source_count": len(matched_sources),
        }

    context = "\n\n".join(context_parts)
    prompt = (
        "Answer the following question using ONLY the context below. "
        "If the context doesn't contain enough information, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    try:
        from llama_index.core.base.llms.types import ChatMessage, MessageRole
        llm_model = brain.get_llm(project.props.llm, db_wrapper)
        resp = llm_model.llm.chat([ChatMessage(role=MessageRole.USER, content=prompt)])
        answer = resp.message.content.strip() if resp.message and resp.message.content else ""
    except Exception as e:
        logging.exception(e)
        raise HTTPException(status_code=500, detail="LLM call failed")

    # Account the KG-query LLM call (it bypasses chat_main).
    try:
        from restai.tools import log_inference
        from restai.limits.accounting import count_usage
        in_tok, out_tok = count_usage(resp, prompt, answer)
        log_inference(project, user, {
            "question": question, "answer": answer,
            "tokens": {"input": in_tok, "output": out_tok}, "status": "success",
        }, db_wrapper)
    except Exception:
        logging.exception("kg_query accounting failed")

    return {
        "answer": answer,
        "entities_matched": [e.name for e in matched_entities],
        "sources": matched_sources,
        "source_count": len(matched_sources),
    }


@router.post("/projects/{projectID}/kg/rebuild", tags=["Knowledge Graph"])
async def kg_rebuild(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Re-extract entities for ALL sources in this project. Runs in background."""
    check_not_restricted(user)
    from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase, KGEntityRelationshipDatabase

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Only available for RAG projects.")

    db_wrapper.db.query(KGEntityRelationshipDatabase).filter(
        KGEntityRelationshipDatabase.project_id == projectID
    ).delete()
    db_wrapper.db.query(KGEntityMentionDatabase).filter(
        KGEntityMentionDatabase.project_id == projectID
    ).delete()
    db_wrapper.db.query(KGEntityDatabase).filter(KGEntityDatabase.project_id == projectID).delete()
    db_wrapper.db.commit()

    sources = project.vector.list() if project.vector is not None else []

    def _rebuild():
        from restai.integrations.knowledge_graph import extract_and_persist
        new_db = DBWrapper()
        try:
            for src in sources:
                try:
                    chunk_data = project.vector.find_source(src)
                    full_text = "\n".join(chunk_data.get("documents") or [])
                    if full_text:
                        extract_and_persist(projectID, src, full_text, request.app.state.brain, new_db)
                except Exception as e:
                    logging.warning("Rebuild failed for source %s: %s", src, e)
        finally:
            try:
                new_db.db.close()
            except Exception:
                pass

    background_tasks.add_task(_rebuild)
    return {"message": f"Rebuild scheduled for {len(sources)} sources", "source_count": len(sources)}

