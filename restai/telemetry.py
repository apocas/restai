"""Anonymized open-source telemetry for RESTai.

Collects aggregate, non-identifying usage statistics and sends them
to a central endpoint periodically. No PII, no content, no API keys.

Controlled by ANONYMIZED_TELEMETRY env var (default: true).
Opt out by setting ANONYMIZED_TELEMETRY=false.
"""

import asyncio
import logging
import platform
import sys
import time
import uuid

import httpx

from restai import config

logger = logging.getLogger(__name__)

TELEMETRY_ENDPOINT = "https://telemetry.restai.cloud/v1/report"
REPORT_INTERVAL_SECONDS = 86400  # 24 hours
STARTUP_DELAY_SECONDS = 60  # Wait for app to stabilize


def _get_or_create_instance_id(db_wrapper) -> str:
    """Get or generate a persistent anonymous instance ID."""
    setting = db_wrapper.get_setting("telemetry_instance_id")
    if setting and setting.value:
        return setting.value
    instance_id = uuid.uuid4().hex
    db_wrapper.upsert_setting("telemetry_instance_id", instance_id)
    return instance_id


def _get_database_type() -> str:
    if getattr(config, "POSTGRES_HOST", None):
        return "postgresql"
    if getattr(config, "MYSQL_HOST", None):
        return "mysql"
    return "sqlite"


def collect_telemetry(db_wrapper) -> dict:
    """Collect anonymized telemetry payload from the database."""
    from restai.models.databasemodels import ProjectDatabase, OutputDatabase
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    instance_id = _get_or_create_instance_id(db_wrapper)

    # Project counts by type
    projects = db_wrapper.db.query(ProjectDatabase).all()
    project_counts = {"projects": len(projects)}
    for ptype in ("rag", "agent", "block"):
        project_counts[f"projects_{ptype}"] = sum(1 for p in projects if p.type == ptype)

    # Basic counts
    user_count = len(db_wrapper.get_users())
    team_count = len(db_wrapper.get_teams())
    llms = db_wrapper.get_llms()
    embeddings = db_wrapper.get_embeddings()

    # LLM/embedding class names (not model names or API keys)
    llm_classes = sorted(set(l.class_name for l in llms if l.class_name))
    embedding_classes = sorted(set(e.class_name for e in embeddings if e.class_name))

    # Vectorstore types in use
    vectorstores = sorted(set(p.vectorstore for p in projects if p.vectorstore))

    # Inference count in last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    inference_count = db_wrapper.db.query(func.count(OutputDatabase.id)).filter(
        OutputDatabase.date >= cutoff
    ).scalar() or 0

    # Daily active users (distinct users with inferences in last 24h)
    dau = db_wrapper.db.query(func.count(func.distinct(OutputDatabase.user_id))).filter(
        OutputDatabase.date >= cutoff
    ).scalar() or 0

    # Feature flags
    features = {
        "gpu": bool(getattr(config, "RESTAI_GPU", False)),
        "docker": bool(getattr(config, "DOCKER_ENABLED", False)),
        "mcp_server": bool(getattr(config, "MCP_SERVER", False)),
        "redis": bool(getattr(config, "REDIS_HOST", "")),
        "sso_google": bool(getattr(config, "GOOGLE_CLIENT_ID", "")),
        "sso_microsoft": bool(getattr(config, "MICROSOFT_CLIENT_ID", "")),
        "sso_github": bool(getattr(config, "GITHUB_CLIENT_ID", "")),
        "ldap": bool(getattr(config, "LDAP_HOST", "")),
        "enforce_2fa": str(getattr(config, "ENFORCE_2FA", "false")).lower() == "true",
    }

    from restai.utils.version import get_version_from_pyproject

    return {
        "instance_id": instance_id,
        "version": get_version_from_pyproject(),
        "python_version": platform.python_version(),
        "os": sys.platform,
        "counts": {
            **project_counts,
            "users": user_count,
            "teams": team_count,
            "llms": len(llms),
            "embeddings": len(embeddings),
        },
        "features": features,
        "llm_classes": llm_classes,
        "embedding_classes": embedding_classes,
        "vectorstores": vectorstores,
        "database": _get_database_type(),
        "inference_count_24h": inference_count,
        "daily_active_users_24h": dau,
    }


async def send_telemetry(payload: dict) -> bool:
    """Send telemetry payload to central endpoint. Fire-and-forget."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(TELEMETRY_ENDPOINT, json=payload)
            return resp.status_code == 200
    except Exception:
        return False


async def telemetry_loop():
    """Background loop: collect and send telemetry every 24 hours."""
    from restai.database import get_db_wrapper

    await asyncio.sleep(STARTUP_DELAY_SECONDS)

    while True:
        try:
            db_wrapper = get_db_wrapper()
            payload = collect_telemetry(db_wrapper)
            await send_telemetry(payload)
            db_wrapper.db.close()
        except Exception:
            logger.debug("Telemetry collection failed", exc_info=True)

        await asyncio.sleep(REPORT_INTERVAL_SECONDS)
