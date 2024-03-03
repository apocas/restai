import os
import json
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, LLMDatabase, ProjectDatabase, RouterEntrancesDatabase, UserDatabase
from app.models import LLMModel, LLMUpdate, ProjectModel, ProjectModelUpdate, User, UserUpdate
from app.tools import DEFAULT_LLMS


if os.environ.get("MYSQL_PASSWORD"):
    host = os.environ.get("MYSQL_HOST") or "127.0.0.1"
    print("Using MySQL database: " + host)
    engine = create_engine('mysql+pymysql://' + (os.environ.get("MYSQL_USER") or "restai") + ':' + os.environ.get("MYSQL_PASSWORD") + '@' +
                           host + '/' +
                           (os.environ.get("MYSQL_DB") or "restai"),
                           pool_size=30,
                           max_overflow=100,
                           pool_recycle=900)
else:
    print("Using sqlite database.")
    engine = create_engine(
        "sqlite:///./restai.db",
        connect_args={
            "check_same_thread": False},
        pool_size=30,
        max_overflow=100,
        pool_recycle=300)


SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


if "users" not in inspect(engine).get_table_names():
    print("Initializing database...")
    default_password = os.environ.get("RESTAI_DEFAULT_PASSWORD") or "admin"
    Base.metadata.create_all(bind=engine)
    dbi = SessionLocal()
    db_user = UserDatabase(
        username="admin",
        hashed_password=pwd_context.hash(default_password),
        is_admin=True)
    dbi.add(db_user)

    for llm in DEFAULT_LLMS:
        llm_class, llm_args, privacy, description, typel = DEFAULT_LLMS[llm]
        db_llm = LLMDatabase(
            name=llm,
            class_name=llm_class,
            options=json.dumps(llm_args),
            privacy=privacy,
            description=description,
            type=typel
        )
        dbi.add(db_llm)  
    
    if os.environ.get("RESTAI_DEMO"):
        print("Creating demo scenario...")
        db_user = UserDatabase(
            username="demo",
            hashed_password=pwd_context.hash("demo"),
            is_private=True,
        )
        dbi.add(db_user)
        
        demo_project1 = ProjectDatabase(
            name="demo1",
            type="inference",
            system="Always end your answers with 'beep beep'.",
            llm="llama2_7b"
        )
        demo_project2 = ProjectDatabase(
            name="demo2",
            type="inference",
            system="Always end your answers with 'boop boop'.",
            llm="llama2_7b"
        )
        demo_project3 = ProjectDatabase(
            name="router1",
            type="router",
            llm="openai_gpt3.5_turbo"
        )
        dbi.add(demo_project1)
        dbi.add(demo_project2)
        dbi.add(demo_project3)
        dbi.commit()
        
        demo_project3.entrances.append(RouterEntrancesDatabase(
            name="choice1", description="The question is about the meaning of life.", destination="demo1", project_id=demo_project3.id))
        demo_project3.entrances.append(RouterEntrancesDatabase(
            name="choice2", description="The question is about anything.", destination="demo2", project_id=demo_project3.id))
        
        demo_project1.users.append(db_user)
        demo_project2.users.append(db_user)
        demo_project3.users.append(db_user)
        
    dbi.commit()
    dbi.close()
    print("Database initialized.")
    print("Default LLMs initialized.")
    print("Default admin user created (admin:" + default_password + ").")

