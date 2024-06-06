from fastapi import HTTPException
from requests import Session
from app import tools
from app.guard import Guard
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from llama_index.core.agent import ReActAgent

class Agent(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        output = {
          "question": chatModel.question,
          "type": "agent",
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
            if guard.verify(chatModel.question):
                output["answer"] = project.model.censorship or self.brain.defaultCensorship
                output["guard"] = True
                output["tokens"] = {
                  "input": tools.tokens_from_string(output["question"]),
                  "output": tools.tokens_from_string(output["answer"])
                }
                yield output
                
        model = self.brain.getLLM(project.model.llm, db)
        chat = self.brain.memories.loadMemory(project.model.name).loadChat(chatModel)
        toolsu = []

        toolsu = self.brain.get_tools(project.model.tools.split(","))

        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=project.model.system, memory=chat.memory, max_iterations=20, verbose=True)

        resp = ""
        try:
            response = agent.chat(chatModel.question)
            resp = response.response
        except Exception as e:
            if str(e) == "Reached max iterations.":
                resp = "I'm sorry, I tried my best..."
        
        output["id"] = chat.id
        output["answer"] = resp
        output["tokens"] = {
          "input": tools.tokens_from_string(output["question"]),
          "output": tools.tokens_from_string(output["answer"])
        }

        yield output
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: Session):
        output = {
          "question": questionModel.question,
          "type": "agent",
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
        toolsu = []

        toolsu = self.brain.get_tools(project.model.tools.split(","))

        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=questionModel.system or project.model.system, max_iterations=20, verbose=True)
        
        resp = ""
        try:
            response = agent.query(questionModel.question)
            resp = response.response
        except Exception as e:
            if str(e) == "Reached max iterations.":
                resp = "I'm sorry, I tried my best..."
        
        output["answer"] = resp
        output["tokens"] = {
          "input": tools.tokens_from_string(output["question"]),
          "output": tools.tokens_from_string(output["answer"])
        }

        yield output