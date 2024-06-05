import os

from dotenv import load_dotenv

load_dotenv()


def loadEnvVars():
    if "EMBEDDINGS_PATH" not in os.environ:
        os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

    if "ANONYMIZED_TELEMETRY" not in os.environ:
        os.environ["ANONYMIZED_TELEMETRY"] = "False"

    if "LOG_LEVEL" not in os.environ:
        os.environ["LOG_LEVEL"] = "INFO"

    os.environ["ALLOW_RESET"] = "true"


loadEnvVars()

RESTAI_PORT = os.environ.get("RESTAI_PORT", 9000)
RESTAI_AUTH_SECRET = os.environ.get("RESTAI_AUTH_SECRET")
RESTAI_AUTH_DISABLE_LOCAL = os.environ.get("RESTAI_AUTH_DISABLE_LOCAL")
RESTAI_DEV = os.environ.get("RESTAI_DEV")

LOG_LEVEL = os.environ.get("LOG_LEVEL")
SENTRY_DSN = os.environ.get("SENTRY_DSN")

MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_HOST = os.environ.get("MYSQL_HOST")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_DB = os.environ.get("MYSQL_DB", "restai")

MYSQL_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "restai")

POSTGRES_URL = "postgresql+psycopg2://"f"{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"

RESTAI_DEFAULT_PASSWORD = os.environ.get("RESTAI_DEFAULT_PASSWORD", "admin")
RESTAI_DEMO = os.environ.get("RESTAI_DEMO")

SQLITE_PATH = os.environ.get("SQLITE_PATH")


REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PORT = os.environ.get("REDIS_PORT")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")

RESTAI_SSO_SECRET = os.environ.get("RESTAI_SSO_SECRET")
RESTAI_SSO_ALG = os.environ.get("RESTAI_SSO_ALG", "HS512")
RESTAI_SSO_CALLBACK = os.environ.get("RESTAI_SSO_CALLBACK")

RESTAI_GPU = os.environ.get("RESTAI_GPU")
RESTAI_DEFAULT_DEVICE = os.environ.get("RESTAI_DEFAULT_DEVICE")

EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH")
