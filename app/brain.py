import gc
import os
import threading
import langchain
from llama_index import LLMPredictor, SQLDatabase, ServiceContext
from llama_index import (
    get_response_synthesizer,
)
from llama_index.embeddings.langchain import LangchainEmbedding
from llama_index.retrievers import VectorIndexRetriever
from llama_index.query_engine import RetrieverQueryEngine
from llama_index.postprocessor import SimilarityPostprocessor
from llama_index.prompts import PromptTemplate
from llama_index.chat_engine.condense_plus_context  import CondensePlusContextChatEngine
from langchain.agents import initialize_agent
from sqlalchemy import create_engine
import torch
from app.llms.llava import LlavaLLM
from app.llms.loader import localLoader
from app.llms.tools.dalle import DalleImage
from app.llms.tools.describeimage import DescribeImage
from app.llms.tools.refineimage import RefineImage
from app.llms.tools.stablediffusion import StableDiffusionImage
from app.model import Model

from app.models import ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel
from app.project import Project
from app.vectordb import vector_init
from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from app.database import dbc
from sqlalchemy.orm import Session
from llama_index.llms import LangChainLLM
from langchain.chat_models import ChatOpenAI
from llama_index.indices.struct_store.sql_query import NLSQLTableQueryEngine


from langchain.chains import LLMChain

