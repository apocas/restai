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
    SQLITE_PATH,
)
from restai.models.databasemodels import (
    ApiKeyDatabase,
    Base,
    ProjectDatabase,
    SettingDatabase,
    UserDatabase,
    TeamDatabase
)

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
    sqlite_path = SQLITE_PATH or "./restai.db"
    print(f"Using sqlite database at {sqlite_path}")
    engine = create_engine(
        f"sqlite:///{sqlite_path}",
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

def _stamp_alembic_head():
    # After a fresh `create_all`, the schema already matches HEAD. If we
    # leave the `alembic_version` table empty, the next `migrate.py
    # upgrade` will replay every migration from 000 against that
    # already-current schema — and the first column-drop migration
    # explodes with KeyError because the column was never created.
    # Stamping head writes the current revision into alembic_version so
    # subsequent upgrades start from the right baseline.
    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    command.stamp(cfg, "head")


if os.getenv("RESTAI_DB_SCHEMA"):
    Base.metadata.create_all(bind=engine)
    # Schema-only bootstrap still needs to mark Alembic at HEAD —
    # otherwise the next `make migrate` replays every revision from
    # 001 against an already-current schema and dies on duplicate
    # column / table errors.
    _stamp_alembic_head()
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

        dbi.close()
        _stamp_alembic_head()
        print("Database initialized.")
        print("Default admin user created (admin:" + default_password + ").")
    else:
        # Ensure new tables are created on existing databases
        Base.metadata.create_all(bind=engine, checkfirst=True)
        print("Database already initialized.")
