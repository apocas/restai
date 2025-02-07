import numpy as np
from llama_index.core import StorageContext
from llama_index.core.indices import VectorStoreIndex
from llama_index.vector_stores.pinecone import PineconeVectorStore

from restai.brain import Brain
from restai.config import PINECONE_API_KEY
from restai.embedding import Embedding
from restai.project import Project
from restai.vectordb.base import VectorBase
from modules.embeddings import EMBEDDINGS
from pinecone import Pinecone, PodSpec, Index


#Pinecone is not ideal for this application. It's ok'ish for direct rag usage, bad for fine index management.
#Doesn't have proper querying mechanism, only subquerying.
#Responses are given before execution of operation...
#This implementation works but wont scale for large datasets.
#https://community.pinecone.io/t/how-to-retrieve-list-of-ids-in-an-index/380/20

class PineconeVector(VectorBase):
    pinecone: Pinecone = None
  
    def __init__(self, brain: Brain, project: Project, embedding: Embedding):
        self.project = project
        self.index = None
        self.pinecone = Pinecone(api_key=PINECONE_API_KEY)
        self.embedding = embedding
        
        self._vector_init()
        pi = self.pinecone.Index(self.project.model.name)
        
        vector_store = PineconeVectorStore(pinecone_index=pi)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self.index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context, embed_model=embedding.embedding)


    def _vector_init(self):
        if self.project.model.name not in self.pinecone.list_indexes().names():
            self.pinecone.create_index(
                name=self.project.model.name,
                dimension=self.embedding.props.dimension,
                metric="cosine",
                spec=PodSpec(
                    environment="gcp-starter"
                )
            )


    def save(self):
        pass


    def load(self, brain):
        pass


    @staticmethod
    def _get_ids_from_query(index: Index, input_vector):
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
        output = []
        pi = self.pinecone.Index(self.project.model.name)
        _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
        
        stats = pi.describe_index_stats()
        if len(stats.namespaces) > 0 and hasattr(stats.namespaces[""], "vector_count"):
            num_vectors = stats.namespaces[""].vector_count
            all_docs = []
            while len(all_docs) < num_vectors:
                input_vector = np.random.rand(dimension).tolist()
                docs = self._get_ids_from_query(pi,input_vector)
                all_docs.extend(docs)
            
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
                output.append({"source": doc["metadata"]["source"], "id": doc["id"]})
        
        return output


    def info(self):
        num_vectors = 0
        pi = self.pinecone.Index(self.project.model.name)
        stats = pi.describe_index_stats()
        if len(stats.namespaces) > 0 and hasattr(stats.namespaces[""], "vector_count"):
            num_vectors = stats.namespaces[""].vector_count
        return num_vectors


    def find_source(self, source):
        ids = []
        metadatas = []
      
        pi = self.pinecone.Index(self.project.model.name)
        _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
        
        num_vectors = pi.describe_index_stats()
        num_vectors = num_vectors.namespaces[""].vector_count
        all_docs = []
        while len(all_docs) < num_vectors:
            input_vector = np.random.rand(dimension).tolist()
            docs = self._get_ids_from_query(pi,input_vector)
            all_docs.extend(docs)
        
        for doc in all_docs:
            if doc["metadata"]["source"] == source:
                ids.append(doc["id"])
                metadatas.append({"source": doc["metadata"]["source"], "keywords": doc["metadata"]["keywords"]})
        
        return {"ids": ids, "metadatas": metadatas, "documents": []}


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
        ids = []
      
        pi = self.pinecone.Index(self.project.model.name)
        _, _, _, _, dimension = EMBEDDINGS[self.project.model.embeddings]
        
        num_vectors = pi.describe_index_stats()
        num_vectors = num_vectors.namespaces[""].vector_count
        all_docs = []
        while len(all_docs) < num_vectors:
            input_vector = np.random.rand(dimension).tolist()
            docs = self._get_ids_from_query(pi,input_vector)
            all_docs.extend(docs)
        
        for doc in all_docs:
            if doc["metadata"]["source"] == source:
                ids.append(doc["id"])
        
        pi.delete(ids=ids, namespace="")
        return ids


    def delete_id(self, id):
        pi = self.pinecone.Index(self.project.model.name)
        pi.delete(ids=[id], namespace="")
        return id


    def reset(self, _):
        self.delete()
        self.index = self._vector_init()