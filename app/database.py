import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.databasemodels import Base, ProjectDatabase, UserProjectDatabase, UserDatabase
from app.models import User, UserUpdate


if os.environ.get("MYSQL_PASSWORD"):
    host = os.environ.get("MYSQL_HOST") or "127.0.0.1"
    print("Using MySQL database: " + host)
    engine = create_engine('mysql+pymysql://' + (os.environ.get("MYSQL_USER") or "restai") + ':' + os.environ.get("MYSQL_PASSWORD") + '@' +
                           host + '/' +
                           (os.environ.get("MYSQL_DB") or "restai"),
                           pool_size=30,
                           max_overflow=100,
                           pool_recycle=900)
else:
    print("Using sqlite database.")
    engine = create_engine(
        "sqlite:///./restai.db",
        connect_args={
            "check_same_thread": False},
        pool_size=30,
        max_overflow=100,
        pool_recycle=900)


SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


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

    def create_user(self, db, username, password, admin=False, private=False):
        if password:
            hash = pwd_context.hash(password)
        else:
            hash = None
        db_user = UserDatabase(
            username=username, hashed_password=hash, is_admin=admin, is_private=private)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def get_users(self, db):
        users = db.query(UserDatabase).all()
        return users

    def get_user_by_apikey(self, db, apikey):
        user = db.query(UserDatabase).filter(
            UserDatabase.api_key == apikey).first()
        return user

    def get_user_by_username(self, db, username):
        user = db.query(UserDatabase).filter(
            UserDatabase.username == username).first()
        return user

    def update_user(self, db, user: User, userc: UserUpdate):
        if userc.password is not None:
            hash = pwd_context.hash(userc.password)
            user.hashed_password = hash

        if userc.is_admin is not None:
            user.is_admin = userc.is_admin

        if userc.is_private is not None:
            user.is_private = userc.is_private

        if userc.sso is not None:
            user.sso = userc.sso

        if userc.api_key is not None:
            user.api_key = userc.api_key

        db.commit()
        return True

    def get_user_by_id(self, db, id):
        user = db.query(UserDatabase).filter(UserDatabase.id == id).first()
        return user

    def delete_user(self, db, user):
        db.delete(user)
        db.commit()
        return True

    def add_userproject(self, db, user, name, projectid):
        db_project = UserProjectDatabase(
            name=name, owner_id=user.id, project_id=projectid)
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project

    def delete_userprojects(self, db, user):
        db.query(UserProjectDatabase).filter(
            UserProjectDatabase.owner_id == user.id).delete()
        db.commit()
        return True

    def get_project_by_name(self, db, name):
        project = db.query(ProjectDatabase).filter(
            ProjectDatabase.name == name).first()
        return project

    def create_project(
            self,
            db,
            name,
            embeddings,
            llm,
            system,
            sandboxed,
            censorship,
            vectorstore,
            type,
            connection):
        db_project = ProjectDatabase(
            name=name,
            embeddings=embeddings,
            llm=llm,
            system=system,
            sandboxed=sandboxed,
            censorship=censorship,
            vectorstore=vectorstore,
            type=type,
            connection=connection)
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project

    def get_projects(self, db):
        projects = db.query(ProjectDatabase).all()
        return projects

    def delete_project(self, db, project):
        db.query(UserProjectDatabase).filter(
            UserProjectDatabase.project_id == project.id).delete()
        db.query(UserProjectDatabase).filter(
            UserProjectDatabase.name == project.name).delete()
        db.delete(project)
        db.commit()
        return True

    def update_project(self, db):
        db.commit()
        return True


dbc = Database()
