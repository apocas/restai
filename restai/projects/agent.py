import json

from llama_index.core.agent import ReActAgent, FunctionAgent
from llama_index.core.agent.workflow.workflow_events import (
    AgentStream,
    AgentOutput,
    ToolCall,
    ToolCallResult,
)

from restai import config
from restai.chat import Chat
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec


class Agent(ProjectBase):

    async def prepare_tools(self, project: Project):
      tools_u = self.brain.get_tools(set((project.props.options.tools or "").split(",")))

      if project.props.options.mcp_servers:
          for mcp_server in project.props.options.mcp_servers:
              allowed_tools = set((mcp_server.tools or "").split(","))
              mcp_client = BasicMCPClient(
                  mcp_server.host,
                  args=mcp_server.args or [],
                  env=mcp_server.env or {},
              )

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

    def _create_agent(self, tools_u, model, system_prompt, project, use_function_agent=False):
        max_iterations = min(
            project.props.options.max_iterations or config.AGENT_MAX_ITERATIONS,
            config.AGENT_MAX_ITERATIONS,
        )

        AgentClass = FunctionAgent if use_function_agent else ReActAgent
        return AgentClass(
            tools=tools_u,
            llm=model.llm,
            system_prompt=system_prompt,
            verbose=True,
            timeout=None,
        ), max_iterations

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        model = self.brain.get_llm(project.props.llm, db)
        context_window = model.props.context_window if model else 4096
        token_limit = int(context_window * 0.75)
        chat: Chat = Chat(chatModel, self.brain.chat_store, token_limit=token_limit, llm=model.llm if model else None)
        output = {
            "question": chatModel.question,
            "type": "agent",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat.chat_id,
        }

        if self.check_input_guard(project, chatModel.question, user, db, output):
            yield output
            return

        tools_u = await self.prepare_tools(project)

        if len(tools_u) == 0:
            chatModel.question += "\nDont use any tool just respond to the user."

        use_function_agent = hasattr(project.props.options, "function_agent") and project.props.options.function_agent is True

        agent, max_iterations = self._create_agent(
            tools_u, model, project.props.system, project, use_function_agent
        )

        try:
            handler = agent.run(
                user_msg=chatModel.question,
                memory=chat.memory,
                max_iterations=max_iterations,
            )

            if chatModel.stream:
                resp_reasoning = ""
                steps = []

                async for event in handler.stream_events():
                    if isinstance(event, AgentStream):
                        if event.delta:
                            yield "data: " + json.dumps({"text": event.delta}) + "\n\n"
                    elif isinstance(event, ToolCallResult):
                        resp_reasoning += "Action: " + event.tool_name + "\n"
                        resp_reasoning += "Action Input: " + json.dumps(event.tool_kwargs) + "\n"
                        resp_reasoning += "Action Output: " + str(event.tool_output.content) + "\n"
                        steps.append({
                            "actions": [{
                                "action": event.tool_name,
                                "input": event.tool_kwargs,
                                "output": str(event.tool_output.content),
                            }],
                            "output": "",
                        })

                result = await handler
                output["answer"] = str(result.response.content or "")
                output["reasoning"] = {"output": resp_reasoning, "steps": steps}

                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                result = await handler
                resp_reasoning = ""
                steps = []

                for tc in (result.tool_calls or []):
                    if isinstance(tc, ToolCallResult):
                        resp_reasoning += "Action: " + tc.tool_name + "\n"
                        resp_reasoning += "Action Input: " + json.dumps(tc.tool_kwargs) + "\n"
                        resp_reasoning += "Action Output: " + str(tc.tool_output.content) + "\n"
                        steps.append({
                            "actions": [{
                                "action": tc.tool_name,
                                "input": tc.tool_kwargs,
                                "output": str(tc.tool_output.content),
                            }],
                            "output": "",
                        })

                output["answer"] = str(result.response.content or "")
                output["reasoning"] = {"output": resp_reasoning, "steps": steps}

                self.brain.post_processing_counting(output)
                yield output
        except Exception as e:
            error_msg = str(e)
            if chatModel.stream:
                if "Max iterations" in error_msg:
                    yield "data: I'm sorry, I tried my best...\n"
                else:
                    yield "data: Inference failed\n"
                yield "event: error\n\n"
            else:
                if "Max iterations" in error_msg and project.props.censorship:
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

        if self.check_input_guard(project, questionModel.question, user, db, output):
            yield output
            return

        model = self.brain.get_llm(project.props.llm, db)

        tools_u = await self.prepare_tools(project)

        if len(tools_u) == 0:
            questionModel.question += "\nDont use any tool just respond to the user."

        system_prompt = questionModel.system or project.props.system
        agent, max_iterations = self._create_agent(tools_u, model, system_prompt, project)

        try:
            handler = agent.run(
                user_msg=questionModel.question,
                max_iterations=max_iterations,
            )
            result = await handler

            resp_reasoning = ""
            steps = []
            for tc in (result.tool_calls or []):
                if isinstance(tc, ToolCallResult):
                    resp_reasoning += "Action: " + tc.tool_name + "\n"
                    resp_reasoning += "Action Input: " + json.dumps(tc.tool_kwargs) + "\n"
                    resp_reasoning += "Action Output: " + str(tc.tool_output.content) + "\n"
                    steps.append({
                        "actions": [{
                            "action": tc.tool_name,
                            "input": tc.tool_kwargs,
                            "output": str(tc.tool_output.content),
                        }],
                        "output": "",
                    })

            output["answer"] = str(result.response.content or "")
            output["reasoning"] = {"output": resp_reasoning, "steps": steps}
        except Exception as e:
            error_msg = str(e)
            if "Max iterations" in error_msg and project.props.censorship:
                output["answer"] = project.props.censorship
            else:
                raise e

        self.brain.post_processing_counting(output)
        yield output
