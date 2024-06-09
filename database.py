import json

from passlib.context import CryptContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.config import (
    MYSQL_HOST,
    MYSQL_URL,
    POSTGRES_HOST,
    POSTGRES_URL,
    RESTAI_DEFAULT_PASSWORD,
    RESTAI_DEMO,
)
from app.models.databasemodels import (
    Base,
    LLMDatabase,
    ProjectDatabase,
    RouterEntrancesDatabase,
    UserDatabase,
)
from app.tools import DEFAULT_LLMS

if MYSQL_HOST:
    print("Using MySQL database")
    engine = create_engine(MYSQL_URL,
                           pool_size=30,
                           max_overflow=100,
                           pool_recycle=900)
elif POSTGRES_HOST:
    print("Using PostgreSQL database")
    engine = create_engine(POSTGRES_URL,
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

# Forcefully raise on failed connection
try:
    with engine.connect() as conn:
        pass
except Exception:
    raise

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


if "users" not in inspect(engine).get_table_names():
    print("Initializing database...")
    default_password = RESTAI_DEFAULT_PASSWORD
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
    
    if RESTAI_DEMO:
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
            llm="llama3_8b",
            creator=db_user.id
        )
        demo_project2 = ProjectDatabase(
            name="demo2",
            type="inference",
            system="Always end your answers with 'boop boop'.",
            llm="llama3_8b",
            creator=db_user.id
        )
        demo_project3 = ProjectDatabase(
            name="router1",
            type="router",
            llm="llama3_8b",
            creator=db_user.id
        )
        demo_project4 = ProjectDatabase(
            name="rag1",
            type="rag",
            llm="llama3_8b",
            embeddings= "all-mpnet-base-v2",
            vectorstore="chromadb",
            creator=db_user.id
        )
        dbi.add(demo_project1)
        dbi.add(demo_project2)
        dbi.add(demo_project3)
        dbi.add(demo_project4)
        dbi.commit()
        
        demo_project3.entrances.append(RouterEntrancesDatabase(
            name="choice1", description="The question is about the meaning of life.", destination="demo1", project_id=demo_project3.id))
        demo_project3.entrances.append(RouterEntrancesDatabase(
            name="choice2", description="The question is about anything.", destination="demo2", project_id=demo_project3.id))
        
        demo_project1.users.append(db_user)
        demo_project2.users.append(db_user)
        demo_project3.users.append(db_user)
        demo_project4.users.append(db_user)
        
    dbi.commit()
    dbi.close()
    print("Database initialized.")
    print("Default LLMs initialized.")
    print("Default admin user created (admin:" + default_password + ").")
else:
    print("Database already initialized.")