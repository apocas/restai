import hashlib
import secrets
import string

from cryptography.fernet import Fernet, InvalidToken

from restai import config

# Load encryption key from dedicated Fernet environment variable
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

def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


# TOTP helpers
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
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


# ─── Field-level encryption for sensitive options ───
_ENC_PREFIX = "$ENC$"


def encrypt_field(value: str) -> str:
    """Encrypt a single string value. Returns prefixed ciphertext.
    No-op if already encrypted or empty."""
    if not value or value.startswith(_ENC_PREFIX):
        return value
    return _ENC_PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    """Decrypt a single prefixed ciphertext. Returns plaintext.
    No-op if not encrypted (backward-compatible with legacy plaintext)."""
    if not value or not value.startswith(_ENC_PREFIX):
        return value
    try:
        return fernet.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        return value


# Keys to encrypt in project options and LLM options
PROJECT_SENSITIVE_KEYS = {
    "telegram_token", "slack_bot_token", "slack_app_token", "connection",
}
LLM_SENSITIVE_KEYS = {"api_key", "key", "password", "secret"}

# Keys inside sync_sources that should be encrypted
SYNC_SOURCE_SENSITIVE_KEYS = {
    "s3_secret_key", "confluence_api_token",
    "sharepoint_client_secret", "gdrive_service_account_json",
}


def encrypt_sensitive_options(opts: dict, sensitive_keys: set) -> dict:
    """Encrypt marked fields in a dict. Returns a new dict."""
    result = dict(opts)
    for key in sensitive_keys:
        val = result.get(key)
        if val and isinstance(val, str):
            result[key] = encrypt_field(val)
    # Handle nested sync_sources
    if "sync_sources" in result and isinstance(result["sync_sources"], list):
        result["sync_sources"] = [
            _encrypt_sync_source(s) for s in result["sync_sources"]
        ]
    return result


def decrypt_sensitive_options(opts: dict, sensitive_keys: set) -> dict:
    """Decrypt marked fields in a dict. Returns a new dict."""
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
