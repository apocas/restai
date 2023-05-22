from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain import LLMChain, OpenAI, PromptTemplate
from langchain.llms import GPT4All, LlamaCpp
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain

from app.project import Project

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}),
    "llamacpp": (LlamaCpp, {"model": "./models/ggml-model-q4_0.bin"}),
    "gpt4all": (GPT4All, {"model": "./models/ggml-gpt4all-j-v1.3-groovy.bin", "backend": "gptj", "n_ctx": 1000}),
    "chat": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-3.5-turbo"}),
    "chat4": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-4"}),
}


class Brain:
    def __init__(self):
        self.projects = []
        self.llmCache = {}

        self.text_splitter = CharacterTextSplitter(
            separator=" ", chunk_size=1024, chunk_overlap=0)

    def getLLM(self, llmModel, **kwargs):
        if llmModel in self.llmCache:
            return self.llmCache[llmModel]
        else:
            if llmModel in LLMS:
                loader_class, llm_args = LLMS[llmModel]
                llm = loader_class(**llm_args, **kwargs)
                self.llmCache[llmModel] = llm
                return llm
            else:
                raise HTTPException(
                    status_code=500, detail='{"error": "Invalid LLM type."}')

    def listProjects(self):
        return [project.model.name for project in self.projects]

    def createProject(self, projectModel):
        project = Project()
        project.boot(projectModel)
        project.save()
        self.projects.append(project)

    def loadProject(self, name):
        for project in self.projects:
            if project.model.name == name:
                return project

        project = Project()
        project.load(name)
        self.projects.append(project)
        return project

    def deleteProject(self, name):
        for project in self.projects:
            if project.model.name == name:
                project.delete()
                self.projects.remove(project)

    def question(self, project, questionModel):
        retriever = project.db.as_retriever(
            search_type="similarity", search_kwargs={"k": 2}
        )

        llm = self.getLLM(questionModel.llm or project.model.llm)

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