from modules.prompts import PROMPTS


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}
        self.defaultCensorship = "This question is outside of my scope. Please ask another question."
        self.defaultNegative = "I'm sorry, I don't know the answer to that."
        self.defaultSystem = ""
        self.loopFailsafe = 0
        self.semaphore = threading.BoundedSemaphore()

    def memoryModelsInfo(self):
        models = []
        for llmr, mr in self.llmCache.items():
            if mr.privacy == "private":
                models.append(llmr)
        return models

    def unloadLLMs(self):
        unloaded = False
        models_to_unload = []
        for llmr, mr in self.llmCache.items():
            if mr.model is not None or mr.tokenizer is not None or isinstance(mr.llm, LlavaLLM):
                print("UNLOADING MODEL " + llmr)
                models_to_unload.append(llmr)

        for modelr in models_to_unload:
            if isinstance(self.llmCache[modelr].llm, LlavaLLM):
                self.llmCache[modelr].llm.model = None
                self.llmCache[modelr].llm.processor = None
                self.llmCache[modelr].llm = None
            else:
                self.llmCache[modelr].llm = None
                self.llmCache[modelr].pipe = None
                self.llmCache[modelr].tokenizer = None
                self.llmCache[modelr].model = None

            gc.collect()
            torch.cuda.empty_cache()

            if isinstance(self.llmCache[modelr].llm, LlavaLLM):
                del self.llmCache[modelr].llm.model
                del self.llmCache[modelr].llm.processor
                del self.llmCache[modelr].llm
            else:
                del self.llmCache[modelr].llm
                del self.llmCache[modelr].pipe
                del self.llmCache[modelr].tokenizer
                del self.llmCache[modelr].model

            self.llmCache[modelr] = None
            del self.llmCache[modelr]

            gc.collect()
            torch.cuda.empty_cache()

            unloaded = True
        return unloaded

    def getLLM(self, llmModel, forced=False, **kwargs):
        new = False
        if llmModel in self.llmCache:
            return self.llmCache[llmModel], False
        else:
            new = True
            if forced == False:
                self.semaphore.acquire()
                unloaded = self.unloadLLMs()

            if llmModel in LLMS:
                llm_class, llm_args, prompt, privacy, description, typel, llm_node = LLMS[
                    llmModel]

                if llm_class == localLoader:
                    print("LOADING MODEL " + llmModel)
                    llm, model, tokenizer, pipe = llm_class(
                        **llm_args, **kwargs)
                    m = Model(
                        llmModel,
                        llm,
                        prompt,
                        privacy,
                        model,
                        tokenizer,
                        pipe,
                        typel)
                else:
                    if llm_class == LlavaLLM:
                        print("LOADING MODEL " + llmModel)
                    llm = llm_class(**llm_args, **kwargs)
                    m = Model(llmModel, llm, prompt, privacy, type=typel)

                self.llmCache[llmModel] = m
                return m, new
            else:
                raise Exception("Invalid LLM type.")

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
                if os.environ["RESTAI_NODE"] != "node1":
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

        if projectModel.sandbox_project is not None and proj_db.sandbox_project != projectModel.sandbox_project:
            proj_db.sandbox_project = projectModel.sandbox_project
            changed = True

        if proj_db.sandboxed == True and projectModel.sandbox_project is None:
            proj_db.sandbox_project = None
            changed = True

        if changed:
            dbc.update_project(db)
            project.model = ProjectModel.model_validate(proj_db)

        return project

    def deleteProject(self, name, db):
        self.findProject(name, db)
        dbc.delete_project(db, dbc.get_project_by_name(db, name))
        proj = self.findProject(name, db)
        if proj is not None:
            proj.delete()
            self.projects.remove(proj)
        return True

    def entryChat(self, projectName: str, input: ChatModel, db: Session):
        self.loopFailsafe = 0
        output = self.recursiveChat(projectName, input, db)
        return output

    def recursiveChat(
            self,
            projectName: str,
            input: ChatModel,
            db: Session,
            chatR=None):
        project = self.findProject(projectName, db)
        if chatR:
            chat = chatR
            questionInput = QuestionModel(
                question=input.question,
            )
            answer, docs, censored = self.questionContext(
                project, questionInput)
            output = {"source_documents": docs, "answer": answer}
        else:
            output, censored = self.chat(project, input)

        if censored:
            projectc = self.findProject(project.model.sandbox_project, db)
            if projectc is not None:
                if self.loopFailsafe >= 10:
                    return chat, {"source_documents": [],
                                  "answer": self.defaultNegative}
                self.loopFailsafe += 1
                output = self.recursiveChat(
                    project.model.sandbox_project, input, db, chat)

        return output

    def chat(self, project, chatModel):
        model, loaded = self.getLLM(project.model.llm)
        chat = project.loadChat(chatModel)

        threshold = chatModel.score or project.model.score or 0.2
        k = chatModel.k or project.model.k or 1

        prompt_template_txt = PROMPTS[model.prompt]
        sysTemplate = project.model.system or self.defaultSystem

        prompt_template = prompt_template_txt.format(
            system=sysTemplate)


        service_context = ServiceContext.from_defaults(
            llm=LangChainLLM(llm=model.llm)
        )
        service_context.llm.query_wrapper_prompt = prompt_template

        retriever = VectorIndexRetriever(
            index=project.db,
            similarity_top_k=k,
        )

        llm = LangChainLLM(model.llm)
        #llm.query_wrapper_prompt = prompt_template

        chat_engine = CondensePlusContextChatEngine(
            retriever=retriever,
            llm=llm,
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)],
            memory=chat.history,
            verbose=True,
            context_prompt=(
                "You are a chatbot, able to have normal interactions, as well as talk about the provided context.\n"
                "Here are the relevant documents for the context:\n"
                "{context_str}"
                "\nInstruction: Use the previous chat history, or the context above, to interact and help the user."
            )
        )

        response = chat_engine.chat(chatModel.question)

        if loaded == True:
            self.semaphore.release()

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

    def entryQuestion(
            self,
            projectName: str,
            input: QuestionModel,
            db: Session):
        self.loopFailsafe = 0
        return self.recursiveQuestion(projectName, input, db)

    def recursiveQuestion(
            self,
            projectName: str,
            input: QuestionModel,
            db: Session,
            recursive=False):
        project = self.findProject(projectName, db)
        output, censored = self.questionContext(
            project, input, recursive)
        if censored:
            projectc = self.findProject(project.model.sandbox_project, db)
            if projectc is not None:
                if self.loopFailsafe >= 10:
                    return self.defaultNegative, []
                self.loopFailsafe += 1
                output, censored = self.recursiveQuestion(
                    project.model.sandbox_project, input, db, True)

        return output, censored

    def questionContext(self, project, questionModel, child=False):
        model, loaded = self.getLLM(project.model.llm)

        prompt_template_txt = PROMPTS[model.prompt]

        if child:
            sysTemplate = project.model.system or self.defaultSystem
        else:
            sysTemplate = questionModel.system or project.model.system or self.defaultSystem

        prompt_template = prompt_template_txt.format(system=sysTemplate)
        #query_wrapper_prompt = PromptTemplate(prompt_template)

        k = questionModel.k or project.model.k or 2
        threshold = questionModel.score or project.model.score or 0.2

        service_context = ServiceContext.from_defaults(
            llm=LangChainLLM(llm=model.llm)
        )
        service_context.llm.query_wrapper_prompt = prompt_template

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

        if isinstance(model.llm, ChatOpenAI):
            qa_prompt_tmpl = sysTemplate + "\n" + qa_prompt_tmpl

        qa_prompt = PromptTemplate(qa_prompt_tmpl)

        response_synthesizer = get_response_synthesizer(
            service_context=service_context, text_qa_template=qa_prompt)

        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)]
        )

        response = query_engine.query(questionModel.question)

        if loaded == True:
            self.semaphore.release()

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

    def entryVision(self, projectName, visionInput, db: Session):
        image = None
        output = ""

        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")

        tools = [
            DalleImage(),
            StableDiffusionImage(),
            RefineImage(),
            DescribeImage(),
        ]

        model, loaded = self.getLLM("openai_gpt3.5", True)

        self.semaphore.acquire()
        self.unloadLLMs()

        agent = initialize_agent(
            tools, model.llm, agent="zero-shot-react-description", verbose=True)
        outputAgent = agent.run(visionInput.question, tags=[visionInput])

        if isinstance(outputAgent, str):
            output = outputAgent
        else:
            if outputAgent["type"] == "describeimage":
                model, loaded = self.getLLM(project.model.llm, True)

                prompt_template_txt = PROMPTS[model.prompt]
                input = prompt_template_txt.format(
                    query_str=visionInput.question)

                output = model.llm.llavaInference(input, visionInput.image)
            else:
                output = outputAgent["prompt"]
                image = outputAgent["image"]

        try:
            self.semaphore.release()
        except ValueError:
            pass

        return output, [], image

    def inference(self, projectName, inferenceModel, db: Session):
        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")
        
        model, loaded = self.getLLM(project.model.llm)

        prompt_template_txt = PROMPTS[model.prompt]
        sysTemplate = inferenceModel.system or project.model.system or self.defaultSystem
        prompt_template = prompt_template_txt.format(system=sysTemplate)

        prompt = langchain.prompts.PromptTemplate(
            template=prompt_template, input_variables=["query_str"]
        )
        chain = LLMChain(llm=model.llm, prompt=prompt)
        inputs = [{"query_str": inferenceModel.question}]
        resp = chain.apply(inputs)

        output = {
            "question": inferenceModel.question,
            "answer": resp[0]["text"].strip(),
            "type": "inference"
        }

        if loaded == True:
            self.semaphore.release()

        return output
    
    def ragSQL(self, projectName, questionModel, db: Session):
        project = self.findProject(projectName, db)
        if project is None:
            raise Exception("Project not found")
        
        model, loaded = self.getLLM(project.model.llm)

        engine = create_engine(project.model.connection)

        sql_database = SQLDatabase(engine)

        llm_predictor = LLMPredictor(llm=model.llm)
        service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)

        tables = None
        if hasattr(questionModel, 'tables') and questionModel.tables is not None:
            tables = questionModel.tables

        query_engine = NLSQLTableQueryEngine(
            sql_database=sql_database,
            service_context=service_context,
            tables=tables,
        )

        response = query_engine.query(questionModel.question)

        output = {
            "question": questionModel.question,
            "answer": response.response,
            "sources": [response.metadata['sql_query']],
            "type": "questionsql"
        }

        if loaded == True:
            self.semaphore.release()

        return output