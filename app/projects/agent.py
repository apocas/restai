import json
from requests import Session
from app import tools, config
from app.chat import Chat
from app.guard import Guard
from app.models.models import ChatModel, QuestionModel, User
from app.project import Project
from app.projects.base import ProjectBase
from llama_index.core.agent import ReActAgent

class Agent(ProjectBase):
  
    def output(self, agent, prompt, output, project):
        done = False
        iterations = 0
        
        task = agent.create_task(prompt)
        
        while not done:
            step_output = agent.run_step(task.task_id)
            done = step_output.is_last
            iterations += 1
            if not done and iterations > config.AGENT_MAX_ITERATIONS:
                output["answer"] = project.model.censorship or "I'm sorry, I tried my best..."
                break
        
        if done:
            steps = []
            resp_reasoning = ""
            completed_steps = agent.get_completed_steps(task.task_id)
            for step in completed_steps:
                step_output = step.output
                step_final = {"actions": [], "output": step_output.response}
                for source in step_output.sources:
                    resp_reasoning += "Action: " + source.tool_name + "\n"
                    resp_reasoning += "Action Input: " + str(source.raw_input) + '\n'
                    step_final["actions"].append({"action": source.tool_name, "input": source.raw_input})
                    
                resp_reasoning += step_output.response + '\n'
                steps.append(step_final)
            response = agent.finalize_response(task.task_id)
            output["answer"] = str(response)
            output["reasoning"] = {"output": resp_reasoning, "steps": steps}
            
        return output
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: Session):
        chat = Chat(chatModel, self.brain.chatstore)
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
                
        model = self.brain.get_llm(project.model.llm, db)
        
        toolsu = self.brain.get_tools((project.model.tools or "").split(","))
        if len(toolsu) == 0:
            chatModel.question += "\nDont use any tool just respond to the user."
        
        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=project.model.system, memory=chat.memory, max_iterations=config.AGENT_MAX_ITERATIONS, verbose=True)
        
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
                output = self.output(agent, chatModel.question, output, project)
                
                output["tokens"] = {
                    "input": tools.tokens_from_string(output["question"]),
                    "output": tools.tokens_from_string(output["answer"])
                }
                yield output
        except Exception as e:
            if chatModel.stream:
                if str(e) == "Reached max iterations.":
                    yield "data: I'm sorry, I tried my best...\n"
                else:
                    yield "data: Inference failed\n" 
                yield "event: error\n\n"
            else:
                if str(e) == "Reached max iterations.":
                    output["answer"] = project.model.censorship or "I'm sorry, I tried my best..."
                    output["tokens"] = {
                        "input": tools.tokens_from_string(output["question"]),
                        "output": tools.tokens_from_string(output["answer"])
                    }
                    yield output
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
                
        model = self.brain.get_llm(project.model.llm, db)
        
        toolsu = self.brain.get_tools((project.model.tools or "").split(","))
        
        if len(toolsu) == 0:
            questionModel.question += "\nDont use any tool just respond to the user."

        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=questionModel.system or project.model.system, max_iterations=config.AGENT_MAX_ITERATIONS, verbose=True)
        
        output = self.output(agent, questionModel.question, output, project)
               
        output["tokens"] = {
            "input": tools.tokens_from_string(output["question"]),
            "output": tools.tokens_from_string(output["answer"])
        }

        yield output