import logging
from sqlalchemy import create_engine, func, or_
from restai import config
from datetime import datetime, timezone
from restai.models.databasemodels import (
    ApiKeyDatabase,
    LLMDatabase,
    EmbeddingDatabase,
    OutputDatabase,
    ProjectDatabase,
    ProjectToolDatabase,
    ProjectRoutineDatabase,
    CronLogDatabase,
    SettingDatabase,
    UserDatabase,
    TeamDatabase,
    TeamImageGeneratorDatabase,
    TeamAudioGeneratorDatabase,
    WidgetDatabase,
    ImageGeneratorDatabase,
    SpeechToTextDatabase,
    ProjectSecretDatabase,
)
from restai.models.models import (
    LLMModel,
    LLMUpdate,
    ProjectModelUpdate,
    User,
    UserUpdate,
    EmbeddingModel,
    EmbeddingUpdate,
    TeamModel,
    TeamModelUpdate,
    TeamModelCreate,
)
from sqlalchemy.orm import sessionmaker, Session
import bcrypt
from typing import Optional, List
from restai.config import MYSQL_HOST, MYSQL_URL, POSTGRES_HOST, POSTGRES_URL
import json
from restai.utils.crypto import decrypt_api_key, hash_api_key, verify_api_key_hash

import logging as _logging
_db_logger = _logging.getLogger(__name__)

if MYSQL_HOST:
    _db_logger.info("Using MySQL database.")
    engine = create_engine(
        MYSQL_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_recycle=config.DB_POOL_RECYCLE,
        # Test the connection liveness on each checkout. MySQL closes
        # idle connections after `wait_timeout` (default 8h) and the
        # client only finds out on the next query — pre-ping catches the
        # death and transparently reconnects, so the dreaded "MySQL has
        # gone away" never bubbles up to the user.
        pool_pre_ping=True,
        # LIFO checkout: hand back the most recently returned connection
        # `pool_recycle`. Net win whenever there's spare pool capacity.
        pool_use_lifo=True,
    )
elif POSTGRES_HOST:
    _db_logger.info("Using PostgreSQL database.")
    engine = create_engine(
        POSTGRES_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_recycle=config.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        pool_use_lifo=True,
    )
else:
    # SQLITE_PATH (env var, also exposed as config.SQLITE_PATH) lets K8s
    # deployments mount a PVC at a known path so the DB survives pod
    # restarts. Defaults to a CWD-relative file for the docker-run /
    # local-dev case.
    _sqlite_path = config.SQLITE_PATH or "./restai.db"
    _db_logger.info("Using sqlite database at %s.", _sqlite_path)
    engine = create_engine(
        f"sqlite:///{_sqlite_path}",
        connect_args={"check_same_thread": False},
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_POOL_RECYCLE,
        pool_recycle=config.DB_POOL_RECYCLE,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# hash_password / verify_password moved to restai.db.passwords; re-exported
# here so existing `from restai.database import verify_password` keeps working.
from restai.db.passwords import hash_password, verify_password

from restai.db.users import UserMixin
from restai.db.llms_embeddings import LLMEmbeddingMixin
from restai.db.widgets import WidgetMixin
from restai.db.project_secrets import ProjectSecretMixin
from restai.db.projects import ProjectMixin
from restai.db.teams import TeamMixin
from restai.db.project_tools_routines import ProjectToolRoutineMixin
from restai.db.settings import SettingMixin
from restai.db.runtime_activity import RuntimeActivityMixin
from restai.db.payments import PaymentMixin
from sqlalchemy.orm import Session


class DBWrapper(
    UserMixin,
    LLMEmbeddingMixin,
    WidgetMixin,
    ProjectSecretMixin,
    ProjectMixin,
    TeamMixin,
    ProjectToolRoutineMixin,
    SettingMixin,
    RuntimeActivityMixin,
    PaymentMixin,
):
    """Single entry point for all DB access. Composed from per-entity mixins
    (restai/db/*.py); every method shares the one Session in ``self.db``. The
    public surface is unchanged from the former monolithic class."""

    __slots__ = ("db",)

    def __init__(self):
        self.db: Session = SessionLocal()

    def close(self):
        self.db.close()


def get_db_wrapper():
    """FastAPI dependency: open a DB wrapper for one request and close
    it when the request is done. The previous version used `return`
    inside `try/finally`, which runs `finally` BEFORE the function
    returns to the caller — meaning the session was closed before any
    route ever saw it. SQLAlchemy was forgiving (closed sessions lazily
    grab a new connection), so it appeared to work but every request
    was thrashing the pool. Yielding makes FastAPI's `Depends()`
    treat this as a generator dep with proper lifecycle.

    Non-FastAPI callers (background tasks, telemetry, agent tools,
    crons, ...) must use `open_db_wrapper()` instead — calling a
    generator function from non-FastAPI code returns a generator
    object, not a wrapper.
    """
    wrapper: DBWrapper = DBWrapper()
    try:
        yield wrapper
    finally:
        wrapper.close()


def open_db_wrapper() -> DBWrapper:
    """Plain factory for non-FastAPI callers. Caller must close()."""
    return DBWrapper()
