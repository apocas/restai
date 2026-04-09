"""agent2 project type — same UX as `agent` but built on the agent2 runtime
which has no llamaindex dependency.

Mirrors the structure of restai/projects/agent.py: same `output` dict shape,
same SSE streaming protocol, same guard handling, same reasoning step format.
The frontend chat playground works unchanged.
"""
import json
from uuid import uuid4

from restai import config
from restai.agent2 import (
    Agent2Runtime,
    Agent2UnsupportedLLMError,
    MCPSessionPool,
    adapt_function_tools,
    build_provider_for_llm,
)
from restai.agent2.memory import get_session, save_session
from restai.agent2.types import ToolUseBlock
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.tools import tokens_from_string


class Agent2(ProjectBase):

    def _build_runtime(
        self,
        project: Project,
        db: DBWrapper,
        system_prompt: str | None,
        extra_tools: list | None = None,
    ) -> Agent2Runtime:
        llm_db = db.get_llm_by_name(project.props.llm)
        if llm_db is None:
            raise ValueError(f"LLM '{project.props.llm}' not found")

        provider, prov_config = build_provider_for_llm(llm_db)

        raw_tool_names = set(
            t.strip() for t in (project.props.options.tools or "").split(",") if t.strip()
        )
        raw_tools = self.brain.get_tools(raw_tool_names) if raw_tool_names else []
        adapted = adapt_function_tools(raw_tools)
        if extra_tools:
            adapted.extend(extra_tools)

        max_iterations = min(
            project.props.options.max_iterations or config.AGENT_MAX_ITERATIONS,
            config.AGENT_MAX_ITERATIONS,
        )

        return Agent2Runtime(
            provider=provider,
            config=prov_config,
            tools=adapted,
            system_prompt=system_prompt or "",
            max_turns=max_iterations,
            mode=project.props.options.agent_mode or "auto",
        )

    @staticmethod
    def _record_step(steps: list, reasoning_buf: list, tool_call: ToolUseBlock, tool_output: str):
        reasoning_buf.append("Action: " + tool_call.name)
        reasoning_buf.append("Action Input: " + json.dumps(tool_call.input))
        reasoning_buf.append("Action Output: " + tool_output)
        steps.append({
            "actions": [{
                "action": tool_call.name,
                "input": tool_call.input,
                "output": tool_output,
            }],
            "output": "",
        })

    @staticmethod
    def _count_tokens(output: dict) -> None:
        """Lightweight tiktoken-based token estimate (agent2 doesn't go through
        llamaindex's TokenCountingHandler)."""
        try:
            output["tokens"] = {
                "input": tokens_from_string(output.get("question") or ""),
                "output": tokens_from_string(output.get("answer") or ""),
                "accuracy": "low",
            }
        except Exception:
            output["tokens"] = {"input": 0, "output": 0, "accuracy": "low"}

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        chat_id = chatModel.id or str(uuid4())

        output = {
            "question": chatModel.question,
            "type": "agent2",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat_id,
        }

        if self.check_input_guard(project, chatModel.question, user, db, output):
            if chatModel.stream:
                yield "data: " + json.dumps({"text": output.get("answer", "")}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                yield output
            return

        async with MCPSessionPool() as mcp_pool:
            try:
                mcp_tools = await mcp_pool.connect_servers(
                    project.props.options.mcp_servers or []
                )
            except Exception:
                mcp_tools = []

            try:
                runtime = self._build_runtime(
                    project, db, project.props.system, extra_tools=mcp_tools
                )
            except Agent2UnsupportedLLMError as e:
                err_msg = str(e)
                if chatModel.stream:
                    yield "data: " + json.dumps({"text": err_msg}) + "\n\n"
                    output["answer"] = err_msg
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    output["answer"] = err_msg
                    yield output
                return

            if not runtime.tools:
                chatModel.question += "\nDont use any tool just respond to the user."

            session = await get_session(self.brain, chat_id)
            steps: list = []
            reasoning_buf: list = []
            # Track the most recent tool call so we can pair it with its result event
            pending_tool_calls: dict = {}

            try:
                async for event in runtime.run_iter(chatModel.question, session=session):
                    if event.type == "assistant":
                        msg = event.message
                        text_now = msg.text_content() if msg else ""
                        # Stream any new text the model produced this turn
                        if chatModel.stream and text_now:
                            yield "data: " + json.dumps({"text": text_now}) + "\n\n"
                        # Remember tool calls so we can attach their outputs later
                        if msg:
                            for block in msg.content:
                                if isinstance(block, ToolUseBlock):
                                    pending_tool_calls[block.id] = block

                    elif event.type == "tool_result":
                        msg = event.message
                        if msg:
                            for block in msg.content:
                                tool_use_id = getattr(block, "tool_use_id", None)
                                tool_call = pending_tool_calls.pop(tool_use_id, None)
                                if tool_call is not None:
                                    self._record_step(
                                        steps, reasoning_buf, tool_call, getattr(block, "content", "") or ""
                                    )

                    elif event.type == "final":
                        output["answer"] = event.data.get("final_text", "") or ""
                        if event.data.get("stop_reason") == "max_turns" and not output["answer"]:
                            output["answer"] = (
                                project.props.censorship
                                or "I'm sorry, I tried my best but couldn't reach a final answer."
                            )

                output["reasoning"] = {"output": "\n".join(reasoning_buf), "steps": steps}
                await save_session(self.brain, chat_id, session)
                self._count_tokens(output)

                if chatModel.stream:
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    yield output

            except Exception as e:
                if chatModel.stream:
                    yield "data: " + json.dumps({"text": f"Inference failed: {e}"}) + "\n\n"
                    yield "event: error\n\n"
                else:
                    if project.props.censorship:
                        output["answer"] = project.props.censorship
                        self._count_tokens(output)
                        yield output
                    else:
                        raise

    async def question(
        self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper
    ):
        output = {
            "question": questionModel.question,
            "type": "agent2",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }

        if self.check_input_guard(project, questionModel.question, user, db, output):
            if questionModel.stream:
                yield "data: " + json.dumps({"text": output.get("answer", "")}) + "\n\n"
                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                yield output
            return

        system_prompt = questionModel.system or project.props.system

        async with MCPSessionPool() as mcp_pool:
            try:
                mcp_tools = await mcp_pool.connect_servers(
                    project.props.options.mcp_servers or []
                )
            except Exception:
                mcp_tools = []

            try:
                runtime = self._build_runtime(
                    project, db, system_prompt, extra_tools=mcp_tools
                )
            except Agent2UnsupportedLLMError as e:
                output["answer"] = str(e)
                if questionModel.stream:
                    yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    yield output
                return

            if not runtime.tools:
                questionModel.question += "\nDont use any tool just respond to the user."

            steps: list = []
            reasoning_buf: list = []
            pending_tool_calls: dict = {}

            try:
                async for event in runtime.run_iter(questionModel.question):
                    if event.type == "assistant" and event.message:
                        for block in event.message.content:
                            if isinstance(block, ToolUseBlock):
                                pending_tool_calls[block.id] = block
                    elif event.type == "tool_result" and event.message:
                        for block in event.message.content:
                            tool_use_id = getattr(block, "tool_use_id", None)
                            tool_call = pending_tool_calls.pop(tool_use_id, None)
                            if tool_call is not None:
                                self._record_step(
                                    steps, reasoning_buf, tool_call, getattr(block, "content", "") or ""
                                )
                    elif event.type == "final":
                        output["answer"] = event.data.get("final_text", "") or ""
                        if event.data.get("stop_reason") == "max_turns" and not output["answer"]:
                            output["answer"] = (
                                project.props.censorship
                                or "I'm sorry, I tried my best but couldn't reach a final answer."
                            )

                output["reasoning"] = {"output": "\n".join(reasoning_buf), "steps": steps}
                self._count_tokens(output)
            except Exception as e:
                if project.props.censorship:
                    output["answer"] = project.props.censorship
                    self._count_tokens(output)
                else:
                    raise

        if questionModel.stream:
            if output.get("answer"):
                yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
