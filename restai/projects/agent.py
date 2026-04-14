"""agent project type — direct LLM chat with optional tool calling.

Built on the agent2 runtime (`restai.agent2`), which is the non-llamaindex
agent loop. Supports built-in tools, MCP servers, multimodal image input,
fallback LLMs, output guards, history compression, ReAct fallback for
tool-callless models, and token-by-token streaming.

Agent projects without any tools configured behave like a plain LLM chat —
the runtime exits after one turn with no extra overhead. Add tools or MCP
servers in the project's Tools tab to turn them into actual agents.
"""
import json
from uuid import uuid4

from fastapi import HTTPException

from restai.agent2 import (
    Agent2Runtime,
    Agent2UnsupportedLLMError,
    MCPSessionPool,
    adapt_function_tools,
    build_provider_for_llm,
)
from restai.agent2.memory import get_session, save_session
from restai.agent2.tool_adapter import AdaptedTool
from restai.agent2.types import ImageBlock, ToolUseBlock
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase
from restai.tools import tokens_from_string


def _make_project_tool_adapted(tool_row, brain) -> AdaptedTool:
    """Create an AdaptedTool from a ProjectToolDatabase row.
    The tool runs code in the Docker sandbox."""
    import json as _json

    try:
        schema = _json.loads(tool_row.parameters) if isinstance(tool_row.parameters, str) else tool_row.parameters
    except (_json.JSONDecodeError, TypeError):
        schema = {"type": "object", "properties": {}, "required": []}

    tool_code = tool_row.code
    tool_name = tool_row.name

    async def _run_project_tool(**kwargs):
        _brain = kwargs.pop("_brain", brain)
        _chat_id = kwargs.pop("_chat_id", None)
        kwargs.pop("_project_id", None)
        if not _brain or not getattr(_brain, "docker_manager", None):
            return "ERROR: Docker is not configured."
        args_json = _json.dumps(kwargs)
        script = f"import json, sys\nargs = json.loads(sys.stdin.readline() or '{{}}')\n{tool_code}"
        return _brain.docker_manager.run_script(_chat_id or "ephemeral", script, stdin_data=args_json)

    return AdaptedTool(
        name=tool_name,
        description=tool_row.description or tool_name,
        input_schema=schema,
        fn=_run_project_tool,
        is_async=True,
        accepts_kwargs=True,
    )


def _wrap_image_error(err: Exception, has_image: bool) -> Exception:
    """Wrap an LLM provider error with a clearer message when an image was
    likely the cause (the model doesn't support vision)."""
    if not has_image:
        return err
    return HTTPException(
        status_code=400,
        detail=(
            "This LLM rejected the request, likely because it does not support "
            "image input. Try a vision-capable model (e.g. OllamaMultiModal, "
            "gpt-4o, claude-3+, gemini-2.0-flash) or remove the image. "
            f"Original error: {err}"
        ),
    )


