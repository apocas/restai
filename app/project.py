import datetime

from app.cache import Cache
from app.chat import Chat
from app.models import ProjectModel

from app.vectordb.tools import FindEmbeddingsPath


class Project:

    def __init__(self, model: ProjectModel):
        self.chats = []
        self.vector = None
        self.model = model
        
        if self.model.cache:
            self.cache = Cache(self)
        else:
            self.cache = None
            
        if self.model.type == "rag":
            FindEmbeddingsPath(self.model.name)
            

    def delete(self):
        if self.vector:
            self.vector.delete()
        if self.cache:
            self.cache.delete()
        

    def loadChat(self, chatModel):
        current_time = datetime.datetime.now()
        one_day_ago = current_time - datetime.timedelta(days=1)

        self.chats = [chat for chat in self.chats if hasattr(
            chat, 'id') and chat.created >= one_day_ago]

        for chat in self.chats:
            if chat.id == chatModel.id:
                return chat

        chat = Chat(chatModel)
        self.chats.append(chat)

        return chat
