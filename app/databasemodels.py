from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserDatabase(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    is_admin = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)
    api_key = Column(String(4096))
    sso = Column(String(4096))
    projects = relationship("UserProjectDatabase", back_populates="owner")


class UserProjectDatabase(Base):
    __tablename__ = "userprojects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))

    owner = relationship("UserDatabase", back_populates="projects")
    project = relationship("ProjectDatabase", back_populates="owners")


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
    score = Column(Float, default=0.3)
    vectorstore = Column(String(255))
    connection = Column(String(4096))
    tables = Column(String(4096))
    llm_rerank = Column(Boolean, default=False)
    colbert_rerank = Column(Boolean, default=False)

    owners = relationship("UserProjectDatabase", back_populates="project")

class LLMDatabase(Base):
    __tablename__ = "llms"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), unique=True, index=True)
    class_name = Column(String(255))
    options = Column(Text)
    privacy = Column(String(255))
    description = Column(Text)
    type = Column(String(255))