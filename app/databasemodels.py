from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float
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
    system = Column(String(4096))
    sandboxed = Column(Boolean, default=False)
    censorship = Column(String(4096))
    k = Column(Integer, default=2)
    score = Column(Float, default=0.3)
    vectorstore = Column(String(255), default="chroma")
    connection = Column(String(4096))

    owners = relationship("UserProjectDatabase", back_populates="project")
