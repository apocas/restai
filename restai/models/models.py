from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, Dict, List, Optional, Union, Iterable
import json
from datetime import datetime

from restai import config


class URLIngestModel(BaseModel):
    """Ingest a web page into a RAG project's knowledge base."""
    url: str = Field(description="URL of the web page to ingest")
    splitter: str = Field(default="sentence", description="Text splitting strategy (e.g. 'sentence', 'token')")
    chunks: int = Field(default=512, description="Maximum chunk size in characters or tokens")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "url": "https://example.com/docs/getting-started",
            "splitter": "sentence",
            "chunks": 512
        }
    })


class TextIngestModel(BaseModel):
    """Ingest raw text into a RAG project's knowledge base."""
    text: str = Field(description="Raw text content to ingest")
    source: str = Field(description="Source identifier for the ingested text")
    splitter: str = Field(default="sentence", description="Text splitting strategy (e.g. 'sentence', 'token')")
    chunks: int = Field(default=512, description="Maximum chunk size in characters or tokens")
    keywords: Union[list[str], None] = Field(default=None, description="Optional keywords to associate with the ingested text")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "text": "RestAI is an AIaaS platform that allows you to create AI projects.",
            "source": "internal-docs",
            "splitter": "sentence",
            "chunks": 512,
            "keywords": ["restai", "platform", "ai"]
        }
    })


class FindModel(BaseModel):
    """Search for embeddings by source or text similarity."""
    source: Union[str, None] = Field(default=None, description="Filter results by source identifier")
    text: Union[str, None] = Field(default=None, description="Text query for similarity search")
    score: Union[float, None] = Field(default=0.0, description="Minimum similarity score threshold (0.0 to 1.0)")
    k: Union[int, None] = Field(default=None, description="Maximum number of results to return")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "text": "How do I configure embeddings?",
            "score": 0.3,
            "k": 5
        }
    })


class InteractionModel(BaseModel):
    """Base model for chat and question interactions."""
    question: str = Field(description="The user's question or prompt")
    stream: Union[bool, None] = Field(default=None, description="Enable streaming response (server-sent events)")


class ImageModel(BaseModel):
    """Image generation request."""
    prompt: str = Field(description="Text prompt describing the image to generate")
    image: Union[str, None] = Field(default=None, description="Base64-encoded input image for image-to-image generation")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "prompt": "A serene mountain landscape at sunset with a lake reflection"
        }
    })


class QuestionModel(InteractionModel):
    """Send a one-shot question to a project."""
    system: Union[str, None] = Field(default=None, description="System prompt override for this question")
    colbert_rerank: Union[bool, None] = Field(default=None, description="Enable ColBERT reranking of retrieved documents")
    llm_rerank: Union[bool, None] = Field(default=None, description="Enable LLM-based reranking of retrieved documents")
    tables: Union[list[str], None] = Field(default=None, description="Restrict RAG-SQL to specific database tables")
    negative: Union[str, None] = Field(default=None, description="Negative prompt to steer the response away from certain content")
    image: Union[str, None] = Field(default=None, description="Base64-encoded image for vision models")
    lite: bool = Field(default=False, description="Return a lightweight response without full source details")
    eval: bool = Field(default=False, description="Enable response evaluation and scoring")
    k: Optional[int] = Field(None, ge=1, le=25, description="Number of documents to retrieve from the knowledge base")
    score: Union[float, None] = Field(default=None, description="Minimum similarity score threshold for retrieved documents")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "question": "What are the main features of RestAI?",
            "stream": False,
            "k": 4,
            "score": 0.3,
            "lite": False,
            "eval": False
        }
    })


class ChatModel(InteractionModel):
    """Send a chat message to a project. Maintains conversation state via the id field."""
    id: Union[str, None] = Field(default=None, description="Conversation ID for maintaining chat state. Omit to start a new conversation.")
    image: Union[str, None] = Field(default=None, description="Base64-encoded image for vision models")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "question": "Tell me about the RAG project type.",
            "stream": False,
            "id": "conv_abc123"
        }
    })


class EntranceModel(BaseModel):
    """Router project entrance configuration."""
    destination: str = Field(description="Target project name to route to")
    name: str = Field(description="Display name for this entrance")
    description: str = Field(description="Description used by the router to decide when to select this entrance")
    model_config = ConfigDict(from_attributes=True)


class RouterModel(BaseModel):
    """Router project reference."""
    name: str = Field(description="Name of the router project")
    model_config = ConfigDict(from_attributes=True)


