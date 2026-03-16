from datetime import datetime
from uuid import uuid4
from llama_index.core.memory import ChatSummaryMemoryBuffer
from llama_index.core.storage.chat_store import BaseChatStore
from restai.models.models import ChatModel

CONTEXT_WINDOW_RATIO = 0.75  # Reserve 25% of context window for response


class Chat:
    def __init__(self, model: ChatModel, chat_store: BaseChatStore, token_limit: int = 3900, llm=None):
        self.model: ChatModel = model

        if not model.id:
            self.chat_id = str(uuid4())
        else:
            self.chat_id = model.id

        self.memory = ChatSummaryMemoryBuffer.from_defaults(
            token_limit=token_limit,
            llm=llm,
            chat_store=chat_store,
            chat_store_key=f"memory_{self.chat_id}",
        )

        self.created: datetime = datetime.now()

    def clear_history(self):
        self.memory.reset()

    def __eq__(self, other: "Chat"):
        return self.chat_id == other.chat_id
