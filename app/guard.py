from llama_index.core.base.llms.types import ChatMessage

from app.brain import Brain
from app.database import DBWrapper


class Guard:
    def __init__(self, projectName: str, brain: Brain, db: DBWrapper):
        self.brain = brain
        self.project = brain.find_project(projectName, db)
        self.db = db

    def verify(self, prompt):        
        model = self.brain.get_llm(self.project.model.llm, self.db)

        sysTemplate = self.project.model.system
        model.llm.system_prompt = sysTemplate

        messages = [
            ChatMessage(
                role="system", content=sysTemplate
            ),
            ChatMessage(role="user", content="Analyze the following text:\n\"" + prompt + "\""),
        ]
        
        resp = model.llm.chat(messages)
        answer = resp.message.content.strip()
        
        try:
            if answer == "BAD":
                return True
            elif answer == "GOOD":
                return False
            else:
                return True
        except Exception as e:
            raise e
