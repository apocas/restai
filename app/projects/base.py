from app.brain import Brain
from abc import ABC, abstractmethod
from app.models.models import ChatModel, QuestionModel, User
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.project import Project


class ProjectBase(ABC):
    def __init__(self, brain: Brain):
        self.brain = brain

    @abstractmethod
    def chat(self, project: Project, chat_model: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')

    @abstractmethod
    def question(self, project: Project, question_model: QuestionModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Question mode not available for this project type."}')