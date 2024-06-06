from fastapi import HTTPException
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase

from llama_index.core.tools import ToolMetadata
from llama_index.core.selectors import LLMSingleSelector
from sqlalchemy.orm import Session

class Router(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        choices = []
          
        for entrance in project.model.entrances:
            choices.append(ToolMetadata(description=entrance.description, name=entrance.name))
        

        selector = LLMSingleSelector.from_defaults(llm=self.brain.getLLM(project.model.llm, db).llm)
        selector_result = selector.select(
            choices, query=questionModel.question
        )
        
        projectNameDest = project.model.entrances[selector_result.selections[0].index].destination
        return projectNameDest