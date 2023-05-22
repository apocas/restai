import uuid


class Chat:
    def __init__(self, model):
        self.model = model

        if model.id is None:
            self.id = uuid.uuid4()

        self.history = []

    def clearHistory(self):
        self.history = []