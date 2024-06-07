import json
from fastapi import HTTPException
from requests import Session
from app import tools
from app.guard import Guard
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from app.tools import tokens_from_string
from llama_index.core.base.llms.types import ChatMessage


class Inference(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        raise HTTPException(status_code=400, detail='{"error": "Chat mode not available for this project type."}')
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        output = {
          "question": questionModel.question,
          "type": "inference",
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
                yield output
                
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
                response = ""
                for text in respgen:
                    response += text.delta
                    yield "data: " + json.dumps({"text": text.delta}) + "\n\n"
                output["answer"] = response
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                resp = model.llm.chat(messages)
                output["answer"] = resp.message.content.strip()
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
      