import json

from llama_index.core.agent import ReActAgent

from restai import tools, config
from restai.chat import Chat
from restai.database import DBWrapper
from restai.guard import Guard
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase


class Agent(ProjectBase):
  
    @staticmethod
    def output(agent, prompt, output, project):
        done = False
        iterations = 0
        resp_reasoning = ""
        steps = []
        
        task = agent.create_task(prompt)
        
        while not done:
            step_output = agent.run_step(task.task_id)
            step_final = {"actions": [], "output": ""}
            if step_output.output.sources:
                for source in step_output.output.sources:
                    resp_reasoning += "Action: " + source.tool_name + "\n"
                    resp_reasoning += "Action Input: " + str(source.raw_input) + '\n'
                    resp_reasoning += "Action Output: " + str(source.raw_output) + '\n'
                    step_final["actions"].append({"action": source.tool_name, "input": source.raw_input, "output": str(source.raw_output)})
            step_final["output"] = step_output.output.response
            steps.append(step_final)
            
            resp_reasoning += step_output.output.response + '\n'
            
            done = step_output.is_last
            iterations += 1
            
            if not done and iterations > config.AGENT_MAX_ITERATIONS:
                output["answer"] = project.model.censorship or "I'm sorry, I tried my best..."
                output["reasoning"] = {"output": "", "steps": []}
                break
        
        if done:
            response = agent.finalize_response(task.task_id)
            output["answer"] = str(response)
            output["reasoning"] = {"output": resp_reasoning, "steps": steps}
            
        return output
  
    def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        chat: Chat = Chat(chatModel, self.brain.chat_store)
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
          "id": chat.chat_id
        }
              
        if project.model.guard:
            guard = Guard(project.model.guard, self.brain, db)
            if guard.verify(chatModel.question):
                output["answer"] = project.model.censorship or self.brain.defaultCensorship
                output["guard"] = True
                self.brain.post_processing_counting(output)
                yield output
                
        model = self.brain.get_llm(project.model.llm, db)
        
        tools_u = self.brain.get_tools(set((project.model.tools or "").split(",")))
        if len(tools_u) == 0:
            chatModel.question += "\nDont use any tool just respond to the user."
        
        agent = ReActAgent.from_tools(tools_u, llm=model.llm, context=project.model.system, memory=chat.memory, max_iterations=config.AGENT_MAX_ITERATIONS, verbose=True)
        
        try:
            if chatModel.stream:
                resp_gen = agent.stream_chat(chatModel.question)
                response = ""
                for text in resp_gen.response_gen:
                    response += text
                    yield "data: " + json.dumps({"text": text}) + "\n\n"
                output["answer"] = response
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                output = self.output(agent, chatModel.question, output, project)
                
                self.brain.post_processing_counting(output)
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
                    self.brain.post_processing_counting(output)
                    yield output
            raise e
  
    def question(self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper):
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
                self.brain.post_processing_counting(output)
                yield output
                
        model = self.brain.get_llm(project.model.llm, db)
        
        toolsu = self.brain.get_tools((project.model.tools or "").split(","))
        
        if len(toolsu) == 0:
            questionModel.question += "\nDont use any tool just respond to the user."

        agent = ReActAgent.from_tools(toolsu, llm=model.llm, context=questionModel.system or project.model.system, max_iterations=config.AGENT_MAX_ITERATIONS, verbose=True)
        
        output = self.output(agent, questionModel.question, output, project)
               
        self.brain.post_processing_counting(output)

        yield output