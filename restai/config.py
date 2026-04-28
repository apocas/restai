"""Process-wide configuration.

Two kinds of config live here:

1. **Boot-only env vars** (POSTGRES_HOST, RESTAI_FERNET_KEY, RESTAI_DEV, etc.)
   are bound as module-level attributes from `os.environ` at import time.
   These are needed before the DB is reachable, so they have to be env-var-only.

2. **GUI-managed settings** (DOCKER_*, BROWSER_*, PROXY_*, REDIS_*, OAuth, GPU,
   MCP, system LLM, retention, 2FA, branding, etc.) live in the `settings` DB
   table. They are NOT bound as module attributes. Instead, `__getattr__` at
   the bottom of this file reads them from the DB on every access.

   This is the only multi-worker-safe approach. Earlier versions mirrored the
   DB onto module-level attributes via `setattr(config, ...)` after each
   PATCH /settings; that mutation only landed in the worker that handled the
   request, so other workers acted on stale (or missing) values. Read-through
   on every access is a few hundred microseconds at most against the
   connection pool — cheap compared to the bug it prevents.

   Env-var support for GUI keys was dropped at the same time. Admins set these
   in the platform Settings page; existing deployments already have the
   env-var-derived values in their DB from earlier seeding.
"""
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

# ---- Boot-only env vars (cannot live in the DB; needed before DB is up) ----

RESTAI_FERNET_KEY = os.environ.get("RESTAI_FERNET_KEY")

RESTAI_URL = os.environ.get("RESTAI_URL")

RESTAI_PORT = os.environ.get("RESTAI_PORT") or 9000
RESTAI_AUTH_SECRET = os.environ.get("RESTAI_AUTH_SECRET")
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


def build_redis_url():
    """Construct a redis:// URL from the live REDIS_* settings.

    Returns None when REDIS_HOST is unset. Goes through `_cfg.X` attribute
    access so this module's `__getattr__` resolves each value from the DB on
    every call — admin Settings changes are picked up immediately by every
    worker without any process-local mirror. (Bare-name lookups like
    `REDIS_HOST` would NOT trigger `__getattr__` — Python looks bare names up
    in module globals, not via descriptor.)
    """
    import restai.config as _cfg
    host = _cfg.REDIS_HOST
    if not host:
        return None
    pwd = _cfg.REDIS_PASSWORD
    port = _cfg.REDIS_PORT or "6379"
    raw_db = _cfg.REDIS_DATABASE
    auth = f":{pwd}@" if pwd else ""
    db = f"/{raw_db}" if raw_db and raw_db != "0" else ""
    return f"redis://{auth}{host}:{port}{db}"

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

RESTAI_DEFAULT_DEVICE = os.environ.get("RESTAI_DEFAULT_DEVICE")

EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH")

# Database connection pool settings
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE") or 5)
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW") or 0)
DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE") or 300)


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

OAUTH_PROVIDERS = {}

SESSION_COOKIE_SAME_SITE = os.environ.get("SESSION_COOKIE_SAME_SITE", "lax")
SESSION_COOKIE_SECURE = (
    os.environ.get("SESSION_COOKIE_SECURE", "false" if RESTAI_DEV else "true").lower() == "true"
)
SSO_SECRET_KEY = os.environ.get("SSO_SECRET_KEY", os.environ.get("SECRET_KEY"))