class LLMModel(BaseModel):
    """LLM provider configuration."""
    name: str = Field(description="Unique name identifier for the LLM")
    class_name: str = Field(description="LLM implementation class (e.g. 'ollama', 'openai', 'anthropic', 'litellm')")
    options: Dict[str, Any] = Field(description="Provider-specific configuration options (model name, API keys, etc.)")
    privacy: str = Field(description="Privacy level: 'public' (cloud-hosted) or 'private' (self-hosted)")
    description: Union[str, None] = Field(default=None, description="Human-readable description of the LLM")
    type: str = Field(description="LLM type: 'chat', 'completion', 'vision', or 'qa'")
    input_cost: float = Field(default=0.0, description="Cost per 1K input tokens in configured currency")
    output_cost: float = Field(default=0.0, description="Cost per 1K output tokens in configured currency")
    context_window: Union[int, None] = Field(default=4096, description="Maximum context window size in tokens")
    teams: list["TeamModel"] = Field(default=[], description="Teams that have access to this LLM")
    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "name": "gpt-4o",
            "class_name": "litellm",
            "options": {"model": "openai/gpt-4o"},
            "privacy": "public",
            "description": "OpenAI GPT-4o model",
            "type": "chat",
            "input_cost": 0.005,
            "output_cost": 0.015,
            "context_window": 128000
        }
    })

    @field_validator('options', mode='before')
    @classmethod
    def parse_options(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


class EmbeddingModel(BaseModel):
    """Embedding model provider configuration."""
    name: str = Field(description="Unique name identifier for the embedding model")
    class_name: str = Field(description="Embedding implementation class (e.g. 'ollama', 'openai')")
    options: str = Field(description="JSON string of provider-specific configuration options")
    privacy: str = Field(description="Privacy level: 'public' (cloud-hosted) or 'private' (self-hosted)")
    description: Union[str, None] = Field(default=None, description="Human-readable description of the embedding model")
    dimension: int = Field(default=1536, description="Output embedding dimension size")
    teams: list["TeamModel"] = Field(default=[], description="Teams that have access to this embedding model")
    model_config = ConfigDict(from_attributes=True, json_schema_extra={
        "example": {
            "name": "text-embedding-3-small",
            "class_name": "openai",
            "options": "{\"model\": \"text-embedding-3-small\"}",
            "privacy": "public",
            "description": "OpenAI small embedding model",
            "dimension": 1536
        }
    })


class Tool(BaseModel):
    """Tool metadata."""
    name: str = Field(description="Unique name of the tool")
    description: str = Field(description="Human-readable description of what the tool does")


class LLMUpdate(BaseModel):
    """Update an existing LLM configuration."""
    class_name: str = Field(default=None, description="LLM implementation class name")
    options: Union[str, Dict[str, Any], None] = Field(default=None, description="Provider-specific configuration options")
    privacy: str = Field(default=None, description="Privacy level: 'public' or 'private'")
    description: str = Field(default=None, description="Human-readable description of the LLM")
    type: str = Field(default=None, description="LLM type: 'chat', 'completion', 'vision', or 'qa'")
    input_cost: float = Field(default=None, description="Cost per 1K input tokens")
    output_cost: float = Field(default=None, description="Cost per 1K output tokens")
    context_window: int = Field(default=None, description="Maximum context window size in tokens")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "options": "{\"model\": \"openai/gpt-4o-mini\"}",
            "privacy": "public",
            "description": "Updated model description",
            "input_cost": 0.003,
            "output_cost": 0.012
        }
    })

    @field_validator('options', mode='before')
    @classmethod
    def serialize_options(cls, v):
        if isinstance(v, dict):
            return json.dumps(v)
        return v


class EmbeddingUpdate(BaseModel):
    """Update an existing embedding model configuration."""
    class_name: str = Field(default=None, description="Embedding implementation class name")
    options: Union[str, Dict[str, Any], None] = Field(default=None, description="Provider-specific configuration options")
    privacy: str = Field(default=None, description="Privacy level: 'public' or 'private'")
    description: str = Field(default=None, description="Human-readable description of the embedding model")
    dimension: int = Field(default=None, description="Output embedding dimension size")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "options": "{\"model\": \"text-embedding-3-large\"}",
            "privacy": "public",
            "dimension": 3072
        }
    })

    @field_validator('options', mode='before')
    @classmethod
    def serialize_options(cls, v):
        if isinstance(v, dict):
            return json.dumps(v)
        return v


class UserProject(BaseModel):
    """Project reference for a user."""
    id: int = Field(description="Unique project identifier")
    model_config = ConfigDict(from_attributes=True)


class ProjectUser(BaseModel):
    """User reference for a project."""
    username: str = Field(description="Username of the assigned user")
    model_config = ConfigDict(from_attributes=True)


class MCPServer(BaseModel):
    """MCP server connection configuration."""
    host: str = Field(description="MCP server command or URL (e.g. 'npx', 'uvx', or an HTTP endpoint)")
    args: Union[list[str], None] = Field(default=None, description="Command-line arguments for the MCP server process")
    env: Union[dict[str, str], None] = Field(default=None, description="Environment variables to pass to the MCP server process")
    tools: Union[str, None] = Field(default=None, description="Comma-separated list of specific tools to enable from this server")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "host": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {},
            "tools": None
        }
    })


class MCPProbeRequest(BaseModel):
    """Probe an MCP server to discover available tools."""
    host: str = Field(description="MCP server command or URL to probe")
    args: Union[list[str], None] = Field(default=None, description="Command-line arguments for the MCP server process")
    env: Union[dict[str, str], None] = Field(default=None, description="Environment variables to pass to the MCP server process")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "host": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        }
    })


