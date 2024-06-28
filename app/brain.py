import json
import logging
import traceback

from llama_index.embeddings.langchain import LangchainEmbedding
from app.vectordb import tools as vector_tools
from app import tools
from app.llm import LLM
from app.models.models import LLMModel, ProjectModel
from app.project import Project
from modules.embeddings import EMBEDDINGS
from app.database import dbc
from sqlalchemy.orm import Session
from transformers import pipeline
from llama_index.core.tools import FunctionTool


class Brain:
    def __init__(self):
        self.llmCache = {}
        self.embeddingCache = {}
        self.defaultCensorship = "I'm sorry, I don't know the answer to that."
        self.defaultSystem = ""
        self.tools = tools.load_tools()

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
                
        if hasattr(llm.llm, 'system_prompt'):
            llm.llm.system_prompt = None
        
        return llm
    
    def loadLLM(self, llmName, db: Session):
        llm_db = dbc.get_llm_by_name(db, llmName)

        if llm_db is not None:
            llmm = LLMModel.model_validate(llm_db)

            llm = tools.getLLMClass(llmm.class_name)(**json.loads(llmm.options))

            if llmName in self.llmCache:
                del self.llmCache[llmName]
            self.llmCache[llmName] = LLM(llmName, llmm, llm)
            return self.llmCache[llmName]
        else:
            return None

    def getEmbedding(self, embeddingModel):
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
              
    def findProject(self, name, db):
        p = dbc.get_project_by_name(db, name)
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
      
    def classify(self, input):
        classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

        sequence_to_classify = input.sequence
        candidate_labels = input.labels
        return classifier(sequence_to_classify, candidate_labels, multi_label=True)
      
    def get_tools(self, names: list[str] = []) -> list[FunctionTool]:
        _tools = []
        
        if names:
          for tool in self.tools:
              if tool.metadata.name in names:
                  _tools.append(tool)
        else:
            _tools = self.tools
                    
        return _tools