from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Union, Iterable
import json
from datetime import datetime

from restai import config


class URLIngestModel(BaseModel):
    url: str
    splitter: str = "sentence"
    chunks: int = 512


class TextIngestModel(BaseModel):
    text: str
    source: str
    splitter: str = "sentence"
    chunks: int = 512
    keywords: Union[list[str], None] = None


class FindModel(BaseModel):
    source: Union[str, None] = None
    text: Union[str, None] = None
    score: Union[float, None] = 0.0
    k: Union[int, None] = None


class InteractionModel(BaseModel):
    question: str
    stream: Union[bool, None] = None
    
class ImageModel(BaseModel):
    prompt: str
    image: Union[str, None] = None

class QuestionModel(InteractionModel):
    system: Union[str, None] = None
    colbert_rerank: Union[bool, None] = None
    llm_rerank: Union[bool, None] = None
    tables: Union[list[str], None] = None
    negative: Union[str, None] = None
    image: Union[str, None] = None
    lite: bool = False
    eval: bool = False
    k: Optional[int] = Field(None, ge=1, le=25)
    score: Union[float, None] = None

class ChatModel(InteractionModel):
    id: Union[str, None] = None

class EntranceModel(BaseModel):
    destination: str
    name: str
    description: str
    model_config = ConfigDict(from_attributes=True)
    
class RouterModel(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)

class LLMModel(BaseModel):
    name: str
    class_name: str
    options: str
    privacy: str
    description: Union[str, None] = None
    type: str
    input_cost: float = 0.0
    output_cost: float = 0.0
    teams: list["TeamModel"] = []
    model_config = ConfigDict(from_attributes=True)

class EmbeddingModel(BaseModel):
    name: str
    class_name: str
    options: str
    privacy: str
    description: Union[str, None] = None
    dimension: int = 1536
    teams: list["TeamModel"] = []
    model_config = ConfigDict(from_attributes=True)
    
class Tool(BaseModel):
    name: str
    description: str
class LLMUpdate(BaseModel):
    class_name: str = None
    options: str = None
    privacy: str = None
    description: str = None
    type: str = None
    input_cost: float = None
    output_cost: float = None
    
class EmbeddingUpdate(BaseModel):
    class_name: str = None
    options: str = None
    privacy: str = None
    description: str = None
    dimension: int = None

class UserProject(BaseModel):
    id: int
    model_config = ConfigDict(from_attributes=True)
    
class ProjectUser(BaseModel):
    username: str
    model_config = ConfigDict(from_attributes=True)
    
class MCPServer(BaseModel):
    host: str
    tools: Union[str, None] = None
class ProjectOptions(BaseModel):
    logging: bool = True
    colbert_rerank: Union[bool, None] = None
    llm_rerank: Union[bool, None] = None
    cache: Union[bool, None] = None
    cache_threshold: Union[float, None] = None
    tables: Union[str, None] = None
    tools: Union[str, None] = None
    score: float = 0.0
    k: int = 4
    max_iterations: int = config.AGENT_MAX_ITERATIONS
    connection: Union[str, None] = None
    mcp_servers: Union[list[MCPServer], None] = None
    model_config = ConfigDict(from_attributes=True)

class ProjectBaseModel(BaseModel):
    id: int
    name: str
    embeddings: Union[str, None] = None
    llm: str
    type: str
    system: Union[str, None] = None
    censorship: Union[str, None] = None
    vectorstore: Union[str, None] = None
    guard: Union[str, None] = None
    human_name: Union[str, None] = None
    human_description: Union[str, None] = None
    entrances: Union[list[EntranceModel], None] = None
    public: bool = False
    creator: Union[int, None] = None
    default_prompt: Union[str, None] = None
    options: Union[str, ProjectOptions] = ProjectOptions()
    users: list[ProjectUser] = []
    model_config = ConfigDict(from_attributes=True)

    @field_validator('options', mode='before')
    @classmethod
    def parse_options(cls, v):
        if isinstance(v, str):
            try:
                return ProjectOptions(**json.loads(v))
            except json.JSONDecodeError:
                return ProjectOptions()
        elif isinstance(v, dict):
            return ProjectOptions(**v)
        return v

class ProjectModel(ProjectBaseModel):
    team: Union["TeamModel", None] = None
    model_config = ConfigDict(from_attributes=True)

class ProjectModelCreate(BaseModel):
    name: str
    embeddings: Union[str, None] = None
    llm: str
    type: str
    human_name: Union[str, None] = None
    human_description: Union[str, None] = None
    vectorstore: Union[str, None] = None
    team_id: int
    
class ProjectResponse(ProjectBaseModel):
    team: Union["TeamResponse", None] = None
class ProjectsResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
    start: int
    end: int

class ProjectInfo(ProjectModel):
    chunks: int = 0
    llm_type: Union[str, None] = None
    llm_privacy: Union[str, None] = None

class UserOptions(BaseModel):
    credit: float = -1.0
    model_config = ConfigDict(from_attributes=True)

class User(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    is_private: bool = False
    projects: list[UserProject] = []
    api_key: Union[str, None] = None
    level: Union[str, None] = None
    options: Union[str, UserOptions] = UserOptions()
    teams: list["TeamModel"] = []
    admin_teams: list["TeamModel"] = []
    model_config = ConfigDict(from_attributes=True)
    
    @field_validator('options', mode='before')
    @classmethod
    def parse_options(cls, v):
        if isinstance(v, str):
            try:
                return UserOptions(**json.loads(v))
            except json.JSONDecodeError:
                return UserOptions()
        elif isinstance(v, dict):
            return UserOptions(**v)
        return v

class UsersResponse(BaseModel):
    users: list[User]
    
class UserBase(BaseModel):
    username: str


class UserLogin(BaseModel):
    user: str
    password: str

class UserCreate(UserBase):
    password: str
    is_admin: bool = False
    is_private: bool = False


class UserUpdate(BaseModel):
    password: str = None
    is_admin: bool = None
    is_private: bool = None
    projects: list[str] = None
    api_key: str = None
    options: Union[UserOptions, None] = None


class ProjectModelUpdate(BaseModel):
    name: Union[str, None] = None
    embeddings: Union[str, None] = None
    llm: Union[str, None] = None
    system: Union[str, None] = None
    censorship: Union[str, None] = None
    score: Union[float, None] = None
    k: Union[int, None] = None
    connection: Union[str, None] = None
    tables: Union[str, None] = None
    llm_rerank: Union[bool, None] = None
    entrances: Union[list[EntranceModel], None] = None
    colbert_rerank: Union[bool, None] = None
    cache: Union[bool, None] = None
    cache_threshold: Union[float, None] = None
    guard: Union[str, None] = None
    human_name: Union[str, None] = None
    human_description: Union[str, None] = None
    tools: Union[str, None] = None
    users: list[str] = None
    public: Union[bool, None] = None
    default_prompt: Union[str, None] = None
    options: Union[ProjectOptions, None] = None
    team_id: Union[int, None] = None

class SourceModel(BaseModel):
    source: str
    keywords: str
    text: str
    score: float
    id: str


class InferenceResponse(BaseModel):
    question: str
    answer: str
    type: str


class QuestionResponse(InferenceResponse):
    sources: Union[list[SourceModel], Union[list[str], None]] = None
    image: Union[str, None] = None

class RagSqlResponse(InferenceResponse):
    sources: list[str]

class VisionResponse(QuestionResponse):
    image: Union[str, None] = None

class ChatResponse(QuestionResponse):
    id: str

class IngestResponse(BaseModel):
    source: str
    documents: int
    chunks: int

class ClassifierModel(BaseModel):
    sequence: str
    labels: list[str]
    
class ClassifierResponse(BaseModel):
    sequence: str
    labels: list[str]
    scores: list[float]
    
class KeyCreate(BaseModel):
    models: list[str]
    name: str
    rpm: Union[int, None] = None
    tpm: Union[int, None] = None
    max_budget: Union[int, None] = None
    duration_budget: Union[str, None] = None

class TeamUser(BaseModel):
    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)
    
class TeamLLM(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)
    
class TeamEmbedding(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)
    
class TeamProject(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)

class TeamModel(BaseModel):
    id: int
    name: str
    description: Union[str, None] = None
    created_at: datetime = None
    users: list[TeamUser] = []
    admins: list[TeamUser] = []
    projects: list[TeamProject] = []
    llms: list[TeamLLM] = []
    embeddings: list[TeamEmbedding] = []
    model_config = ConfigDict(from_attributes=True)
    
class TeamResponse(BaseModel):
    id: int
    name: str

class TeamModelCreate(BaseModel):
    name: str
    description: Union[str, None] = None
    users: list[str] = []
    admins: list[str] = []
    projects: list[str] = []
    llms: list[str] = []
    embeddings: list[str] = []
    creator_id: Union[int, None] = None
    
class TeamModelUpdate(BaseModel):
    name: Union[str, None] = None
    description: Union[str, None] = None
    users: list[str] = None
    admins: list[str] = None
    projects: list[str] = None
    llms: list[str] = None
    embeddings: list[str] = None
    
class TeamsResponse(BaseModel):
    teams: list[TeamModel]