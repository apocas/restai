import json
import logging
import traceback
from llama_index.embeddings.langchain import LangchainEmbedding
from app.database import DBWrapper
from app.vectordb import tools as vector_tools
from app import tools
from app.llm import LLM
from app.models.models import LLMModel, ProjectModel, ClassifierModel
from app.project import Project
from modules.embeddings import EMBEDDINGS
from transformers import pipeline
from llama_index.core.tools import FunctionTool


class Brain:
    def __init__(self):
        self.embeddingCache = {}
        self.defaultCensorship = "I'm sorry, I don't know the answer to that."
        self.defaultSystem = ""
        self.tools = tools.load_tools()

    def get_llm(self, llmName, db: DBWrapper, **kwargs):
        llm = self.load_llm(llmName, db)

        if hasattr(llm.llm, 'system_prompt'):
            llm.llm.system_prompt = None
        return llm

    @staticmethod
    def load_llm(llmName: str, db: DBWrapper):
        llm_db = db.get_llm_by_name(llmName)

        if llm_db is not None:
            llm_model = LLMModel.model_validate(llm_db)

            llm_class, llm_default_params = tools.get_llm_class(llm_model.class_name)
            llm_params = json.loads(llm_model.options)
            if llm_default_params is not None:
                llm_params.update(llm_default_params)
            llm = llm_class(**llm_params)

            return LLM(llmName, llm_model, llm)
        else:
            return None

    def get_embedding(self, embeddingModel):
        if embeddingModel in self.embeddingCache:
            return self.embeddingCache[embeddingModel]
        else:
            if embeddingModel in EMBEDDINGS:
                embedding_class, embedding_args, _, _, _ = EMBEDDINGS[embeddingModel]
                model = LangchainEmbedding(embedding_class(**embedding_args))
                self.embeddingCache[embeddingModel] = model
                return model
            else:
                raise Exception("Invalid Embedding type.")

    def find_project(self, name: str, db: DBWrapper):
        p = db.get_project_by_name(name)
        if p is None:
            return None
        proj = ProjectModel.model_validate(p)
        if proj is not None:
            project = Project(proj)
            project.model = proj
            if project.model.type == "rag":
                try:
                    project.vector = vector_tools.findVectorDB(project)(self, project)
                except Exception as e:
                    logging.error(e)
                    traceback.print_tb(e.__traceback__)
                    project.vector = None
            return project

    @staticmethod
    def classify(classifier_model: ClassifierModel):
        classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

        sequence_to_classify = classifier_model.sequence
        candidate_labels = classifier_model.labels
        return classifier(sequence_to_classify, candidate_labels, multi_label=True)

    def get_tools(self, names=None) -> list[FunctionTool]:
        if names is None:
            names = []
        _tools = []

        if names:
            for tool in self.tools:
                if tool.metadata.name in names:
                    _tools.append(tool)
        else:
            _tools = self.tools

        return _tools
