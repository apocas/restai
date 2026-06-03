"""DBWrapper project + prompt-version methods (mixin).

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


class ProjectMixin:
    __slots__ = ()

    def get_project_by_name(self, name: str) -> Optional[ProjectDatabase]:
        project: Optional[ProjectDatabase] = (
            self.db.query(ProjectDatabase).filter(ProjectDatabase.name == name).first()
        )
        return project

    def get_project_by_id(self, id: int) -> Optional[ProjectDatabase]:
        project: Optional[ProjectDatabase] = (
            self.db.query(ProjectDatabase).filter(ProjectDatabase.id == id).first()
        )
        return project

    def create_project(
        self,
        name: str,
        embeddings: str,
        llm: str,
        vectorstore: str,
        human_name: str,
        human_description: str,
        project_type: str,
        creator: int,
        team_id: int,
    ) -> Optional[ProjectDatabase]:
        team = self.get_team_by_id(team_id)
        if team is None:
            return None
            
        # Validate that the team has access to the specified LLM (block projects don't need one)
        if llm:
            llm_db = self.get_llm_by_name(llm)
            if llm_db is None or llm_db not in team.llms:
                return None
            
        # If embeddings are specified, validate that the team has access to it
        if embeddings:
            embedding_db = self.get_embedding_by_name(embeddings)
            if embedding_db is None or embedding_db not in team.embeddings:
                return None
                
        creator_user = self.get_user_by_id(creator) if creator else None

        db_project: ProjectDatabase = ProjectDatabase(
            name=name,
            embeddings=embeddings,
            llm=llm,
            vectorstore=vectorstore,
            human_name=human_name,
            human_description=human_description,
            type=project_type,
            creator=creator,
            options='{"logging": true}',
        )
        self.db.add(db_project)

        # Associate with team and creator in ONE transaction so we never
        # end up with a project row that has no users.
        if db_project not in team.projects:
            team.projects.append(db_project)
        if creator_user and db_project not in creator_user.projects:
            creator_user.projects.append(db_project)

        self.db.commit()
        self.db.refresh(db_project)

        return db_project

    def delete_project(self, project: ProjectDatabase) -> bool:
        project_id = int(project.id)

        # App-side fallback for SQLite + pre-050 deployments where the
        # FK lacks ON DELETE CASCADE. M2M secondary tables are excluded
        # — the ORM relationship handles those and a manual DELETE here
        # races it into StaleDataError.
        from sqlalchemy import text as _sql_text
        _CHILDREN_CASCADE = [
            "prompt_versions", "eval_runs", "eval_datasets",
            "project_invitations", "widgets", "kg_entities",
            "kg_entity_mentions", "kg_entity_relationships",
            "retrieval_events", "guard_events", "project_comments",
            "project_tools", "project_routines",
            "project_memory_bank_entries", "bulk_ingest_jobs",
            "project_secrets", "routine_execution_log",
        ]
        for tbl in _CHILDREN_CASCADE:
            try:
                self.db.execute(
                    _sql_text(f"DELETE FROM {tbl} WHERE project_id = :pid"),
                    {"pid": project_id},
                )
            except Exception as e:
                logging.debug("delete_project: skip %s (%s)", tbl, e)
        # Preserve audit history when the project goes away.
        try:
            self.db.execute(
                _sql_text("UPDATE output SET project_id = NULL WHERE project_id = :pid"),
                {"pid": project_id},
            )
        except Exception as e:
            logging.debug("delete_project: skip output null-out (%s)", e)

        self.db.delete(project)
        self.db.commit()
        try:
            from restai.memory import search as memory_search
            memory_search.delete_project(project_id)
        except Exception as e:
            logging.warning("delete_project: memory_search cleanup failed: %s", e)
        return True

    def edit_project(self, id: int, projectModel: ProjectModelUpdate) -> bool:
        proj_db: Optional[ProjectDatabase] = self.get_project_by_id(id)
        if proj_db is None:
            return False

        changed = False
        
        # Get all teams that have this project to validate LLM/embedding access
        teams_with_project = [team for team in self.get_teams() if proj_db in team.projects]
        if not teams_with_project:
            return False  # Project should belong to at least one team
        
        if projectModel.users is not None:
            new_users = []
            rejected = []
            for username in projectModel.users:
                user_db = self.get_user_by_username(username)
                if user_db is None:
                    rejected.append(f"{username} (not found)")
                    continue
                # Platform admins bypass the team membership check
                if user_db.is_admin:
                    new_users.append(user_db)
                    continue
                # Otherwise the user must belong to one of the project's teams
                in_team = any(
                    user_db in team.users or user_db in team.admins
                    for team in teams_with_project
                )
                if in_team:
                    new_users.append(user_db)
                else:
                    rejected.append(f"{username} (not in project's team)")

            if rejected:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot assign users: {', '.join(rejected)}",
                )

            proj_db.users = new_users
            changed = True

        if projectModel.name is not None and proj_db.name != projectModel.name:
            if (
                self.db.query(ProjectDatabase)
                .filter(
                    ProjectDatabase.creator == proj_db.creator,
                    ProjectDatabase.name == projectModel.name,
                    ProjectDatabase.id != proj_db.id,
                )
                .first()
                is not None
            ):
                return False
            proj_db.name = projectModel.name
            changed = True

        if projectModel.llm is not None and proj_db.llm != projectModel.llm:
            llm_db = self.get_llm_by_name(projectModel.llm)
            if llm_db is None:
                return False
                
            llm_access = False
            for team in teams_with_project:
                if llm_db in team.llms:
                    llm_access = True
                    break
                    
            if not llm_access:
                return False  # No team has access to this LLM
                
            proj_db.llm = projectModel.llm
            changed = True

        if projectModel.embeddings is not None and proj_db.embeddings != projectModel.embeddings:
            if projectModel.embeddings:  # Only check if embeddings is not empty
                embedding_db = self.get_embedding_by_name(projectModel.embeddings)
                if embedding_db is None:
                    return False

                embedding_access = False
                for team in teams_with_project:
                    if embedding_db in team.embeddings:
                        embedding_access = True
                        break

                if not embedding_access:
                    return False  # No team has access to this embedding model

            # Note: the memory_search vectordb collection is also
            # invalidated on embedding swap, but that's a non-SQL
            # side effect handled by the router (see
            # `route_edit_project` → `Project.reset_memory_index`).
            # Keeping it out of this CRUD function keeps the SQL
            # layer pure.
            proj_db.embeddings = projectModel.embeddings
            changed = True

        if projectModel.system is not None and proj_db.system != projectModel.system:
            proj_db.system = projectModel.system
            changed = True
            # Auto-create prompt version
            self._create_prompt_version(proj_db.id, projectModel.system, user_id=getattr(projectModel, '_user_id', None))

        if (
            projectModel.censorship is not None
            and proj_db.censorship != projectModel.censorship
        ):
            proj_db.censorship = projectModel.censorship
            changed = True

        if projectModel.guard is not None and proj_db.guard != projectModel.guard:
            proj_db.guard = projectModel.guard
            changed = True

        if (
            projectModel.human_name is not None
            and proj_db.human_name != projectModel.human_name
        ):
            proj_db.human_name = projectModel.human_name
            changed = True

        if (
            projectModel.human_description is not None
            and proj_db.human_description != projectModel.human_description
        ):
            proj_db.human_description = projectModel.human_description
            changed = True

        if projectModel.public is not None and proj_db.public != projectModel.public:
            proj_db.public = projectModel.public
            changed = True

        if (
            projectModel.default_prompt is not None
            and proj_db.default_prompt != projectModel.default_prompt
        ):
            proj_db.default_prompt = projectModel.default_prompt
            changed = True

        # eval_llm follows the same team-scoped access rule as the main `llm`:
        # the user can only point evals at an LLM one of the project's teams
        # can use. Empty/None = "use the project's own LLM" (no check needed).
        if projectModel.options is not None and getattr(projectModel.options, "eval_llm", None):
            eval_llm_db = self.get_llm_by_name(projectModel.options.eval_llm)
            if eval_llm_db is None or not any(eval_llm_db in team.llms for team in teams_with_project):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail=f"No access to eval LLM '{projectModel.options.eval_llm}'",
                )

        if hasattr(projectModel, "options") and projectModel.options is not None:
            from restai.utils.crypto import encrypt_sensitive_options, PROJECT_SENSITIVE_KEYS
            # Keys that aren't surfaced in the project-edit form — they are
            # owned by dedicated endpoints (e.g. the Mobile pairing flow) and
            # must not be wiped when the edit form POSTs a ProjectOptions dump.
            PRESERVED_KEYS = ("mobile_enabled", "mobile_api_key_id")
            try:
                current_options = json.loads(proj_db.options) if proj_db.options else {}
            except json.JSONDecodeError:
                current_options = {}
            new_options = projectModel.options.model_dump()
            new_options = encrypt_sensitive_options(new_options, PROJECT_SENSITIVE_KEYS)
            for k in PRESERVED_KEYS:
                if k in current_options:
                    new_options[k] = current_options[k]
            if current_options != new_options:
                proj_db.options = json.dumps(new_options)
                changed = True

        if changed:
            self.db.commit()
        return True

    def _create_prompt_version(self, project_id: int, system_prompt: str, user_id: int = None):
        from restai.models.databasemodels import PromptVersionDatabase

        self.db.query(PromptVersionDatabase).filter(
            PromptVersionDatabase.project_id == project_id,
            PromptVersionDatabase.is_active == True,
        ).update({"is_active": False})

        max_version = (
            self.db.query(func.max(PromptVersionDatabase.version))
            .filter(PromptVersionDatabase.project_id == project_id)
            .scalar()
        ) or 0

        version = PromptVersionDatabase(
            project_id=project_id,
            version=max_version + 1,
            system_prompt=system_prompt or "",
            created_by=user_id,
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        self.db.add(version)

    def get_prompt_versions(self, project_id: int):
        from restai.models.databasemodels import PromptVersionDatabase
        return (
            self.db.query(PromptVersionDatabase)
            .filter(PromptVersionDatabase.project_id == project_id)
            .order_by(PromptVersionDatabase.version.desc())
            .all()
        )

    def get_prompt_version(self, version_id: int):
        from restai.models.databasemodels import PromptVersionDatabase
        return self.db.query(PromptVersionDatabase).filter(PromptVersionDatabase.id == version_id).first()

    def get_active_prompt_version(self, project_id: int):
        from restai.models.databasemodels import PromptVersionDatabase
        return (
            self.db.query(PromptVersionDatabase)
            .filter(PromptVersionDatabase.project_id == project_id, PromptVersionDatabase.is_active == True)
            .first()
        )
