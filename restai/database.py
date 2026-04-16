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
    )
elif POSTGRES_HOST:
    _db_logger.info("Using PostgreSQL database.")
    engine = create_engine(
        POSTGRES_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_recycle=config.DB_POOL_RECYCLE,
    )
else:
    _db_logger.info("Using sqlite database.")
    engine = create_engine(
        "sqlite:///./restai.db",
        connect_args={"check_same_thread": False},
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_POOL_RECYCLE,
        pool_recycle=config.DB_POOL_RECYCLE,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


class DBWrapper:
    __slots__ = ("db",)

    def __init__(self):
        self.db: Session = SessionLocal()

    def create_user(
        self,
        username: str,
        password: Optional[str],
        admin: bool = False,
        private: bool = False,
        restricted: bool = False,
    ) -> UserDatabase:
        password_hash: Optional[str]
        if password:
            password_hash = hash_password(password)
        else:
            password_hash = None
        db_user: UserDatabase = UserDatabase(
            username=username,
            hashed_password=password_hash,
            is_admin=admin,
            is_private=private,
            is_restricted=restricted,
            options='{"credit": -1.0}',
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def create_llm(
        self,
        name: str,
        class_name: str,
        options: str,
        privacy: str,
        description: str,
        context_window: int = 4096,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
    ) -> LLMDatabase:
        # Encrypt sensitive fields (api_key) in the options JSON
        from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
        import json as _json
        try:
            opts_dict = _json.loads(options) if isinstance(options, str) else options
            opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
            options = _json.dumps(opts_dict)
        except Exception as e:
            logging.warning("Failed to encrypt LLM options: %s", e)

        db_llm: LLMDatabase = LLMDatabase(
            name=name,
            class_name=class_name,
            options=options,
            privacy=privacy,
            description=description,
            context_window=context_window,
            input_cost=input_cost,
            output_cost=output_cost,
        )
        self.db.add(db_llm)
        self.db.commit()
        self.db.refresh(db_llm)
        return db_llm

    def create_embedding(
        self,
        name: str,
        class_name: str,
        options: str,
        privacy: str,
        description: str,
        dimension: int,
    ) -> EmbeddingDatabase:
        db_embedding: EmbeddingDatabase = EmbeddingDatabase(
            name=name,
            class_name=class_name,
            options=options,
            privacy=privacy,
            description=description,
            dimension=dimension,
        )
        self.db.add(db_embedding)
        self.db.commit()
        self.db.refresh(db_embedding)
        return db_embedding

    def get_users(self) -> list[UserDatabase]:
        users: list[UserDatabase] = self.db.query(UserDatabase).all()
        return users

    def get_llms(self) -> list[LLMDatabase]:
        llms: list[LLMDatabase] = self.db.query(LLMDatabase).all()
        return llms

    def get_embeddings(self) -> list[EmbeddingDatabase]:
        embeddings: list[EmbeddingDatabase] = self.db.query(EmbeddingDatabase).all()
        return embeddings

    def get_llm_by_name(self, name: str) -> Optional[LLMDatabase]:
        llm: Optional[LLMDatabase] = (
            self.db.query(LLMDatabase).filter(LLMDatabase.name == name).first()
        )
        return llm

    def get_llm_by_id(self, id: int) -> Optional[LLMDatabase]:
        return self.db.query(LLMDatabase).filter(LLMDatabase.id == id).first()

    def get_embedding_by_name(self, name: str) -> Optional[EmbeddingDatabase]:
        llm: Optional[EmbeddingDatabase] = (
            self.db.query(EmbeddingDatabase)
            .filter(EmbeddingDatabase.name == name)
            .first()
        )
        return llm

    def get_embedding_by_id(self, id: int) -> Optional[EmbeddingDatabase]:
        return self.db.query(EmbeddingDatabase).filter(EmbeddingDatabase.id == id).first()

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

    # ── Widget methods ─────────────────────────────────────────────────

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
        """Look up a widget by plaintext key using prefix-then-verify (salted hash)."""
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

    def update_user(self, user: User, user_update: UserUpdate) -> bool:
        if user_update.password is not None:
            user.hashed_password = hash_password(user_update.password)

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

    def update_llm(self, llm: LLMModel, llmUpdate: LLMUpdate) -> bool:
        if llmUpdate.class_name is not None and llm.class_name != llmUpdate.class_name:
            llm.class_name = llmUpdate.class_name

        if llmUpdate.options is not None and llm.options != llmUpdate.options:
            # Encrypt sensitive fields (api_key) before persisting
            from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
            import json as _json
            try:
                opts_dict = _json.loads(llmUpdate.options) if isinstance(llmUpdate.options, str) else llmUpdate.options
                # If api_key is the masked value, preserve the existing one
                if opts_dict.get("api_key") == "********":
                    existing = _json.loads(llm.options) if isinstance(llm.options, str) else (llm.options or {})
                    if "api_key" in existing:
                        opts_dict["api_key"] = existing["api_key"]
                    else:
                        del opts_dict["api_key"]
                opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
                llm.options = _json.dumps(opts_dict) if isinstance(llmUpdate.options, str) else opts_dict
            except Exception as e:
                logging.warning("Failed to encrypt LLM options on update: %s", e)
                llm.options = llmUpdate.options

        if llmUpdate.privacy is not None and llm.privacy != llmUpdate.privacy:
            llm.privacy = llmUpdate.privacy

        if (
            llmUpdate.description is not None
            and llm.description != llmUpdate.description
        ):
            llm.description = llmUpdate.description

        if llmUpdate.input_cost is not None and llm.input_cost != llmUpdate.input_cost:
            llm.input_cost = llmUpdate.input_cost

        if (
            llmUpdate.output_cost is not None
            and llm.output_cost != llmUpdate.output_cost
        ):
            llm.output_cost = llmUpdate.output_cost

        if (
            llmUpdate.context_window is not None
            and llm.context_window != llmUpdate.context_window
        ):
            llm.context_window = llmUpdate.context_window

        self.db.commit()
        return True

    def update_embedding(
        self, embedding: EmbeddingModel, embeddingUpdate: EmbeddingUpdate
    ) -> bool:
        if (
            embeddingUpdate.class_name is not None
            and embedding.class_name != embeddingUpdate.class_name
        ):
            embedding.class_name = embeddingUpdate.class_name

        if (
            embeddingUpdate.options is not None
            and embedding.options != embeddingUpdate.options
        ):
            # If api_key is the masked value, preserve the existing one
            import json as _json
            try:
                new_opts = _json.loads(embeddingUpdate.options) if isinstance(embeddingUpdate.options, str) else (embeddingUpdate.options or {})
                if new_opts.get("api_key") == "********":
                    existing = _json.loads(embedding.options) if isinstance(embedding.options, str) else (embedding.options or {})
                    if "api_key" in existing:
                        new_opts["api_key"] = existing["api_key"]
                    else:
                        del new_opts["api_key"]
                    embeddingUpdate.options = _json.dumps(new_opts)
            except Exception:
                pass
            embedding.options = embeddingUpdate.options

        if (
            embeddingUpdate.privacy is not None
            and embedding.privacy != embeddingUpdate.privacy
        ):
            embedding.privacy = embeddingUpdate.privacy

        if (
            embeddingUpdate.description is not None
            and embedding.description != embeddingUpdate.description
        ):
            embedding.description = embeddingUpdate.description

        if (
            embeddingUpdate.dimension is not None
            and embedding.dimension != embeddingUpdate.dimension
        ):
            embedding.dimension = embeddingUpdate.dimension

        self.db.commit()
        return True

    def delete_llm(self, llm: LLMDatabase) -> bool:
        self.db.delete(llm)
        self.db.commit()
        return True

    def delete_embedding(self, embedding: EmbeddingDatabase) -> bool:
        self.db.delete(embedding)
        self.db.commit()
        return True

    def get_user_by_id(self, user_id: int) -> Optional[UserDatabase]:
        user: Optional[UserDatabase] = (
            self.db.query(UserDatabase).filter(UserDatabase.id == user_id).first()
        )
        return user

    def delete_user(self, user: UserDatabase) -> bool:
        self.db.delete(user)
        self.db.commit()
        return True

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
        # Validate that the team exists
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
                
        # Look up the creator so we can associate them in the same transaction
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
        self.db.delete(project)
        self.db.commit()
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
            # Validate that at least one team has access to this LLM
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
            # Validate that at least one team has access to this embedding model
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

        if hasattr(projectModel, "options") and projectModel.options is not None:
            from restai.utils.crypto import encrypt_sensitive_options, PROJECT_SENSITIVE_KEYS
            try:
                current_options = json.loads(proj_db.options) if proj_db.options else {}
                new_options = projectModel.options.model_dump()
                new_options = encrypt_sensitive_options(new_options, PROJECT_SENSITIVE_KEYS)
                if current_options != new_options:
                    proj_db.options = json.dumps(new_options)
                    changed = True
            except json.JSONDecodeError:
                new_options = projectModel.options.model_dump()
                new_options = encrypt_sensitive_options(new_options, PROJECT_SENSITIVE_KEYS)
                proj_db.options = json.dumps(new_options)
                changed = True

        if changed:
            self.db.commit()
        return True

    def create_team(self, team_create: TeamModelCreate) -> TeamDatabase:
        db_team: TeamDatabase = TeamDatabase(
            name=team_create.name,
            description=team_create.description,
            creator_id=team_create.creator_id,
            budget=team_create.budget,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(db_team)
        self.db.commit()
        self.db.refresh(db_team)
        return db_team

    def get_team_by_id(self, team_id: int) -> Optional[TeamDatabase]:
        team: Optional[TeamDatabase] = (
            self.db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
        )
        return team

    def get_team_by_name(self, name: str) -> Optional[TeamDatabase]:
        team: Optional[TeamDatabase] = (
            self.db.query(TeamDatabase).filter(TeamDatabase.name == name).first()
        )
        return team

    def get_teams(self) -> List[TeamDatabase]:
        teams: List[TeamDatabase] = self.db.query(TeamDatabase).all()
        return teams

    def update_team(self, team: TeamDatabase, team_update: TeamModelUpdate) -> bool:
        changed = False

        if team_update.name is not None and team.name != team_update.name:
            team.name = team_update.name
            changed = True

        if team_update.description is not None and team.description != team_update.description:
            team.description = team_update.description
            changed = True

        if team_update.budget is not None and team.budget != team_update.budget:
            team.budget = team_update.budget
            changed = True

        if team_update.branding is not None:
            import json
            team.branding = json.dumps(team_update.branding.model_dump())
            changed = True

        if changed:
            team.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return changed

    def delete_team(self, team: TeamDatabase) -> bool:
        self.db.delete(team)
        self.db.commit()
        return True

    def add_user_to_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user not in team.users:
            team.users.append(user)
            self.db.commit()
        return True
    
    def remove_user_from_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user in team.users:
            team.users.remove(user)
            self.db.commit()
        return True
    
    def add_admin_to_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user not in team.admins:
            team.admins.append(user)
            self.db.commit()
        return True
    
    def remove_admin_from_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user in team.admins:
            team.admins.remove(user)
            self.db.commit()
        return True
    
    def add_project_to_team(self, team: TeamDatabase, project: ProjectDatabase) -> bool:
        if project not in team.projects:
            team.projects.append(project)
            self.db.commit()
        return True
    
    def remove_project_from_team(self, team: TeamDatabase, project: ProjectDatabase) -> bool:
        if project in team.projects:
            team.projects.remove(project)
            self.db.commit()
        return True
    
    def add_llm_to_team(self, team: TeamDatabase, llm: LLMDatabase) -> bool:
        if llm not in team.llms:
            team.llms.append(llm)
            self.db.commit()
        return True
    
    def remove_llm_from_team(self, team: TeamDatabase, llm: LLMDatabase) -> bool:
        if llm in team.llms:
            team.llms.remove(llm)
            self.db.commit()
        return True
    
    def add_embedding_to_team(self, team: TeamDatabase, embedding: EmbeddingDatabase) -> bool:
        if embedding not in team.embeddings:
            team.embeddings.append(embedding)
            self.db.commit()
        return True
    
    def remove_embedding_from_team(self, team: TeamDatabase, embedding: EmbeddingDatabase) -> bool:
        if embedding in team.embeddings:
            team.embeddings.remove(embedding)
            self.db.commit()
        return True
        
    def get_teams_for_user(self, user_id: int) -> List[TeamDatabase]:
        """Get all teams where the user is a member or admin"""
        user = self.get_user_by_id(user_id)
        if user is None:
            return []
        return list(set(user.teams + user.admin_teams))
        
    def get_settings(self) -> list[SettingDatabase]:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, decrypt_field
        rows = self.db.query(SettingDatabase).all()
        for r in rows:
            if r.key in SETTINGS_ENCRYPTED_KEYS and r.value:
                self.db.expunge(r)
                r.value = decrypt_field(r.value)
        return rows

    def get_setting(self, key: str) -> Optional[SettingDatabase]:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, decrypt_field
        row = self.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
        if row and key in SETTINGS_ENCRYPTED_KEYS and row.value:
            self.db.expunge(row)
            row.value = decrypt_field(row.value)
        return row

    def get_setting_value(self, key: str, default: str = "") -> str:
        """Get a setting value by key, returning default if not found or empty."""
        row = self.get_setting(key)
        return row.value if row and row.value else default

    def upsert_setting(self, key: str, value: str) -> None:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, encrypt_field
        stored_value = encrypt_field(value) if (key in SETTINGS_ENCRYPTED_KEYS and value) else value
        existing = self.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
        if existing:
            existing.value = stored_value
        else:
            self.db.add(SettingDatabase(key=key, value=stored_value))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()

    def get_team_spending(self, team_id: int) -> float:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        result = self.db.query(
            func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0.0)
        ).filter(
            or_(
                OutputDatabase.project_id.in_(
                    self.db.query(ProjectDatabase.id).filter(ProjectDatabase.team_id == team_id)
                ),
                OutputDatabase.team_id == team_id
            ),
            OutputDatabase.date >= month_start
        ).scalar()
        return float(result)

    def update_team_members(self, team: TeamDatabase, team_update: TeamModelUpdate) -> bool:
        changed = False
        
        # Update users
        if team_update.users is not None:
            team.users = []
            for username in team_update.users:
                user_db = self.get_user_by_username(username)
                if user_db is not None:
                    team.users.append(user_db)
            changed = True
            
        # Update admins
        if team_update.admins is not None:
            team.admins = []
            for username in team_update.admins:
                user_db = self.get_user_by_username(username)
                if user_db is not None:
                    team.admins.append(user_db)
            changed = True
            
        # Update projects
        if team_update.projects is not None:
            team.projects = []
            for project_name in team_update.projects:
                project_db = self.get_project_by_name(project_name)
                if project_db is not None:
                    team.projects.append(project_db)
            changed = True
            
        # Update LLMs
        if team_update.llms is not None:
            team.llms = []
            for llm_name in team_update.llms:
                llm_db = self.get_llm_by_name(llm_name)
                if llm_db is not None:
                    team.llms.append(llm_db)
            changed = True
            
        # Update embeddings
        if team_update.embeddings is not None:
            team.embeddings = []
            for embedding_name in team_update.embeddings:
                embedding_db = self.get_embedding_by_name(embedding_name)
                if embedding_db is not None:
                    team.embeddings.append(embedding_db)
            changed = True

        # Update image generators
        if team_update.image_generators is not None:
            team.image_generators = []
            self.db.flush()
            for gen_name in team_update.image_generators:
                team.image_generators.append(
                    TeamImageGeneratorDatabase(team_id=team.id, generator_name=gen_name)
                )
            changed = True

        # Update audio generators
        if team_update.audio_generators is not None:
            team.audio_generators = []
            self.db.flush()
            for gen_name in team_update.audio_generators:
                team.audio_generators.append(
                    TeamAudioGeneratorDatabase(team_id=team.id, generator_name=gen_name)
                )
            changed = True

        if changed:
            team.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
        return changed


    def add_image_generator_to_team(self, team: TeamDatabase, generator_name: str) -> bool:
        existing = self.db.query(TeamImageGeneratorDatabase).filter(
            TeamImageGeneratorDatabase.team_id == team.id,
            TeamImageGeneratorDatabase.generator_name == generator_name
        ).first()
        if existing is None:
            team.image_generators.append(
                TeamImageGeneratorDatabase(team_id=team.id, generator_name=generator_name)
            )
            self.db.commit()
        return True

    def remove_image_generator_from_team(self, team: TeamDatabase, generator_name: str) -> bool:
        item = self.db.query(TeamImageGeneratorDatabase).filter(
            TeamImageGeneratorDatabase.team_id == team.id,
            TeamImageGeneratorDatabase.generator_name == generator_name
        ).first()
        if item is not None:
            self.db.delete(item)
            self.db.commit()
        return True

    def add_audio_generator_to_team(self, team: TeamDatabase, generator_name: str) -> bool:
        existing = self.db.query(TeamAudioGeneratorDatabase).filter(
            TeamAudioGeneratorDatabase.team_id == team.id,
            TeamAudioGeneratorDatabase.generator_name == generator_name
        ).first()
        if existing is None:
            team.audio_generators.append(
                TeamAudioGeneratorDatabase(team_id=team.id, generator_name=generator_name)
            )
            self.db.commit()
        return True

    def remove_audio_generator_from_team(self, team: TeamDatabase, generator_name: str) -> bool:
        item = self.db.query(TeamAudioGeneratorDatabase).filter(
            TeamAudioGeneratorDatabase.team_id == team.id,
            TeamAudioGeneratorDatabase.generator_name == generator_name
        ).first()
        if item is not None:
            self.db.delete(item)
            self.db.commit()
        return True


    def _create_prompt_version(self, project_id: int, system_prompt: str, user_id: int = None):
        """Create a new prompt version record, marking it as active."""
        from restai.models.databasemodels import PromptVersionDatabase

        # Deactivate current active version
        self.db.query(PromptVersionDatabase).filter(
            PromptVersionDatabase.project_id == project_id,
            PromptVersionDatabase.is_active == True,
        ).update({"is_active": False})

        # Get next version number
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
        """Get all prompt versions for a project, newest first."""
        from restai.models.databasemodels import PromptVersionDatabase
        return (
            self.db.query(PromptVersionDatabase)
            .filter(PromptVersionDatabase.project_id == project_id)
            .order_by(PromptVersionDatabase.version.desc())
            .all()
        )

    def get_prompt_version(self, version_id: int):
        """Get a specific prompt version by ID."""
        from restai.models.databasemodels import PromptVersionDatabase
        return self.db.query(PromptVersionDatabase).filter(PromptVersionDatabase.id == version_id).first()

    def get_active_prompt_version(self, project_id: int):
        """Get the active prompt version for a project."""
        from restai.models.databasemodels import PromptVersionDatabase
        return (
            self.db.query(PromptVersionDatabase)
            .filter(PromptVersionDatabase.project_id == project_id, PromptVersionDatabase.is_active == True)
            .first()
        )

    # ── Project Tools (agent-created) ────────────────────────────────────

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

    # ── Project Routines (scheduled messages) ────────────────────────────

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

    # ── Cron Logs ────────────────────────────────────────────────────────

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


def get_db_wrapper() -> DBWrapper:
    wrapper: DBWrapper = DBWrapper()
    try:
        return wrapper
    finally:
        wrapper.db.close()
