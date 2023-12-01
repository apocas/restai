from pydantic import BaseModel, ConfigDict
from typing import Union


class URLIngestModel(BaseModel):
    url: str


class EmbeddingModel(BaseModel):
    source: Union[str, None] = None


class InteractionModel(BaseModel):
    score: Union[float, None] = None
    k: Union[int, None] = None


class QuestionModel(InteractionModel):
    question: str
    system: Union[str, None] = None


class ChatModel(InteractionModel):
    question: str
    id: Union[str, None] = None


class ProjectModel(BaseModel):
    name: str
    embeddings: str
    llm: str
    system: Union[str, None] = None
    sandboxed: Union[bool, None] = None
    censorship: Union[str, None] = None
    score: float = 0.2
    k: int = 2
    sandbox_project: Union[str, None] = None
    model_config = ConfigDict(from_attributes=True)


class ProjectInfo(ProjectModel):
    documents: int = 0
    metadatas: int = 0


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


class ProjectModelUpdate(BaseModel):
    embeddings: Union[str, None] = None
    llm: Union[str, None] = None
    system: Union[str, None] = None
    sandboxed: Union[bool, None] = None
    censorship: Union[str, None] = None
    score: Union[float, None] = None
    k: Union[int, None] = None
    sandbox_project: Union[str, None] = None


class HardwareInfo(BaseModel):
    cpu_load: float
    ram_usage: float
    gpu_load: Union[int, None] = None
    gpu_temp: Union[int, None] = None
    gpu_ram_usage: Union[int, None] = None


class SourceModel(BaseModel):
    source: str
    content: str
    keywords: str


class QuestionResponse(BaseModel):
    question: str
    answer: str
    type: str
    sources: list[SourceModel]


class ChatResponse(QuestionResponse):
    id: str
