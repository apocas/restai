from sqlalchemy import create_engine
from restai import config
from datetime import datetime
from restai.models.databasemodels import (
    LLMDatabase,
    EmbeddingDatabase,
    ProjectDatabase,
    RouterEntrancesDatabase,
    UserDatabase,
    TeamDatabase,
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
from passlib.context import CryptContext
from typing import Optional, List
from restai.config import MYSQL_HOST, MYSQL_URL, POSTGRES_HOST, POSTGRES_URL
import json

if MYSQL_HOST:
    print("Using MySQL database: " + MYSQL_HOST)
    engine = create_engine(
        MYSQL_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_recycle=config.DB_POOL_RECYCLE,
    )
elif POSTGRES_HOST:
    print("Using PostgreSQL database")
    engine = create_engine(
        POSTGRES_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_recycle=config.DB_POOL_RECYCLE,
    )
else:
    print("Using sqlite database.")
    engine = create_engine(
        "sqlite:///./restai.db",
        connect_args={"check_same_thread": False},
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_POOL_RECYCLE,
        pool_recycle=config.DB_POOL_RECYCLE,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    ) -> UserDatabase:
        password_hash: Optional[str]
        if password:
            password_hash = pwd_context.hash(password)
        else:
            password_hash = None
        db_user: UserDatabase = UserDatabase(
            username=username,
            hashed_password=password_hash,
            is_admin=admin,
            is_private=private,
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
        llm_type: str,
    ) -> LLMDatabase:
        db_llm: LLMDatabase = LLMDatabase(
            name=name,
            class_name=class_name,
            options=options,
            privacy=privacy,
            description=description,
            type=llm_type,
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

    def get_embedding_by_name(self, name: str) -> Optional[EmbeddingDatabase]:
        llm: Optional[EmbeddingDatabase] = (
            self.db.query(EmbeddingDatabase)
            .filter(EmbeddingDatabase.name == name)
            .first()
        )
        return llm

    def get_user_by_apikey(self, apikey: str) -> Optional[UserDatabase]:
        user: Optional[UserDatabase] = (
            self.db.query(UserDatabase).filter(UserDatabase.api_key == apikey).first()
        )
        return user

    def get_user_by_username(self, username: str) -> Optional[UserDatabase]:
        user: Optional[UserDatabase] = (
            self.db.query(UserDatabase)
            .filter(UserDatabase.username == username)
            .first()
        )
        return user

    def update_user(self, user: User, user_update: UserUpdate) -> bool:
        if user_update.password is not None:
            user.hashed_password = pwd_context.hash(user_update.password)

        if user_update.is_admin is not None:
            user.is_admin = user_update.is_admin

        if user_update.is_private is not None:
            user.is_private = user_update.is_private

        if user_update.api_key is not None:
            user.api_key = user_update.api_key

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
            llm.options = llmUpdate.options

        if llmUpdate.privacy is not None and llm.privacy != llmUpdate.privacy:
            llm.privacy = llmUpdate.privacy

        if (
            llmUpdate.description is not None
            and llm.description != llmUpdate.description
        ):
            llm.description = llmUpdate.description

        if llmUpdate.type is not None and llm.type != llmUpdate.type:
            llm.type = llmUpdate.type

        if llmUpdate.input_cost is not None and llm.input_cost != llmUpdate.input_cost:
            llm.input_cost = llmUpdate.input_cost

        if (
            llmUpdate.output_cost is not None
            and llm.output_cost != llmUpdate.output_cost
        ):
            llm.output_cost = llmUpdate.output_cost

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
            
        # Validate that the team has access to the specified LLM
        llm_db = self.get_llm_by_name(llm)
        if llm_db is None or llm_db not in team.llms:
            return None
            
        # If embeddings are specified, validate that the team has access to it
        if embeddings:
            embedding_db = self.get_embedding_by_name(embeddings)
            if embedding_db is None or embedding_db not in team.embeddings:
                return None
                
        db_project: ProjectDatabase = ProjectDatabase(
            name=name,
            embeddings=embeddings,
            llm=llm,
            vectorstore=vectorstore,
            human_name=human_name,
            human_description=human_description,
            type=project_type,
            creator=creator,
            options='{"logging": true}',  # Initialize with default options
        )
        self.db.add(db_project)
        self.db.commit()
        self.db.refresh(db_project)
        
        # Associate the project with the team
        self.add_project_to_team(team, db_project)
        
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
            proj_db.users = []
            for username in projectModel.users:
                user_db = self.get_user_by_username(username)
                if user_db is not None:
                    # Validate that the user belongs to at least one of the teams associated with this project
                    user_is_in_team = False
                    for team in teams_with_project:
                        if user_db in team.users or user_db in team.admins:
                            user_is_in_team = True
                            break
                    
                    # Only add the user if they belong to one of the project's teams
                    if user_is_in_team:
                        proj_db.users.append(user_db)
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

        if projectModel.entrances is not None:
            proj_db.entrances = []
            for entrance in projectModel.entrances:
                proj_db.entrances.append(
                    RouterEntrancesDatabase(
                        name=entrance.name,
                        description=entrance.description,
                        destination=entrance.destination,
                        project_id=proj_db.id,
                    )
                )
            changed = True

        if hasattr(projectModel, "options") and projectModel.options is not None:
            try:
                current_options = json.loads(proj_db.options) if proj_db.options else {}
                new_options = projectModel.options.model_dump()
                if current_options != new_options:
                    proj_db.options = json.dumps(new_options)
                    changed = True
            except json.JSONDecodeError:
                proj_db.options = json.dumps(projectModel.options.model_dump())
                changed = True

        if changed:
            self.db.commit()
        return True

    def create_team(self, team_create: TeamModelCreate) -> TeamDatabase:
        db_team: TeamDatabase = TeamDatabase(
            name=team_create.name,
            description=team_create.description,
            creator_id=team_create.creator_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
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

        if changed:
            team.updated_at = datetime.utcnow()
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
            
        if changed:
            team.updated_at = datetime.utcnow()
            self.db.commit()
            
        return changed


def get_db_wrapper() -> DBWrapper:
    wrapper: DBWrapper = DBWrapper()
    try:
        return wrapper
    finally:
        wrapper.db.close()
