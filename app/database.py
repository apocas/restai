from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, ProjectDatabase, UserDatabase


class Database:
    def __init__(self):
        self.engine = create_engine(
            "sqlite:///./restai.db", connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine)

        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def create_tables(self):
        print("Creating tables...")
        Base.metadata.create_all(bind=self.engine)

    def create_user(self, db, username, password, admin=False):
        hash = self.pwd_context.hash(password)
        db_user = UserDatabase(
            username=username, hashed_password=hash, is_admin=admin)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def get_users(self, db):
        return db.query(UserDatabase).all()

    def get_user(self, db, username):
        return db.query(UserDatabase).filter(
            UserDatabase.username == username).first()

    def update_user(self, db, user, password):
        hash = self.pwd_context.hash(password)
        user.hashed_password = hash
        db.commit()
        return True

    def get_user_by_id(self, db, id):
        return db.query(UserDatabase).filter(UserDatabase.id == id).first()

    def delete_user(self, db, user):
        db.delete(user)
        db.commit()
        return True

    def add_project(self, db, user, name):
        db_project = ProjectDatabase(name=name, owner_id=user.id)
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project

    def remove_project_from_user(self, db, user, project):
        user.projects.remove(project)
        db.commit()
        return True
