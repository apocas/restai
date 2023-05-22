from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain import OpenAI
from langchain.llms import GPT4All, LlamaCpp

from app.project import Project

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}),
    "llamacpp": (LlamaCpp, {"model": "./models/ggml-model-q4_0.bin"}),
    "gpt4all": (GPT4All, {"model": "./models/ggml-gpt4all-j-v1.3-groovy.bin", "backend": "gptj", "n_ctx": 1000}),
}


class Brain:
    def __init__(self):
        self.projects = []

        self.text_splitter = CharacterTextSplitter(
            separator=" ", chunk_size=1024, chunk_overlap=0)

        self.llmCache = {}

    def loadLLM(self, llmModel, **kwargs):
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

        llm = self.loadLLM(questionModel.llm or project.model.llm)

        qa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
        )

        return qa.run(questionModel.question)
