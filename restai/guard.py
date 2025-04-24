from typing import Optional

from llama_index.core.base.llms.types import ChatMessage, MessageRole

from restai.brain import Brain
from restai.database import DBWrapper
from restai.llm import LLM
from restai.project import Project


class Guard:
    def __init__(self, projectName: str, brain: Brain, db: DBWrapper):
        self.brain: Brain = brain
        self.project: Optional[Project] = brain.find_project(projectName, db)
        self.db: DBWrapper = db

    def verify(self, prompt: str) -> bool:
        model: Optional[LLM] = self.brain.get_llm(self.project.props.llm, self.db)

        sysTemplate: Optional[str] = self.project.props.system
        model.llm.system_prompt = sysTemplate

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate),
            ChatMessage(
                role=MessageRole.USER,
                content=f'Analyze the following text:\n"{prompt}"',
            ),
        ]

        resp = model.llm.chat(messages)
        answer: str = resp.message.content.strip()

        match answer:
            case "BAD":
                return True
            case "GOOD":
                return False
            case _:
                return True
