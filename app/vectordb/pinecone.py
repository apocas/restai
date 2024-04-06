import os

import numpy as np
from app.brain import Brain
from app.project import Project
from app.vectordb.base import VectorBase
from llama_index.core.indices import VectorStoreIndex
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.core import StorageContext
from pinecone import Pinecone, ServerlessSpec, PodSpec, Index

from modules.embeddings import EMBEDDINGS

class PineconeVector(VectorBase):
    pinecone: Pinecone = None
  
    def __init__(self, brain: Brain, project: Project):
        self.project = project
        self.index = None
        self.pinecone = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
        
        self._vector_init(brain)
        pi = self.pinecone.Index(self.project.model.name)
        
        vector_store = PineconeVectorStore(pinecone_index=pi)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self.index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context, embed_model=brain.getEmbedding(self.project.model.embeddings))


    def _vector_init(self, brain: Brain):
        if self.project.model.name not in self.pinecone.list_indexes().names():  
            _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
              
            self.pinecone.create_index(
                name=self.project.model.name,
                dimension=dimension,
                metric="cosine",
                spec=PodSpec(
                    environment="gcp-starter"
                )
            )


    def save(self):
        pass


    def load(self, brain):
        pass


    def _get_ids_from_query(self, index: Index, input_vector):
        results = index.query(
            top_k=10000,
            include_values=False,
            include_metadata=True,
            vector=input_vector,
        )
        docs = []
        for result in results['matches']:
            docs.append({"id": result.id, "metadata": result.metadata, "score": result.score})
            
        return docs

    def list(self):
        pi = self.pinecone.Index(self.project.model.name)
        _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
        
        num_vectors = pi.describe_index_stats()
        num_vectors = num_vectors.namespaces[""].vector_count
        all_docs = []
        while len(all_docs) < num_vectors:
            input_vector = np.random.rand(dimension).tolist()
            docs = self._get_ids_from_query(pi,input_vector)
            all_docs.extend(docs)
        
        output = []
        for doc in all_docs:
            if doc["metadata"]["source"] not in output:
                output.append(doc["metadata"]["source"])
        
        return output


    def list_source(self, source):
        pi = self.pinecone.Index(self.project.model.name)
        _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
        
        num_vectors = pi.describe_index_stats()
        num_vectors = num_vectors.namespaces[""].vector_count
        all_docs = []
        while len(all_docs) < num_vectors:
            input_vector = np.random.rand(dimension).tolist()
            docs = self._get_ids_from_query(pi,input_vector)
            all_docs.extend(docs)
        
        output = []
        for doc in all_docs:
            if doc["metadata"]["source"] == source:
                output.append({"source": doc["metadata"]["source"], "id": doc["id"], "score": doc["score"]})
        
        return output


    def info(self):
        pi = self.pinecone.Index(self.project.model.name)
        num_vectors = pi.describe_index_stats()
        num_vectors = num_vectors.namespaces[""].vector_count
        return num_vectors


    def find_source(self, source):
        pass


    def find_id(self, id):
        output = {"id": id}
        pi = self.pinecone.Index(self.project.model.name)

        results = pi.query(
            top_k=1,
            include_values=False,
            include_metadata=True,
            id=id,
        )

        matches = results['matches']
        if len(matches) == 0:
            return output
        
        output["metadata"] = {k: v for k, v in matches[0].metadata.items() if not k.startswith('_')}
        output["document"] = ""

        return output


    def delete(self):
        self.pinecone.delete_index(self.project.model.name)
        

    def delete_source(self, source):
        pass


    def delete_id(self, id):
        pass


    def reset(self, brain):
        pass