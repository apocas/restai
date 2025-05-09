from restai.brain import Brain
from abc import ABC, abstractmethod
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from fastapi import HTTPException
from restai.project import Project


class ProjectBase(ABC):
    def __init__(self, brain: Brain):
        self.brain: Brain = brain

    @abstractmethod
    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")

    @abstractmethod
    async def question(self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Question mode not available for this project type.")