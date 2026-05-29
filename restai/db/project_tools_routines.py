"""DBWrapper project tool + routine methods (mixin).

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


class ProjectToolRoutineMixin:
    __slots__ = ()

    def get_project_tools(self, project_id: int) -> list[ProjectToolDatabase]:
        return (
            self.db.query(ProjectToolDatabase)
            .filter(ProjectToolDatabase.project_id == project_id)
            .order_by(ProjectToolDatabase.name)
            .all()
        )

    def get_project_tool_by_name(self, project_id: int, name: str) -> Optional[ProjectToolDatabase]:
        return (
            self.db.query(ProjectToolDatabase)
            .filter(ProjectToolDatabase.project_id == project_id, ProjectToolDatabase.name == name)
            .first()
        )

    def upsert_project_tool(self, project_id: int, name: str, description: str, parameters: str, code: str) -> ProjectToolDatabase:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        existing = self.get_project_tool_by_name(project_id, name)
        if existing:
            existing.description = description
            existing.parameters = parameters
            existing.code = code
            existing.updated_at = now
            self.db.commit()
            return existing
        tool = ProjectToolDatabase(
            project_id=project_id,
            name=name,
            description=description,
            parameters=parameters,
            code=code,
            created_at=now,
            updated_at=now,
        )
        self.db.add(tool)
        self.db.commit()
        return tool

    def delete_project_tool(self, project_id: int, name: str) -> bool:
        tool = self.get_project_tool_by_name(project_id, name)
        if tool:
            self.db.delete(tool)
            self.db.commit()
            return True
        return False

    def get_project_routines(self, project_id: int) -> list[ProjectRoutineDatabase]:
        return (
            self.db.query(ProjectRoutineDatabase)
            .filter(ProjectRoutineDatabase.project_id == project_id)
            .order_by(ProjectRoutineDatabase.name)
            .all()
        )

    def get_all_enabled_routines(self) -> list[ProjectRoutineDatabase]:
        return (
            self.db.query(ProjectRoutineDatabase)
            .filter(ProjectRoutineDatabase.enabled == True)
            .all()
        )

    def get_project_routine_by_id(self, routine_id: int) -> Optional[ProjectRoutineDatabase]:
        return self.db.query(ProjectRoutineDatabase).filter(ProjectRoutineDatabase.id == routine_id).first()

    def create_project_routine(self, project_id: int, name: str, message: str, schedule_minutes: int, enabled: bool = True) -> ProjectRoutineDatabase:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        routine = ProjectRoutineDatabase(
            project_id=project_id,
            name=name,
            message=message,
            schedule_minutes=schedule_minutes,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.db.add(routine)
        self.db.commit()
        self.db.refresh(routine)
        return routine

    def delete_project_routine(self, routine_id: int) -> bool:
        routine = self.get_project_routine_by_id(routine_id)
        if routine:
            self.db.delete(routine)
            self.db.commit()
            return True
        return False
