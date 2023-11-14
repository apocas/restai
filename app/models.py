from pydantic import BaseModel, ConfigDict
from typing import Union


class IngestModel(BaseModel):
    url: str
    recursive: bool = False
    depth: int = 2


class EmbeddingModel(BaseModel):
    source: Union[str, None] = None


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
    llm: Union[str, None] = None
    system: Union[str, None] = None


class UserProject(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


class User(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    projects: list[UserProject] = []
    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    password: str = None
    is_admin: bool = None
    projects: list[str] = None
