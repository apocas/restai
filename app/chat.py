import datetime
import uuid

from llama_index.core.memory import ChatMemoryBuffer
from llama_index.storage.chat_store.redis import RedisChatStore

from app.config import REDIS_HOST, REDIS_PORT

class Chat:
    def __init__(self, model):
        self.model = model

        if model.id is None:
            self.id = str(uuid.uuid4())
        else:
            self.id = model.id

        if REDIS_HOST is not None:
            self.memory = ChatMemoryBuffer.from_defaults(token_limit=3900, chat_store=RedisChatStore(redis_url=f"redis://{REDIS_HOST}:{REDIS_PORT}"), chat_store_key=self.id)
        else:
            self.memory = ChatMemoryBuffer.from_defaults(token_limit=3900)

        self.created = datetime.datetime.now()

    def clearHistory(self):
        self.memory.reset()

    def __eq__(self, other):
        return self.id == other.id
