

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from restai.config import MYSQL_URL, SQLITE_PATH
from restai.models.databasemodels import Base

sqlite_path = SQLITE_PATH or "./restai.db"
engine_lite = create_engine(f"sqlite:///{sqlite_path}")

engine_mysql = create_engine(MYSQL_URL)

Base.metadata.create_all(engine_mysql)

with engine_lite.connect() as conn_lite:
    with engine_mysql.connect() as conn_mysql:
        for table in Base.metadata.sorted_tables:
            print(table.c)
            inserted = 0
            skipped_duplicates = 0
            for row in conn_lite.execute(select(table.c)):
                print(row._mapping)
                try:
                    conn_mysql.execute(table.insert().values(row._mapping))
                    conn_mysql.commit()
                    inserted += 1
                except IntegrityError as e:
                    # Duplicate PK/unique key means this row already exists
                    # in MySQL (common when rerunning this script).
                    if getattr(getattr(e, "orig", None), "args", [None])[0] == 1062:
                        conn_mysql.rollback()
                        skipped_duplicates += 1
                        continue
                    conn_mysql.rollback()
                    raise
            print(
                f"{table.name}: inserted={inserted}, skipped_duplicates={skipped_duplicates}"
            )

# Stamp the destination at alembic head. Without this, alembic_version
# is empty and the next `make migrate` runs every revision from base
# against a DB that already has the tables — first non-idempotent
# migration explodes on "table already exists". `stamp` only writes the
# version row; no DDL.
cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", MYSQL_URL)
command.stamp(cfg, "head")