class ProjectOptions(BaseModel):
    """Project-level configuration options."""
    logging: bool = Field(default=True, description="Enable inference logging for this project")
    colbert_rerank: Union[bool, None] = Field(default=None, description="Enable ColBERT reranking of retrieved documents")
    llm_rerank: Union[bool, None] = Field(default=None, description="Enable LLM-based reranking of retrieved documents")
    cache: Union[bool, None] = Field(default=None, description="Enable response caching")
    cache_threshold: Union[float, None] = Field(default=None, description="Similarity threshold for cache hits (0.0 to 1.0)")
    tables: Union[str, None] = Field(default=None, description="Comma-separated list of allowed database tables for RAG-SQL")
    tools: Union[str, None] = Field(default=None, description="Comma-separated list of enabled tool names")
    score: float = Field(default=0.0, description="Minimum similarity score threshold for retrieved documents")
    k: int = Field(default=4, description="Number of documents to retrieve from the knowledge base")
    max_iterations: int = Field(default=config.AGENT_MAX_ITERATIONS, description="Maximum iterations for agent project execution")
    connection: Union[str, None] = Field(default=None, description="Database connection string for RAG-SQL projects")
    mcp_servers: Union[list[MCPServer], None] = Field(default=None, description="List of MCP server configurations for agent projects")
    telegram_token: Union[str, None] = Field(default=None, description="Telegram bot token for Telegram integration")
    model_config = ConfigDict(from_attributes=True)


class ProjectBaseModel(BaseModel):
    """Base project model with all properties."""
    id: int = Field(description="Unique project identifier")
    name: str = Field(description="URL-friendly project name (used in API paths)")
    embeddings: Union[str, None] = Field(default=None, description="Name of the embedding model used for this project")
    llm: str = Field(description="Name of the LLM used for this project")
    type: str = Field(description="Project type: 'rag', 'inference', 'agent', 'vision', 'router', or 'ragsql'")
    system: Union[str, None] = Field(default=None, description="System prompt for the LLM")
    censorship: Union[str, None] = Field(default=None, description="Censorship message returned when the guard rejects a query")
    vectorstore: Union[str, None] = Field(default=None, description="Vector store backend: 'chroma' or 'redis'")
    guard: Union[str, None] = Field(default=None, description="Name of the LLM used as a content guard")
    human_name: Union[str, None] = Field(default=None, description="Human-readable display name for the project")
    human_description: Union[str, None] = Field(default=None, description="Human-readable description of the project")
    entrances: Union[list[EntranceModel], None] = Field(default=None, description="Router entrance configurations (router projects only)")
    public: bool = Field(default=False, description="Whether the project is publicly accessible without authentication")
    creator: Union[int, None] = Field(default=None, description="User ID of the project creator")
    default_prompt: Union[str, None] = Field(default=None, description="Default prompt template for the project")
    options: Union[str, ProjectOptions] = Field(default=ProjectOptions(), description="Project configuration options")
    users: list[ProjectUser] = Field(default=[], description="Users assigned to this project")
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
    """Project model with team information."""
    team: Union["TeamModel", None] = Field(default=None, description="Team that owns this project")
    model_config = ConfigDict(from_attributes=True)


class ProjectModelCreate(BaseModel):
    """Create a new AI project."""
    name: str = Field(description="URL-friendly project name (must be unique)")
    embeddings: Union[str, None] = Field(default=None, description="Name of the embedding model (required for RAG projects)")
    llm: str = Field(description="Name of the LLM to use")
    type: str = Field(description="Project type: 'rag', 'inference', 'agent', 'vision', 'router', or 'ragsql'")
    human_name: Union[str, None] = Field(default=None, description="Human-readable display name")
    human_description: Union[str, None] = Field(default=None, description="Human-readable project description")
    vectorstore: Union[str, None] = Field(default=None, description="Vector store backend: 'chroma' or 'redis'")
    team_id: int = Field(description="ID of the team that will own this project")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "my-rag-project",
            "embeddings": "text-embedding-3-small",
            "llm": "gpt-4o",
            "type": "rag",
            "human_name": "My RAG Project",
            "human_description": "A knowledge base powered by GPT-4o",
            "vectorstore": "chroma",
            "team_id": 1
        }
    })


class ProjectResponse(ProjectBaseModel):
    """Project response with simplified team."""
    team: Union["TeamResponse", None] = Field(default=None, description="Simplified team reference")


class ProjectsResponse(BaseModel):
    """Paginated list of projects."""
    projects: list[ProjectResponse] = Field(description="List of projects in the current page")
    total: int = Field(description="Total number of projects matching the query")
    start: int = Field(description="Starting index of the current page (0-based)")
    end: int = Field(description="Ending index of the current page (exclusive)")


class ProjectInfo(ProjectModel):
    """Extended project info including chunk count and LLM details."""
    chunks: int = Field(default=0, description="Number of document chunks in the project's knowledge base")
    llm_type: Union[str, None] = Field(default=None, description="Type of the associated LLM")
    llm_privacy: Union[str, None] = Field(default=None, description="Privacy level of the associated LLM")


class UserOptions(BaseModel):
    """User-level configuration options."""
    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreate(BaseModel):
    """Create a new API key."""
    description: str = Field(default="", description="Human-readable description of the API key's purpose")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "description": "CI/CD pipeline key"
        }
    })


