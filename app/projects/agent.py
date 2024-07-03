import json
from requests import Session
from app import tools
from app.chat import Chat
from app.guard import Guard
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from llama_index.core.agent import ReActAgent

class Agent(ProjectBase):
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        chat = Chat(chatModel)
        output = {
          "question": chatModel.question,
          "type": "agent",
          "sources": [],
          "guard": False,
          "tokens": {
              "input": 0,
              "output": 0
          },
          "project": project.model.name,
          "id": chat.id
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
        
        toolsu = self.brain.get_tools((project.model.tools or "").split(","))

        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=project.model.system, memory=chat.memory, max_iterations=20, verbose=True)
        
        try:
            if(chatModel.stream):
                respgen = agent.stream_chat(chatModel.question)
                response = ""
                for text in respgen.response_gen:
                    response += text
                    yield "data: " + json.dumps({"text": text}) + "\n\n"
                output["answer"] = response
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                response = agent.chat(chatModel.question)
                output["answer"] = response.response
                output["tokens"] = {
                    "input": tools.tokens_from_string(output["question"]),
                    "output": tools.tokens_from_string(output["answer"])
                }
                yield output
        except Exception as e:              
            if chatModel.stream:
                yield "data: Inference failed\n" 
            elif str(e) == "Reached max iterations.":
                yield "data: I'm sorry, I tried my best...\n"
            yield "event: error\n\n"
            raise e
  
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
        
        toolsu = self.brain.get_tools((project.model.tools or "").split(","))

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