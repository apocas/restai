from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from app.tools import tokens_from_string
from llama_index.core.utilities.sql_wrapper import SQLDatabase
from llama_index.core.indices.struct_store.sql_query import NLSQLTableQueryEngine
from sqlalchemy import create_engine


class RAGSql(ProjectBase):

    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')

    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        model = self.brain.getLLM(project.model.llm, db)

        engine = create_engine(project.model.connection)

        sql_database = SQLDatabase(engine)

        tables = None
        if hasattr(questionModel, 'tables') and questionModel.tables is not None:
            tables = questionModel.tables
        elif project.model.tables:
            tables = [table.strip() for table in project.model.tables.split(',')]

        query_engine = NLSQLTableQueryEngine(
            llm=model.llm,
            sql_database=sql_database,
            tables=tables,
        )

        question = (project.model.system or self.brain.defaultSystem) + "\n Question: " + questionModel.question

        try:
            response = query_engine.query(question)
        except Exception as e:
            raise e

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": [response.metadata['sql_query']],
            "type": "questionsql",
            "project": project.model.name
        }
        
        output["tokens"] = {
          "input": tokens_from_string(output["question"]),
          "output": tokens_from_string(output["answer"])
        }

        return output