class ApiKeyResponse(BaseModel):
    """API key metadata (without the key value)."""
    id: int = Field(description="Unique API key identifier")
    key_prefix: str = Field(description="First characters of the key for identification (e.g. 'sk-abc...')")
    description: str = Field(description="Human-readable description of the API key")
    created_at: datetime = Field(description="Timestamp when the API key was created")
    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreatedResponse(BaseModel):
    """API key creation response including the plaintext key (shown only once)."""
    id: int = Field(description="Unique API key identifier")
    api_key: str = Field(description="The full plaintext API key (only shown once at creation time)")
    key_prefix: str = Field(description="First characters of the key for identification")
    description: str = Field(description="Human-readable description of the API key")
    created_at: datetime = Field(description="Timestamp when the API key was created")


class User(BaseModel):
    """Full user profile with projects, teams, and API keys."""
    id: int = Field(description="Unique user identifier")
    username: str = Field(description="Unique username")
    is_admin: bool = Field(default=False, description="Whether the user has administrator privileges")
    is_private: bool = Field(default=False, description="Whether the user's profile is private")
    projects: list[UserProject] = Field(default=[], description="Projects assigned to this user")
    api_keys: list[ApiKeyResponse] = Field(default=[], description="API keys owned by this user")
    level: Union[str, None] = Field(default=None, description="User's subscription or access level")
    options: Union[str, UserOptions] = Field(default=UserOptions(), description="User configuration options")
    teams: list["TeamModel"] = Field(default=[], description="Teams the user is a member of")
    admin_teams: list["TeamModel"] = Field(default=[], description="Teams the user is an admin of")
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


class LimitedUser(BaseModel):
    """Limited user info visible to non-admin users."""
    id: int = Field(description="Unique user identifier")
    username: str = Field(description="Unique username")
    model_config = ConfigDict(from_attributes=True)


class UsersResponse(BaseModel):
    """List of users."""
    users: list[Union[User, LimitedUser]] = Field(description="List of user objects (full or limited based on requester's role)")


class UserBase(BaseModel):
    """Base user model."""
    username: str = Field(description="Unique username")


class UserLogin(BaseModel):
    """Login credentials."""
    user: str = Field(description="Username")
    password: str = Field(description="User's password")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "user": "admin",
            "password": "your-password"
        }
    })


class UserCreate(UserBase):
    """Create a new user."""
    password: str = Field(description="Password for the new user")
    is_admin: bool = Field(default=False, description="Grant administrator privileges")
    is_private: bool = Field(default=False, description="Make user profile private")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "username": "johndoe",
            "password": "securepassword123",
            "is_admin": False,
            "is_private": False
        }
    })


class UserUpdate(BaseModel):
    """Update user properties."""
    password: str = Field(default=None, description="New password for the user")
    is_admin: bool = Field(default=None, description="Update administrator privileges")
    is_private: bool = Field(default=None, description="Update profile privacy setting")
    projects: list[str] = Field(default=None, description="List of project names to assign to the user")
    options: Union[UserOptions, None] = Field(default=None, description="User configuration options to update")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "password": "newsecurepassword",
            "is_admin": False,
            "projects": ["my-rag-project", "my-agent"]
        }
    })


class ProjectModelUpdate(BaseModel):
    """Update project properties."""
    name: Union[str, None] = Field(default=None, description="New project name")
    embeddings: Union[str, None] = Field(default=None, description="Name of the embedding model")
    llm: Union[str, None] = Field(default=None, description="Name of the LLM to use")
    system: Union[str, None] = Field(default=None, description="System prompt for the LLM")
    censorship: Union[str, None] = Field(default=None, description="Censorship message returned when the guard rejects a query")
    score: Union[float, None] = Field(default=None, description="Minimum similarity score threshold")
    k: Union[int, None] = Field(default=None, description="Number of documents to retrieve")
    connection: Union[str, None] = Field(default=None, description="Database connection string for RAG-SQL projects")
    tables: Union[str, None] = Field(default=None, description="Comma-separated list of allowed database tables")
    llm_rerank: Union[bool, None] = Field(default=None, description="Enable LLM-based reranking")
    entrances: Union[list[EntranceModel], None] = Field(default=None, description="Router entrance configurations")
    colbert_rerank: Union[bool, None] = Field(default=None, description="Enable ColBERT reranking")
    cache: Union[bool, None] = Field(default=None, description="Enable response caching")
    cache_threshold: Union[float, None] = Field(default=None, description="Similarity threshold for cache hits")
    guard: Union[str, None] = Field(default=None, description="Name of the LLM used as a content guard")
    human_name: Union[str, None] = Field(default=None, description="Human-readable display name")
    human_description: Union[str, None] = Field(default=None, description="Human-readable project description")
    tools: Union[str, None] = Field(default=None, description="Comma-separated list of enabled tool names")
    users: list[str] = Field(default=None, description="List of usernames to assign to this project")
    public: Union[bool, None] = Field(default=None, description="Whether the project is publicly accessible")
    default_prompt: Union[str, None] = Field(default=None, description="Default prompt template")
    options: Union[ProjectOptions, None] = Field(default=None, description="Project configuration options to update")
    team_id: Union[int, None] = Field(default=None, description="ID of the team that owns this project")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "llm": "gpt-4o",
            "system": "You are a helpful assistant.",
            "human_name": "Updated Project Name",
            "k": 5,
            "score": 0.3,
            "public": False
        }
    })


