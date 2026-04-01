from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Float, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base


Base = declarative_base()

users_projects = Table(
    "users_projects",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
)

# Team-related relationship tables
teams_users = Table(
    "teams_users",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)

teams_admins = Table(
    "teams_admins",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)

teams_projects = Table(
    "teams_projects",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id"), primary_key=True),
    Column("project_id", ForeignKey("projects.id"), primary_key=True),
)

teams_llms = Table(
    "teams_llms",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id"), primary_key=True),
    Column("llm_id", ForeignKey("llms.id"), primary_key=True),
)

teams_embeddings = Table(
    "teams_embeddings",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id"), primary_key=True),
    Column("embedding_id", ForeignKey("embeddings.id"), primary_key=True),
)

class TeamDatabase(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    description = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    budget = Column(Float, default=-1.0)
    branding = Column(Text, default="{}")

    # Many-to-many relationships
    users = relationship('UserDatabase', secondary=teams_users, back_populates='teams')
    admins = relationship('UserDatabase', secondary=teams_admins, back_populates='admin_teams')
    projects = relationship('ProjectDatabase', back_populates='team')
    llms = relationship('LLMDatabase', secondary=teams_llms, back_populates='teams')
    embeddings = relationship('EmbeddingDatabase', secondary=teams_embeddings, back_populates='teams')
    image_generators = relationship("TeamImageGeneratorDatabase", back_populates="team", cascade="all, delete-orphan")
    audio_generators = relationship("TeamAudioGeneratorDatabase", back_populates="team", cascade="all, delete-orphan")

class ProjectDatabase(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    embeddings = Column(String(255))
    type = Column(String(255))
    llm = Column(String(255))
    system = Column(Text)
    censorship = Column(String(4096))
    vectorstore = Column(String(255))
    guard = Column(String(255))
    human_name = Column(String(255))
    human_description = Column(Text)
    creator = Column(Integer)
    public = Column(Boolean, default=False)
    default_prompt = Column(Text)
    options = Column(Text, default="{}")
    team_id = Column(Integer, ForeignKey("teams.id"))
    users = relationship('UserDatabase', secondary=users_projects, back_populates='projects', lazy="select")
    team = relationship('TeamDatabase', back_populates='projects')

class UserDatabase(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    is_admin = Column(Boolean, default=False)  # Platform admin
    is_private = Column(Boolean, default=False)
    api_key = Column(String(4096))  # Legacy column, kept for existing DBs
    options = Column(Text, default="{}")
    totp_secret = Column(String(500), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    totp_recovery_codes = Column(Text, nullable=True)
    projects = relationship('ProjectDatabase', secondary=users_projects, back_populates='users')
    teams = relationship('TeamDatabase', secondary=teams_users, back_populates='users')
    admin_teams = relationship('TeamDatabase', secondary=teams_admins, back_populates='admins')
    api_keys = relationship('ApiKeyDatabase', back_populates='user', cascade='all, delete-orphan')


class ApiKeyDatabase(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    encrypted_key = Column(String(4096), nullable=False)
    key_prefix = Column(String(12), nullable=False)
    description = Column(String(255), default="")
    created_at = Column(DateTime, nullable=False)
    allowed_projects = Column(Text, nullable=True)
    read_only = Column(Boolean, nullable=False, default=False)

    user = relationship('UserDatabase', back_populates='api_keys')

class OutputDatabase(Base):
    __tablename__ = "output"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text)
    answer = Column(Text)
    
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    team_id = Column(Integer, ForeignKey('teams.id'), nullable=True)

    llm = Column(String(255))

    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    input_cost = Column(Float)
    output_cost = Column(Float)

    date = Column(DateTime, index=True)
    latency_ms = Column(Integer, nullable=True)

    chat_id = Column(String(255), index=True)


class EvalDatasetDatabase(Base):
    __tablename__ = "eval_datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    description = Column(Text, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    test_cases = relationship("EvalTestCaseDatabase", back_populates="dataset", cascade="all, delete-orphan")
    runs = relationship("EvalRunDatabase", back_populates="dataset", cascade="all, delete-orphan")


class EvalTestCaseDatabase(Base):
    __tablename__ = "eval_test_cases"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("eval_datasets.id"), nullable=False)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    context = Column(Text, nullable=True)
    created_at = Column(DateTime)

    dataset = relationship("EvalDatasetDatabase", back_populates="test_cases")


class PromptVersionDatabase(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=False)
    description = Column(String(500), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime)
    is_active = Column(Boolean, default=False)


class EvalRunDatabase(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("eval_datasets.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    prompt_version_id = Column(Integer, ForeignKey("prompt_versions.id"), nullable=True)
    status = Column(String(50), default="pending")
    metrics = Column(Text)
    summary = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime)
    error = Column(Text, nullable=True)

    dataset = relationship("EvalDatasetDatabase", back_populates="runs")
    results = relationship("EvalResultDatabase", back_populates="run", cascade="all, delete-orphan")


class EvalResultDatabase(Base):
    __tablename__ = "eval_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("eval_runs.id"), nullable=False)
    test_case_id = Column(Integer, ForeignKey("eval_test_cases.id"), nullable=False)
    actual_answer = Column(Text, nullable=True)
    retrieval_context = Column(Text, nullable=True)
    metric_name = Column(String(255))
    score = Column(Float)
    reason = Column(Text, nullable=True)
    passed = Column(Boolean, default=False)
    latency_ms = Column(Integer, nullable=True)

    run = relationship("EvalRunDatabase", back_populates="results")


class TeamInvitationDatabase(Base):
    __tablename__ = "team_invitations"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    username = Column(String(255), nullable=False, index=True)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False)

    team = relationship("TeamDatabase")


class AuditLogDatabase(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(255), nullable=True)
    action = Column(String(10), nullable=False)
    resource = Column(String(500), nullable=False)
    status_code = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False, index=True)


class RetrievalEventDatabase(Base):
    __tablename__ = "retrieval_events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    source = Column(String(500), nullable=False, index=True)
    score = Column(Float, nullable=True)
    chunk_id = Column(String(255), nullable=True, index=True)
    chunk_token_length = Column(Integer, nullable=True)
    chunk_text_length = Column(Integer, nullable=True)
    date = Column(DateTime, nullable=False, index=True)


class GuardEventDatabase(Base):
    __tablename__ = "guard_events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    guard_project = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phase = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)
    mode = Column(String(10), nullable=False, default="block")
    text_checked = Column(Text, nullable=True)
    guard_response = Column(Text, nullable=True)
    date = Column(DateTime, nullable=False, index=True)


class LLMDatabase(Base):
    __tablename__ = "llms"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), unique=True, index=True)
    class_name = Column(String(255))
    options = Column(Text)
    privacy = Column(String(255))
    description = Column(Text)
    type = Column(String(255))
    input_cost = Column(Float, default=0.0)
    output_cost = Column(Float, default=0.0)
    context_window = Column(Integer, default=4096)
    teams = relationship('TeamDatabase', secondary=teams_llms, back_populates='llms')
    
class SettingDatabase(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)


class EmbeddingDatabase(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), unique=True, index=True)
    class_name = Column(String(255))
    options = Column(Text)
    privacy = Column(String(255))
    description = Column(Text)
    dimension = Column(Integer, default=1536)
    teams = relationship('TeamDatabase', secondary=teams_embeddings, back_populates='embeddings')


class TeamImageGeneratorDatabase(Base):
    __tablename__ = "teams_image_generators"
    team_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    generator_name = Column(String(255), primary_key=True)
    team = relationship("TeamDatabase", back_populates="image_generators")


class TeamAudioGeneratorDatabase(Base):
    __tablename__ = "teams_audio_generators"
    team_id = Column(Integer, ForeignKey("teams.id"), primary_key=True)
    generator_name = Column(String(255), primary_key=True)
    team = relationship("TeamDatabase", back_populates="audio_generators")