class Agent(ProjectBase):

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

        # Load agent-created project tools from DB
        from restai.database import DBWrapper as _DBW
        _db = _DBW()
        try:
            project_tools = _db.get_project_tools(project.props.id)
            for pt in project_tools:
                if pt.enabled:
                    adapted.append(_make_project_tool_adapted(pt, self.brain))
        finally:
            _db.db.close()

        return Agent2Runtime(
            provider=provider,
            config=prov_config,
            tools=adapted,
            system_prompt=system_prompt or "",
            max_turns=project.props.options.max_iterations,
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
        """Lightweight tiktoken-based token estimate."""
        try:
            output["tokens"] = {
                "input": tokens_from_string(output.get("question") or ""),
                "output": tokens_from_string(output.get("answer") or ""),
                "accuracy": "low",
            }
        except Exception:
            output["tokens"] = {"input": 0, "output": 0, "accuracy": "low"}

    def _finalize_reasoning(self, output: dict, reasoning_buf: list, steps: list) -> None:
        """Build the reasoning dict from tool steps if any, then let
        `post_processing_reasoning` extract `<think>...</think>` blocks from
        the answer if no tool reasoning was recorded. Strips think tags from
        the answer either way."""
        if steps:
            output["reasoning"] = {"output": "\n".join(reasoning_buf), "steps": steps}
        self.brain.post_processing_reasoning(output)

    async def _drive_runtime(
        self,
        runtime,
        *,
        prompt: str,
        session,
        image_block,
        stream: bool,
        project: Project,
        output: dict,
    ):
        """Drive the runtime's event loop, yield text deltas as `str`, mutate
        `output["answer"]` and `output["reasoning"]` along the way. Used by
        both `chat()` and `question()` to share the (otherwise identical)
        per-event handling."""
        steps: list = []
        reasoning_buf: list = []
        # Pair tool calls with their results so the reasoning panel renders correctly
        pending_tool_calls: dict = {}

        async for event in runtime.run_iter(
            prompt,
            session=session,
            image=image_block,
            stream=stream,
        ):
            if event.type == "text_delta":
                delta = event.data.get("text", "")
                if delta:
                    yield delta

            elif event.type == "assistant":
                msg = event.message
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

        self._finalize_reasoning(output, reasoning_buf, steps)

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        chat_id = chatModel.id or str(uuid4())

        output = {
            "question": chatModel.question,
            "type": "agent",
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

            runtime._chat_id = chat_id
            runtime._brain = self.brain
            runtime._project_id = project.props.id
            session = await get_session(self.brain, chat_id)
            image_block = ImageBlock.from_data_url(chatModel.image) if chatModel.image else None
            streamed_any_text = False

            try:
                async for delta in self._drive_runtime(
                    runtime,
                    prompt=chatModel.question,
                    session=session,
                    image_block=image_block,
                    stream=chatModel.stream,
                    project=project,
                    output=output,
                ):
                    streamed_any_text = True
                    yield "data: " + json.dumps({"text": delta}) + "\n\n"

                await save_session(self.brain, chat_id, session)
                self._count_tokens(output)
                self.check_output_guard(project, user, db, output)

                if chatModel.stream:
                    # Emit the final answer text only if streaming didn't
                    # already deliver it (e.g. fell back to ReAct mid-run).
                    if not streamed_any_text and output.get("answer"):
                        yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"

            except Exception as e:
                wrapped = _wrap_image_error(e, bool(chatModel.image))
                if chatModel.stream:
                    yield "data: " + json.dumps({"text": f"Agent failed: {wrapped}"}) + "\n\n"
                    yield "event: error\n\n"
                else:
                    if project.props.censorship:
                        output["answer"] = project.props.censorship
                        self._count_tokens(output)
                    else:
                        raise wrapped

        # Non-streaming yield MUST be outside the `async with MCPSessionPool()`
        # block. When the caller does `async for line in gen: return line`, the
        # generator is abandoned after the first yield. If that yield happens
        # inside the async-with, the pool's __aexit__ runs in a GC/finalizer
        # task → "exit cancel scope in different task" → corrupted HTTP response.
        if not chatModel.stream:
            if "answer" not in output:
                output["answer"] = project.props.censorship or "No response generated."
            yield output

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

            runtime._brain = self.brain
            runtime._project_id = project.props.id
            image_block = ImageBlock.from_data_url(questionModel.image) if questionModel.image else None
            streamed_any_text = False

            try:
                async for delta in self._drive_runtime(
                    runtime,
                    prompt=questionModel.question,
                    session=None,
                    image_block=image_block,
                    stream=questionModel.stream,
                    project=project,
                    output=output,
                ):
                    streamed_any_text = True
                    yield "data: " + json.dumps({"text": delta}) + "\n\n"

                self._count_tokens(output)
                self.check_output_guard(project, user, db, output)
            except Exception as e:
                wrapped = _wrap_image_error(e, bool(questionModel.image))
                if questionModel.stream:
                    yield "data: " + json.dumps({"text": f"Agent failed: {wrapped}"}) + "\n\n"
                    yield "event: error\n\n"
                    return
                if project.props.censorship:
                    output["answer"] = project.props.censorship
                    self._count_tokens(output)
                else:
                    raise wrapped

        if questionModel.stream:
            if not streamed_any_text and output.get("answer"):
                yield "data: " + json.dumps({"text": output["answer"]}) + "\n\n"
            yield "data: " + json.dumps(output) + "\n"
            yield "event: close\n\n"
        else:
            yield output
