from sqlalchemy import create_engine
from restai import config
from restai.models.databasemodels import (
    LLMDatabase,
    EmbeddingDatabase,
    ProjectDatabase,
    RouterEntrancesDatabase,
    UserDatabase,
)
from restai.models.models import (
    LLMModel,
    LLMUpdate,
    ProjectModelUpdate,
    User,
    UserUpdate,
    EmbeddingModel,
    EmbeddingUpdate,
)
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from typing import Optional
from restai.config import MYSQL_HOST, MYSQL_URL, POSTGRES_HOST, POSTGRES_URL

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

        if user_update.sso is not None:
            user.sso = user_update.sso

        if user_update.api_key is not None:
            user.api_key = user_update.api_key

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

    def create_project(
        self,
        name: str,
        embeddings: str,
        llm: str,
        vectorstore: str,
        human_name: str,
        project_type: str,
        creator: int,
    ) -> ProjectDatabase:
        db_project: ProjectDatabase = ProjectDatabase(
            name=name,
            embeddings=embeddings,
            llm=llm,
            vectorstore=vectorstore,
            human_name=human_name,
            type=project_type,
            creator=creator,
        )
        self.db.add(db_project)
        self.db.commit()
        self.db.refresh(db_project)
        return db_project

    def get_projects(self) -> list[ProjectDatabase]:
        projects: list[ProjectDatabase] = self.db.query(ProjectDatabase).all()
        return projects

    def delete_project(self, project: ProjectDatabase) -> bool:
        self.db.delete(project)
        self.db.commit()
        return True

    def edit_project(self, name: str, projectModel: ProjectModelUpdate) -> bool:
        proj_db: Optional[ProjectDatabase] = self.get_project_by_name(name)
        if proj_db is None:
            return False

        changed = False
        if projectModel.users is not None:
            proj_db.users = []
            for user in projectModel.users:
                u = self.get_user_by_username(user)
                if u is not None:
                    proj_db.users.append(u)
            changed = True
        
        if projectModel.llm is not None and proj_db.llm != projectModel.llm:
            proj_db.llm = projectModel.llm
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

        if projectModel.k is not None and proj_db.k != projectModel.k:
            proj_db.k = projectModel.k
            changed = True

        if projectModel.score is not None and proj_db.score != projectModel.score:
            proj_db.score = projectModel.score
            changed = True

        if (
            projectModel.connection is not None
            and proj_db.connection != projectModel.connection
            and "://xxxx:xxxx@" not in projectModel.connection
        ):
            proj_db.connection = projectModel.connection
            changed = True

        if projectModel.tables is not None and proj_db.tables != projectModel.tables:
            proj_db.tables = projectModel.tables
            changed = True

        if (
            projectModel.llm_rerank is not None
            and proj_db.llm_rerank != projectModel.llm_rerank
        ):
            proj_db.llm_rerank = projectModel.llm_rerank
            changed = True

        if (
            projectModel.colbert_rerank is not None
            and proj_db.colbert_rerank != projectModel.colbert_rerank
        ):
            proj_db.colbert_rerank = projectModel.colbert_rerank
            changed = True

        if projectModel.cache is not None and proj_db.cache != projectModel.cache:
            proj_db.cache = projectModel.cache
            changed = True

        if (
            projectModel.cache_threshold is not None
            and proj_db.cache_threshold != projectModel.cache_threshold
        ):
            proj_db.cache_threshold = projectModel.cache_threshold
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

        if projectModel.tools is not None and proj_db.tools != projectModel.tools:
            proj_db.tools = projectModel.tools
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

        if changed:
            self.db.commit()
        return True


def get_db_wrapper() -> DBWrapper:
    wrapper: DBWrapper = DBWrapper()
    try:
        return wrapper
    finally:
        wrapper.db.close()
