import json
from httpx import HTTPStatusError
from llama_index import LLMPredictor, SQLDatabase, ServiceContext
from llama_index import (
    get_response_synthesizer,
)
from llama_index.embeddings.langchain import LangchainEmbedding
from llama_index.retrievers import VectorIndexRetriever
from llama_index.query_engine import RetrieverQueryEngine
from llama_index.postprocessor import SimilarityPostprocessor
from llama_index.prompts import PromptTemplate
from llama_index.chat_engine import CondensePlusContextChatEngine, ContextChatEngine
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
from llama_index.indices.struct_store.sql_query import NLSQLTableQueryEngine

from llama_index.schema import ImageDocument

from llama_index.core.llms.types import ChatMessage


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}
        self.defaultCensorship = "This question is outside of my scope. Please ask another question."
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
        if llmName in self.llmCache:
            return self.llmCache[llmName]
        else:
            return self.loadLLM(llmName, db)
    
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
            projectModel.system,
            projectModel.sandboxed,
            projectModel.censorship,
            projectModel.vectorstore,
            projectModel.type,
            projectModel.connection,
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

        if projectModel.sandboxed is not None and proj_db.sandboxed != projectModel.sandboxed:
            proj_db.sandboxed = projectModel.sandboxed
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

        retriever = VectorIndexRetriever(
            index=project.db,
            similarity_top_k=k,
        )

        service_context = ServiceContext.from_defaults(
            llm=model.llm,
            system_prompt=sysTemplate
        )

        chat_engine = ContextChatEngine.from_defaults(
            service_context=service_context,
            retriever=retriever,
            system_prompt=sysTemplate,
            memory=chat.history,
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)],
        )

        try:
            response = chat_engine.chat(chatModel.question)
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                if model.props.class_name == "Ollama":
                    ollama.pull(json.loads(model.props.options).get("model"))
                    response = chat_engine.chat(chatModel.question)
            else:
                raise e

        output_nodes = []
        for node in response.source_nodes:
            output_nodes.append(
                {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})

        output = {
            "id": chat.id,
            "question": chatModel.question,
            "answer": response.response,
            "sources": output_nodes,
            "type": "chat"
        }

        censored = False
        if project.model.sandboxed and len(response.source_nodes) == 0:
            censored = True
            output["answer"] = project.model.censorship or self.defaultCensorship

        return output, censored

    def entryQuestion(self, projectName: str, questionModel: QuestionModel, db: Session):
        project = self.findProject(projectName, db)

        model = self.getLLM(project.model.llm, db)

        sysTemplate = questionModel.system or project.model.system or self.defaultSystem

        k = questionModel.k or project.model.k or 2
        threshold = questionModel.score or project.model.score or 0.2

        service_context = ServiceContext.from_defaults(
            llm=model.llm,
            system_prompt=sysTemplate
        )

        retriever = VectorIndexRetriever(
            index=project.db,
            similarity_top_k=k,
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

        response_synthesizer = get_response_synthesizer(
            service_context=service_context, text_qa_template=qa_prompt)

        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)]
        )

        try:
            response = query_engine.query(questionModel.question)
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                if model.props.class_name == "Ollama":
                    ollama.pull(json.loads(model.props.options).get("model"))
                    response = query_engine.query(questionModel.question)
            else:
                raise e

        output_nodes = []
        for node in response.source_nodes:
            output_nodes.append(
                {"source": node.metadata["source"], "keywords": node.metadata["keywords"], "score": node.score, "id": node.node_id, "text": node.text})

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": output_nodes,
            "type": "question"
        }

        censored = False
        if project.model.sandboxed and len(response.source_nodes) == 0:
            censored = True
            output["answer"] = project.model.censorship or self.defaultCensorship

        return output, censored

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
                except HTTPStatusError as e:
                    if e.response.status_code == 404:
                        if model.props.class_name == "Ollama":
                            ollama.pull(json.loads(model.props.options).get("model"))
                            response = model.llm.complete(prompt=visionInput.question, image_documents=[ImageDocument(image=visionInput.image)])
                    else:
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
            resp = model.llm.chat(messages)
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                if model.props.class_name == "Ollama":
                    ollama.pull(json.loads(model.props.options).get("model"))
                    resp = model.llm.chat(messages)
            else:
                raise e

        output = {
            "question": inferenceModel.question,
            "answer": resp.message.content.strip(),
            "type": "inference"
        }

        return output

    def ragSQL(self, projectName, questionModel, db: Session):
        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        model = self.getLLM(project.model.llm, db)

        engine = create_engine(project.model.connection)

        sql_database = SQLDatabase(engine)

        llm_predictor = LLMPredictor(llm=model.llm)
        service_context = ServiceContext.from_defaults(
            llm_predictor=llm_predictor
        )

        tables = None
        if hasattr(questionModel, 'tables') and questionModel.tables is not None:
            tables = questionModel.tables
        elif project.model.tables:
            tables = [table.strip() for table in project.model.tables.split(',')]

        query_engine = NLSQLTableQueryEngine(
            sql_database=sql_database,
            service_context=service_context,
            tables=tables,
        )

        question = (project.model.system or self.defaultSystem) + "\n Question: " + questionModel.question

        try:
            response = query_engine.query(question)
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                if model.props.class_name == "Ollama":
                    ollama.pull(json.loads(model.props.options).get("model"))
                    response = query_engine.query(question)
            else:
                raise e

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": [response.metadata['sql_query']],
            "type": "questionsql"
        }

        return output
