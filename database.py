import json
import os
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from restai.config import (
    MYSQL_HOST,
    MYSQL_URL,
    POSTGRES_HOST,
    POSTGRES_URL,
    RESTAI_DEFAULT_PASSWORD,
    RESTAI_DEMO,
)
from restai.models.databasemodels import (
    Base,
    LLMDatabase,
    ProjectDatabase,
    RouterEntrancesDatabase,
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
            hashed_password=pwd_context.hash(default_password),
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
        
        if RESTAI_DEMO == True:
            print("Creating demo scenario...")
            db_user = UserDatabase(
                username="demo",
                hashed_password=pwd_context.hash("demo"),
                is_private=True,
            )
            dbi.add(db_user)
            
            dbi.commit()
            
            demo_project1 = ProjectDatabase(
                name="demo1",
                type="inference",
                system="Always end your answers with 'beep beep'.",
                llm="llama31_8b",
                creator=db_user.id
            )
            demo_project2 = ProjectDatabase(
                name="demo2",
                type="inference",
                system="Always end your answers with 'boop boop'.",
                llm="llama31_8b",
                creator=db_user.id
            )
            demo_project3 = ProjectDatabase(
                name="router1",
                type="router",
                llm="llama31_8b",
                creator=db_user.id
            )
            demo_project4 = ProjectDatabase(
                name="rag1",
                type="rag",
                llm="llama31_8b",
                embeddings= "all-mpnet-base-v2",
                vectorstore="chromadb",
                creator=db_user.id
            )
            demo_project5 = ProjectDatabase(
                name="vision1",
                type="vision",
                llm="llava16_13b",
                creator=db_user.id
            )
            dbi.add(demo_project1)
            dbi.add(demo_project2)
            dbi.add(demo_project3)
            dbi.add(demo_project4)
            dbi.add(demo_project5)
            dbi.commit()
            
            demo_project3.entrances.append(RouterEntrancesDatabase(
                name="choice1", description="The question is about the meaning of life.", destination="demo1", project_id=demo_project3.id))
            demo_project3.entrances.append(RouterEntrancesDatabase(
                name="choice2", description="The question is about anything.", destination="demo2", project_id=demo_project3.id))
            
            demo_project1.users.append(db_user)
            demo_project2.users.append(db_user)
            demo_project3.users.append(db_user)
            demo_project4.users.append(db_user)
            demo_project5.users.append(db_user)
            
            demo_team = TeamDatabase(
                name="Demo Team",
                description="A team for demonstration purposes",
                created_at=datetime.now(),
                creator=db_user.id
            )
            dbi.add(demo_team)
            dbi.commit()
            
            # Add the demo user to the team
            demo_team.users.append(db_user)
            demo_team.admins.append(db_user)
            
            # Add the required LLMs and embeddings to the demo team
            llama_llm = dbi.query(LLMDatabase).filter(LLMDatabase.name == "llama31_8b").first()
            llava_llm = dbi.query(LLMDatabase).filter(LLMDatabase.name == "llava16_13b").first()
            mpnet_embedding = dbi.query(EmbeddingDatabase).filter(EmbeddingDatabase.name == "all-mpnet-base-v2").first()
            
            if llama_llm:
                demo_team.llms.append(llama_llm)
            if llava_llm:
                demo_team.llms.append(llava_llm)
            if mpnet_embedding:
                demo_team.embeddings.append(mpnet_embedding)
                
            # Associate the projects with the team
            demo_team.projects.append(demo_project1)
            demo_team.projects.append(demo_project2)
            demo_team.projects.append(demo_project3)
            demo_team.projects.append(demo_project4)
            demo_team.projects.append(demo_project5)
            
            dbi.commit()
            
        dbi.commit()
        dbi.close()
        print("Database initialized.")
        print("Default LLMs initialized.")
        print("Default admin user created (admin:" + default_password + ").")
    else:
        print("Database already initialized.")