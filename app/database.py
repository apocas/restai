from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, ProjectDatabase, UserProjectDatabase, UserDatabase
from app.models import ProjectModel, User, UserUpdate
from app.project import Project

engine = create_engine(
    "sqlite:///./restai.db", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


if "users" not in inspect(engine).get_table_names():
    print("Initializing database...")
    Base.metadata.create_all(bind=engine)
    dbi = SessionLocal()
    db_user = UserDatabase(
        username="admin",
        hashed_password=pwd_context.hash("admin"),
        is_admin=True)
    dbi.add(db_user)
    dbi.commit()
    dbi.refresh(db_user)
    dbi.close()
    print("Database initialized. Default admin user created (admin:admin).")


class Database:
    def __init__(self):
        self.db = SessionLocal()

    def create_user(self, username, password, admin=False):
        hash = pwd_context.hash(password)
        db_user = UserDatabase(
            username=username, hashed_password=hash, is_admin=admin)
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def get_users(self):
        return self.db.query(UserDatabase).all()

    def get_user_by_username(self, username):
        return self.db.query(UserDatabase).filter(
            UserDatabase.username == username).first()

    def update_user(self, user: User, userc: UserUpdate):
        if userc.password is not None:
            hash = pwd_context.hash(userc.password)
            user.hashed_password = hash
            
        if userc.is_admin is not None:
            user.is_admin = userc.is_admin

        user.hashed_password = hash
        self.db.commit()
        return True

    def get_user_by_id(self, id):
        return self.db.query(UserDatabase).filter(UserDatabase.id == id).first()

    def delete_user(self, user):
        self.db.delete(user)
        self.db.commit()
        return True

    def add_userproject(self, user, name):
        db_project = UserProjectDatabase(name=name, owner_id=user.id)
        self.db.add(db_project)
        self.db.commit()
        self.db.refresh(db_project)
        return db_project

    def delete_userprojects(self, user):
        self.db.query(UserProjectDatabase).filter(
            UserProjectDatabase.owner_id == user.id).delete()
        self.db.commit()
        return True

    def get_project_by_name(self, name):
        return self.db.query(ProjectDatabase).filter(
            ProjectDatabase.name == name).first()
        
    def create_project(self, name, embeddings, llm, system):
        db_project = ProjectDatabase(
            name=name, embeddings=embeddings, llm=llm, system=system)
        self.db.add(db_project)
        self.db.commit()
        self.db.refresh(db_project)
        return db_project
      
    def get_projects(self):
        return self.db.query(ProjectDatabase).all()
      
    def delete_project(self, project):
        self.db.delete(project)
        self.db.commit()
        return True

    def update_project(self):
        self.db.commit()
        return True

dbc = Database()
