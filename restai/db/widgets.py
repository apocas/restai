"""DBWrapper widget methods (mixin).

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


class WidgetMixin:
    __slots__ = ()

    def create_widget(self, project_id, creator_id, encrypted_key, key_hash, key_prefix, name, config_json, allowed_domains_json):
        now = datetime.now(timezone.utc)
        widget = WidgetDatabase(
            project_id=project_id,
            creator_id=creator_id,
            encrypted_key=encrypted_key,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            config=config_json,
            allowed_domains=allowed_domains_json,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(widget)
        self.db.commit()
        self.db.refresh(widget)
        return widget

    def get_widget_by_id(self, widget_id):
        return self.db.query(WidgetDatabase).filter(WidgetDatabase.id == widget_id).first()

    def get_widget_by_key_hash(self, key_hash):
        return self.db.query(WidgetDatabase).filter(WidgetDatabase.key_hash == key_hash).first()

    def get_widget_by_key(self, plaintext_key):
        prefix = plaintext_key[:11]
        candidates = self.db.query(WidgetDatabase).filter(WidgetDatabase.key_prefix == prefix).all()
        for w in candidates:
            if verify_api_key_hash(plaintext_key, w.key_hash):
                return w
        return None

    def get_widgets_for_project(self, project_id):
        return (
            self.db.query(WidgetDatabase)
            .filter(WidgetDatabase.project_id == project_id)
            .order_by(WidgetDatabase.created_at.desc())
            .all()
        )

    def delete_widget(self, widget):
        self.db.delete(widget)
        self.db.commit()
        return True