class Database:

    def create_user(self, db, username, password, admin=False, private=False):
        if password:
            hash = pwd_context.hash(password)
        else:
            hash = None
        db_user = UserDatabase(
            username=username, hashed_password=hash, is_admin=admin, is_private=private)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def create_llm(self, db, name, class_name, options, privacy, description, type):
        db_llm = LLMDatabase(
            name=name, class_name=class_name, options=options, privacy=privacy, description=description, type=type)
        db.add(db_llm)
        db.commit()
        db.refresh(db_llm)
        return db_llm

    def get_users(self, db):
        users = db.query(UserDatabase).all()
        return users
    
    def get_llms(self, db):
        llms = db.query(LLMDatabase).all()
        return llms

    def get_llm_by_name(self, db, name):
        llm = db.query(LLMDatabase).filter(
            LLMDatabase.name == name).first()
        return llm

    def get_user_by_apikey(self, db, apikey):
        user = db.query(UserDatabase).filter(
            UserDatabase.api_key == apikey).first()
        return user

    def get_user_by_username(self, db, username):
        user = db.query(UserDatabase).filter(
            UserDatabase.username == username).first()
        return user

    def update_user(self, db, user: User, userc: UserUpdate):
        if userc.password is not None:
            hash = pwd_context.hash(userc.password)
            user.hashed_password = hash

        if userc.is_admin is not None:
            user.is_admin = userc.is_admin

        if userc.is_private is not None:
            user.is_private = userc.is_private

        if userc.sso is not None:
            user.sso = userc.sso

        if userc.api_key is not None:
            user.api_key = userc.api_key

        db.commit()
        return True

    def update_llm(self, db, llm: LLMModel, llmUpdate: LLMUpdate):
        if llmUpdate.class_name is not None and llm.class_name != llmUpdate.class_name:
          llm.class_name = llmUpdate.class_name

        if llmUpdate.options is not None and llm.options != llmUpdate.options:
            llm.options = llmUpdate.options

        if llmUpdate.privacy is not None and llm.privacy != llmUpdate.privacy:
            llm.privacy = llmUpdate.privacy

        if llmUpdate.description is not None and llm.description != llmUpdate.description:
            llm.description = llmUpdate.description

        if llmUpdate.type is not None and llm.type != llmUpdate.type:
            llm.type = llmUpdate.type

        db.commit()
        return True
    
    def delete_llm(self, db, llm):
        db.delete(llm)
        db.commit()
        return True

    def get_user_by_id(self, db, id):
        user = db.query(UserDatabase).filter(UserDatabase.id == id).first()
        return user

    def delete_user(self, db, user):
        db.delete(user)
        db.commit()
        return True

    def get_project_by_name(self, db, name):
        project = db.query(ProjectDatabase).filter(
            ProjectDatabase.name == name).first()
        return project

    def create_project(
            self,
            db,
            name,
            embeddings,
            llm,
            vectorstore,
            type):
        db_project = ProjectDatabase(
            name=name,
            embeddings=embeddings,
            llm=llm,
            vectorstore=vectorstore,
            type=type)
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project

    def get_projects(self, db):
        projects = db.query(ProjectDatabase).all()
        return projects

    def delete_project(self, db, project):
        db.delete(project)
        db.commit()
        return True

    def update_project(self, db):
        db.commit()
        return True

    def editProject(self, name, projectModel: ProjectModelUpdate, db):
        proj_db = dbc.get_project_by_name(db, name)
        if proj_db is None:
            return False

        changed = False
        if projectModel.llm is not None and proj_db.llm != projectModel.llm:
            proj_db.llm = projectModel.llm
            changed = True

        if projectModel.system is not None and proj_db.system != projectModel.system:
            proj_db.system = projectModel.system
            changed = True

        if projectModel.censorship is not None and proj_db.censorship != projectModel.censorship:
            proj_db.censorship = projectModel.censorship
            changed = True

        if projectModel.k is not None and proj_db.k != projectModel.k:
            proj_db.k = projectModel.k
            changed = True

        if projectModel.score is not None and proj_db.score != projectModel.score:
            proj_db.score = projectModel.score
            changed = True

        if projectModel.connection is not None and proj_db.system != projectModel.connection and "://xxxx:xxxx@" not in projectModel.connection:
            proj_db.connection = projectModel.connection
            changed = True
        
        if projectModel.tables is not None and proj_db.tables != projectModel.tables:
            proj_db.tables = projectModel.tables
            changed = True
            
        if projectModel.llm_rerank is not None and proj_db.llm_rerank != projectModel.llm_rerank:
            proj_db.llm_rerank = projectModel.llm_rerank
            changed = True
        
        if projectModel.colbert_rerank is not None and proj_db.colbert_rerank != projectModel.colbert_rerank:
            proj_db.colbert_rerank = projectModel.colbert_rerank
            changed = True
        
        if projectModel.entrances is not None:
            proj_db.entrances = []
            for entrance in projectModel.entrances:
                proj_db.entrances.append(RouterEntrancesDatabase(
                    name=entrance.name, description=entrance.description, destination=entrance.destination, project_id=proj_db.id))
            changed = True

        if changed:
            dbc.update_project(db)

        return True


dbc = Database()
