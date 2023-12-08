import uuid


class Chat:
    def __init__(self, model):
        self.model = model

        if model.id is None:
            self.id = str(uuid.uuid4())

        self.history = []

    def clearHistory(self):
        self.history = []

    def __eq__(self, other):
        return self.id == other.id
