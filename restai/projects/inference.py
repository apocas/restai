import json
import logging
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from restai.chat import Chat
from restai.database import DBWrapper
from restai.guard import Guard
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase


class Inference(ProjectBase):

    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):

        chat: Chat = Chat(chat_model, self.brain.chat_store)
        output = {
            "question": chat_model.question,
            "type": "inference",
            "sources": [],
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
            "id": chat.chat_id,
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            if guard.verify(chat_model.question):
                output["answer"] = (
                    project.props.censorship or self.brain.defaultCensorship
                )
                output["guard"] = True
                self.brain.post_processing_counting(output)
                yield output

        llm_model = self.brain.get_llm(project.props.llm, db)

        sysTemplate = project.props.system or self.brain.defaultSystem

        if sysTemplate:
            llm_model.llm.system_prompt = sysTemplate

            if not chat.memory.get_all():
                chat.memory.chat_store.add_message(
                    chat.memory.chat_store_key,
                    ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate),
                )

        chat.memory.chat_store.add_message(
            chat.memory.chat_store_key,
            ChatMessage(role=MessageRole.USER, content=chat_model.question),
        )
        messages = chat.memory.get_all()

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
                resp = llm_model.llm.chat(messages)
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

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            if guard.verify(question_model.question):
                output["answer"] = (
                    project.props.censorship or self.brain.defaultCensorship
                )
                output["guard"] = True
                self.brain.post_processing_counting(output)
                yield output

        model = self.brain.get_llm(project.props.llm, db)

        sysTemplate = (
            question_model.system or project.props.system or self.brain.defaultSystem
        )

        messages = []

        if sysTemplate:
            model.llm.system_prompt = sysTemplate
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate))

        messages.append(
            ChatMessage(role=MessageRole.USER, content=question_model.question)
        )

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
                resp = model.llm.chat(messages)
                output["answer"] = resp.message.content.strip()

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield output
        except Exception as e:
            logging.exception(e)
            if question_model.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e
