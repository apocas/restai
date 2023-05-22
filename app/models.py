from pydantic import BaseModel
from typing import Union


class IngestModel(BaseModel):
    url: str


class QuestionModel(BaseModel):
    question: str
    llm: Union[str, None] = None
    system: Union[str, None] = None


class ChatModel(BaseModel):
    message: str
    id: Union[str, None] = None


class ProjectModel(BaseModel):
    name: str
    embeddings: Union[str, None] = None
    embeddings_model: Union[str, None] = None
    llm: Union[str, None] = None
