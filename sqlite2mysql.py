from sqlalchemy import create_engine, select

from app.config import MYSQL_URL, SQLITE_PATH
from app.databasemodels import Base

engine_lite = create_engine("sqlite:///" + SQLITE_PATH)

engine_mysql = create_engine(MYSQL_URL)

Base.metadata.create_all(engine_mysql)

with engine_lite.connect() as conn_lite:
    with engine_mysql.connect() as conn_mysql:
        for table in Base.metadata.sorted_tables:
            print(table.c)
            for row in conn_lite.execute(select(table.c)):
                print(row._mapping)
                conn_mysql.execute(table.insert().values(row._mapping))
                conn_mysql.commit()
