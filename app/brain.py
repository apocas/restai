import os
from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain, LLMChain
from langchain.vectorstores import Chroma

from app.project import Project
from modules.embeddings import EMBEDDINGS
from modules.llms import LLMS


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}
        self.embeddingCache = {}

        self.text_splitter = CharacterTextSplitter(
            separator=" ", chunk_size=1024, chunk_overlap=0)

    def getLLM(self, llmModel, **kwargs):
        if llmModel in self.llmCache:
            return self.llmCache[llmModel]
        else:
            if llmModel in LLMS:
                llm_class, llm_args = LLMS[llmModel]
                llm = llm_class(**llm_args, **kwargs)
                self.llmCache[llmModel] = llm
                return llm
            else:
                raise Exception("Invalid LLM type.")

    def getEmbedding(self, embeddingModel, **kwargs):
        if embeddingModel in self.embeddingCache:
            return self.embeddingCache[embeddingModel]
        else:
            if embeddingModel in EMBEDDINGS:
                embedding_class, embedding_args = EMBEDDINGS[embeddingModel]
                model = embedding_class(**embedding_args)
                self.embeddingCache[embeddingModel] = model
                return model
            else:
                raise Exception("Invalid Embedding type.")

    def listProjects(self):
        return [project.model.name for project in self.projects]

    def createProject(self, projectModel):
        project = Project()
        project.boot(projectModel)
        kwargs = {}
        if project.model.embeddings_model != None:
            kwargs["model"] = project.model.embeddings_model
        embedding = self.getEmbedding(project.model.embeddings, **kwargs)
        project.db = Chroma(
            persist_directory=os.path.join(os.environ["EMBEDDINGS_PATH"], project.model.name), embedding_function=embedding
        )
        project.save()
        self.projects.append(project)

    def loadProject(self, name):
        for project in self.projects:
            if project.model.name == name:
                return project

        project = Project()
        project.load(name)
        project.db = Chroma(
            persist_directory=os.path.join(os.environ["EMBEDDINGS_PATH"], project.model.name), embedding_function=self.getEmbedding(project.model.embeddings, model=project.model.embeddings_model)
        )
        self.projects.append(project)
        return project

    def deleteProject(self, name):
        for project in self.projects:
            if project.model.name == name:
                project.delete()
                self.projects.remove(project)

    def question(self, project, questionModel):
        llm = self.getLLM(questionModel.llm or project.model.llm)
        
        retriever = project.db.as_retriever(
            search_type="similarity", search_kwargs={"k": 2}
        )

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
        )

        return qa.run(questionModel.question).strip()

    def chat(self, project, chatModel):
        llm = self.getLLM("chat")
        chat = project.loadChat(chatModel)

        retriever = project.db.as_retriever(
            search_type="similarity", search_kwargs={"k": 2}
        )

        self.conversationalChain = ConversationalRetrievalChain.from_llm(
            llm=llm, retriever=retriever
        )

        result = self.conversationalChain(
            {"question": chatModel.message, "chat_history": chat.history}
        )
        chat.history.append((chatModel.message, result["answer"]))
        return chat, result["answer"].strip()

    def questionContext(self, project, questionModel):
        llm = self.getLLM(questionModel.llm or "chat")

        prompt_template = """{system}

            Question: {{question}}
            =========
            Context: {{context}}
            =========
            Answer:""".format(system=questionModel.system)

        prompt = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )
        chain = LLMChain(llm=llm, prompt=prompt)

        docs = project.db.similarity_search(questionModel.question, k=1)
        inputs = [{"context": doc.page_content,
                   "question": questionModel.question} for doc in docs]
        return chain.apply(inputs)[0]["text"].strip()
