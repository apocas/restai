import os
import json
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, LLMDatabase, ProjectDatabase, RouterEntrancesDatabase, UserDatabase
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
else:
    print("Database already initialized.")