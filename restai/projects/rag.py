import json
from typing import Optional

from fastapi import HTTPException

from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.prompts import PromptTemplate
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.postprocessor.llm_rerank import LLMRerank
from llama_index.postprocessor.colbert_rerank import ColbertRerank
from restai.chat import Chat
from restai.database import DBWrapper
from restai.eval import eval_rag
from restai.guard import Guard
from restai.llm import LLM
from restai.models.models import QuestionModel, ChatModel, User
from restai.project import Project
from restai.tools import tokens_from_string
from restai.projects.base import ProjectBase
from llama_index.core.utilities.sql_wrapper import SQLDatabase
from llama_index.core.indices.struct_store.sql_query import NLSQLTableQueryEngine
from sqlalchemy import create_engine


class RAG(ProjectBase):

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        model: Optional[LLM] = self.brain.get_llm(project.props.llm, db)
        context_window = model.props.context_window if model else 4096
        token_limit = int(context_window * 0.75)
        chat: Chat = Chat(chatModel, self.brain.chat_store, token_limit=token_limit, llm=model.llm if model else None)

        output = {
            "id": chat.chat_id,
            "question": chatModel.question,
            "sources": [],
            "cached": False,
            "guard": False,
            "type": "chat",
            "project": project.props.name,
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            result = guard.verify(chatModel.question, phase="input")
            if result:
                guard_mode = project.props.options.guard_mode or "block"
                from restai.tools import log_guard_event
                action = "block" if result.blocked else "pass"
                if result.blocked and guard_mode == "warn":
                    action = "warn"
                log_guard_event(project, project.props.guard, user, "input", action, guard_mode, chatModel.question, result.raw_response, db)
                if result.blocked and guard_mode == "block":
                    output["answer"] = project.props.censorship or self.brain.defaultCensorship
                    output["guard"] = True
                    self.brain.post_processing_counting(output)
                    yield output
                    return
                elif result.blocked:
                    output["guard"] = True

        threshold = project.props.options.score or 0.0
        k = project.props.options.k or 1

        sysTemplate = project.props.system or self.brain.defaultSystem

        if project.props.options.colbert_rerank or project.props.options.llm_rerank:
            final_k = k * 2
        else:
            final_k = k

        retriever = VectorIndexRetriever(
            index=project.vector.index,
            similarity_top_k=final_k,
        )

        postprocessors = []

        if project.props.options.colbert_rerank:
            postprocessors.append(
                ColbertRerank(
                    top_n=k,
                    model="colbert-ir/colbertv2.0",
                    tokenizer="colbert-ir/colbertv2.0",
                    keep_retrieval_score=True,
                )
            )

        if project.props.options.llm_rerank:
            postprocessors.append(
                LLMRerank(
                    choice_batch_size=k,
                    top_n=k,
                    llm=model.llm,
                )
            )

        postprocessors.append(SimilarityPostprocessor(similarity_cutoff=threshold))

        chat_engine = ContextChatEngine.from_defaults(
            retriever=retriever,
            system_prompt=sysTemplate,
            memory=chat.memory,
            node_postprocessors=postprocessors,
            llm=model.llm,
        )

        try:
            if chatModel.stream:
                response = chat_engine.stream_chat(chatModel.question)
            else:
                response = chat_engine.chat(chatModel.question)

            for node in response.source_nodes:
                source = {"score": node.score, "id": node.node_id, "text": node.text}

                if "source" in node.metadata:
                    source["source"] = node.metadata["source"]
                if "keywords" in node.metadata:
                    source["keywords"] = node.metadata["keywords"]

                output["sources"].append(source)

            if chatModel.stream:
                if hasattr(response, "response_gen"):
                    parts = []
                    for text in response.response_gen:
                        parts.append(text)
                        yield "data: " + json.dumps({"text": text}) + "\n\n"

                    output["answer"] = "".join(parts)

                    self.brain.post_processing_reasoning(output)
                    self.brain.post_processing_counting(output)

                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    output["answer"] = self.brain.defaultCensorship
                    yield "data: " + json.dumps({"text": "text"}) + "\n\n"

                    self.brain.post_processing_reasoning(output)
                    self.brain.post_processing_counting(output)

                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:
                if len(response.source_nodes) == 0:
                    output["answer"] = (
                        project.props.censorship or self.brain.defaultCensorship
                    )
                else:
                    output["answer"] = response.response

                    if project.cache:
                        project.cache.add(chatModel.question, response.response)

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield output
        except Exception as e:
            if chatModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e

    async def question(
        self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper
    ):
        output = {
            "question": questionModel.question,
            "type": "question",
            "sources": [],
            "cached": False,
            "guard": False,
            "tokens": {"input": 0, "output": 0},
            "project": project.props.name,
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            result = guard.verify(questionModel.question, phase="input")
            if result:
                guard_mode = project.props.options.guard_mode or "block"
                from restai.tools import log_guard_event
                action = "block" if result.blocked else "pass"
                if result.blocked and guard_mode == "warn":
                    action = "warn"
                log_guard_event(project, project.props.guard, user, "input", action, guard_mode, questionModel.question, result.raw_response, db)
                if result.blocked and guard_mode == "block":
                    output["answer"] = project.props.censorship or self.brain.defaultCensorship
                    output["guard"] = True
                    self.brain.post_processing_counting(output)
                    yield output
                    return
                elif result.blocked:
                    output["guard"] = True

        model = self.brain.get_llm(project.props.llm, db)

        # SQL query path: when a database connection is configured, use NL-to-SQL
        if project.props.options.connection:
            if questionModel.stream:
                raise HTTPException(
                    status_code=400,
                    detail="Streaming is not supported for SQL queries."
                )

            engine = create_engine(project.props.options.connection)
            try:
                sql_database = SQLDatabase(engine)

                tables = None
                if hasattr(questionModel, 'tables') and questionModel.tables is not None:
                    tables = questionModel.tables
                elif project.props.options.tables:
                    tables = [table.strip() for table in project.props.options.tables.split(',')]

                sysTemplate = (
                    questionModel.system or project.props.system or self.brain.defaultSystem
                )
                question = sysTemplate + "\n Question: " + questionModel.question

                query_engine = NLSQLTableQueryEngine(
                    llm=model.llm,
                    sql_database=sql_database,
                    tables=tables,
                )

                response = query_engine.query(question)

                output["answer"] = response.response
                output["sources"] = [response.metadata['sql_query']]
                output["tokens"] = {
                    "input": tokens_from_string(output["question"]),
                    "output": tokens_from_string(output["answer"])
                }
                yield output
                return
            finally:
                engine.dispose()

        sysTemplate = (
            questionModel.system or project.props.system or self.brain.defaultSystem
        )

        k = questionModel.k or project.props.options.k or 2
        threshold = questionModel.score or project.props.options.score or 0.0

        if (
            questionModel.colbert_rerank
            or questionModel.llm_rerank
            or project.props.options.colbert_rerank
            or project.props.options.llm_rerank
        ):
            final_k = k * 2
        else:
            final_k = k

        retriever = VectorIndexRetriever(
            index=project.vector.index,
            similarity_top_k=final_k,
        )

        qa_prompt_tmpl = (
            "Context information is below.\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "Given the context information and not prior knowledge, "
            "answer the query.\n"
            "Query: {query_str}\n"
            "Answer: "
        )

        qa_prompt = PromptTemplate(qa_prompt_tmpl)

        model.llm.system_prompt = sysTemplate

        response_synthesizer = get_response_synthesizer(
            llm=model.llm, text_qa_template=qa_prompt, streaming=questionModel.stream
        )

        postprocessors = []

        if questionModel.colbert_rerank or project.props.options.colbert_rerank:
            postprocessors.append(
                ColbertRerank(
                    top_n=k,
                    model="colbert-ir/colbertv2.0",
                    tokenizer="colbert-ir/colbertv2.0",
                    keep_retrieval_score=True,
                )
            )

        if questionModel.llm_rerank or project.props.options.llm_rerank:
            postprocessors.append(
                LLMRerank(
                    choice_batch_size=k,
                    top_n=k,
                    llm=model.llm,
                )
            )

        postprocessors.append(SimilarityPostprocessor(similarity_cutoff=threshold))

        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
            node_postprocessors=postprocessors,
        )

        try:
            response = query_engine.query(questionModel.question)

            if hasattr(response, "source_nodes"):
                for node in response.source_nodes:
                    output["sources"].append(
                        {
                            "source": node.metadata["source"],
                            "keywords": node.metadata["keywords"],
                            "score": node.score,
                            "id": node.node_id,
                            "text": node.text,
                        }
                    )

            if questionModel.eval and not questionModel.stream:
                metric = eval_rag(
                    questionModel.question,
                    response,
                    self.brain.get_llm("openai_gpt4", db).llm,
                )
                output["evaluation"] = {"reason": metric.reason, "score": metric.score}

            if questionModel.stream:
                if hasattr(response, "response_gen"):
                    failed = True
                    answer = ""
                    for text in response.response_gen:
                        failed = False
                        answer += text
                        yield "data: " + json.dumps({"text": text}) + "\n\n"
                    if failed:
                        yield "data: " + response.response_txt + "\n\n"
                    output["answer"] = answer

                    self.brain.post_processing_reasoning(output)
                    self.brain.post_processing_counting(output)

                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    output["answer"] = self.brain.defaultCensorship
                    yield "data: " + json.dumps(
                        {"text": self.brain.defaultCensorship}
                    ) + "\n\n"
                    
                    self.brain.post_processing_reasoning(output)
                    self.brain.post_processing_counting(output)
                    
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:
                if len(response.source_nodes) == 0:
                    output["answer"] = (
                        project.props.censorship or self.brain.defaultCensorship
                    )
                else:
                    output["answer"] = response.response

                    if project.cache:
                        project.cache.add(questionModel.question, response.response)

                self.brain.post_processing_reasoning(output)
                self.brain.post_processing_counting(output)

                yield output
        except Exception as e:
            if questionModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e
