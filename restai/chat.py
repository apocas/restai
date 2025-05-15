from datetime import datetime
from uuid import uuid4
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.storage.chat_store import BaseChatStore
from restai import config
from restai.models.models import ChatModel

from llama_index.core.memory import (
    StaticMemoryBlock,
    FactExtractionMemoryBlock,
    VectorMemoryBlock,
)
from llama_index.core.memory import Memory


class Chat:
    def __init__(self, model: ChatModel, chat_store: BaseChatStore):
        self.model: ChatModel = model

        if not model.id:
            self.chat_id = str(uuid4())
        else:
            self.chat_id = model.id

        """
        blocks = [
            StaticMemoryBlock(
                name="core_info",
                static_content="My name is Logan, and I live in Saskatoon. I work at LlamaIndex.",
                priority=0,
            ),
            FactExtractionMemoryBlock(
                name="extracted_info",
                llm=llm,
                max_facts=50,
                priority=1,
            ),
            VectorMemoryBlock(
                name="vector_memory",
                # required: pass in a vector store like qdrant, chroma, weaviate, milvus, etc.
                vector_store=vector_store,
                priority=2,
                embed_model=embed_model,
                # The top-k message batches to retrieve
                # similarity_top_k=2,
                # optional: How many previous messages to include in the retrieval query
                # retrieval_context_window=5
                # optional: pass optional node-postprocessors for things like similarity threshold, etc.
                # node_postprocessors=[...],
            ),
        ]

        self.memory2 = Memory.from_defaults(
            session_id=self.chat_id,
            token_limit=40000,
            memory_blocks=blocks,
            async_database_uri=config.SQL_URL,
            insert_method="system",
        )
        """
        self.memory: ChatMemoryBuffer = ChatMemoryBuffer.from_defaults(
            token_limit=3900,
            chat_store=chat_store,
            chat_store_key=f"memory_{self.chat_id}",
        )

        self.created: datetime = datetime.now()

    def clear_history(self):
        self.memory.reset()

    def __eq__(self, other: "Chat"):
        return self.chat_id == other.chat_id
