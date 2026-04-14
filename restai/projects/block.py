import json
import logging
from uuid import uuid4

from fastapi import HTTPException

from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.projects.block_interpreter import BlockInterpreter

logger = logging.getLogger(__name__)


class Block(ProjectBase):

    def _get_workspace(self, project: Project) -> dict:
        workspace = None
        if project.props.options:
            opts = project.props.options
            if hasattr(opts, "blockly_workspace"):
                workspace = opts.blockly_workspace
            elif isinstance(opts, dict):
                workspace = opts.get("blockly_workspace")
        if not workspace:
            raise HTTPException(
                status_code=400,
                detail="No block workspace configured for this project.",
            )
        return workspace

    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        from restai.agent2.memory import get_session, save_session
        from restai.agent2.types import Message, TextBlock, user_text_message

        workspace = self._get_workspace(project)
        chat_id = chat_model.id or str(uuid4())

        output = {
            "question": chat_model.question,
            "type": "block",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat_id,
        }

        if self.check_input_guard(project, chat_model.question, user, db, output):
            yield output
            return

        # Load session and add user message
        session = await get_session(self.brain, chat_id)
        session.messages.append(user_text_message(chat_model.question))

        interpreter = BlockInterpreter(
            workspace_json=workspace,
            input_text=chat_model.question,
            brain=self.brain,
            user=user,
            db=db,
            image=chat_model.image,
            chat_id=chat_id,
            widget_context=getattr(project, "widget_context", None),
        )
        result = await interpreter.execute()
        output["answer"] = result or ""

        # Save assistant response to session
        session.messages.append(
            Message(role="assistant", content=[TextBlock(text=output["answer"])])
        )
        await save_session(self.brain, chat_id, session)

        yield output

    async def question(self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper):
        workspace = self._get_workspace(project)

        interpreter = BlockInterpreter(
            workspace_json=workspace,
            input_text=question_model.question,
            brain=self.brain,
            user=user,
            db=db,
            image=question_model.image,
            widget_context=getattr(project, "widget_context", None),
        )
        result = await interpreter.execute()

        output = {
            "question": question_model.question,
            "type": "block",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "answer": result,
        }

        yield output