class SourceModel(BaseModel):
    """Retrieved source document with relevance score."""
    source: str = Field(description="Source identifier of the retrieved document")
    keywords: str = Field(description="Keywords associated with the source document")
    text: str = Field(description="Text content of the retrieved chunk")
    score: float = Field(description="Relevance score (0.0 to 1.0)")
    id: str = Field(description="Unique identifier of the document chunk")


class InferenceResponse(BaseModel):
    """Response from an inference project."""
    question: str = Field(description="The original question that was asked")
    answer: str = Field(description="The LLM-generated answer")
    type: str = Field(description="Project type that generated this response")


class QuestionResponse(InferenceResponse):
    """Response from a RAG question with sources."""
    sources: Union[list[SourceModel], Union[list[str], None]] = Field(default=None, description="Source documents used to generate the answer")
    image: Union[str, None] = Field(default=None, description="Base64-encoded image in the response (vision projects)")


class RagSqlResponse(InferenceResponse):
    """Response from a RAG-SQL query."""
    sources: list[str] = Field(description="SQL queries generated and executed")


class ChatResponse(QuestionResponse):
    """Response from a chat interaction including conversation ID."""
    id: str = Field(description="Conversation ID for continuing the chat session")


class IngestResponse(BaseModel):
    """Result of a knowledge base ingestion operation."""
    source: str = Field(description="Source identifier of the ingested content")
    documents: int = Field(description="Number of documents processed")
    chunks: int = Field(description="Number of chunks created from the documents")


class ClassifierModel(BaseModel):
    """Text classification request."""
    sequence: str = Field(description="Text to classify")
    labels: list[str] = Field(description="Candidate labels for classification")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "sequence": "I need help with my billing account",
            "labels": ["billing", "technical", "general"]
        }
    })


class ClassifierResponse(BaseModel):
    """Text classification result with scores."""
    sequence: str = Field(description="The classified text")
    labels: list[str] = Field(description="Labels ordered by confidence (highest first)")
    scores: list[float] = Field(description="Confidence scores corresponding to each label")


class KeyCreate(BaseModel):
    """Create a LiteLLM proxy API key."""
    models: list[str] = Field(description="List of model names this key can access")
    name: str = Field(description="Human-readable name for the API key")
    rpm: Union[int, None] = Field(default=None, description="Rate limit in requests per minute")
    tpm: Union[int, None] = Field(default=None, description="Rate limit in tokens per minute")
    max_budget: Union[int, None] = Field(default=None, description="Maximum budget for this key")
    duration_budget: Union[str, None] = Field(default=None, description="Budget reset duration (e.g. '30d', '1h')")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "models": ["gpt-4o", "gpt-4o-mini"],
            "name": "production-key",
            "rpm": 100,
            "tpm": 100000,
            "max_budget": 50
        }
    })


class TeamUser(BaseModel):
    """User reference within a team."""
    id: int = Field(description="Unique user identifier")
    username: str = Field(description="Username of the team member")
    model_config = ConfigDict(from_attributes=True)


class TeamLLM(BaseModel):
    """LLM reference within a team."""
    id: int = Field(description="Unique LLM identifier")
    name: str = Field(description="Name of the LLM")
    model_config = ConfigDict(from_attributes=True)


class TeamEmbedding(BaseModel):
    """Embedding model reference within a team."""
    id: int = Field(description="Unique embedding model identifier")
    name: str = Field(description="Name of the embedding model")
    model_config = ConfigDict(from_attributes=True)


class TeamProject(BaseModel):
    """Project reference within a team."""
    id: int = Field(description="Unique project identifier")
    name: str = Field(description="Name of the project")
    model_config = ConfigDict(from_attributes=True)


class TeamModel(BaseModel):
    """Full team details with members, admins, and resources."""
    id: int = Field(description="Unique team identifier")
    name: str = Field(description="Team name")
    description: Union[str, None] = Field(default=None, description="Human-readable team description")
    created_at: datetime = Field(default=None, description="Timestamp when the team was created")
    budget: float = Field(default=-1.0, description="Team budget cap in configured currency (-1 means unlimited)")
    spending: Union[float, None] = Field(default=None, description="Total amount spent by the team (only present when budget >= 0)")
    remaining: Union[float, None] = Field(default=None, description="Remaining budget (only present when budget >= 0)")
    users: list[TeamUser] = Field(default=[], description="Team members")
    admins: list[TeamUser] = Field(default=[], description="Team administrators")
    projects: list[TeamProject] = Field(default=[], description="Projects owned by this team")
    llms: list[TeamLLM] = Field(default=[], description="LLMs accessible to this team")
    embeddings: list[TeamEmbedding] = Field(default=[], description="Embedding models accessible to this team")
    image_generators: list[str] = Field(default=[], description="Image generator names accessible to this team")
    audio_generators: list[str] = Field(default=[], description="Audio generator names accessible to this team")
    model_config = ConfigDict(from_attributes=True)

    @field_validator('image_generators', mode='before')
    @classmethod
    def parse_image_generators(cls, v):
        if v and len(v) > 0 and hasattr(v[0], 'generator_name'):
            return [item.generator_name for item in v]
        return v

    @field_validator('audio_generators', mode='before')
    @classmethod
    def parse_audio_generators(cls, v):
        if v and len(v) > 0 and hasattr(v[0], 'generator_name'):
            return [item.generator_name for item in v]
        return v


