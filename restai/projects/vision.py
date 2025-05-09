from fastapi import HTTPException
from llama_index.core.schema import ImageDocument
from restai import tools
from restai.database import DBWrapper
from restai.guard import Guard
from restai.models.models import ChatModel, QuestionModel, User
from restai.project import Project
from restai.projects.base import ProjectBase


class Vision(ProjectBase):

    async def chat(self, project: Project, chatModel: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")

    async def question(self, project: Project, questionModel: QuestionModel, user: User, db: DBWrapper):
        output = {
            "question": questionModel.question,
            "type": "vision",
            "sources": [],
            "guard": False,
            "tokens": {
                "input": 0,
                "output": 0
            },
            "project": project.props.name
        }

        if project.props.guard:
            guard = Guard(project.props.guard, self.brain, db)
            if guard.verify(questionModel.question):
                output["answer"] = project.props.censorship or self.brain.defaultCensorship
                output["guard"] = True
                output["tokens"] = {
                    "input": tools.tokens_from_string(output["question"]),
                    "output": tools.tokens_from_string(output["answer"])
                }
                return output

        model = self.brain.get_llm(project.props.llm, db)

        try:
            response = model.llm.complete(prompt=questionModel.question,
                                          image_documents=[ImageDocument(image=questionModel.image)])
        except Exception as e:
            raise e

        output["answer"] = response.text
        
        self.brain.post_processing_counting(output)

        return output
