import json
import logging

from fastapi import HTTPException

from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.projects.block_interpreter import BlockInterpreter

logger = logging.getLogger(__name__)


class Block(ProjectBase):

    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(
            status_code=400,
            detail="Chat mode not available for block projects. Use question mode.",
        )
        yield  # unreachable; makes this an async generator as chat_main expects

    async def question(self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper):
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

        interpreter = BlockInterpreter(
            workspace_json=workspace,
            input_text=question_model.question,
            brain=self.brain,
            user=user,
            db=db,
            image=question_model.image,
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
