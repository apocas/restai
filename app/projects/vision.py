from fastapi import HTTPException
from llama_index.core.schema import ImageDocument
from langchain.agents import initialize_agent
from app.llms.workers.dalle import DalleImage
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from sqlalchemy.orm import Session
from langchain_community.chat_models import ChatOpenAI
from app.config import RESTAI_GPU


class Vision(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        image = None
        output = ""
        isprivate = user.is_private

        tools = [
            DalleImage()
        ]
        
        if RESTAI_GPU:
            from app.llms.workers.stablediffusion import StableDiffusionImage
            from app.llms.workers.describeimage import DescribeImage
            from app.llms.workers.instantid import InstantID
            tools.append(StableDiffusionImage())
            tools.append(DescribeImage())
            tools.append(InstantID())

        if isprivate:
            tools.pop(0)

        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

        agent = initialize_agent(
            tools, llm, agent="zero-shot-react-description", verbose=False)
        
        outputAgent = agent.run(questionModel.question, tags=[questionModel])
        

        if isinstance(outputAgent, str):
            output = outputAgent
        else:
            if outputAgent["type"] == "describeimage":
                model = self.brain.getLLM(project.model.llm, db)

                try:
                    response = model.llm.complete(prompt=questionModel.question, image_documents=[ImageDocument(image=questionModel.image)])
                except Exception as e:
                    raise e
                
                output = response.text
                image = questionModel.image
            else:
                output = outputAgent["prompt"]
                image = outputAgent["image"]
                
        outputf = {
            "question": questionModel.question,
            "answer": output,
            "image": image,
            "sources": [],
            "type": "vision"
        }

        return outputf