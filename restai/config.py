import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def load_env_vars():
    if "EMBEDDINGS_PATH" not in os.environ:
        os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

    if "ANONYMIZED_TELEMETRY" not in os.environ:
        os.environ["ANONYMIZED_TELEMETRY"] = "True"

    if "LOG_LEVEL" not in os.environ:
        os.environ["LOG_LEVEL"] = "INFO"

    if "DEEPEVAL_UPDATE_WARNING_OPT_OUT" not in os.environ:
        os.environ["DEEPEVAL_UPDATE_WARNING_OPT_OUT"] = "YES"

    os.environ["ALLOW_RESET"] = "true"


load_env_vars()

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

def _ensure_env_secret(var_name, generator=None):
    if not os.environ.get(var_name):
        secret = generator() if generator else secrets.token_urlsafe(64)
        os.environ[var_name] = secret
        try:
            with open(env_path, "a") as f:
                f.write(f"\n{var_name}=\"{secret}\"\n")
                print(f"New random {var_name} written to {env_path}")
        except Exception as e:
            print(f"Warning: Could not write {var_name} to .env: {e}")

_ensure_env_secret("RESTAI_AUTH_SECRET")
_ensure_env_secret("SSO_SECRET_KEY")

def _generate_fernet_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()

_ensure_env_secret("RESTAI_FERNET_KEY", generator=_generate_fernet_key)

RESTAI_FERNET_KEY = os.environ.get("RESTAI_FERNET_KEY")

RESTAI_NAME = os.environ.get("RESTAI_NAME") or "RESTai"

RESTAI_URL = os.environ.get("RESTAI_URL")

RESTAI_PORT = os.environ.get("RESTAI_PORT") or 9000
RESTAI_AUTH_SECRET = os.environ.get("RESTAI_AUTH_SECRET")
RESTAI_AUTH_DISABLE_LOCAL = os.environ.get("RESTAI_AUTH_DISABLE_LOCAL", "").lower() in ("true", "1")
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

SQL_URL = POSTGRES_URL if POSTGRES_HOST else (MYSQL_URL if MYSQL_HOST else None)

RESTAI_DEFAULT_PASSWORD = os.environ.get("RESTAI_DEFAULT_PASSWORD") or "admin"



SQLITE_PATH = os.environ.get("SQLITE_PATH")


HF_TOKEN = os.environ.get("HF_TOKEN")


REDIS_HOST = os.environ.get("REDIS_HOST")
REDIS_PORT = os.environ.get("REDIS_PORT")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REDIS_DATABASE = os.environ.get("REDIS_DATABASE")


def build_redis_url():
    """Construct a redis:// URL from the live REDIS_* config attrs.

    Returns None when REDIS_HOST is unset. Reads the module attributes at call
    time so the admin Settings GUI can update them in-process and the next
    caller picks up the new value.
    """
    if not REDIS_HOST:
        return None
    auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    db = (
        f"/{REDIS_DATABASE}"
        if REDIS_DATABASE and REDIS_DATABASE != "0"
        else ""
    )
    port = REDIS_PORT or "6379"
    return f"redis://{auth}{REDIS_HOST}:{port}{db}"

CHROMADB_HOST = os.environ.get("CHROMADB_HOST")
CHROMADB_PORT = os.environ.get("CHROMADB_PORT")

PGVECTOR_HOST = os.environ.get("PGVECTOR_HOST") or POSTGRES_HOST
PGVECTOR_PORT = os.environ.get("PGVECTOR_PORT") or os.environ.get("POSTGRES_PORT", "5432")
PGVECTOR_USER = os.environ.get("PGVECTOR_USER") or POSTGRES_USER
PGVECTOR_PASSWORD = os.environ.get("PGVECTOR_PASSWORD") or POSTGRES_PASSWORD
PGVECTOR_DB = os.environ.get("PGVECTOR_DB", "restai_vectors")

