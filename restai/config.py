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

RESTAI_NAME = os.environ.get("RESTAI_NAME") or "RESTai"

RESTAI_PORT = os.environ.get("RESTAI_PORT") or 9000
RESTAI_AUTH_SECRET = os.environ.get("RESTAI_AUTH_SECRET")
RESTAI_AUTH_DISABLE_LOCAL = os.environ.get("RESTAI_AUTH_DISABLE_LOCAL")
RESTAI_DEV = (
    True if os.environ.get("RESTAI_DEV", "").lower() in ("true", "1") else False
)

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
RESTAI_DEMO = (
    True if os.environ.get("RESTAI_DEMO", "").lower() in ("true", "1") else False
)

SQLITE_PATH = os.environ.get("SQLITE_PATH")


REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PORT = os.environ.get("REDIS_PORT")

CHROMADB_HOST = os.environ.get("CHROMADB_HOST")
CHROMADB_PORT = os.environ.get("CHROMADB_PORT")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")

RESTAI_GPU = (
    True if os.environ.get("RESTAI_GPU", "").lower() in ("true", "1") else False
)
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


OAUTH_PROVIDERS = {}
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_SCOPE = os.environ.get("GOOGLE_OAUTH_SCOPE", "openid email profile")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_CLIENT_TENANT_ID = os.environ.get("MICROSOFT_CLIENT_TENANT_ID", "")
MICROSOFT_OAUTH_SCOPE = os.environ.get("MICROSOFT_OAUTH_SCOPE", "openid email profile")
MICROSOFT_REDIRECT_URI = os.environ.get("MICROSOFT_REDIRECT_URI", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
GITHUB_CLIENT_SCOPE = os.environ.get("GITHUB_CLIENT_SCOPE", "user:email")
GITHUB_CLIENT_REDIRECT_URI = os.environ.get("GITHUB_CLIENT_REDIRECT_URI", "")
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "")
OPENID_PROVIDER_URL = os.environ.get("OPENID_PROVIDER_URL", "")
OPENID_REDIRECT_URI = os.environ.get("OPENID_REDIRECT_URI", "")
OAUTH_SCOPES = os.environ.get("OAUTH_SCOPES", "openid email profile")
OAUTH_PROVIDER_NAME = os.environ.get("OAUTH_PROVIDER_NAME", "SSO")
OAUTH_EMAIL_CLAIM = os.environ.get("OAUTH_EMAIL_CLAIM", "email")
OAUTH_ALLOWED_DOMAINS = [
    domain.strip() for domain in os.environ.get("OAUTH_ALLOWED_DOMAINS", "*").split(",")
]
AUTO_CREATE_USER = (
    os.environ.get("AUTO_CREATE_USER", "False").lower() == "true"
)
SESSION_COOKIE_SAME_SITE = os.environ.get("SESSION_COOKIE_SAME_SITE", "lax")
SESSION_COOKIE_SECURE = (
    os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
)
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    os.environ.get(
        "JWT_SECRET_KEY", "t0p-s3cr3t"
    ),
)

def load_oauth_providers():
    OAUTH_PROVIDERS.clear()
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:

        def google_oauth_register(client):
            client.register(
                name="google",
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": GOOGLE_OAUTH_SCOPE},
                redirect_uri=GOOGLE_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["google"] = {
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "register": google_oauth_register,
        }

    if (
        MICROSOFT_CLIENT_ID
        and MICROSOFT_CLIENT_SECRET
        and MICROSOFT_CLIENT_TENANT_ID
    ):

        def microsoft_oauth_register(client):
            client.register(
                name="microsoft",
                client_id=MICROSOFT_CLIENT_ID,
                client_secret=MICROSOFT_CLIENT_SECRET,
                server_metadata_url=f"https://login.microsoftonline.com/{MICROSOFT_CLIENT_TENANT_ID}/v2.0/.well-known/openid-configuration",
                client_kwargs={
                    "scope": MICROSOFT_OAUTH_SCOPE,
                },
                redirect_uri=MICROSOFT_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["microsoft"] = {
            "redirect_uri": MICROSOFT_REDIRECT_URI,
            "picture_url": "https://graph.microsoft.com/v1.0/me/photo/$value",
            "register": microsoft_oauth_register,
        }

    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:

        def github_oauth_register(client):
            client.register(
                name="github",
                client_id=GITHUB_CLIENT_ID,
                client_secret=GITHUB_CLIENT_SECRET,
                access_token_url="https://github.com/login/oauth/access_token",
                authorize_url="https://github.com/login/oauth/authorize",
                api_base_url="https://api.github.com",
                userinfo_endpoint="https://api.github.com/user",
                client_kwargs={"scope": GITHUB_CLIENT_SCOPE},
                redirect_uri=GITHUB_CLIENT_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["github"] = {
            "redirect_uri": GITHUB_CLIENT_REDIRECT_URI,
            "register": github_oauth_register,
            "sub_claim": "id",
        }

    if (
        OAUTH_CLIENT_ID
        and OAUTH_CLIENT_SECRET
        and OPENID_PROVIDER_URL
    ):

        def oidc_oauth_register(client):
            client.register(
                name="oidc",
                client_id=OAUTH_CLIENT_ID,
                client_secret=OAUTH_CLIENT_SECRET,
                server_metadata_url=OPENID_PROVIDER_URL,
                client_kwargs={
                    "scope": OAUTH_SCOPES,
                },
                redirect_uri=OPENID_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["oidc"] = {
            "name": OAUTH_PROVIDER_NAME,
            "redirect_uri": OPENID_REDIRECT_URI,
            "register": oidc_oauth_register,
        }


load_oauth_providers()
