import json
from httpx import HTTPStatusError
from llama_index.core.service_context_elements.llm_predictor import LLMPredictor
from llama_index.core.utilities.sql_wrapper import SQLDatabase
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.embeddings.langchain import LangchainEmbedding
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.prompts import PromptTemplate
from llama_index.core.chat_engine import CondensePlusContextChatEngine, ContextChatEngine
from llama_index.core.indices.struct_store.sql_query import NLSQLTableQueryEngine
from llama_index.core.schema import ImageDocument
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.postprocessor.llm_rerank import LLMRerank
from llama_index.postprocessor.colbert_rerank import ColbertRerank
from langchain.agents import initialize_agent
import ollama
from sqlalchemy import create_engine
from app.llms.tools.dalle import DalleImage
from app.llms.tools.describeimage import DescribeImage
from app.llms.tools.instantid import InstantID
from app.llms.tools.stablediffusion import StableDiffusionImage
from app.model import Model

from app.models import LLMModel, ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel
from app.project import Project
from app.tools import getLLMClass
from app.vectordb import vector_init
from modules.embeddings import EMBEDDINGS
from app.database import dbc
from sqlalchemy.orm import Session
from langchain_community.chat_models import ChatOpenAI


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}
        self.defaultCensorship = "This question is outside of my scope. Didn't find any related data."
        self.defaultNegative = "I'm sorry, I don't know the answer to that."
        self.defaultSystem = ""
        self.loopFailsafe = 0

    def memoryModelsInfo(self):
        models = []
        for llmr, mr in self.llmCache.items():
            if mr.privacy == "private":
                models.append(llmr)
        return models

    def getLLM(self, llmName, db: Session, **kwargs):      
        llm = None
      
        if llmName in self.llmCache:
            llm = self.llmCache[llmName]
        else:
            llm = self.loadLLM(llmName, db)
        
        if llm.props.class_name == "Ollama":
            model_name = json.loads(llm.props.options).get("model")
            try:
                ollama.show(model_name)
            except Exception as e:
              if isinstance(e, HTTPStatusError) and e.response.status_code == 404:
                  ollama.pull(model_name)
              else:
                  pass
        
        return llm
    
    def loadLLM(self, llmName, db: Session):
        llm_db = dbc.get_llm_by_name(db, llmName)

        if llm_db is not None:
            llmm = LLMModel.model_validate(llm_db)

            llm = getLLMClass(llmm.class_name)(**json.loads(llmm.options))

            if llmName in self.llmCache:
                del self.llmCache[llmName]
            self.llmCache[llmName] = Model(llmName, llmm, llm)
            return self.llmCache[llmName]
        else:
            return None

    def getEmbedding(self, embeddingModel):
        if embeddingModel in self.embeddingCache:
            return self.embeddingCache[embeddingModel]
        else:
            if embeddingModel in EMBEDDINGS:
                embedding_class, embedding_args, privacy, description = EMBEDDINGS[embeddingModel]
                model = LangchainEmbedding(embedding_class(**embedding_args))
                self.embeddingCache[embeddingModel] = model
                return model
            else:
                raise Exception("Invalid Embedding type.")

    def findProject(self, name, db):
        for project in self.projects:
            if project.model.name == name:
                p = dbc.get_project_by_name(db, name)
                if p is None:
                    return None
                proj = ProjectModel.model_validate(p)
                project.model = proj
                return project

        p = dbc.get_project_by_name(db, name)
        if p is None:
            return None
        proj = ProjectModel.model_validate(p)
        if proj is not None:
            project = Project()
            project.model = proj
            if project.model.type == "rag":
                project.db = vector_init(self, project)
            self.projects.append(project)
            return project

    def createProject(self, projectModel, db):
        dbc.create_project(
            db,
            projectModel.name,
            projectModel.embeddings,
            projectModel.llm,
            projectModel.vectorstore,
            projectModel.type,
        )
        project = Project()
        project.boot(projectModel)
        project.db = vector_init(self, project)
        self.projects.append(project)
        return project

    def editProject(self, name, projectModel: ProjectModelUpdate, db):
        project = self.findProject(name, db)
        if project is None:
            return False

        proj_db = dbc.get_project_by_name(db, name)
        if proj_db is None:
            raise Exception("Project not found")

        changed = False
        if projectModel.llm is not None and proj_db.llm != projectModel.llm:
            proj_db.llm = projectModel.llm
            changed = True

        if projectModel.system is not None and proj_db.system != projectModel.system:
            proj_db.system = projectModel.system
            changed = True

        if projectModel.censorship is not None and proj_db.censorship != projectModel.censorship:
            proj_db.censorship = projectModel.censorship
            changed = True

        if projectModel.k is not None and proj_db.k != projectModel.k:
            proj_db.k = projectModel.k
            changed = True

        if projectModel.score is not None and proj_db.score != projectModel.score:
            proj_db.score = projectModel.score
            changed = True

        if projectModel.connection is not None and proj_db.system != projectModel.connection and "://xxxx:xxxx@" not in projectModel.connection:
            proj_db.connection = projectModel.connection
            changed = True
        
        if projectModel.tables is not None and proj_db.tables != projectModel.tables:
            proj_db.tables = projectModel.tables
            changed = True
            
        if projectModel.llm_rerank is not None and proj_db.llm_rerank != projectModel.llm_rerank:
            proj_db.llm_rerank = projectModel.llm_rerank
            changed = True
        
        if projectModel.colbert_rerank is not None and proj_db.colbert_rerank != projectModel.colbert_rerank:
            proj_db.colbert_rerank = projectModel.colbert_rerank
            changed = True

        if changed:
            dbc.update_project(db)
            project.model = ProjectModel.model_validate(proj_db)

        return project

    def deleteProject(self, name, db):
        proj = self.findProject(name, db)
        dbc.delete_project(db, dbc.get_project_by_name(db, name))
        if proj is not None:
            proj.delete()
            self.projects.remove(proj)
        return True

    def entryChat(self, projectName: str, chatModel: ChatModel, db: Session):
        project = self.findProject(projectName, db)

        model = self.getLLM(project.model.llm, db)
        chat = project.loadChat(chatModel)

        threshold = chatModel.score or project.model.score or 0.2
        k = chatModel.k or project.model.k or 1

        sysTemplate = project.model.system or self.defaultSystem
        
        if project.model.colbert_rerank or project.model.llm_rerank:
            final_k = k * 2
        else:
            final_k = k

        retriever = VectorIndexRetriever(
            index=project.db,
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
            memory=chat.history,
            node_postprocessors=postprocessors,
        )
        chat_engine._llm = model.llm

        try:
            if chatModel.stream:
                response = chat_engine.stream_chat(chatModel.question)
            else:
                response = chat_engine.chat(chatModel.question)

            output_nodes = []
            for node in response.source_nodes:
                output_nodes.append(
                    {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})

            output = {
                "id": chat.id,
                "question": chatModel.question,
                "sources": output_nodes,
                "type": "chat"
            }

            if chatModel.stream:
                if hasattr(response, "response_gen"): 
                    for text in response.response_gen:
                        yield "data: " + text + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else:
                    yield "data: " + self.defaultCensorship + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:  
                if len(response.source_nodes) == 0:
                    output["answer"] = project.model.censorship or self.defaultCensorship
                else:
                    output["answer"] = response.response

                yield output
        except Exception as e:              
            if chatModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e


    def entryQuestion(self, projectName: str, questionModel: QuestionModel, db: Session):
        project = self.findProject(projectName, db)

        model = self.getLLM(project.model.llm, db)

        sysTemplate = questionModel.system or project.model.system or self.defaultSystem

        k = questionModel.k or project.model.k or 2
        threshold = questionModel.score or project.model.score or 0.2

        if questionModel.colbert_rerank or questionModel.llm_rerank or project.model.colbert_rerank or project.model.llm_rerank:
            final_k = k * 2
        else:
            final_k = k

        retriever = VectorIndexRetriever(
            index=project.db,
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

        llm_predictor = LLMPredictor(llm=model.llm, system_prompt=sysTemplate)

        response_synthesizer = get_response_synthesizer(llm=llm_predictor, text_qa_template=qa_prompt, streaming=questionModel.stream)

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

            output_nodes = []
            if hasattr(response, "source_nodes"): 
                for node in response.source_nodes:
                    output_nodes.append(
                        {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})
                    
            output = {
                "question": questionModel.question,
                "sources": output_nodes,
                "type": "question"
            }

            if questionModel.stream:
                if hasattr(response, "response_gen"): 
                    for text in response.response_gen:
                        yield "data: " + text + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
                else :
                    yield "data: " + self.defaultCensorship + "\n\n"
                    yield "data: " + json.dumps(output) + "\n"
                    yield "event: close\n\n"
            else:
                if len(response.source_nodes) == 0:
                    output["answer"] = project.model.censorship or self.defaultCensorship
                else:
                    output["answer"] = response.response

                yield output
        except Exception as e:
            if questionModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e

    def entryVision(self, projectName, visionInput, isprivate, db: Session):
        image = None
        output = ""

        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        tools = [
            DalleImage(),
            StableDiffusionImage(),
            DescribeImage(),
            InstantID(),
        ]

        if isprivate:
            tools.pop(0)

        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

        agent = initialize_agent(
            tools, llm, agent="zero-shot-react-description", verbose=True)
        
        outputAgent = agent.run(visionInput.question, tags=[visionInput])

        if isinstance(outputAgent, str):
            output = outputAgent
        else:
            if outputAgent["type"] == "describeimage":
                model = self.getLLM(project.model.llm, db)

                try:
                    response = model.llm.complete(prompt=visionInput.question, image_documents=[ImageDocument(image=visionInput.image)])
                except Exception as e:
                    raise e
                
                output = response.text
                image = visionInput.image
            else:
                output = outputAgent["prompt"]
                image = outputAgent["image"]

        return output, [], image

    def inference(self, projectName, inferenceModel, db: Session):
        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        model = self.getLLM(project.model.llm, db)

        sysTemplate = inferenceModel.system or project.model.system or self.defaultSystem
        model.llm.system_prompt = sysTemplate

        #model.llm.system = sysTemplate
        #resp = model.llm.complete(inferenceModel.question)
        messages = [
            ChatMessage(
                role="system", content=sysTemplate
            ),
            ChatMessage(role="user", content=inferenceModel.question),
        ]

        try:
            if(inferenceModel.stream):
                respgen = model.llm.stream_chat(messages)
                for text in respgen:
                    yield "data: " + text.delta + "\n\n"
                yield "event: close\n\n"
            else:
                resp = model.llm.chat(messages)
                output = {
                    "question": inferenceModel.question,
                    "answer": resp.message.content.strip(),
                    "type": "inference"
                }
                yield output
        except Exception as e:              
            if inferenceModel.stream:
                yield "data: Inference failed\n"
                yield "event: error\n\n"
            raise e

    def ragSQL(self, projectName, questionModel, db: Session):
        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        model = self.getLLM(project.model.llm, db)

        engine = create_engine(project.model.connection)

        sql_database = SQLDatabase(engine)

        tables = None
        if hasattr(questionModel, 'tables') and questionModel.tables is not None:
            tables = questionModel.tables
        elif project.model.tables:
            tables = [table.strip() for table in project.model.tables.split(',')]

        query_engine = NLSQLTableQueryEngine(
            llm=model.llm,
            sql_database=sql_database,
            tables=tables,
        )

        question = (project.model.system or self.defaultSystem) + "\n Question: " + questionModel.question

        try:
            response = query_engine.query(question)
        except Exception as e:
            raise e

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": [response.metadata['sql_query']],
            "type": "questionsql"
        }

        return output
