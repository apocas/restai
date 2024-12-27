import json
import logging
import traceback
from typing import Optional, Iterable
from llama_index.embeddings.langchain import LangchainEmbedding
from app.database import DBWrapper
from app.models.databasemodels import ProjectDatabase
from app.vectordb import tools as vector_tools
from app import tools
from app.llm import LLM
from app.embedding import Embedding
from app.models.models import LLMModel, ProjectModel, ClassifierModel, EmbeddingModel
from app.project import Project
from modules.embeddings import EMBEDDINGS
from transformers import pipeline
from llama_index.core.tools import FunctionTool
from app import config
from app.config import REDIS_HOST, REDIS_PORT
from llama_index.storage.chat_store.redis import RedisChatStore
from llama_index.core.storage.chat_store import SimpleChatStore
from llama_index.core.storage.chat_store.base import BaseChatStore
import tiktoken
from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler

class Brain:
    def __init__(self):
        self.defaultCensorship: str = "I'm sorry, I don't know the answer to that."
        self.defaultSystem: str = ""
        self.tools: list[FunctionTool] = tools.load_tools()

        self.tokenizer = tiktoken.get_encoding("cl100k_base").encode
        self.token_counter = TokenCountingHandler(
            tokenizer=self.tokenizer
        )
        Settings.callback_manager = CallbackManager([self.token_counter])
        
        if config.RESTAI_GPU:
            self.generators: list[FunctionTool] = tools.load_generators()
            self.audio_generators: list[FunctionTool] = tools.load_audio_generators()

        self.chat_store: BaseChatStore
        if REDIS_HOST is not None:
            self.chat_store = RedisChatStore(redis_url=f"redis://{REDIS_HOST}:{REDIS_PORT}")
        else:
            self.chat_store = SimpleChatStore()

    def get_llm(self, llmName: str, db: DBWrapper) -> Optional[LLM]:
        llm: Optional[LLM] = self.load_llm(llmName, db)

        if llm is None:
            return None

        if hasattr(llm.llm, 'system_prompt'):
            llm.llm.system_prompt = None
        return llm

    @staticmethod
    def load_llm(llmName: str, db: DBWrapper) -> Optional[LLM]:
        llm_db = db.get_llm_by_name(llmName)

        if llm_db is not None:
            llm_model = LLMModel.model_validate(llm_db)

            llm_class, llm_default_params = tools.get_llm_class(
                llm_model.class_name)
            llm_params = json.loads(llm_model.options)
            if llm_default_params is not None:
                llm_params.update(llm_default_params)
            llm = llm_class(**llm_params)

            return LLM(llmName, llm_model, llm)
        else:
            return None
    
    @staticmethod
    def get_embedding(embeddingName: str, db: DBWrapper) -> Optional[LLM]:
        embedding_db = db.get_embedding_by_name(embeddingName)

        if embedding_db is not None:
            embedding_model = EmbeddingModel.model_validate(embedding_db)

            embedding_class, embedding_default_params = tools.get_embedding_class(
                embedding_model.class_name)
            llm_params = json.loads(embedding_model.options)
            if embedding_default_params is not None:
                llm_params.update(embedding_default_params)
            embedding = embedding_class(**llm_params)

            return Embedding(embeddingName, embedding_model, embedding)
        else:
            if embeddingName in EMBEDDINGS:
                embedding_class, embedding_args, privacy, description, dimension = EMBEDDINGS[embeddingName]
                model = LangchainEmbedding(embedding_class(**embedding_args))
                return Embedding(embeddingName, EmbeddingModel(name=embeddingName, class_name="LangChain", options="{}", privacy=privacy, description=description, dimension=dimension), model)
            else:
                return None

    def find_project(self, name: str, db: DBWrapper) -> Optional[Project]:
        p: Optional[ProjectDatabase] = db.get_project_by_name(name)
        if p is None:
            return None
          
        proj: ProjectModel = ProjectModel.model_validate(p)
        if proj is None:
            return None
          
        project: Project = Project(proj)
        project.model = proj
        if project.model.type == "rag":
            try:
                project.vector = vector_tools.find_vector_db(project)(self, project, self.get_embedding(project.model.embeddings, db))
            except Exception as e:
                logging.error(e)
                traceback.print_tb(e.__traceback__)
                project.vector = None
        return project

    @staticmethod
    def classify(classifier_model: ClassifierModel):
        classifier = pipeline("zero-shot-classification",
                              model="facebook/bart-large-mnli")

        sequence_to_classify = classifier_model.sequence
        candidate_labels = classifier_model.labels
        return classifier(sequence_to_classify, candidate_labels, multi_label=True)

    def get_tools(self, names: Optional[Iterable[str]] = None) -> list[FunctionTool]:
        if names is None:
            names = []
        _tools = []

        if len(names) > 0:
            for tool in self.tools:
                if tool.metadata.name in names:
                    _tools.append(tool)
        else:
            _tools = self.tools

        return _tools

    def get_generators(self, names: Optional[Iterable[str]] = None) -> list[FunctionTool]:
        if names is None:
            names = []
        _generators = []

        if names:
            for generator in self.generators:
                if generator.__module__.split(".")[-1] in names:
                    _generators.append(generator)
        else:
            _generators = self.generators

        return _generators

    def get_audio_generators(self, names: Optional[Iterable[str]] = None) -> list[FunctionTool]:
        if names is None:
            names = []
        _generators = []

        if names:
            for generator in self.audio_generators:
                if generator.__module__.split(".")[-1] in names:
                    _generators.append(generator)
        else:
            _generators = self.audio_generators

        return _generators
