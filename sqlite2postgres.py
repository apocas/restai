from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text

from restai.config import POSTGRES_URL, SQLITE_PATH
from restai.models.databasemodels import Base

engine_lite = create_engine("sqlite:///" + SQLITE_PATH)

engine_pg = create_engine(POSTGRES_URL)

Base.metadata.create_all(engine_pg)

with engine_lite.connect() as conn_lite:
    with engine_pg.connect() as conn_pg:
        for table in Base.metadata.sorted_tables:
            print(table.c)
            for row in conn_lite.execute(select(table.c)):
                print(row._mapping)
                conn_pg.execute(table.insert().values(row._mapping))
                conn_pg.commit()

# Bump identity sequences. Postgres SERIAL/IDENTITY sequences don't
# track explicit-value inserts (unlike MySQL AUTO_INCREMENT), so after
# a bulk copy the next user-created row collides with an existing PK.
# `pg_get_serial_sequence` returns NULL for non-serial PKs, which we
# skip. `setval(seq, MAX(pk))` advances each sequence past the
# imported max.
with engine_pg.connect() as conn_pg:
    for table in Base.metadata.sorted_tables:
        for col in table.primary_key.columns:
            seq_row = conn_pg.execute(
                text("SELECT pg_get_serial_sequence(:t, :c)"),
                {"t": table.name, "c": col.name},
            ).scalar()
            if not seq_row:
                continue
            max_id = conn_pg.execute(
                text(f"SELECT MAX({col.name}) FROM {table.name}")
            ).scalar()
            if max_id is None:
                continue
            conn_pg.execute(text("SELECT setval(:s, :v)"), {"s": seq_row, "v": max_id})
        conn_pg.commit()

# Stamp the destination at alembic head. Without this, alembic_version
# is empty and the next `make migrate` runs every revision from base
# against a DB that already has the tables — first non-idempotent
# migration explodes on "table already exists". `stamp` only writes the
# version row; no DDL.
cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", POSTGRES_URL)
command.stamp(cfg, "head")
