import json
from typing import Optional

from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.prompts import PromptTemplate
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.postprocessor.llm_rerank import LLMRerank
from llama_index.postprocessor.colbert_rerank import ColbertRerank
from app.chat import Chat
from app.database import DBWrapper
from app.eval import eval_rag
from app.guard import Guard
from app.llm import LLM
from app.models.models import QuestionModel, ChatModel, User
from app.project import Project
from app.tools import tokens_from_string
from app.projects.base import ProjectBase


class RAG(ProjectBase):

    def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        model: Optional[LLM] = self.brain.get_llm(project.model.llm, db)
        chat: Chat = Chat(chatModel, self.brain.chat_store)
        
        output = {
            "id": chat.chat_id,
            "question": chatModel.question,
            "sources": [],
            "cached": False,
            "guard": False,
            "type": "chat",
            "project": project.model.name
        }
        
        if project.model.guard:
            guard = Guard(project.model.guard, self.brain, db)
            if guard.verify(chatModel.question):
                output["answer"] = project.model.censorship or self.brain.defaultCensorship
                output["guard"] = True
                output["tokens"] = {
                  "input": tokens_from_string(output["question"]),
                  "output": tokens_from_string(output["answer"])
                }
                yield output

        threshold = project.model.score or 0.2
        k = project.model.k or 1

        sysTemplate = project.model.system or self.brain.defaultSystem
        
        if project.model.colbert_rerank or project.model.llm_rerank:
            final_k = k * 2
        else:
            final_k = k

        retriever = VectorIndexRetriever(
            index=project.vector.index,
            similarity_top_k=final_k,
        )

        postprocessors = []

        if project.model.colbert_rerank:
            postprocessors.append(ColbertRerank(
                top_n=k,
                model="colbert-ir/colbertv2.0",
                tokenizer="colbert-ir/colbertv2.0",
                keep_retrieval_score=True,
            ))

        if project.model.llm_rerank:
            postprocessors.append(LLMRerank(
                choice_batch_size=k,
                top_n=k,
                llm=model.llm,
            ))
            
        postprocessors.append(SimilarityPostprocessor(similarity_cutoff=threshold))

        chat_engine = ContextChatEngine.from_defaults(
            retriever=retriever,
            system_prompt=sysTemplate,
            memory=chat.memory,
            node_postprocessors=postprocessors,
            llm=model.llm
        )

        try:
            if chatModel.stream:
                response = chat_engine.stream_chat(chatModel.question)
            else:
                response = chat_engine.chat(chatModel.question)

            for node in response.source_nodes:
                output["sources"].append(
                    {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})

            if chatModel.stream:
                if hasattr(response, "response_gen"):
                    resp = ""
                    for text in response.response_gen:
                        resp += text
                        yield "data: " + json.dumps({"text": text}) + "\n\n"
                    output["answer"] = resp
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    output["answer"] = self.brain.defaultCensorship
                    yield "data: " + json.dumps({"text": "text"}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:  
                if len(response.source_nodes) == 0:
                    output["answer"] = project.model.censorship or self.brain.defaultCensorship
                else:
                    output["answer"] = response.response
                    
                    if project.cache:
                        project.cache.add(chatModel.question, response.response)

                output["tokens"] = {
                  "input": tokens_from_string(output["question"]),
                  "output": tokens_from_string(output["answer"])
                }

                yield output
        except Exception as e:              
            if chatModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e


    def question(self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper):
        output = {
          "question": questionModel.question,
          "type": "question",
          "sources": [],
          "cached": False,
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
                  "input": tokens_from_string(output["question"]),
                  "output": tokens_from_string(output["answer"])
                }
                yield output
            
        model = self.brain.get_llm(project.model.llm, db)

        sysTemplate = questionModel.system or project.model.system or self.brain.defaultSystem

        k = questionModel.k or project.model.k or 2
        threshold = questionModel.score or project.model.score or 0.2

        if questionModel.colbert_rerank or questionModel.llm_rerank or project.model.colbert_rerank or project.model.llm_rerank:
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

        response_synthesizer = get_response_synthesizer(llm=model.llm, text_qa_template=qa_prompt, streaming=questionModel.stream)

        postprocessors = []

        if questionModel.colbert_rerank or project.model.colbert_rerank:
            postprocessors.append(ColbertRerank(
                top_n=k,
                model="colbert-ir/colbertv2.0",
                tokenizer="colbert-ir/colbertv2.0",
                keep_retrieval_score=True,
            ))

        if questionModel.llm_rerank or project.model.llm_rerank:
            postprocessors.append(LLMRerank(
                choice_batch_size=k,
                top_n=k,
                llm=model.llm,
            ))
            
        postprocessors.append(SimilarityPostprocessor(similarity_cutoff=threshold))
        
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
            node_postprocessors=postprocessors
        )

        try:
            response = query_engine.query(questionModel.question)

            if hasattr(response, "source_nodes"): 
                for node in response.source_nodes:
                    output["sources"].append(
                        {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})
            
            if questionModel.eval and not questionModel.stream:
                metric = eval_rag(questionModel.question, response, self.brain.get_llm("openai_gpt4", db).llm)
                output["evaluation"] = {
                    "reason": metric.reason,
                    "score": metric.score
                }

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
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else :
                    output["answer"] = self.brain.defaultCensorship
                    yield "data: " + json.dumps({"text": self.brain.defaultCensorship}) + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:
                if len(response.source_nodes) == 0:
                    output["answer"] = project.model.censorship or self.brain.defaultCensorship
                else:
                    output["answer"] = response.response
                    
                    if project.cache:
                        project.cache.add(questionModel.question, response.response)

                output["tokens"] = {
                  "input": tokens_from_string(output["question"]),
                  "output": tokens_from_string(output["answer"])
                }

                yield output
        except Exception as e:
            if questionModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e
