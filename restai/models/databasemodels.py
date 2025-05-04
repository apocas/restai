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
    
    # Many-to-many relationships
    users = relationship('UserDatabase', secondary=teams_users, back_populates='teams')
    admins = relationship('UserDatabase', secondary=teams_admins, back_populates='admin_teams')
    projects = relationship('ProjectDatabase', secondary=teams_projects, back_populates='teams')
    llms = relationship('LLMDatabase', secondary=teams_llms, back_populates='teams')
    embeddings = relationship('EmbeddingDatabase', secondary=teams_embeddings, back_populates='teams')

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
    users = relationship('UserDatabase', secondary=users_projects, back_populates='projects', lazy="select")
    entrances = relationship("RouterEntrancesDatabase", back_populates="project", lazy="select")
    teams = relationship('TeamDatabase', secondary=teams_projects, back_populates='projects')

class UserDatabase(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    is_admin = Column(Boolean, default=False)  # Platform admin
    is_private = Column(Boolean, default=False)
    api_key = Column(String(4096))
    options = Column(Text, default="{}")
    projects = relationship('ProjectDatabase', secondary=users_projects, back_populates='users')
    teams = relationship('TeamDatabase', secondary=teams_users, back_populates='users')
    admin_teams = relationship('TeamDatabase', secondary=teams_admins, back_populates='admins')

class OutputDatabase(Base):
    __tablename__ = "output"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text)
    answer = Column(Text)
    
    project_id = Column(Integer, ForeignKey('projects.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    
    llm = Column(String(255))
    
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    input_cost = Column(Float)
    output_cost = Column(Float)
    
    date = Column(DateTime)
    
    chat_id = Column(String(255))
    
class RouterEntrancesDatabase(Base):
    __tablename__ = "routerentrances"

    id = Column(Integer, primary_key=True, index=True)
    destination = Column(String(255), index=True)
    name = Column(String(255), index=True)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"))
    
    project = relationship("ProjectDatabase", back_populates="entrances")


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
    teams = relationship('TeamDatabase', secondary=teams_llms, back_populates='llms')
    
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
