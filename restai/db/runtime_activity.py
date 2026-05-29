"""DBWrapper cron-log + docker/browser activity methods (mixin).

Split out of the former monolithic restai/database.py. Each method still uses
`self.db` (the shared Session); the concrete `DBWrapper` in restai/database.py
composes these mixins, so the public API is unchanged.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import func, or_

from restai.models.databasemodels import (
    ApiKeyDatabase, LLMDatabase, EmbeddingDatabase, OutputDatabase, ProjectDatabase,
    ProjectToolDatabase, ProjectRoutineDatabase, CronLogDatabase, SettingDatabase,
    UserDatabase, TeamDatabase, TeamImageGeneratorDatabase, TeamAudioGeneratorDatabase,
    WidgetDatabase, ImageGeneratorDatabase, SpeechToTextDatabase, ProjectSecretDatabase,
)
from restai.models.models import (
    LLMModel, LLMUpdate, ProjectModelUpdate, User, UserUpdate, EmbeddingModel,
    EmbeddingUpdate, TeamModel, TeamModelUpdate, TeamModelCreate,
)
from restai.utils.crypto import decrypt_api_key, hash_api_key, verify_api_key_hash
from restai.db.passwords import hash_password, verify_password


class RuntimeActivityMixin:
    __slots__ = ()

    def create_cron_log(self, job, status, message, details=None, items_processed=0, duration_ms=None):
        from datetime import datetime, timezone
        entry = CronLogDatabase(
            job=job,
            status=status,
            message=message,
            details=details,
            items_processed=items_processed,
            duration_ms=duration_ms,
            date=datetime.now(timezone.utc),
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def get_cron_logs(self, job=None, status=None, start=0, end=50):
        query = self.db.query(CronLogDatabase).order_by(CronLogDatabase.date.desc())
        if job:
            query = query.filter(CronLogDatabase.job == job)
        if status:
            query = query.filter(CronLogDatabase.status == status)
        return query.offset(start).limit(end - start).all()

    def upsert_docker_activity(self, chat_id: str, container_id: str | None = None) -> None:
        """Bump `last_activity` for a chat's Docker container. Called on
        every `DockerManager.exec_command`. Multi-server safe — the
        cleanup cron reads from this table instead of in-memory state."""
        from datetime import datetime, timezone
        from restai.models.databasemodels import DockerChatActivityDatabase
        if not chat_id:
            return
        now = datetime.now(timezone.utc)
        row = (
            self.db.query(DockerChatActivityDatabase)
            .filter(DockerChatActivityDatabase.chat_id == chat_id)
            .first()
        )
        if row is None:
            row = DockerChatActivityDatabase(
                chat_id=chat_id,
                last_activity=now,
                container_id=container_id,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.last_activity = now
            if container_id:
                row.container_id = container_id
            row.updated_at = now
        self.db.commit()

    def delete_docker_activity(self, chat_id: str) -> None:
        from restai.models.databasemodels import DockerChatActivityDatabase
        if not chat_id:
            return
        (
            self.db.query(DockerChatActivityDatabase)
            .filter(DockerChatActivityDatabase.chat_id == chat_id)
            .delete()
        )
        self.db.commit()

    def get_docker_activity(self, chat_id: str):
        from restai.models.databasemodels import DockerChatActivityDatabase
        if not chat_id:
            return None
        return (
            self.db.query(DockerChatActivityDatabase)
            .filter(DockerChatActivityDatabase.chat_id == chat_id)
            .first()
        )

    def upsert_browser_activity(self, chat_id: str, container_id: str | None = None) -> None:
        """Bump `last_activity` for a chat's browser container. Called
        on every `browser.runtime.call()`. Cleanup cron reads from this
        table so eviction reflects real idle time, not container age."""
        from datetime import datetime, timezone
        from restai.models.databasemodels import BrowserChatActivityDatabase
        if not chat_id:
            return
        now = datetime.now(timezone.utc)
        row = (
            self.db.query(BrowserChatActivityDatabase)
            .filter(BrowserChatActivityDatabase.chat_id == chat_id)
            .first()
        )
        if row is None:
            row = BrowserChatActivityDatabase(
                chat_id=chat_id,
                last_activity=now,
                container_id=container_id,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.last_activity = now
            if container_id:
                row.container_id = container_id
            row.updated_at = now
        self.db.commit()

    def delete_browser_activity(self, chat_id: str) -> None:
        from restai.models.databasemodels import BrowserChatActivityDatabase
        if not chat_id:
            return
        (
            self.db.query(BrowserChatActivityDatabase)
            .filter(BrowserChatActivityDatabase.chat_id == chat_id)
            .delete()
        )
        self.db.commit()
