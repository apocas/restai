from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, ProjectDatabase, UserDatabase

engine = create_engine(
    "sqlite:///./restai.db", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

    def create_user(self, db, username, password, admin=False):
        hash = pwd_context.hash(password)
        db_user = UserDatabase(
            username=username, hashed_password=hash, is_admin=admin)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def get_users(self, db):
        return db.query(UserDatabase).all()

    def get_user_by_username(self, db, username):
        return db.query(UserDatabase).filter(
            UserDatabase.username == username).first()

    def update_user(self, db, user: UserDatabase, password):
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

    def delete_projects(self, db, user):
        db.query(ProjectDatabase).filter(
            ProjectDatabase.owner_id == user.id).delete()
        db.commit()
        return True


dbc = Database()
