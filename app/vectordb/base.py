from abc import ABC, abstractmethod
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from app.brain import Brain
from app.project import Project

class VectorBase(ABC):
    index: BasePydanticVectorStore = None
    project: Project = None
    
    @abstractmethod
    def save(self):
        pass
      
    @abstractmethod
    def load(self, brain: Brain):
        pass

    @abstractmethod
    def list(self):
        pass

    @abstractmethod
    def list_source(self, source):
        pass

    @abstractmethod
    def info(self):
        pass

    @abstractmethod
    def find_source(self, source):
        pass

    @abstractmethod
    def find_id(self, id):
        pass

    @abstractmethod
    def delete(self):
        pass

    @abstractmethod
    def delete_source(self, source):
        pass

    @abstractmethod
    def delete_id(self, id):
        pass

    @abstractmethod
    def reset(self, brain):
        pass