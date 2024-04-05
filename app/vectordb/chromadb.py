import shutil
import chromadb
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext

from app.vectordb.tools import FindEmbeddingsPath
from llama_index.vector_stores.chroma import ChromaVectorStore
from app.vectordb.base import VectorBase


class ChromaDBVector(VectorBase):
    db = None
    chroma_collection = None
  
    def __init__(self, brain, project):
        path = FindEmbeddingsPath(project.model.name)
        self.db = chromadb.PersistentClient(path=path)
        self.chroma_collection = self.db.get_or_create_collection(project.model.name)
        self.project = project
        self.index = self._vector_init(brain)
    
    
    def _vector_init(self, brain):
        vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(
            vector_store, storage_context=storage_context, embed_model=brain.getEmbedding(
            self.project.model.embeddings)) 


    def save(self):
        pass
      
    def load(self, brain):
        pass

    def list(self):
        output = []
        collection = self.db.get_or_create_collection(self.project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )

        index = 0
        for metadata in docs["metadatas"]:
            if metadata["source"] not in output:
                output.append(metadata["source"])
            index = index + 1

        return {"embeddings": output}


    def list_source(self, source):
        output = []
      
        collection = self.db.get_or_create_collection(self.project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )

        index = 0
        for metadata in docs["metadatas"]:
            if metadata["source"] == source:
                output.append(metadata["source"])
            index = index + 1

        return output


    def info(self):
        collection = self.db.get_or_create_collection(self.project.model.name)

        docs = collection.get(
            include=["metadatas"]
        )
        return len(docs["ids"])

    def find_source(self, source):
        docs = []
        
        collection = self.db.get_or_create_collection(self.project.model.name)
        docs = collection.get(where={'source': source})
        
        return docs


    def find_id(self, id):
        output = {"id": id}
        
        collection = self.db.get_or_create_collection(self.project.model.name)
        docs = collection.get(ids=[id])
        output["metadata"] = {
            k: v for k, v in docs["metadatas"][0].items() if not k.startswith('_')}
        output["document"] = docs["documents"][0]

        return output


    def delete(self):
        try:
            embeddingsPath = FindEmbeddingsPath(self.project.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass
        

    def delete_source(self, source):
        ids = []
        collection = self.db.get_or_create_collection(self.project.model.name)
        ids = collection.get(where={'source': source})['ids']
        if len(ids):
            collection.delete(ids)
       
        return ids


    def delete_id(self, id):
        collection = self.db.get_or_create_collection(self.project.model.name)
        ids = collection.get(ids=[id])['ids']
        if len(ids):
            collection.delete(ids)
        return id


    def reset(self, brain):
        self.db.reset()
        self.index = self._vector_init(brain)