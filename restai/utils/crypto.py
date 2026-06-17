import hashlib
import hmac
import json as _json
import os
import secrets
import string

from cryptography.fernet import Fernet, InvalidToken

from restai import config

FERNET_KEY = config.RESTAI_FERNET_KEY
if not FERNET_KEY:
    raise RuntimeError("RESTAI_FERNET_KEY environment variable not set.")

fernet = Fernet(FERNET_KEY)

def encrypt_api_key(api_key: str) -> str:
    return fernet.encrypt(api_key.encode()).decode()

def decrypt_api_key(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Invalid API key token or decryption failed.")


# PBKDF2-prefixed hashes; legacy bare SHA256 hashes still accepted for lookups.
_PBKDF2_PREFIX = "$pbkdf2$"
_PBKDF2_ITERATIONS = 100_000


def hash_api_key(plaintext: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, _PBKDF2_ITERATIONS)
    return _PBKDF2_PREFIX + salt.hex() + "$" + dk.hex()


def verify_api_key_hash(plaintext: str, stored_hash: str) -> bool:
    """Accepts PBKDF2 or legacy SHA256."""
    if stored_hash.startswith(_PBKDF2_PREFIX):
        rest = stored_hash[len(_PBKDF2_PREFIX):]
        parts = rest.split("$", 1)
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected = bytes.fromhex(parts[1])
        dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, _PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk, expected)
    return hmac.compare_digest(hashlib.sha256(plaintext.encode()).hexdigest(), stored_hash)


def encrypt_totp_secret(secret: str) -> str:
    return fernet.encrypt(secret.encode()).decode()

def decrypt_totp_secret(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Invalid TOTP secret token or decryption failed.")

def generate_recovery_codes(count: int = 8) -> list[str]:
    alphabet = string.ascii_lowercase + string.digits
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(count)]

def hash_recovery_code(code: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", code.strip().lower().encode(), salt, _PBKDF2_ITERATIONS)
    return _PBKDF2_PREFIX + salt.hex() + "$" + dk.hex()

def verify_recovery_code(code: str, stored_hash: str) -> bool:
    """Accepts PBKDF2 or legacy SHA256."""
    if stored_hash.startswith(_PBKDF2_PREFIX):
        rest = stored_hash[len(_PBKDF2_PREFIX):]
        parts = rest.split("$", 1)
        if len(parts) != 2:
            return False
        salt = bytes.fromhex(parts[0])
        expected = bytes.fromhex(parts[1])
        dk = hashlib.pbkdf2_hmac("sha256", code.strip().lower().encode(), salt, _PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk, expected)
    return hmac.compare_digest(hashlib.sha256(code.strip().lower().encode()).hexdigest(), stored_hash)


_ENC_PREFIX = "$ENC$"


def encrypt_field(value: str) -> str:
    """No-op if already encrypted or empty."""
    if not value or value.startswith(_ENC_PREFIX):
        return value
    return _ENC_PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    """No-op if not encrypted (backward-compatible with legacy plaintext)."""
    if not value or not value.startswith(_ENC_PREFIX):
        return value
    try:
        return fernet.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        return value


PROJECT_SENSITIVE_KEYS = {
    "telegram_token", "slack_bot_token", "connection",
    "whatsapp_access_token", "whatsapp_app_secret", "whatsapp_verify_token",
    "twilio_auth_token", "webhook_secret",
    "ftp_password",
}
LLM_SENSITIVE_KEYS = {"api_key", "key", "password", "secret"}

TEAM_SENSITIVE_KEYS = {"smtp_password"}

# Per-source secret fields in sync_sources[]; separate from top-level PROJECT_SENSITIVE_KEYS.
# Used by strip_sensitive_project_options and the masking in routers/projects.py:route_edit_project.
_SYNC_SOURCE_SECRET_KEYS = (
    "s3_access_key",
    "s3_secret_key",
    "confluence_api_token",
    "sharepoint_client_secret",
    "gdrive_service_account_json",
)


def strip_sensitive_project_options(options_blob):
    """Drop credential-bearing fields. Used by template publish/instantiate.

    Accepts a JSON string OR dict; returns the same shape."""
    if not options_blob:
        return options_blob

    if isinstance(options_blob, str):
        try:
            opts = _json.loads(options_blob)
        except Exception:
            # Unparseable — safer to wipe than ship potentially-credential bytes.
            return "{}"
        was_str = True
    elif isinstance(options_blob, dict):
        opts = dict(options_blob)
        was_str = False
    else:
        return options_blob

    if not isinstance(opts, dict):
        return options_blob

    for k in PROJECT_SENSITIVE_KEYS:
        opts.pop(k, None)

    sync_sources = opts.get("sync_sources")
    if isinstance(sync_sources, list):
        for src in sync_sources:
            if isinstance(src, dict):
                for k in _SYNC_SOURCE_SECRET_KEYS:
                    src.pop(k, None)

    mcp_servers = opts.get("mcp_servers")
    if isinstance(mcp_servers, list):
        for srv in mcp_servers:
            if isinstance(srv, dict):
                # env/headers can carry bearer tokens / OAuth refresh — instantiator must reconfigure.
                srv.pop("env", None)
                srv.pop("headers", None)

    return _json.dumps(opts) if was_str else opts


SETTINGS_ENCRYPTED_KEYS = {
    "proxy_key",
    "redis_password",
    "sso_google_client_secret",
    "sso_microsoft_client_secret",
    "sso_github_client_secret",
    "sso_oidc_client_secret",
    "vectordb_pgvector_password",
    "vectordb_weaviate_api_key",
    "vectordb_pinecone_api_key",
    "ldap_app_password",
    "smtp_password",
    "payment_stripe_secret_key",
    "payment_stripe_webhook_secret",
    "payment_paypal_client_secret",
}

SYNC_SOURCE_SENSITIVE_KEYS = {
    "s3_secret_key", "confluence_api_token",
    "sharepoint_client_secret", "gdrive_service_account_json",
}


def encrypt_sensitive_options(opts: dict, sensitive_keys: set) -> dict:
    result = dict(opts)
    for key in sensitive_keys:
        val = result.get(key)
        if val and isinstance(val, str):
            result[key] = encrypt_field(val)
    if "sync_sources" in result and isinstance(result["sync_sources"], list):
        result["sync_sources"] = [
            _encrypt_sync_source(s) for s in result["sync_sources"]
        ]
    return result


def decrypt_sensitive_options(opts: dict, sensitive_keys: set) -> dict:
    result = dict(opts)
    for key in sensitive_keys:
        val = result.get(key)
        if val and isinstance(val, str):
            result[key] = decrypt_field(val)
    if "sync_sources" in result and isinstance(result["sync_sources"], list):
        result["sync_sources"] = [
            _decrypt_sync_source(s) for s in result["sync_sources"]
        ]
    return result


def _encrypt_sync_source(src) -> dict:
    if isinstance(src, dict):
        s = dict(src)
    elif hasattr(src, "model_dump"):
        s = src.model_dump()
    else:
        return src
    for key in SYNC_SOURCE_SENSITIVE_KEYS:
        val = s.get(key)
        if val and isinstance(val, str):
            s[key] = encrypt_field(val)
    return s


def _decrypt_sync_source(src) -> dict:
    s = dict(src) if isinstance(src, dict) else src
    if not isinstance(s, dict):
        return s
    for key in SYNC_SOURCE_SENSITIVE_KEYS:
        val = s.get(key)
        if val and isinstance(val, str):
            s[key] = decrypt_field(val)
    return s
