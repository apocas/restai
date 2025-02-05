
from sqlalchemy.schema import CreateTable

from sqlalchemy.dialects import mysql

from app.models.databasemodels import LLMDatabase, OutputDatabase

print(CreateTable(OutputDatabase.__table__).compile(dialect=mysql.dialect()))
print(CreateTable(LLMDatabase.__table__).compile(dialect=mysql.dialect()))