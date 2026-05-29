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

@router.get("/projects/{projectID}/guards/summary", tags=["Guards"])
async def get_guard_summary(
    projectID: int = PathParam(description="Project ID"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get guard event summary statistics for a project."""
    from restai.models.databasemodels import GuardEventDatabase

    total = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID
    ).scalar() or 0

    blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action == "block",
    ).scalar() or 0

    warns = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action == "warn",
    ).scalar() or 0

    input_blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action.in_(["block", "warn"]),
        GuardEventDatabase.phase == "input",
    ).scalar() or 0

    output_blocks = db_wrapper.db.query(func.count(GuardEventDatabase.id)).filter(
        GuardEventDatabase.project_id == projectID,
        GuardEventDatabase.action.in_(["block", "warn"]),
        GuardEventDatabase.phase == "output",
    ).scalar() or 0

    return {
        "total_checks": total,
        "total_blocks": blocks,
        "block_rate": round(blocks / total, 4) if total > 0 else 0,
        "input_blocks": input_blocks,
        "output_blocks": output_blocks,
        "warn_count": warns,
    }


@router.get("/projects/{projectID}/guards/daily", tags=["Guards"])
async def get_guard_daily(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year"),
    month: int = Query(None, ge=1, le=12, description="Month"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get daily guard event counts for charting."""
    import datetime as dt
    import calendar
    from restai.models.databasemodels import GuardEventDatabase

    now = dt.datetime.now(dt.timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    start_date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    end_date = dt.datetime(year, month, last_day, 23, 59, 59, tzinfo=dt.timezone.utc)

    rows = (
        db_wrapper.db.query(
            func.date(GuardEventDatabase.date).label("date"),
            func.count(GuardEventDatabase.id).label("checks"),
            func.sum(case((GuardEventDatabase.action == "block", 1), else_=0)).label("blocks"),
            func.sum(case((GuardEventDatabase.action == "warn", 1), else_=0)).label("warns"),
        )
        .filter(
            GuardEventDatabase.project_id == projectID,
            GuardEventDatabase.date >= start_date,
            GuardEventDatabase.date <= end_date,
        )
        .group_by(func.date(GuardEventDatabase.date))
        .all()
    )

    return {
        "events": [
            {
                "date": r.date,
                "checks": r.checks,
                "blocks": r.blocks or 0,
                "warns": r.warns or 0,
            }
            for r in rows
        ]
    }


@router.get("/projects/{projectID}/guards/events", tags=["Guards"])
async def get_guard_events(
    projectID: int = PathParam(description="Project ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start"),
    end: int = Query(20, ge=1, le=100000, description="Pagination end"),
    phase: str = Query(None, description="Filter by phase: input/output"),
    action: str = Query(None, description="Filter by action: block/pass/warn"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get paginated guard events for a project."""
    from restai.models.databasemodels import GuardEventDatabase
    from restai.models.models import GuardEventResponse

    query = db_wrapper.db.query(GuardEventDatabase).filter(
        GuardEventDatabase.project_id == projectID
    )
    if phase:
        query = query.filter(GuardEventDatabase.phase == phase)
    if action:
        query = query.filter(GuardEventDatabase.action == action)

    total = query.count()
    events = query.order_by(GuardEventDatabase.date.desc()).offset(start).limit(end - start).all()

    return {
        "events": [GuardEventResponse.model_validate(e) for e in events],
        "total": total,
    }


@router.get("/projects/{projectID}/analytics/sources", tags=["Statistics"])
async def get_source_analytics(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get per-source retrieval analytics for a RAG project."""
    import datetime as dt
    from restai.models.databasemodels import RetrievalEventDatabase

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Source analytics only available for RAG projects")

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    rows = (
        db_wrapper.db.query(
            RetrievalEventDatabase.source,
            func.count(RetrievalEventDatabase.id).label("retrievals"),
            func.avg(RetrievalEventDatabase.score).label("avg_score"),
        )
        .filter(
            RetrievalEventDatabase.project_id == projectID,
            RetrievalEventDatabase.date >= since,
        )
        .group_by(RetrievalEventDatabase.source)
        .order_by(func.count(RetrievalEventDatabase.id).desc())
        .all()
    )

    sources = [
        {
            "source": r.source,
            "retrievals": r.retrievals,
            "avg_score": round(r.avg_score, 3) if r.avg_score else 0,
        }
        for r in rows
    ]

    retrieved_sources = {r.source for r in rows}
    all_sources = set()
    if project.vector:
        try:
            all_sources = set(project.vector.list())
        except Exception:
            pass

    never_retrieved = sorted(all_sources - retrieved_sources)

    return {
        "sources": sources,
        "never_retrieved": never_retrieved,
    }


def _nearest_chunk_size(token_count: int) -> int:
    """Snap a token count to the nearest standard chunk size."""
    standard_sizes = [64, 128, 256, 512, 1024, 2048]
    return min(standard_sizes, key=lambda s: abs(s - token_count))


@router.get("/projects/{projectID}/analytics/chunking", tags=["Statistics"])
async def get_chunking_analytics(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Analyze chunk size distributions and retrieval patterns to recommend optimal chunk sizes."""
    import datetime as dt
    from restai.models.databasemodels import RetrievalEventDatabase
    from restai.tools import tokens_from_string

    project = get_project(projectID, db_wrapper, request.app.state.brain)
    if project.props.type != "rag":
        raise HTTPException(status_code=400, detail="Chunking analytics only available for RAG projects")

    MAX_CHUNKS = 50000
    truncated = False

    all_chunks = []
    if project.vector:
        try:
            all_chunks = project.vector.list_all_chunks(limit=MAX_CHUNKS)
            if len(all_chunks) >= MAX_CHUNKS:
                truncated = True
        except Exception:
            pass

    chunk_token_lengths = []
    for chunk in all_chunks:
        text = chunk.get("text", "")
        if text:
            try:
                tl = tokens_from_string(text)
            except Exception:
                tl = len(text) // 4
            chunk_token_lengths.append(tl)

    buckets = [0, 64, 128, 256, 512, 1024, 2048]
    bucket_labels = []
    bucket_counts = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        label = f"{low}-{high}"
        count = sum(1 for tl in chunk_token_lengths if low <= tl < high)
        bucket_labels.append(label)
        bucket_counts.append(count)
    overflow = sum(1 for tl in chunk_token_lengths if tl >= buckets[-1])
    if overflow or not bucket_labels:
        bucket_labels.append(f"{buckets[-1]}+")
        bucket_counts.append(overflow)

    total_chunks_count = len(chunk_token_lengths)
    avg_chunk_tokens = round(sum(chunk_token_lengths) / max(total_chunks_count, 1))
    sorted_lengths = sorted(chunk_token_lengths)
    median_chunk_tokens = sorted_lengths[total_chunks_count // 2] if sorted_lengths else 0

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    retrieval_rows = (
        db_wrapper.db.query(
            RetrievalEventDatabase.chunk_id,
            RetrievalEventDatabase.chunk_token_length,
            RetrievalEventDatabase.score,
        )
        .filter(
            RetrievalEventDatabase.project_id == projectID,
            RetrievalEventDatabase.date >= since,
        )
        .all()
    )

    retrieved_chunk_ids = set()
    retrieved_token_lengths = []
    retrieved_scores = []
    for row in retrieval_rows:
        if row.chunk_id:
            retrieved_chunk_ids.add(row.chunk_id)
        if row.chunk_token_length:
            retrieved_token_lengths.append(row.chunk_token_length)
        if row.score is not None:
            retrieved_scores.append(row.score)

    ret_bucket_counts = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        count = sum(1 for tl in retrieved_token_lengths if low <= tl < high)
        ret_bucket_counts.append(count)
    ret_bucket_counts.append(sum(1 for tl in retrieved_token_lengths if tl >= buckets[-1]))

    avg_retrieved_tokens = round(sum(retrieved_token_lengths) / max(len(retrieved_token_lengths), 1)) if retrieved_token_lengths else None
    avg_score = round(sum(retrieved_scores) / max(len(retrieved_scores), 1), 3) if retrieved_scores else None

    score_by_bucket = []
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        scores_in_bucket = [
            row.score for row in retrieval_rows
            if row.chunk_token_length and low <= row.chunk_token_length < high and row.score is not None
        ]
        score_by_bucket.append({
            "bucket": f"{low}-{high}",
            "avg_score": round(sum(scores_in_bucket) / len(scores_in_bucket), 3) if scores_in_bucket else None,
            "count": len(scores_in_bucket),
        })

    all_chunk_ids = {c["id"] for c in all_chunks}
    never_retrieved_chunks = len(all_chunk_ids - retrieved_chunk_ids) if all_chunk_ids else 0
    retrieval_rate = round(len(retrieved_chunk_ids) / max(len(all_chunk_ids), 1), 3) if all_chunk_ids else 0

    recommendations = []

    if avg_retrieved_tokens and avg_chunk_tokens:
        ratio = avg_retrieved_tokens / avg_chunk_tokens
        if ratio < 0.7:
            suggested = _nearest_chunk_size(avg_retrieved_tokens)
            recommendations.append({
                "type": "reduce_chunk_size",
                "severity": "high" if ratio < 0.5 else "medium",
                "message": (
                    f"Your average chunk is {avg_chunk_tokens} tokens, but retrieved chunks "
                    f"average {avg_retrieved_tokens} tokens. Consider using {suggested}-token chunks "
                    f"for better precision."
                ),
                "suggested_chunk_size": suggested,
            })
        elif ratio > 1.3:
            suggested = _nearest_chunk_size(avg_retrieved_tokens)
            recommendations.append({
                "type": "increase_chunk_size",
                "severity": "medium",
                "message": (
                    f"Retrieved chunks average {avg_retrieved_tokens} tokens, larger than your "
                    f"typical chunk of {avg_chunk_tokens} tokens. Consider increasing to "
                    f"{suggested} tokens for more context per retrieval."
                ),
                "suggested_chunk_size": suggested,
            })

    if retrieval_rate < 0.3 and total_chunks_count > 10:
        recommendations.append({
            "type": "low_retrieval_rate",
            "severity": "medium",
            "message": (
                f"Only {round(retrieval_rate * 100)}% of chunks have been retrieved in the last "
                f"{days} days. Many chunks may be redundant or poorly sized."
            ),
        })

    best_bucket = max(
        (b for b in score_by_bucket if b["avg_score"] is not None and b["count"] >= 3),
        key=lambda b: b["avg_score"],
        default=None,
    )
    if best_bucket:
        recommendations.append({
            "type": "best_scoring_range",
            "severity": "info",
            "message": (
                f"Chunks in the {best_bucket['bucket']} token range have the highest average "
                f"retrieval score ({best_bucket['avg_score']}). Consider targeting this range."
            ),
        })

    return {
        "total_chunks": total_chunks_count,
        "truncated": truncated,
        "avg_chunk_tokens": avg_chunk_tokens,
        "median_chunk_tokens": median_chunk_tokens,
        "size_distribution": {
            "buckets": bucket_labels,
            "counts": bucket_counts,
        },
        "retrieval_analysis": {
            "total_retrievals": len(retrieval_rows),
            "unique_chunks_retrieved": len(retrieved_chunk_ids),
            "retrieval_rate": retrieval_rate,
            "never_retrieved_chunks": never_retrieved_chunks,
            "avg_retrieved_tokens": avg_retrieved_tokens,
            "avg_score": avg_score,
            "size_distribution": {
                "buckets": bucket_labels,
                "counts": ret_bucket_counts,
            },
            "score_by_size": score_by_bucket,
        },
        "recommendations": recommendations,
        "days": days,
    }


@router.get("/projects/{projectID}/analytics/conversations", tags=["Statistics"])
async def get_conversation_analytics(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year"),
    month: int = Query(None, ge=1, le=12, description="Month"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get conversation analytics for a project."""
    import datetime as dt
    import calendar
    from restai.models.databasemodels import UserDatabase

    now = dt.datetime.now(dt.timezone.utc)
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    start_date = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
    last_day = calendar.monthrange(year, month)[1]
    end_date = dt.datetime(year, month, last_day, 23, 59, 59, tzinfo=dt.timezone.utc)

    base_filter = [
        OutputDatabase.project_id == projectID,
        OutputDatabase.date >= start_date,
        OutputDatabase.date <= end_date,
    ]

    total_messages = db_wrapper.db.query(func.count(OutputDatabase.id)).filter(*base_filter).scalar() or 0
    total_conversations = db_wrapper.db.query(func.count(func.distinct(OutputDatabase.chat_id))).filter(
        *base_filter, OutputDatabase.chat_id.isnot(None)
    ).scalar() or 0
    avg_latency = db_wrapper.db.query(func.avg(OutputDatabase.latency_ms)).filter(*base_filter).scalar()
    total_tokens = db_wrapper.db.query(
        func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens)
    ).filter(*base_filter).scalar() or 0
    total_cost = db_wrapper.db.query(
        func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost)
    ).filter(*base_filter).scalar() or 0

    summary = {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "avg_messages_per_conversation": round(total_messages / total_conversations, 1) if total_conversations > 0 else 0,
        "avg_latency_ms": round(avg_latency) if avg_latency else 0,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
    }

    daily_rows = (
        db_wrapper.db.query(
            func.date(OutputDatabase.date).label("date"),
            func.count(func.distinct(OutputDatabase.chat_id)).label("conversations"),
            func.count(OutputDatabase.id).label("messages"),
        )
        .filter(*base_filter)
        .group_by(func.date(OutputDatabase.date))
        .order_by(func.date(OutputDatabase.date))
        .all()
    )
    daily = [{"date": r.date, "conversations": r.conversations, "messages": r.messages} for r in daily_rows]

    hourly_rows = (
        db_wrapper.db.query(
            func.extract("hour", OutputDatabase.date).label("hour"),
            func.count(OutputDatabase.id).label("messages"),
        )
        .filter(*base_filter)
        .group_by(func.extract("hour", OutputDatabase.date))
        .order_by(func.extract("hour", OutputDatabase.date))
        .all()
    )
    hourly_map = {int(r.hour): r.messages for r in hourly_rows}
    hourly = [{"hour": h, "messages": hourly_map.get(h, 0)} for h in range(24)]

    top_user_rows = (
        db_wrapper.db.query(
            OutputDatabase.user_id,
            UserDatabase.username,
            func.count(OutputDatabase.id).label("messages"),
        )
        .join(UserDatabase, OutputDatabase.user_id == UserDatabase.id)
        .filter(*base_filter)
        .group_by(OutputDatabase.user_id, UserDatabase.username)
        .order_by(func.count(OutputDatabase.id).desc())
        .limit(10)
        .all()
    )
    top_users = [{"user_id": r.user_id, "username": r.username, "messages": r.messages} for r in top_user_rows]

    status_rows = (
        db_wrapper.db.query(
            OutputDatabase.status,
            func.count(OutputDatabase.id).label("count"),
        )
        .filter(*base_filter)
        .group_by(OutputDatabase.status)
        .all()
    )
    status_breakdown = [{"status": (r.status or "success"), "count": r.count} for r in status_rows]

    LATENCY_BUCKETS = [
        ("0-100ms", 0, 100),
        ("100-500ms", 100, 500),
        ("500ms-2s", 500, 2000),
        ("2-10s", 2000, 10000),
        ("10s+", 10000, None),
    ]
    latency_buckets = []
    for label, lo, hi in LATENCY_BUCKETS:
        q = db_wrapper.db.query(func.count(OutputDatabase.id)).filter(
            *base_filter,
            OutputDatabase.latency_ms.isnot(None),
            OutputDatabase.latency_ms >= lo,
        )
        if hi is not None:
            q = q.filter(OutputDatabase.latency_ms < hi)
        latency_buckets.append({"bucket": label, "count": q.scalar() or 0})

    llm_rows = (
        db_wrapper.db.query(
            OutputDatabase.llm,
            func.count(OutputDatabase.id).label("messages"),
            func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("tokens"),
            func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("cost"),
        )
        .filter(*base_filter, OutputDatabase.llm.isnot(None))
        .group_by(OutputDatabase.llm)
        .order_by(func.count(OutputDatabase.id).desc())
        .all()
    )
    llm_breakdown = [
        {
            "llm": r.llm,
            "messages": r.messages,
            "tokens": int(r.tokens or 0),
            "cost": round(float(r.cost or 0), 4),
        }
        for r in llm_rows
    ]

    return {
        "summary": summary,
        "daily": daily,
        "hourly": hourly,
        "top_users": top_users,
        "status_breakdown": status_breakdown,
        "latency_buckets": latency_buckets,
        "llm_breakdown": llm_breakdown,
    }


@router.get("/projects/{projectID}/logs", tags=["Statistics"])
async def get_token_consumption(
    projectID: int = PathParam(description="Project ID"),
    start: int = Query(0, ge=0, le=100000, description="Pagination start offset"),
    end: int = Query(10, ge=1, le=100000, description="Pagination end offset"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get inference logs for a project."""
    try:
        project = db_wrapper.get_project_by_id(projectID)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        logs = (
            db_wrapper.db.query(OutputDatabase)
            .filter_by(project_id=project.id)
            .order_by(OutputDatabase.date.desc())
            .offset(start)
            .limit(end - start)
            .all()
        )
        return {"logs": logs}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


_REPLAY_MAX_TURNS = 500


@router.get("/projects/{projectID}/logs/conversation/{chat_id}", tags=["Statistics"])
async def get_conversation_replay(
    projectID: int = PathParam(description="Project ID"),
    chat_id: str = PathParam(description="Chat session id"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Return every OutputDatabase row for a chat_id (capped at 500 turns)."""
    try:
        validate_safe_name(chat_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    try:
        project = db_wrapper.get_project_by_id(projectID)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        rows = (
            db_wrapper.db.query(OutputDatabase)
            .filter(
                OutputDatabase.project_id == project.id,
                OutputDatabase.chat_id == chat_id,
            )
            .order_by(OutputDatabase.date.asc())
            .limit(_REPLAY_MAX_TURNS + 1)
            .all()
        )
        truncated = len(rows) > _REPLAY_MAX_TURNS
        if truncated:
            rows = rows[:_REPLAY_MAX_TURNS]
        return {"turns": rows, "truncated": truncated, "chat_id": chat_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/projects/{projectID}/tokens/daily", tags=["Statistics"])
async def get_monthly_token_consumption(
    projectID: int = PathParam(description="Project ID"),
    year: int = Query(None, ge=2000, le=2100, description="Year for the report (defaults to current year)"),
    month: int = Query(None, ge=1, le=12, description="Month for the report (defaults to current month)"),
    _: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get daily token consumption for a project."""
    try:
        project = db_wrapper.get_project_by_id(projectID)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        now = datetime.datetime.now(datetime.timezone.utc)
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        start_date = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime.datetime(
            year, month, last_day, 23, 59, 59, tzinfo=datetime.timezone.utc
        )

        token_consumptions = (
            db_wrapper.db.query(
                func.date(OutputDatabase.date).label("date"),
                func.sum(OutputDatabase.input_tokens).label("input_tokens"),
                func.sum(OutputDatabase.output_tokens).label("output_tokens"),
                func.sum(OutputDatabase.input_cost).label("input_cost"),
                func.sum(OutputDatabase.output_cost).label("output_cost"),
                func.avg(OutputDatabase.latency_ms).label("avg_latency_ms"),
            )
            .filter(
                OutputDatabase.project_id == project.id,
                OutputDatabase.date >= start_date,
                OutputDatabase.date <= end_date,
            )
            .group_by(func.date(OutputDatabase.date))
            .all()
        )

        return {
            "tokens": [
                {
                    "date": tc.date,
                    "input_tokens": tc.input_tokens,
                    "output_tokens": tc.output_tokens,
                    "input_cost": tc.input_cost,
                    "output_cost": tc.output_cost,
                    "avg_latency_ms": round(tc.avg_latency_ms) if tc.avg_latency_ms else 0,
                }
                for tc in token_consumptions
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
