import logging
from uuid import uuid4

from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase

logger = logging.getLogger(__name__)


_BUILDER_HINT = (
    "This is an app-builder project. Open the in-browser builder at "
    "/admin/project/{id}/builder to edit the generated app's source files, "
    "preview it live, and deploy. The chat / question API is intentionally "
    "inactive on this project type."
)


class App(ProjectBase):
    """App-builder project type; chat/question return a builder hint instead of calling an LLM."""

    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        chat_id = chat_model.id or str(uuid4())
        yield {
            "question": chat_model.question,
            "answer": _BUILDER_HINT.format(id=project.props.id),
            "type": "app",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat_id,
        }

    async def question(self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper):
        yield {
            "question": question_model.question,
            "answer": _BUILDER_HINT.format(id=project.props.id),
            "type": "app",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }
