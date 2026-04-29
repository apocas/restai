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
    """App-builder project type.

    Holds a generated TypeScript-frontend + PHP-backend + SQLite app on disk.
    Source files live at <install_root>/apps/<project_id>/ and are edited via
    the /builder UI; a Docker container previews them live and deploy ships
    the result via FTP/SFTP or ZIP. The LLM attached to the project is used
    only at builder-time for code generation — it is never called from this
    handler. chat() / question() return a hint pointing the caller to the
    builder rather than raising, so the existing chat UI doesn't choke when
    a user lands on the playground for an app project.
    """

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
