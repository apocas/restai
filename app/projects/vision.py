from fastapi import HTTPException
from llama_index.core.schema import ImageDocument
from langchain.agents import initialize_agent
from app.guard import Guard
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
        output = {
          "question": questionModel.question,
          "type": "vision",
          "sources": [],
          "guard": False,
          "tokens": {
              "input": 0,
              "output": 0
          },
          "project": project.model.name
        }
        
        if project.model.guard:
            guard = Guard(project.model.guard, self.brain, db)
            if guard.verify(questionModel.question):
                output["answer"] = project.model.censorship or self.brain.defaultCensorship
                output["guard"] = True
                output["tokens"] = {
                  "input": tools.tokens_from_string(output["question"]),
                  "output": tools.tokens_from_string(output["answer"])
                }
                return output
                
        image = None
        output_temp = ""
        isprivate = user.is_private

        tools = [
            DalleImage()
        ]
        
        if RESTAI_GPU:
            from app.llms.workers.stablediffusion import StableDiffusionImage
            from app.llms.workers.describeimage import DescribeImage
            from app.llms.workers.instantid import InstantID
            from app.llms.workers.flux import FluxImage
            tools.append(StableDiffusionImage())
            tools.append(FluxImage())
            tools.append(DescribeImage())
            tools.append(InstantID())

        if isprivate:
            tools.pop(0)

        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

        agent = initialize_agent(
            tools, llm, agent="zero-shot-react-description", verbose=False)
        
        outputAgent = agent.run(questionModel.question, tags=[questionModel])
        

        if isinstance(outputAgent, str):
            output_temp = outputAgent
        else:
            if outputAgent["type"] == "describeimage":
                model = self.brain.get_llm(project.model.llm, db)

                try:
                    response = model.llm.complete(prompt=questionModel.question, image_documents=[ImageDocument(image=questionModel.image)])
                except Exception as e:
                    raise e
                
                output_temp = response.text
                image = questionModel.image
            else:
                output_temp = outputAgent["prompt"]
                image = outputAgent["image"]
                
        output["answer"] = output_temp
        output["image"] = image

        return output