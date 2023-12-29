import datetime
import json
import os
import shutil
import time

from app.chat import Chat
from app.models import ProjectModel

from langchain.vectorstores import Chroma

from app.tools import FindEmbeddingsPath
from app.vectordb import vector_delete


class Project:

    def __init__(self):
        self.chats = []
        self.db: None
        self.model: ProjectModel

    def boot(self, model: ProjectModel):
        self.model = model
        self.initializePaths()

    def delete(self):
        vector_delete(self)

    def initializePaths(self):
        if not os.path.exists(os.environ["EMBEDDINGS_PATH"]):
            os.makedirs(os.environ["EMBEDDINGS_PATH"])

        embeddingsPath = FindEmbeddingsPath(self.model.name)

        if embeddingsPath is None:
            embeddingsPath = os.path.join(
                os.environ["EMBEDDINGS_PATH"], self.model.name + "_" + str(int(time.time())))
            os.mkdir(embeddingsPath)


    def loadChat(self, chatModel):
        current_time = datetime.datetime.now()
        one_day_ago = current_time - datetime.timedelta(days=1)

        self.chats = [chat for chat in self.chats if hasattr(chat, 'id') and chat.created >= one_day_ago]

        for chat in self.chats:
            if chat.id == chatModel.id:
                return chat

        chat = Chat(chatModel)
        self.chats.append(chat)
        return chat
