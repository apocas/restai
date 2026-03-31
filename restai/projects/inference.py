import base64
import json
import logging
from llama_index.core.base.llms.types import ChatMessage, MessageRole, TextBlock, ImageBlock
from restai.chat import Chat
from restai.database import DBWrapper
from restai.guard import Guard
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase


def _build_user_message(text: str, image_b64: str | None = None) -> ChatMessage:
    """Build a ChatMessage, using multimodal blocks when an image is present."""
    if image_b64:
        return ChatMessage(role=MessageRole.USER, blocks=[
            TextBlock(text=text),
            ImageBlock(image=base64.b64decode(image_b64)),
        ])
    return ChatMessage(role=MessageRole.USER, content=text)


class Inference(ProjectBase):

    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):

        llm_model = self.brain.get_llm(project.props.llm, db)
        context_window = llm_model.props.context_window if llm_model else 4096
        token_limit = int(context_window * 0.75)
        chat: Chat = Chat(chat_model, self.brain.chat_store, token_limit=token_limit, llm=llm_model.llm if llm_model else None)
        output = {
            "question": chat_model.question,
            "type": "inference",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat.chat_id,
        }

        if self.check_input_guard(project, chat_model.question, user, db, output):
            yield output
            return

        sysTemplate = project.props.system or self.brain.defaultSystem

        if sysTemplate:
            llm_model.llm.system_prompt = sysTemplate

            if not chat.memory.get_all():
                chat.memory.chat_store.add_message(
                    chat.memory.chat_store_key,
                    ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate),
                )

        # Store text-only message in chat history (image is per-message, not persisted)
        chat.memory.chat_store.add_message(
            chat.memory.chat_store_key,
            ChatMessage(role=MessageRole.USER, content=chat_model.question),
        )

        # Build messages for LLM call — replace the last USER message with multimodal if image present
        messages = chat.memory.get()
        if chat_model.image:
            messages[-1] = _build_user_message(chat_model.question, chat_model.image)

        try:
            if chat_model.stream:
                resp_gen = llm_model.llm.stream_chat(messages)
                parts = []
                for text in resp_gen:
                    parts.append(text.delta)
                    yield "data: " + json.dumps({"text": text.delta}) + "\n\n"
                response = "".join(parts)

                output["answer"] = response

                chat.memory.chat_store.add_message(
                    chat.memory.chat_store_key,
                    ChatMessage(role=MessageRole.ASSISTANT, content=response),
                )

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                try:
                    resp = llm_model.llm.chat(messages)
                except Exception as primary_error:
                    fallback_name = project.props.options.fallback_llm if project.props.options else None
                    if fallback_name:
                        fallback_model = self.brain.get_llm(fallback_name, db)
                        if fallback_model:
                            logging.warning("Primary LLM failed, using fallback '%s': %s", fallback_name, primary_error)
                            if sysTemplate:
                                fallback_model.llm.system_prompt = sysTemplate
                            resp = fallback_model.llm.chat(messages)
                        else:
                            raise primary_error
                    else:
                        raise primary_error

                if resp.message and resp.message.content:
                    output["answer"] = resp.message.content.strip()
                else:
                    output["answer"] = ""

                chat.memory.chat_store.add_message(
                    chat.memory.chat_store_key,
                    ChatMessage(
                        role=MessageRole.ASSISTANT, content=resp.message.content.strip()
                    ),
                )

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield output
        except Exception as e:
            logging.exception(e)
            if chat_model.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e

    async def question(
        self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper
    ):
        output = {
            "question": question_model.question,
            "type": "inference",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }

        if self.check_input_guard(project, question_model.question, user, db, output):
            yield output
            return

        model = self.brain.get_llm(project.props.llm, db)

        sysTemplate = (
            question_model.system or project.props.system or self.brain.defaultSystem
        )

        messages = []

        if sysTemplate:
            model.llm.system_prompt = sysTemplate
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate))

        messages.append(_build_user_message(question_model.question, question_model.image))

        try:
            if question_model.stream:
                resp_gen = model.llm.stream_chat(messages)

                parts = []
                for text in resp_gen:
                    parts.append(text.delta)
                    yield "data: " + json.dumps({"text": text.delta}) + "\n\n"
                response = "".join(parts)

                output["answer"] = response

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield "data: " + json.dumps(output) + "\n"
                yield "event: close\n\n"
            else:
                try:
                    resp = model.llm.chat(messages)
                except Exception as primary_error:
                    fallback_name = project.props.options.fallback_llm if project.props.options else None
                    if fallback_name:
                        fallback_model = self.brain.get_llm(fallback_name, db)
                        if fallback_model:
                            logging.warning("Primary LLM failed, using fallback '%s': %s", fallback_name, primary_error)
                            if sysTemplate:
                                fallback_model.llm.system_prompt = sysTemplate
                            resp = fallback_model.llm.chat(messages)
                        else:
                            raise primary_error
                    else:
                        raise primary_error

                output["answer"] = resp.message.content.strip()

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                # Output guard
                if project.props.options.guard_output and output.get("answer"):
                    out_guard = Guard(project.props.options.guard_output, self.brain, db)
                    out_result = out_guard.verify(output["answer"], phase="output")
                    if out_result:
                        guard_mode = project.props.options.guard_mode or "block"
                        out_action = "block" if out_result.blocked else "pass"
                        if out_result.blocked and guard_mode == "warn":
                            out_action = "warn"
                        from restai.tools import log_guard_event
                        log_guard_event(project, project.props.options.guard_output, user, "output", out_action, guard_mode, output["answer"], out_result.raw_response, db)
                        if out_result.blocked and guard_mode == "block":
                            output["answer"] = project.props.censorship or self.brain.defaultCensorship
                            output["guard"] = True
                        elif out_result.blocked:
                            output["guard"] = True

                yield output
        except Exception as e:
            logging.exception(e)
            if question_model.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e
