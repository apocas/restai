import gc
import os
import queue
import threading
from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain, LLMChain
from langchain.vectorstores import Chroma
import torch
from app.loader import localLoader
from app.model import Model

from app.models import EmbeddingModel, ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel
from app.project import Project
from app.tools import FindEmbeddingsPath, print_cuda_mem
from app.vectordb import vector_init
from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS
from app.database import dbc
from sqlalchemy.orm import Session

from modules.prompts import PROMPTS


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}
        self.defaultCensorship = "This question is outside of my scope. Please ask another question."
        self.defaultNegative = "I'm sorry, I don't know the answer to that."
        self.defaultSystem = "You are a digital assistant, answer the question about the following context. NEVER invent an answer, if you don't know the answer, just say you don't know. If you don't understand the question, just say you don't understand."
        self.loopFailsafe = 0
        self.semaphore = threading.BoundedSemaphore()

        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=[" "], chunk_size=1024, chunk_overlap=30)
        
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
            if mr.model is not None or mr.tokenizer is not None:
                print("UNLOADING MODEL " + llmr)
                models_to_unload.append(llmr)

        for modelr in models_to_unload:
            #print_cuda_mem()
            self.llmCache[modelr].model = None
            self.llmCache[modelr].tokenizer = None
            self.llmCache[modelr].pipe = None
            gc.collect()
            torch.cuda.empty_cache()
            del self.llmCache[modelr].model
            del self.llmCache[modelr].tokenizer
            del self.llmCache[modelr].pipe
            self.llmCache[modelr] = None
            del self.llmCache[modelr]
            gc.collect()
            torch.cuda.empty_cache()
            #print_cuda_mem()
            unloaded = True
        return unloaded

    def getLLM(self, llmModel, **kwargs):
        new = False
        if llmModel in self.llmCache:
            return self.llmCache[llmModel], False
        else:
            new = True
            self.semaphore.acquire()
            unloaded = self.unloadLLMs()

            if llmModel in LLMS:
                llm_class, llm_args, prompt, privacy, description = LLMS[llmModel]

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
                        pipe)
                else:
                    llm = llm_class(**llm_args, **kwargs)
                    m = Model(llmModel, llm, prompt, privacy)

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
                model = embedding_class(**embedding_args)
                self.embeddingCache[embeddingModel] = model
                return model
            else:
                raise Exception("Invalid Embedding type.")

    def findProject(self, name, db):
        for project in self.projects:
            if project.model.name == name:
                return project

        p = dbc.get_project_by_name(db, name)
        if p is None:
            return None
        proj = ProjectModel.model_validate(p)
        if proj is not None:
            project = Project()
            project.model = proj
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

        if projectModel.sandbox_project is not None and proj_db.sandbox_project != projectModel.sandbox_project:
            proj_db.sandbox_project = projectModel.sandbox_project
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
        chat, output = self.recursiveChat(projectName, input, db)
        chat.history.append((input.question, output["answer"]))
        return chat, output

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
            chat, output, censored = self.chat(project, input)

        if censored:
            projectc = self.findProject(project.model.sandbox_project, db)
            if projectc is not None:
                if self.loopFailsafe >= 10:
                    return chat, {"source_documents": [],
                                  "answer": self.defaultNegative}
                self.loopFailsafe += 1
                chat, output = self.recursiveChat(
                    project.model.sandbox_project, input, db, chat)

        return chat, output

    def chat(self, project, chatModel):
        model, loaded = self.getLLM(project.model.llm)
        chat = project.loadChat(chatModel)

        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "score_threshold": chatModel.score or project.model.score or 0.2,
                "k": chatModel.k or project.model.k or 1})

        prompt_template_txt = PROMPTS[model.prompt]
        sysTemplate = project.model.system or self.defaultSystem
        prompt_template = prompt_template_txt.format(
            system=sysTemplate, history="Chat History: {chat_history}")

        custom_prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question", "chat_history"],
        )

        conversationalChain = ConversationalRetrievalChain.from_llm(
            llm=model.llm,
            retriever=retriever,
            return_source_documents=True,
            combine_docs_chain_kwargs={
                "prompt": custom_prompt})

        result = conversationalChain(
            {"question": chatModel.question, "chat_history": chat.history}
        )
        
        if loaded == True:
            self.semaphore.release()

        if project.model.sandboxed and len(result["source_documents"]) == 0:
            return chat, {"source_documents": [
            ], "answer": project.model.censorship or self.defaultCensorship}, True

        return chat, result, False

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
        answer, docs, censored = self.questionContext(
            project, input, recursive)
        if censored:
            projectc = self.findProject(project.model.sandbox_project, db)
            if projectc is not None:
                if self.loopFailsafe >= 10:
                    return self.defaultNegative, []
                self.loopFailsafe += 1
                answer, docs = self.recursiveQuestion(
                    project.model.sandbox_project, input, db, True)

        return answer, docs

    def questionContext(self, project, questionModel, child=False):
        model, loaded = self.getLLM(project.model.llm)

        prompt_template_txt = PROMPTS[model.prompt]

        if child:
            sysTemplate = project.model.system or self.defaultSystem
        else:
            sysTemplate = questionModel.system or project.model.system or self.defaultSystem

        prompt_template = prompt_template_txt.format(
            system=sysTemplate, history="")

        prompt = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )
        chain = LLMChain(llm=model.llm, prompt=prompt)

        retriever = project.db.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "score_threshold": questionModel.score or project.model.score or 0.2,
                "k": questionModel.k or project.model.k or 1})

        try:
            docs = retriever.get_relevant_documents(questionModel.question)
        except BaseException:
            docs = []

        if len(docs) == 0:
            if project.model.sandboxed:
                return project.model.censorship or self.defaultCensorship, [], True
            else:
                inputs = [{"context": "",
                           "question": questionModel.question}]
        else:
            inputs = [{"context": doc.page_content,
                       "question": questionModel.question} for doc in docs]

        output = chain.apply(inputs)
        
        if loaded == True:
            self.semaphore.release()
            
        return output[0]["text"].strip(), docs, False
