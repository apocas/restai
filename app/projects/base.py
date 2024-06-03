from app.brain import Brain

from app.models.models import ChatModel, QuestionModel, User
from sqlalchemy.orm import Session

from app.project import Project

class ProjectBase:
    def __init__(self, brain: Brain):
        self.brain = brain
        
    def entryChat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        pass
    
    def entryQuestion(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        pass