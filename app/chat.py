import datetime
import uuid

from llama_index.core.memory import ChatMemoryBuffer


class Chat:
    def __init__(self, model):
        self.model = model

        if model.id is None:
            self.id = str(uuid.uuid4())
        else:
            self.id = model.id

        self.memory = ChatMemoryBuffer.from_defaults(token_limit=3900)

        self.created = datetime.datetime.now()

    def clearHistory(self):
        self.memory.reset()
        self.history = []

    def __eq__(self, other):
        return self.id == other.id
