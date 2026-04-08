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


class EntityBoostPostprocessor:
    """Custom postprocessor that boosts retrieval scores for chunks whose source
    contains entities mentioned in the user's query. Additive boost — does not
    filter out non-matching chunks. Falls back gracefully if no entities found.
    """

    def __init__(self, brain, db, project_id: int, query: str, boost_factor: float = 1.5):
        self.brain = brain
        self.db = db
        self.project_id = project_id
        self.query = query
        self.boost_factor = boost_factor
        self._matched_sources: Optional[set] = None

    def _compute_matched_sources(self) -> set:
        if self._matched_sources is not None:
            return self._matched_sources
        try:
            import re as _re
            from restai.knowledge_graph import find_entities_in_text, normalize_entity_name
            from restai.models.databasemodels import KGEntityDatabase, KGEntityMentionDatabase

            # Primary path: word-boundary match the query against entities ALREADY
            # in this project's graph. NER on short queries is unreliable; the DB
            # knows what we have, so direct matching is more robust.
            project_entities = (
                self.db.db.query(KGEntityDatabase)
                .filter(KGEntityDatabase.project_id == self.project_id)
                .all()
            )
            if not project_entities:
                self._matched_sources = set()
                return self._matched_sources

            query_padded = " " + _re.sub(r"[^\w\s]", " ", (self.query or "").lower()) + " "
            matched_ids = {
                e.id for e in project_entities
                if e.normalized and f" {e.normalized} " in query_padded
            }

            # Supplement with NER hits in case the query phrasing is different
            try:
                ner_hits = find_entities_in_text(self.query, self.brain)
                if ner_hits:
                    ner_normalized = [normalize_entity_name(n) for n, _ in ner_hits]
                    extra_ids = {
                        e.id for e in project_entities
                        if e.normalized in ner_normalized
                    }
                    matched_ids |= extra_ids
            except Exception:
                pass

            if not matched_ids:
                self._matched_sources = set()
                return self._matched_sources

            sources = {
                row.source for row in self.db.db.query(KGEntityMentionDatabase)
                .filter(KGEntityMentionDatabase.entity_id.in_(list(matched_ids)))
                .all()
            }
            self._matched_sources = sources
        except Exception:
            self._matched_sources = set()
        return self._matched_sources

    def postprocess_nodes(self, nodes, query_bundle=None, query_str=None):
        matched = self._compute_matched_sources()
        if not matched:
            return nodes
        for node in nodes:
            try:
                node_source = node.node.metadata.get("source") if hasattr(node, "node") else None
                if node_source and node_source in matched:
                    if node.score is not None:
                        node.score = node.score * self.boost_factor
            except Exception:
                pass
        # Re-sort after boosting
        try:
            nodes.sort(key=lambda n: n.score or 0, reverse=True)
        except Exception:
            pass
        return nodes


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

        if self.check_input_guard(project, chatModel.question, user, db, output):
            yield output
            return

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

        if project.props.options.enable_knowledge_graph:
            postprocessors.append(
                EntityBoostPostprocessor(
                    brain=self.brain, db=db, project_id=project.props.id, query=chatModel.question,
                )
            )

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
                    source["source"] = node.metadata.get("source", "unknown")
                if "keywords" in node.metadata:
                    source["keywords"] = node.metadata["keywords"]

                output["sources"].append(source)

            if chatModel.stream:
                parts = []
                if hasattr(response, "response_gen"):
                    for text in response.response_gen:
                        parts.append(text)
                        yield "data: " + json.dumps({"text": text}) + "\n\n"

                answer = "".join(parts).strip()
                if not answer or len(output["sources"]) == 0:
                    censorship = project.props.censorship or self.brain.defaultCensorship
                    output["answer"] = censorship
                    if not parts:
                        yield "data: " + json.dumps({"text": censorship}) + "\n\n"
                else:
                    output["answer"] = answer

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

        if self.check_input_guard(project, questionModel.question, user, db, output):
            yield output
            return

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

        if project.props.options.enable_knowledge_graph:
            postprocessors.append(
                EntityBoostPostprocessor(
                    brain=self.brain, db=db, project_id=project.props.id, query=questionModel.question,
                )
            )

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
            try:
                response = query_engine.query(questionModel.question)
            except Exception as primary_error:
                fallback_name = project.props.options.fallback_llm if project.props.options else None
                if fallback_name:
                    fallback_model = self.brain.get_llm(fallback_name, db)
                    if fallback_model:
                        logging.warning("Primary LLM failed in RAG query, using fallback '%s': %s", fallback_name, primary_error)
                        fallback_synthesizer = get_response_synthesizer(llm=fallback_model.llm)
                        fallback_engine = RetrieverQueryEngine(
                            retriever=retriever,
                            response_synthesizer=fallback_synthesizer,
                            node_postprocessors=postprocessors,
                        )
                        response = fallback_engine.query(questionModel.question)
                    else:
                        raise primary_error
                else:
                    raise primary_error

            if hasattr(response, "source_nodes"):
                for node in response.source_nodes:
                    output["sources"].append(
                        {
                            "source": node.metadata.get("source", "unknown"),
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
                parts = []
                if hasattr(response, "response_gen"):
                    for text in response.response_gen:
                        parts.append(text)
                        yield "data: " + json.dumps({"text": text}) + "\n\n"

                answer = "".join(parts).strip()
                if not answer or len(response.source_nodes) == 0:
                    censorship = project.props.censorship or self.brain.defaultCensorship
                    output["answer"] = censorship
                    if not parts:
                        yield "data: " + json.dumps({"text": censorship}) + "\n\n"
                else:
                    output["answer"] = answer

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
