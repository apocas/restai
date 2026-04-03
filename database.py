import json
import os
from datetime import datetime

import bcrypt
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from restai.config import (
    MYSQL_HOST,
    MYSQL_URL,
    POSTGRES_HOST,
    POSTGRES_URL,
    RESTAI_DEFAULT_PASSWORD,
)
from restai.models.databasemodels import (
    ApiKeyDatabase,
    Base,
    LLMDatabase,
    ProjectDatabase,
    SettingDatabase,
    UserDatabase,
    EmbeddingDatabase,
    TeamDatabase
)
from restai.tools import DEFAULT_LLMS, DEFAULT_EMBEDDINGS

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

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

if os.getenv("RESTAI_DB_SCHEMA"):
    Base.metadata.create_all(bind=engine)
else:
    if "users" not in inspect(engine).get_table_names():
        print("Initializing database...")
        default_password = RESTAI_DEFAULT_PASSWORD
        Base.metadata.create_all(bind=engine)
        dbi = SessionLocal()
        db_user = UserDatabase(
            username="admin",
            hashed_password=hash_password(default_password),
            is_admin=True)
        dbi.add(db_user)
        
        dbi.commit()
        
        # Create a default team and add the admin user to it
        default_team = TeamDatabase(
            name="Default Team",
            description="Default team created during initialization",
            created_at=datetime.now()
        )
        dbi.add(default_team)
        dbi.commit()
        
        # Add admin as both a team member and a team admin
        default_team.users.append(db_user)
        default_team.admins.append(db_user)
        dbi.commit()

        for llm in DEFAULT_LLMS:
            llm_class, llm_args, privacy, description, typel, input_cost, output_cost = DEFAULT_LLMS[llm]
            db_llm = LLMDatabase(
                name=llm,
                class_name=llm_class,
                options=json.dumps(llm_args),
                privacy=privacy,
                description=description,
                type=typel,
                input_cost=input_cost,
                output_cost=output_cost
            )
            dbi.add(db_llm)
            
            # Add this LLM to the default team
            default_team.llms.append(db_llm)
            
        dbi.commit()
        
        for embedding in DEFAULT_EMBEDDINGS:
            embedding_class, embedding_args, privacy, description, dimension = DEFAULT_EMBEDDINGS[embedding]
            db_embedding = EmbeddingDatabase(
                name=embedding,
                class_name=embedding_class,
                options=json.dumps(embedding_args),
                privacy=privacy,
                description=description,
                dimension=dimension
            )
            dbi.add(db_embedding)
            
            # Add this embedding model to the default team
            default_team.embeddings.append(db_embedding)
            
        dbi.commit()
        
        dbi.commit()
        dbi.close()
        print("Database initialized.")
        print("Default LLMs initialized.")
        print("Default admin user created (admin:" + default_password + ").")
    else:
        print("Database already initialized.")