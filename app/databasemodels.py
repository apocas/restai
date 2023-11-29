from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserDatabase(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=True)
    projects = relationship("UserProjectDatabase", back_populates="owner")


class UserProjectDatabase(Base):
    __tablename__ = "userprojects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))

    owner = relationship("UserDatabase", back_populates="projects")
    project = relationship("ProjectDatabase", back_populates="owners")


class ProjectDatabase(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, unique=True, index=True)
    embeddings = Column(String)
    llm = Column(String)
    system = Column(String)
    sandboxed = Column(Boolean, default=False)
    censorship = Column(String)
    k = Column(Integer, default=2)
    score = Column(Float, default=0.2)
    sandbox_project = Column(String)

    owners = relationship("UserProjectDatabase", back_populates="project")