class TeamResponse(BaseModel):
    """Simplified team reference."""
    id: int = Field(description="Unique team identifier")
    name: str = Field(description="Team name")


class TeamModelCreate(BaseModel):
    """Create a new team."""
    name: str = Field(description="Team name (must be unique)")
    description: Union[str, None] = Field(default=None, description="Human-readable team description")
    budget: float = Field(default=-1.0, description="Team budget cap (-1 means unlimited)")
    users: list[str] = Field(default=[], description="Usernames to add as team members")
    admins: list[str] = Field(default=[], description="Usernames to add as team administrators")
    projects: list[str] = Field(default=[], description="Project names to assign to this team")
    llms: list[str] = Field(default=[], description="LLM names to make accessible to this team")
    embeddings: list[str] = Field(default=[], description="Embedding model names to make accessible to this team")
    image_generators: list[str] = Field(default=[], description="Image generator names to make accessible to this team")
    audio_generators: list[str] = Field(default=[], description="Audio generator names to make accessible to this team")
    creator_id: Union[int, None] = Field(default=None, description="User ID of the team creator (set automatically)")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "engineering",
            "description": "Engineering team",
            "users": ["alice", "bob"],
            "admins": ["alice"],
            "projects": [],
            "llms": ["gpt-4o"],
            "embeddings": ["text-embedding-3-small"]
        }
    })


class TeamModelUpdate(BaseModel):
    """Update team properties."""
    name: Union[str, None] = Field(default=None, description="New team name")
    description: Union[str, None] = Field(default=None, description="Updated team description")
    budget: Union[float, None] = Field(default=None, description="Team budget cap (-1 means unlimited)")
    users: list[str] = Field(default=None, description="Updated list of member usernames (replaces existing)")
    admins: list[str] = Field(default=None, description="Updated list of admin usernames (replaces existing)")
    projects: list[str] = Field(default=None, description="Updated list of project names (replaces existing)")
    llms: list[str] = Field(default=None, description="Updated list of LLM names (replaces existing)")
    embeddings: list[str] = Field(default=None, description="Updated list of embedding model names (replaces existing)")
    image_generators: list[str] = Field(default=None, description="Updated list of image generator names (replaces existing)")
    audio_generators: list[str] = Field(default=None, description="Updated list of audio generator names (replaces existing)")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "engineering-v2",
            "description": "Updated engineering team",
            "users": ["alice", "bob", "charlie"],
            "admins": ["alice"]
        }
    })


class TeamsResponse(BaseModel):
    """List of teams."""
    teams: list[TeamModel] = Field(description="List of team objects")


class OllamaInstanceModel(BaseModel):
    """Ollama instance connection details."""
    host: str = Field(default="localhost", description="Ollama server hostname or IP address")
    port: int = Field(default=11434, description="Ollama server port")


class OllamaModelInfo(BaseModel):
    """Ollama model metadata."""
    name: str = Field(description="Model name identifier")
    modified_at: Optional[str] = Field(default=None, description="Last modification timestamp")
    size: Optional[int] = Field(default=None, description="Model size in bytes")
    digest: Optional[str] = Field(default=None, description="Model digest hash")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional model metadata (family, parameters, quantization, etc.)")
    capabilities: Optional[List[str]] = Field(default=None, description="Model capabilities (e.g. 'completion', 'embedding', 'vision')")
    embedding_length: Optional[int] = Field(default=None, description="Embedding dimension length (for embedding models)")


class OllamaModelPullRequest(BaseModel):
    """Pull a model to an Ollama instance."""
    name: str = Field(description="Name of the model to pull (e.g. 'llama3', 'nomic-embed-text')")
    host: str = Field(default="localhost", description="Ollama server hostname or IP address")
    port: int = Field(default=11434, description="Ollama server port")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "llama3",
            "host": "localhost",
            "port": 11434
        }
    })


class OllamaModelPullResponse(BaseModel):
    """Result of an Ollama model pull operation."""
    status: str = Field(description="Pull operation status (e.g. 'success', 'error')")
    model: str = Field(description="Name of the pulled model")
    digest: Optional[str] = Field(default=None, description="Digest hash of the pulled model")


