from fastapi import HTTPException
from requests import Session
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from app.tools import tokens_from_string
from llama_index.core.base.llms.types import ChatMessage


class Inference(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        model = self.brain.getLLM(project.model.llm, db)

        sysTemplate = questionModel.system or project.model.system or self.brain.defaultSystem
        model.llm.system_prompt = sysTemplate

        messages = [
            ChatMessage(
                role="system", content=sysTemplate
            ),
            ChatMessage(role="user", content=questionModel.question),
        ]

        try:
            if(questionModel.stream):
                respgen = model.llm.stream_chat(messages)
                for text in respgen:
                    yield "data: " + text.delta + "\n\n"
                yield "event: close\n\n"
            else:
                resp = model.llm.chat(messages)
                output = {
                    "question": questionModel.question,
                    "answer": resp.message.content.strip(),
                    "type": "inference"
                }
                output["tokens"] = {
                    "input": tokens_from_string(output["question"]),
                    "output": tokens_from_string(output["answer"])
                }
                yield output
        except Exception as e:              
            if questionModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e
      