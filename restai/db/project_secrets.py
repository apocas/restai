"""DBWrapper project-secret methods (mixin).

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


class ProjectSecretMixin:
    __slots__ = ()

    def get_project_secrets(self, project_id: int) -> list[ProjectSecretDatabase]:
        return (
            self.db.query(ProjectSecretDatabase)
            .filter(ProjectSecretDatabase.project_id == project_id)
            .order_by(ProjectSecretDatabase.name)
            .all()
        )

    def get_project_secret_by_id(self, secret_id: int) -> Optional[ProjectSecretDatabase]:
        return self.db.query(ProjectSecretDatabase).filter(ProjectSecretDatabase.id == secret_id).first()

    def get_project_secret_by_name(self, project_id: int, name: str) -> Optional[ProjectSecretDatabase]:
        return (
            self.db.query(ProjectSecretDatabase)
            .filter(ProjectSecretDatabase.project_id == project_id, ProjectSecretDatabase.name == name)
            .first()
        )

    def create_project_secret(
        self,
        project_id: int,
        name: str,
        value: str,
        description: Optional[str] = None,
    ) -> ProjectSecretDatabase:
        from restai.utils.crypto import encrypt_field
        now = datetime.now(timezone.utc)
        row = ProjectSecretDatabase(
            project_id=project_id,
            name=name,
            value=encrypt_field(value),
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def edit_project_secret(self, secret: ProjectSecretDatabase, update) -> bool:
        """Patch a project secret. Value `"********"` preserves the
        existing stored value (same mask-round-trip as LLMs)."""
        from restai.utils.crypto import encrypt_field

        changed = False
        if update.value is not None and update.value != "********":
            secret.value = encrypt_field(update.value)
            changed = True
        if update.description is not None and secret.description != update.description:
            secret.description = update.description
            changed = True
        if changed:
            secret.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return changed

    def delete_project_secret(self, secret: ProjectSecretDatabase) -> bool:
        self.db.delete(secret)
        self.db.commit()
        return True

    @staticmethod
    def _decrypt_secret_row(row) -> Optional[str]:
        if row is None or not row.value:
            return None
        from restai.utils.crypto import decrypt_field
        try:
            return decrypt_field(row.value)
        except Exception:
            return None

    def resolve_project_secret(self, project_id: int, name: str) -> Optional[str]:
        """Server-side plaintext resolution — only called from inside a tool
        (e.g. `browser_fill`). Returns None when the secret doesn't exist.
        The plaintext never crosses back into LLM context because callers
        pass it directly to the micro-server, not back to the agent."""
        return self._decrypt_secret_row(self.get_project_secret_by_name(project_id, name))

    def resolve_all_project_secrets(self, project_id: int) -> dict[str, str]:
        """All decrypted project secrets, ``{name: plaintext}``. Same
        plaintext-never-leaks-to-LLM-context guarantee as
        `resolve_project_secret` — values go straight to the kernel
        via Docker's exec env."""
        out: dict[str, str] = {}
        for row in self.get_project_secrets(project_id):
            if not row.name:
                continue
            plaintext = self._decrypt_secret_row(row)
            if plaintext is not None:
                out[row.name] = plaintext
        return out