class SettingsResponse(BaseModel):
    """Current platform settings."""
    app_name: str = Field(description="Application display name")
    hide_branding: bool = Field(description="Whether to hide RestAI branding in the UI")
    proxy_enabled: bool = Field(description="Whether the LiteLLM proxy is enabled")
    proxy_url: Optional[str] = Field(default="", description="LiteLLM proxy URL")
    proxy_key: Optional[str] = Field(default="", description="LiteLLM proxy API key")
    proxy_team_id: Optional[str] = Field(default="", description="LiteLLM proxy team identifier")
    agent_max_iterations: int = Field(description="Maximum iterations for agent project execution")
    max_audio_upload_size: int = Field(description="Maximum audio upload file size in bytes")
    currency: str = Field(default="EUR", description="Currency code for cost display (e.g. 'EUR', 'USD')")
    redis_host: Optional[str] = Field(default="", description="Redis host for chat history persistence")
    redis_port: Optional[str] = Field(default="6379", description="Redis port")
    redis_password: Optional[str] = Field(default="", description="Redis password (masked)")
    redis_database: Optional[str] = Field(default="0", description="Redis database number")
    # Authentication
    auth_disable_local: bool = Field(default=False, description="Disable local username/password authentication")
    sso_auto_create_user: bool = Field(default=False, description="Auto-create user on first SSO login")
    sso_allowed_domains: Optional[str] = Field(default="*", description="Comma-separated allowed email domains for SSO")
    # Google OAuth
    sso_google_client_id: Optional[str] = Field(default="", description="Google OAuth client ID")
    sso_google_client_secret: Optional[str] = Field(default="", description="Google OAuth client secret (masked)")
    sso_google_redirect_uri: Optional[str] = Field(default="", description="Google OAuth redirect URI")
    sso_google_scope: Optional[str] = Field(default="openid email profile", description="Google OAuth scope")
    # Microsoft OAuth
    sso_microsoft_client_id: Optional[str] = Field(default="", description="Microsoft OAuth client ID")
    sso_microsoft_client_secret: Optional[str] = Field(default="", description="Microsoft OAuth client secret (masked)")
    sso_microsoft_tenant_id: Optional[str] = Field(default="", description="Microsoft OAuth tenant ID")
    sso_microsoft_redirect_uri: Optional[str] = Field(default="", description="Microsoft OAuth redirect URI")
    sso_microsoft_scope: Optional[str] = Field(default="openid email profile", description="Microsoft OAuth scope")
    # GitHub OAuth
    sso_github_client_id: Optional[str] = Field(default="", description="GitHub OAuth client ID")
    sso_github_client_secret: Optional[str] = Field(default="", description="GitHub OAuth client secret (masked)")
    sso_github_redirect_uri: Optional[str] = Field(default="", description="GitHub OAuth redirect URI")
    sso_github_scope: Optional[str] = Field(default="user:email", description="GitHub OAuth scope")
    # Generic OIDC
    sso_oidc_client_id: Optional[str] = Field(default="", description="OIDC client ID")
    sso_oidc_client_secret: Optional[str] = Field(default="", description="OIDC client secret (masked)")
    sso_oidc_provider_url: Optional[str] = Field(default="", description="OIDC provider discovery URL")
    sso_oidc_redirect_uri: Optional[str] = Field(default="", description="OIDC redirect URI")
    sso_oidc_scopes: Optional[str] = Field(default="openid email profile", description="OIDC scopes")
    sso_oidc_provider_name: Optional[str] = Field(default="SSO", description="OIDC provider display name")
    sso_oidc_email_claim: Optional[str] = Field(default="email", description="OIDC email claim field")
    # GPU
    gpu_enabled: bool = Field(default=False, description="Whether GPU features are enabled")
    gpu_worker_devices: Optional[str] = Field(default="", description="Comma-separated GPU indices for worker processes (e.g. '0,1')")


