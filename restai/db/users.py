"""DBWrapper user + API-key methods (mixin).

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


class UserMixin:
    __slots__ = ()

    def create_user(
        self,
        username: str,
        password: Optional[str],
        admin: bool = False,
        private: bool = False,
        restricted: bool = False,
    ) -> UserDatabase:
        from datetime import datetime, timezone
        password_hash: Optional[str]
        if password:
            password_hash = hash_password(password)
            password_updated_at = datetime.now(timezone.utc)
        else:
            password_hash = None
            password_updated_at = None
        db_user: UserDatabase = UserDatabase(
            username=username,
            hashed_password=password_hash,
            password_updated_at=password_updated_at,
            is_admin=admin,
            is_private=private,
            is_restricted=restricted,
            options='{"credit": -1.0}',
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def get_users(self) -> list[UserDatabase]:
        users: list[UserDatabase] = self.db.query(UserDatabase).all()
        return users

    def get_user_by_apikey(self, apikey: str):
        """Returns (UserDatabase, ApiKeyDatabase) or (UserDatabase, None) for legacy, or (None, None)."""
        # Lookup by key_prefix, then verify the salted hash
        prefix = apikey[:8]
        candidates = (
            self.db.query(ApiKeyDatabase)
            .filter(ApiKeyDatabase.key_prefix == prefix)
            .all()
        )
        for api_key_row in candidates:
            if verify_api_key_hash(apikey, api_key_row.key_hash):
                return api_key_row.user, api_key_row
        # Fallback: check legacy api_key column for migration period
        for user in self.db.query(UserDatabase).filter(UserDatabase.api_key.isnot(None)):
            try:
                if decrypt_api_key(user.api_key) == apikey:
                    return user, None
            except Exception:
                continue
        return None, None

    def get_user_by_username(self, username: str) -> Optional[UserDatabase]:
        user: Optional[UserDatabase] = (
            self.db.query(UserDatabase)
            .filter(UserDatabase.username == username)
            .first()
        )
        return user

    def get_user_by_id(self, user_id: int) -> Optional[UserDatabase]:
        user: Optional[UserDatabase] = (
            self.db.query(UserDatabase).filter(UserDatabase.id == user_id).first()
        )
        return user

    def update_user(self, user: User, user_update: UserUpdate) -> bool:
        if user_update.password is not None:
            from datetime import datetime, timezone
            user.hashed_password = hash_password(user_update.password)
            user.password_updated_at = datetime.now(timezone.utc)

        if user_update.is_admin is not None:
            user.is_admin = user_update.is_admin

        if user_update.is_private is not None:
            user.is_private = user_update.is_private

        if user_update.is_restricted is not None:
            user.is_restricted = user_update.is_restricted

        if hasattr(user_update, "options") and user_update.options is not None:
            try:
                current_options = json.loads(user.options) if user.options else {}
                new_options = user_update.options.model_dump()
                if current_options != new_options:
                    user.options = json.dumps(new_options)
            except json.JSONDecodeError:
                user.options = json.dumps(user_update.options.model_dump())

        self.db.commit()
        return True

    def delete_user(self, user: UserDatabase) -> bool:
        self.db.delete(user)
        self.db.commit()
        return True

    def create_api_key(self, user_id: int, encrypted_key: str, key_hash: str, key_prefix: str, description: str, allowed_projects: str = None, read_only: bool = False) -> ApiKeyDatabase:
        api_key = ApiKeyDatabase(
            user_id=user_id,
            encrypted_key=encrypted_key,
            key_hash=key_hash,
            key_prefix=key_prefix,
            description=description,
            created_at=datetime.now(timezone.utc),
            allowed_projects=allowed_projects,
            read_only=read_only,
        )
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)
        return api_key

    def get_api_keys_for_user(self, user_id: int) -> list[ApiKeyDatabase]:
        return (
            self.db.query(ApiKeyDatabase)
            .filter(ApiKeyDatabase.user_id == user_id)
            .order_by(ApiKeyDatabase.created_at.desc())
            .all()
        )

    def delete_api_key(self, api_key_id: int, user_id: int) -> bool:
        api_key = (
            self.db.query(ApiKeyDatabase)
            .filter(ApiKeyDatabase.id == api_key_id, ApiKeyDatabase.user_id == user_id)
            .first()
        )
        if api_key is None:
            return False
        self.db.delete(api_key)
        self.db.commit()
        return True
