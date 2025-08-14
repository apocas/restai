import json

from llama_index.core.agent import ReActAgent, FunctionAgent

from restai import config
from restai.chat import Chat
from restai.database import DBWrapper
from restai.guard import Guard
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec


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
                    resp_reasoning += "Action Input: " + str(source.raw_input) + "\n"
                    resp_reasoning += "Action Output: " + str(source.raw_output) + "\n"
                    step_final["actions"].append(
                        {
                            "action": source.tool_name,
                            "input": source.raw_input,
                            "output": str(source.raw_output),
                        }
                    )
            step_final["output"] = step_output.output.response
            steps.append(step_final)

            resp_reasoning += step_output.output.response + "\n"

            done = step_output.is_last
            iterations += 1

            if not done and (iterations > project.props.options.max_iterations or iterations > config.AGENT_MAX_ITERATIONS):
                output["answer"] = (
                    project.props.censorship or "I'm sorry, I tried my best..."
                )
                output["reasoning"] = {"output": "", "steps": []}
                break

        if done:
            response = agent.finalize_response(task.task_id)
            output["answer"] = str(response)
            output["reasoning"] = {"output": resp_reasoning, "steps": steps}

        return output
      
    async def prepare_tools(self, project: Project):
      tools_u = self.brain.get_tools(set((project.props.options.tools or "").split(",")))
        
      if project.props.options.mcp_servers:
          for mcp_server in project.props.options.mcp_servers:
              allowed_tools = set((mcp_server.tools or "").split(","))
              mcp_client = BasicMCPClient(mcp_server.host)
              
              # Only include allowed_tools if it's not empty
              if allowed_tools and allowed_tools != {""}: 
                  mcp_tool_spec = McpToolSpec(
                      client=mcp_client,
                      allowed_tools=allowed_tools,
                  )
              else:
                  mcp_tool_spec = McpToolSpec(
                      client=mcp_client,
                  )
                  
              tools_u = tools_u + await mcp_tool_spec.to_tool_list_async()
                
      return tools_u
      

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        chat: Chat = Chat(chatModel, self.brain.chat_store)
        output = {
            "question": chatModel.question,
            "type": "agent",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat.chat_id,
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            if guard.verify(chatModel.question):
                output["answer"] = (
                    project.props.censorship or self.brain.defaultCensorship
                )
                output["guard"] = True
                self.brain.post_processing_counting(output)
                yield output

        model = self.brain.get_llm(project.props.llm, db)

        tools_u = await self.prepare_tools(project)
        
        if len(tools_u) == 0:
            chatModel.question += "\nDont use any tool just respond to the user."

        # Check if function_agent attribute exists and is True
        use_function_agent = hasattr(project.props.options, "function_agent") and project.props.options.function_agent is True
        
        if use_function_agent:
            agent = FunctionAgent.from_tools(
                tools_u,
                llm=model.llm,
                system_prompt=project.props.system,
                memory=chat.memory,
                verbose=True,
            )
        else:
            agent = ReActAgent.from_tools(
                tools_u,
                llm=model.llm,
                context=project.props.system,
                memory=chat.memory,
                max_iterations=project.props.options.max_iterations,
                verbose=True,
            )

        try:
            if chatModel.stream:
                resp_gen = agent.stream_chat(chatModel.question)
                
                parts = []
                for text in resp_gen.response_gen:
                    parts.append(text)
                    yield "data: " + json.dumps({"text": text}) + "\n\n"
                output["answer"] = "".join(parts)
                
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
                if str(e) == "Reached max iterations." and project.props.censorship:
                    output["answer"] = project.props.censorship
                    self.brain.post_processing_counting(output)
                    yield output
                else:
                    raise e

    async def question(
        self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper
    ):
        output = {
            "question": questionModel.question,
            "type": "agent",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            if guard.verify(questionModel.question):
                output["answer"] = (
                    project.props.censorship or self.brain.defaultCensorship
                )
                output["guard"] = True
                self.brain.post_processing_counting(output)
                yield output

        model = self.brain.get_llm(project.props.llm, db)

        tools_u = await self.prepare_tools(project)

        if len(tools_u) == 0:
            questionModel.question += "\nDont use any tool just respond to the user."

        agent = ReActAgent.from_tools(
            tools_u,
            llm=model.llm,
            context=questionModel.system or project.props.system,
            max_iterations=project.props.options.max_iterations,
            verbose=True,
        )

        try:
            output = self.output(agent, questionModel.question, output, project)
        except Exception as e:
            if str(e) == "Reached max iterations." and project.props.censorship:
                output["answer"] = project.props.censorship
            else:
                raise e

        self.brain.post_processing_counting(output)
        yield output
