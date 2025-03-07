import os

from dotenv import load_dotenv

load_dotenv()


def load_env_vars():
    if "EMBEDDINGS_PATH" not in os.environ:
        os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

    if "ANONYMIZED_TELEMETRY" not in os.environ:
        os.environ["ANONYMIZED_TELEMETRY"] = "False"

    if "LOG_LEVEL" not in os.environ:
        os.environ["LOG_LEVEL"] = "INFO"

    os.environ["ALLOW_RESET"] = "true"


load_env_vars()

RESTAI_PORT = os.environ.get("RESTAI_PORT") or 9000
RESTAI_AUTH_SECRET = os.environ.get("RESTAI_AUTH_SECRET")
RESTAI_AUTH_DISABLE_LOCAL = os.environ.get("RESTAI_AUTH_DISABLE_LOCAL")
RESTAI_DEV = True if os.environ.get("RESTAI_DEV", "").lower() in ('true', '1') else False

LOG_LEVEL = os.environ.get("LOG_LEVEL")
SENTRY_DSN = os.environ.get("SENTRY_DSN")

MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
MYSQL_HOST = os.environ.get("MYSQL_HOST")
MYSQL_USER = os.environ.get("MYSQL_USER") or "restai"
MYSQL_DB = os.environ.get("MYSQL_DB") or "restai"

MYSQL_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "restai")

POSTGRES_URL = (
    "postgresql+psycopg2://"
    f"{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
)

RESTAI_DEFAULT_PASSWORD = os.environ.get("RESTAI_DEFAULT_PASSWORD") or "admin"
RESTAI_DEMO = True if os.environ.get("RESTAI_DEMO", "").lower() in ('true', '1') else False

SQLITE_PATH = os.environ.get("SQLITE_PATH")


REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PORT = os.environ.get("REDIS_PORT")

CHROMADB_HOST = os.environ.get("CHROMADB_HOST")
CHROMADB_PORT = os.environ.get("CHROMADB_PORT")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")

RESTAI_SSO_SECRET = os.environ.get("RESTAI_SSO_SECRET")
RESTAI_SSO_ALG = os.environ.get("RESTAI_SSO_ALG") or "HS512"
RESTAI_SSO_CALLBACK = os.environ.get("RESTAI_SSO_CALLBACK")

RESTAI_GPU = True if os.environ.get("RESTAI_GPU", "").lower() in ('true', '1') else False
RESTAI_DEFAULT_DEVICE = os.environ.get("RESTAI_DEFAULT_DEVICE")

EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH")

# Database connection pool settings
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE") or 100)
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW") or 300)
DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE") or 300)

AGENT_MAX_ITERATIONS = int(os.environ.get("AGENT_MAX_ITERATIONS") or 20)

ENABLE_LDAP = os.environ.get("ENABLE_LDAP")
LDAP_SERVER_HOST = os.environ.get("LDAP_SERVER_HOST")
LDAP_SERVER_PORT = os.environ.get("LDAP_SERVER_PORT")
LDAP_ATTRIBUTE_FOR_MAIL = os.environ.get("LDAP_ATTRIBUTE_FOR_MAIL")
LDAP_ATTRIBUTE_FOR_USERNAME = os.environ.get("LDAP_ATTRIBUTE_FOR_USERNAME")
LDAP_SEARCH_BASE = os.environ.get("LDAP_SEARCH_BASE")
LDAP_SEARCH_FILTERS = os.environ.get("LDAP_SEARCH_FILTERS")
LDAP_APP_DN = os.environ.get("LDAP_APP_DN")
LDAP_APP_PASSWORD = os.environ.get("LDAP_APP_PASSWORD")
LDAP_USE_TLS = os.environ.get("LDAP_USE_TLS")
LDAP_CA_CERT_FILE = os.environ.get("LDAP_CA_CERT_FILE")
LDAP_CIPHERS = os.environ.get("LDAP_CIPHERS")

PROXY_URL = os.environ.get("PROXY_URL")
PROXY_KEY = os.environ.get("PROXY_KEY")
PROXY_TEAM_ID = os.environ.get("PROXY_TEAM_ID")