WEAVIATE_HOST = os.environ.get("WEAVIATE_HOST")
WEAVIATE_PORT = os.environ.get("WEAVIATE_PORT", "8080")
WEAVIATE_GRPC_PORT = os.environ.get("WEAVIATE_GRPC_PORT", "50051")
WEAVIATE_API_KEY = os.environ.get("WEAVIATE_API_KEY")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX")

def detect_gpu():
    """Auto-detect GPU availability via nvidia-smi."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_gpu_info():
    """Query detailed GPU information via nvidia-smi.

    Returns a list of dicts with keys: index, name, brand, driver_version,
    memory_total, memory_used, memory_free, temperature, utilization,
    power_draw, power_limit, cuda_version, pci_bus_id.
    Returns an empty list if nvidia-smi is unavailable.
    """
    import subprocess

    # First get CUDA version from nvidia-smi header
    cuda_version = ""
    try:
        header = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=5,
        )
        if header.returncode == 0:
            for line in header.stdout.splitlines():
                if "CUDA Version" in line:
                    parts = line.split("CUDA Version:")
                    if len(parts) > 1:
                        cuda_version = parts[1].strip().rstrip("|").strip()
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    fields = [
        "index", "name", "driver_version",
        "memory.total", "memory.used", "memory.free",
        "temperature.gpu", "utilization.gpu", "power.draw", "power.limit",
        "pci.bus_id",
    ]
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    gpus = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(fields):
            continue
        gpu = {
            "index": int(parts[0]),
            "name": parts[1],
            "driver_version": parts[2],
            "memory_total": f"{parts[3]} MiB",
            "memory_used": f"{parts[4]} MiB",
            "memory_free": f"{parts[5]} MiB",
            "temperature": f"{parts[6]} °C" if parts[6] not in ("[N/A]", "") else "N/A",
            "utilization": f"{parts[7]} %" if parts[7] not in ("[N/A]", "") else "N/A",
            "power_draw": f"{parts[8]} W" if parts[8] not in ("[N/A]", "") else "N/A",
            "power_limit": f"{parts[9]} W" if parts[9] not in ("[N/A]", "") else "N/A",
            "pci_bus_id": parts[10],
            "cuda_version": cuda_version,
        }
        gpus.append(gpu)
    return gpus

_gpu_env = os.environ.get("RESTAI_GPU", "").lower()
if _gpu_env in ("true", "1"):
    RESTAI_GPU = True
elif _gpu_env in ("false", "0"):
    RESTAI_GPU = False
else:
    RESTAI_GPU = detect_gpu()
RESTAI_DEFAULT_DEVICE = os.environ.get("RESTAI_DEFAULT_DEVICE")
GPU_WORKER_DEVICES = os.environ.get("GPU_WORKER_DEVICES", "")

RESTAI_MCP = os.environ.get("MCP_SERVER", "").lower() in ("true", "1")

DOCKER_ENABLED = False
SYSTEM_LLM = os.environ.get("SYSTEM_LLM", "")

DOCKER_URL = os.environ.get("DOCKER_URL", "")
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "python:3.12-slim")
DOCKER_TIMEOUT = int(os.environ.get("DOCKER_TIMEOUT", "900"))
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "none")

DATA_RETENTION_DAYS = 0

EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH")

# Database connection pool settings
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE") or 100)
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW") or 300)
DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE") or 300)


MAX_AUDIO_UPLOAD_SIZE = int(os.environ.get("MAX_AUDIO_UPLOAD_SIZE") or 10)

MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE_MB") or 100) * 1024 * 1024  # Default 100MB

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

HIDE_BRANDING = os.environ.get("RESTAI_HIDE", "").lower() in ("true", "1")

CURRENCY = os.environ.get("CURRENCY", "EUR")

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
AUTO_CREATE_USER = os.environ.get("AUTO_CREATE_USER", "False").lower() == "true"
SSO_AUTO_RESTRICTED = True
SSO_AUTO_TEAM_ID = None
SESSION_COOKIE_SAME_SITE = os.environ.get("SESSION_COOKIE_SAME_SITE", "lax")
SESSION_COOKIE_SECURE = (
    os.environ.get("SESSION_COOKIE_SECURE", "false" if RESTAI_DEV else "true").lower() == "true"
)
SSO_SECRET_KEY = os.environ.get("SSO_SECRET_KEY", os.environ.get("SECRET_KEY"))


def load_oauth_providers():
    """Build OAUTH_PROVIDERS from current module-level attributes."""
    # Import ourselves so we always read the latest attribute values
    import restai.config as _cfg

    OAUTH_PROVIDERS.clear()
    if _cfg.GOOGLE_CLIENT_ID and _cfg.GOOGLE_CLIENT_SECRET:

        def google_oauth_register(client, _c=_cfg):
            client.register(
                name="google",
                client_id=_c.GOOGLE_CLIENT_ID,
                client_secret=_c.GOOGLE_CLIENT_SECRET,
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": _c.GOOGLE_OAUTH_SCOPE},
                redirect_uri=_c.GOOGLE_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["google"] = {
            "redirect_uri": _cfg.GOOGLE_REDIRECT_URI,
            "register": google_oauth_register,
        }

    if _cfg.MICROSOFT_CLIENT_ID and _cfg.MICROSOFT_CLIENT_SECRET and _cfg.MICROSOFT_CLIENT_TENANT_ID:

        def microsoft_oauth_register(client, _c=_cfg):
            client.register(
                name="microsoft",
                client_id=_c.MICROSOFT_CLIENT_ID,
                client_secret=_c.MICROSOFT_CLIENT_SECRET,
                server_metadata_url=f"https://login.microsoftonline.com/{_c.MICROSOFT_CLIENT_TENANT_ID}/v2.0/.well-known/openid-configuration",
                client_kwargs={
                    "scope": _c.MICROSOFT_OAUTH_SCOPE,
                },
                redirect_uri=_c.MICROSOFT_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["microsoft"] = {
            "redirect_uri": _cfg.MICROSOFT_REDIRECT_URI,
            "picture_url": "https://graph.microsoft.com/v1.0/me/photo/$value",
            "register": microsoft_oauth_register,
        }

    if _cfg.GITHUB_CLIENT_ID and _cfg.GITHUB_CLIENT_SECRET:

        def github_oauth_register(client, _c=_cfg):
            client.register(
                name="github",
                client_id=_c.GITHUB_CLIENT_ID,
                client_secret=_c.GITHUB_CLIENT_SECRET,
                access_token_url="https://github.com/login/oauth/access_token",
                authorize_url="https://github.com/login/oauth/authorize",
                api_base_url="https://api.github.com",
                userinfo_endpoint="https://api.github.com/user",
                client_kwargs={"scope": _c.GITHUB_CLIENT_SCOPE},
                redirect_uri=_c.GITHUB_CLIENT_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["github"] = {
            "redirect_uri": _cfg.GITHUB_CLIENT_REDIRECT_URI,
            "register": github_oauth_register,
            "sub_claim": "id",
        }

    if _cfg.OAUTH_CLIENT_ID and _cfg.OAUTH_CLIENT_SECRET and _cfg.OPENID_PROVIDER_URL:

        def oidc_oauth_register(client, _c=_cfg):
            client.register(
                name="oidc",
                client_id=_c.OAUTH_CLIENT_ID,
                client_secret=_c.OAUTH_CLIENT_SECRET,
                server_metadata_url=_c.OPENID_PROVIDER_URL,
                client_kwargs={
                    "scope": _c.OAUTH_SCOPES,
                },
                redirect_uri=_c.OPENID_REDIRECT_URI,
            )

        OAUTH_PROVIDERS["oidc"] = {
            "name": _cfg.OAUTH_PROVIDER_NAME,
            "redirect_uri": _cfg.OPENID_REDIRECT_URI,
            "register": oidc_oauth_register,
        }


load_oauth_providers()