# ---------------------------------------------------------------------------
# GUI-managed settings — DB-backed, read on every access via __getattr__
# ---------------------------------------------------------------------------
#
# Mapping shape: <module attr name> -> (db_key, type_, default).
# type_ is one of: str, bool, int, "csv-list".
# Setting `default=None` on RESTAI_GPU is a sentinel meaning "auto-detect".
#
_GUI_SETTING_ATTRS = {
    "RESTAI_NAME": ("app_name", str, "RESTai"),
    "HIDE_BRANDING": ("hide_branding", bool, False),
    "RESTAI_AUTH_DISABLE_LOCAL": ("auth_disable_local", bool, False),
    "PROXY_URL": ("proxy_url", str, None),
    "PROXY_KEY": ("proxy_key", str, None),
    "PROXY_TEAM_ID": ("proxy_team_id", str, None),
    "MAX_AUDIO_UPLOAD_SIZE": ("max_audio_upload_size", int, 10),
    "CURRENCY": ("currency", str, "EUR"),
    "REDIS_HOST": ("redis_host", str, None),
    "REDIS_PORT": ("redis_port", str, None),
    "REDIS_PASSWORD": ("redis_password", str, None),
    "REDIS_DATABASE": ("redis_database", str, None),
    "AUTO_CREATE_USER": ("sso_auto_create_user", bool, False),
    "OAUTH_ALLOWED_DOMAINS": ("sso_allowed_domains", "csv-list", ["*"]),
    "SSO_AUTO_RESTRICTED": ("sso_auto_restricted", bool, True),
    "SSO_AUTO_TEAM_ID": ("sso_auto_team_id", str, None),
    "GOOGLE_CLIENT_ID": ("sso_google_client_id", str, ""),
    "GOOGLE_CLIENT_SECRET": ("sso_google_client_secret", str, ""),
    "GOOGLE_REDIRECT_URI": ("sso_google_redirect_uri", str, ""),
    "GOOGLE_OAUTH_SCOPE": ("sso_google_scope", str, "openid email profile"),
    "MICROSOFT_CLIENT_ID": ("sso_microsoft_client_id", str, ""),
    "MICROSOFT_CLIENT_SECRET": ("sso_microsoft_client_secret", str, ""),
    "MICROSOFT_CLIENT_TENANT_ID": ("sso_microsoft_tenant_id", str, ""),
    "MICROSOFT_REDIRECT_URI": ("sso_microsoft_redirect_uri", str, ""),
    "MICROSOFT_OAUTH_SCOPE": ("sso_microsoft_scope", str, "openid email profile"),
    "GITHUB_CLIENT_ID": ("sso_github_client_id", str, ""),
    "GITHUB_CLIENT_SECRET": ("sso_github_client_secret", str, ""),
    "GITHUB_CLIENT_REDIRECT_URI": ("sso_github_redirect_uri", str, ""),
    "GITHUB_CLIENT_SCOPE": ("sso_github_scope", str, "user:email"),
    "OAUTH_CLIENT_ID": ("sso_oidc_client_id", str, ""),
    "OAUTH_CLIENT_SECRET": ("sso_oidc_client_secret", str, ""),
    "OPENID_PROVIDER_URL": ("sso_oidc_provider_url", str, ""),
    "OPENID_REDIRECT_URI": ("sso_oidc_redirect_uri", str, ""),
    "OAUTH_SCOPES": ("sso_oidc_scopes", str, "openid email profile"),
    "OAUTH_PROVIDER_NAME": ("sso_oidc_provider_name", str, "SSO"),
    "OAUTH_EMAIL_CLAIM": ("sso_oidc_email_claim", str, "email"),
    "RESTAI_GPU": ("gpu_enabled", bool, None),  # None sentinel => auto-detect
    "GPU_WORKER_DEVICES": ("gpu_worker_devices", str, ""),
    "RESTAI_MCP": ("mcp_enabled", bool, False),
    "SYSTEM_LLM": ("system_llm", str, ""),
    "DOCKER_ENABLED": ("docker_enabled", bool, False),
    "DOCKER_URL": ("docker_url", str, ""),
    "DOCKER_IMAGE": ("docker_image", str, "python:3.12-slim"),
    "DOCKER_TIMEOUT": ("docker_timeout", int, 900),
    "DOCKER_NETWORK": ("docker_network", str, "none"),
    "DOCKER_READ_ONLY": ("docker_read_only", bool, True),
    "BROWSER_ENABLED": ("browser_enabled", bool, False),
    "BROWSER_IMAGE": ("browser_image", str, "mcr.microsoft.com/playwright/python:v1.48.0-jammy"),
    "BROWSER_NETWORK": ("browser_network", str, "bridge"),
    "BROWSER_TIMEOUT": ("browser_timeout", int, 900),
    "DATA_RETENTION_DAYS": ("data_retention_days", int, 0),
    "ENFORCE_2FA": ("enforce_2fa", bool, False),
}


def _coerce_setting(raw: str, type_, default):
    if not raw:
        return default
    if type_ is bool:
        return raw.lower() in ("true", "1", "yes")
    if type_ is int:
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default
    if type_ == "csv-list":
        parts = [s.strip() for s in raw.split(",") if s.strip()]
        return parts or default
    return raw


def __getattr__(name):
    """Read GUI-managed settings from the DB on demand.

    Module-level __getattr__ fires only when an attribute is NOT defined on the
    module. Boot-only env vars are bound at import time above and don't go
    through here. Anything in `_GUI_SETTING_ATTRS` is resolved per-access from
    the `settings` table, so multi-worker uvicorn deployments see the live
    value without any in-process mirroring.

    DB failures (e.g. very early bootstrap before the schema exists) fall back
    to the declared default; for RESTAI_GPU the fallback is `detect_gpu()`.
    """
    spec = _GUI_SETTING_ATTRS.get(name)
    if spec is None:
        raise AttributeError(f"module 'restai.config' has no attribute {name!r}")
    db_key, type_, default = spec

    try:
        from restai.database import DBWrapper
        wrapper = DBWrapper()
        try:
            raw = wrapper.get_setting_value(db_key, "")
        finally:
            wrapper.db.close()
    except Exception:
        raw = ""

    if name == "RESTAI_GPU" and default is None and not raw:
        return detect_gpu()

    return _coerce_setting(raw, type_, default)


def load_oauth_providers():
    """Build OAUTH_PROVIDERS from current GUI-managed OAuth settings.

    Each provider's register callback closes over the values *at call time of
    the callback*, not at registration, so authlib gets the current DB values
    when it actually invokes them. Called once at startup and again from
    `reinit_oauth(app)` after a settings PATCH.
    """
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


# Note: load_oauth_providers() is NOT called at import time anymore — the DB
# may not be reachable yet during early bootstrap. main.py's lifespan calls it
# after seed_defaults runs, and routers/settings.py:patch_settings calls it
# again whenever an OAuth setting changes.
