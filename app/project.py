import json
import os
import shutil
import time

from app.chat import Chat
from app.models import ProjectModel

from langchain.vectorstores import Chroma

from app.tools import FindEmbeddingsPath


class Project:

    def __init__(self):
        self.chats = []
        self.db: Chroma
        self.model: ProjectModel

    def boot(self, model: ProjectModel):
        self.model = model
        self.initializePaths()

    def delete(self):
        try:
            embeddingsPath = FindEmbeddingsPath(self.model.name)
            shutil.rmtree(embeddingsPath, ignore_errors=True)
        except BaseException:
            pass

        if os.path.exists(
            os.path.join(
                os.environ["UPLOADS_PATH"],
                self.model.name)):
            shutil.rmtree(
                os.path.join(
                    os.environ["UPLOADS_PATH"],
                    self.model.name),
                ignore_errors=True)

    def initializePaths(self):
        if not os.path.exists(os.environ["EMBEDDINGS_PATH"]):
            os.makedirs(os.environ["EMBEDDINGS_PATH"])

        try:
            embeddingsPath = FindEmbeddingsPath(self.model.name)
        except BaseException:
            embeddingsPath = os.path.join(
                os.environ["EMBEDDINGS_PATH"], self.model.name + "_" + str(int(time.time())))
            os.mkdir(embeddingsPath)

        if not os.path.exists(
            os.path.join(
                os.environ["UPLOADS_PATH"],
                self.model.name)):
            os.mkdir(os.path.join(
                os.environ["UPLOADS_PATH"], self.model.name))

    def loadChat(self, chatModel):
        for chat in self.chats:
            if chat.id == chatModel.id:
                return chat

        chat = Chat(chatModel)
        self.chats.append(chat)
        return chat
