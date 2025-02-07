from datetime import datetime
from uuid import uuid4
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.storage.chat_store import BaseChatStore
from restai.models.models import ChatModel


class Chat:
    def __init__(self, model: ChatModel, chat_store: BaseChatStore):
        self.model: ChatModel = model

        if not model.id:
            self.chat_id = str(uuid4())
        else:
            self.chat_id = model.id

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
