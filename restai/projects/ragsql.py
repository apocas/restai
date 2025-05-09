from fastapi import HTTPException
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.tools import tokens_from_string
from llama_index.core.utilities.sql_wrapper import SQLDatabase
from llama_index.core.indices.struct_store.sql_query import NLSQLTableQueryEngine
from sqlalchemy import create_engine


class RAGSql(ProjectBase):

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")

    async def question(self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper):
        model = self.brain.get_llm(project.props.llm, db)

        engine = create_engine(project.props.connection)

        sql_database = SQLDatabase(engine)

        tables = None
        if hasattr(questionModel, 'tables') and questionModel.tables is not None:
            tables = questionModel.tables
        elif project.props.tables:
            tables = [table.strip() for table in project.props.tables.split(',')]

        query_engine = NLSQLTableQueryEngine(
            llm=model.llm,
            sql_database=sql_database,
            tables=tables,
        )

        question = (project.props.system or self.brain.defaultSystem) + "\n Question: " + questionModel.question

        try:
            response = query_engine.query(question)
        except Exception as e:
            raise e

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": [response.metadata['sql_query']],
            "type": "questionsql",
            "project": project.props.name
        }
        
        output["tokens"] = {
          "input": tokens_from_string(output["question"]),
          "output": tokens_from_string(output["answer"])
        }

        return output