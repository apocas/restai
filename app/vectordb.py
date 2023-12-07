import os
from langchain.vectorstores import Chroma, FAISS

from app.tools import FindEmbeddingsPath

class VectorDB:
    def __init__(self, project):
      self.project = project
      
      path = FindEmbeddingsPath(project.model.name)
      
      if project.model.vectorstore == "chroma":
        self.db = Chroma(
              persist_directory=path, embedding_function=self.getEmbedding(
                  project.model.embeddings))
      elif project.model.vectorstore == "faiss":
        if path is None or len(os.listdir(path) == 0):
            self.db = FAISS(embedding_function=self.getEmbedding(project.model.embeddings))
        else:  
            self.load()
      
    def save(self):
        if self.project.model.vectorstore == "faiss":
            self.db.save_local(FindEmbeddingsPath(
                self.project.model.name))
        elif self.project.model.vectorstore == "chroma":
            self.db.persist()
        
    def load(self):
        if self.project.model.vectorstore == "faiss":
            self.db = FAISS.load_local(FindEmbeddingsPath(
                self.project.model.name), self.getEmbedding(
                self.project.model.embeddings))