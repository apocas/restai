import json
import os
import shutil

from langchain.vectorstores import Chroma
from app.chat import Chat
from app.models import ProjectModel

from app.tools import GetEmbedding


class Project:

    def __init__(self):
        self.chats = []

    def boot(self, model: ProjectModel):
        self.model = model
        self.loadEmbedding()

    def delete(self):
        if os.path.exists(os.path.join(os.environ["PROJECTS_PATH"], f'{self.model.name}.json')):
            os.remove(os.path.join(
                os.environ["PROJECTS_PATH"], f'{self.model.name}.json'))

        if os.path.exists(os.path.join(os.environ["EMBEDDINGS_PATH"], self.model.name)):
            self.db.delete_collection()
            shutil.rmtree(os.path.join(
                os.environ["EMBEDDINGS_PATH"], self.model.name), ignore_errors=True)

    def save(self):
        if os.path.exists(os.path.join(os.environ["PROJECTS_PATH"], f'{self.model.name}.json')):
            raise ValueError("Project already exists")

        if not os.path.exists('./projects'):
            os.makedirs('./projects')

        if not os.path.exists(os.environ["EMBEDDINGS_PATH"]):
            os.makedirs(os.environ["EMBEDDINGS_PATH"])

        if not os.path.join(os.environ["EMBEDDINGS_PATH"], self.model.name):
            os.mkdir(os.path.join(
                os.environ["EMBEDDINGS_PATH"], self.model.name))

        file_path = os.path.join(
            os.environ["PROJECTS_PATH"], f'{self.model.name}.json')
        model_json = json.dumps(self.model.dict(), indent=4)

        with open(file_path, 'w') as f:
            f.write(model_json)

    def load(self, name):
        if name is None:
            raise ValueError("Name cannot be None")

        file_path = os.path.join('projects', f'{name}.json')

        with open(file_path, 'r') as f:
            model_json = json.load(f)

        self.model = ProjectModel(**model_json)
        self.loadEmbedding()

    def loadEmbedding(self):
        self.embedding = GetEmbedding(
            self.model.embeddings, self.model.embeddings_model)  # type: ignore

        self.db = Chroma(
            persist_directory=os.path.join(os.environ["EMBEDDINGS_PATH"], self.model.name), embedding_function=self.embedding
        )

    def loadChat(self, chatModel):
        for chat in self.chats:
            if chat.id == chatModel.id:
                return chat

        chat = Chat(chatModel)
        self.chats.append(chat)
        return chat