class SettingsUpdate(BaseModel):
    """Update platform settings."""
    app_name: Optional[str] = Field(default=None, description="Application display name")
    hide_branding: Optional[bool] = Field(default=None, description="Whether to hide RestAI branding in the UI")
    proxy_enabled: Optional[bool] = Field(default=None, description="Whether the LiteLLM proxy is enabled")
    proxy_url: Optional[str] = Field(default=None, description="LiteLLM proxy URL")
    proxy_key: Optional[str] = Field(default=None, description="LiteLLM proxy API key")
    proxy_team_id: Optional[str] = Field(default=None, description="LiteLLM proxy team identifier")
    agent_max_iterations: Optional[int] = Field(default=None, description="Maximum iterations for agent project execution")
    max_audio_upload_size: Optional[int] = Field(default=None, description="Maximum audio upload file size in bytes")
    currency: Optional[str] = Field(default=None, description="Currency code for cost display (e.g. 'EUR', 'USD')")
    redis_host: Optional[str] = Field(default=None, description="Redis host for chat history persistence")
    redis_port: Optional[str] = Field(default=None, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_database: Optional[str] = Field(default=None, description="Redis database number")
    # Authentication
    auth_disable_local: Optional[bool] = Field(default=None, description="Disable local username/password authentication")
    sso_auto_create_user: Optional[bool] = Field(default=None, description="Auto-create user on first SSO login")
    sso_allowed_domains: Optional[str] = Field(default=None, description="Comma-separated allowed email domains for SSO")
    # Google OAuth
    sso_google_client_id: Optional[str] = Field(default=None, description="Google OAuth client ID")
    sso_google_client_secret: Optional[str] = Field(default=None, description="Google OAuth client secret")
    sso_google_redirect_uri: Optional[str] = Field(default=None, description="Google OAuth redirect URI")
    sso_google_scope: Optional[str] = Field(default=None, description="Google OAuth scope")
    # Microsoft OAuth
    sso_microsoft_client_id: Optional[str] = Field(default=None, description="Microsoft OAuth client ID")
    sso_microsoft_client_secret: Optional[str] = Field(default=None, description="Microsoft OAuth client secret")
    sso_microsoft_tenant_id: Optional[str] = Field(default=None, description="Microsoft OAuth tenant ID")
    sso_microsoft_redirect_uri: Optional[str] = Field(default=None, description="Microsoft OAuth redirect URI")
    sso_microsoft_scope: Optional[str] = Field(default=None, description="Microsoft OAuth scope")
    # GitHub OAuth
    sso_github_client_id: Optional[str] = Field(default=None, description="GitHub OAuth client ID")
    sso_github_client_secret: Optional[str] = Field(default=None, description="GitHub OAuth client secret")
    sso_github_redirect_uri: Optional[str] = Field(default=None, description="GitHub OAuth redirect URI")
    sso_github_scope: Optional[str] = Field(default=None, description="GitHub OAuth scope")
    # Generic OIDC
    sso_oidc_client_id: Optional[str] = Field(default=None, description="OIDC client ID")
    sso_oidc_client_secret: Optional[str] = Field(default=None, description="OIDC client secret")
    sso_oidc_provider_url: Optional[str] = Field(default=None, description="OIDC provider discovery URL")
    sso_oidc_redirect_uri: Optional[str] = Field(default=None, description="OIDC redirect URI")
    sso_oidc_scopes: Optional[str] = Field(default=None, description="OIDC scopes")
    sso_oidc_provider_name: Optional[str] = Field(default=None, description="OIDC provider display name")
    sso_oidc_email_claim: Optional[str] = Field(default=None, description="OIDC email claim field")
    # GPU
    gpu_enabled: Optional[bool] = Field(default=None, description="Whether GPU features are enabled")
    gpu_worker_devices: Optional[str] = Field(default=None, description="Comma-separated GPU indices for worker processes (e.g. '0,1')")
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "app_name": "My AI Platform",
            "hide_branding": True,
            "currency": "USD",
            "agent_max_iterations": 25
        }
    })


class DeleteResponse(BaseModel):
    """Confirmation of resource deletion."""
    deleted: str = Field(description="Identifier of the deleted resource")


class MessageResponse(BaseModel):
    """Generic operation response."""
    message: str = Field(description="Status message")


class OpenAIChatMessage(BaseModel):
    """A single message in an OpenAI chat completion request."""
    role: str = Field(description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(description="Message content")


class OpenAIChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(description="Model name to use")
    messages: list[OpenAIChatMessage] = Field(description="List of messages in the conversation")
    temperature: Optional[float] = Field(default=None, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens to generate")
    stream: bool = Field(default=False, description="Enable streaming response via SSE")


class OpenAIChatCompletionChoice(BaseModel):
    """A single choice in a chat completion response."""
    index: int = Field(description="Choice index")
    message: OpenAIChatMessage = Field(description="The generated message")
    finish_reason: str = Field(default="stop", description="Reason the generation stopped")


class OpenAIChatCompletionUsage(BaseModel):
    """Token usage info for a chat completion."""
    prompt_tokens: int = Field(description="Number of input tokens")
    completion_tokens: int = Field(description="Number of output tokens")
    total_tokens: int = Field(description="Total tokens used")


class OpenAIChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str = Field(description="Unique completion identifier")
    object: str = Field(default="chat.completion", description="Object type")
    created: int = Field(description="Unix timestamp of creation")
    model: str = Field(description="Model used")
    choices: list[OpenAIChatCompletionChoice] = Field(description="Generated completions")
    usage: OpenAIChatCompletionUsage = Field(description="Token usage statistics")


class OpenAIAudioTranscriptionResponse(BaseModel):
    """OpenAI-compatible audio transcription response."""
    text: str = Field(description="Transcribed text")


class OpenAIEmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request."""
    model: str = Field(description="Embedding model name to use")
    input: Union[str, list[str]] = Field(description="Text(s) to embed")


class OpenAIEmbeddingData(BaseModel):
    """A single embedding result."""
    object: str = Field(default="embedding")
    embedding: list[float] = Field(description="The embedding vector")
    index: int = Field(description="Index of the input text")


class OpenAIEmbeddingUsage(BaseModel):
    """Token usage for an embedding request."""
    prompt_tokens: int = Field(description="Number of input tokens")
    total_tokens: int = Field(description="Total tokens used")


class OpenAIEmbeddingResponse(BaseModel):
    """OpenAI-compatible embedding response."""
    object: str = Field(default="list")
    data: list[OpenAIEmbeddingData] = Field(description="Embedding results")
    model: str = Field(description="Model used")
    usage: OpenAIEmbeddingUsage = Field(description="Token usage statistics")
