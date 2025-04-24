from fastapi import HTTPException

from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase

from llama_index.core.tools import ToolMetadata
from llama_index.core.selectors import LLMSingleSelector

class Router(ProjectBase):
  
    def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper):
        choices = []
          
        for entrance in project.props.entrances:
            choices.append(ToolMetadata(description=entrance.description, name=entrance.name))
        

        selector = LLMSingleSelector.from_defaults(llm=self.brain.get_llm(project.props.llm, db).llm)
        selector_result = selector.select(
            choices, query=questionModel.question
        )
        
        projectNameDest = project.props.entrances[selector_result.selections[0].index].destination
        return projectNameDest