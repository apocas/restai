import datetime
from app.chat import Chat

class Recollection:
    def __init__(self):
        self.memories = []
    
    def loadMemory(self, project):
        for memory in self.memories:
            if memory.project == project:
                return memory
        
        memory = Memory(project)
        self.memories.append(memory)
        
        return memory

class Memory:
  
    def __init__(self, project):
        self.project = project
        self.chats = []
        
    def loadChat(self, chatModel):
        one_day_ago = datetime.datetime.now() - datetime.timedelta(days=1)

        self.chats = [chat for chat in self.chats if hasattr(
            chat, 'id') and chat.created >= one_day_ago]

        for chat in self.chats:
            if chat.id == chatModel.id:
                return chat

        chat = Chat(chatModel)
        self.chats.append(chat)

        return chat