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

class ProjectDatabase(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    embeddings = Column(String(255))
    type = Column(String(255))
    llm = Column(String(255))
    system = Column(Text)
    censorship = Column(String(4096))
    k = Column(Integer, default=4)
    score = Column(Float, default=0.0)
    vectorstore = Column(String(255))
    connection = Column(String(4096))
    tables = Column(String(4096))
    llm_rerank = Column(Boolean, default=False)
    colbert_rerank = Column(Boolean, default=False)
    cache = Column(Boolean, default=False)
    cache_threshold = Column(Float, default=0.9)
    guard = Column(String(255))
    human_name = Column(String(255))
    human_description = Column(Text)
    tools = Column(Text)
    creator = Column(Integer)
    public = Column(Boolean, default=False)
    default_prompt = Column(Text)
    options = Column(Text, default="{}")
    users = relationship('UserDatabase', secondary=users_projects, back_populates='projects', lazy="select")
    entrances = relationship("RouterEntrancesDatabase", back_populates="project", lazy="select")

class UserDatabase(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    is_admin = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)
    api_key = Column(String(4096))
    sso = Column(String(4096))
    projects = relationship('ProjectDatabase', secondary=users_projects, back_populates='users')
    

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
    
class EmbeddingDatabase(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), unique=True, index=True)
    class_name = Column(String(255))
    options = Column(Text)
    privacy = Column(String(255))
    description = Column(Text)
    dimension = Column(Integer, default=1536)
