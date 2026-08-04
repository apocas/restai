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
}
LLM_SENSITIVE_KEYS = {"api_key", "key", "password", "secret"}

# The exact-name set above misses provider-specific credential fields — most
# visibly Bedrock's `aws_access_key_id` / `aws_secret_access_key`, which were
# therefore neither encrypted at rest nor masked in API responses. Rather than
# chase every provider's naming, treat any option whose NAME looks like a
# credential as one.
#
# Two deliberate constraints keep this from over-matching:
#   * bare "token" is NOT a pattern — it would swallow `max_tokens`.
#   * only STRING values are ever matched, so a numeric option can never be
#     replaced by the mask sentinel or fed to the encryptor.
_SENSITIVE_NAME_PATTERNS = (
    "api_key", "apikey", "access_key", "secret", "password", "passwd",
    "credential", "auth_token", "access_token", "refresh_token", "private_key",
)


def sensitive_option_names(opts: dict, base_keys: set) -> set:
    """`base_keys` plus every string-valued option whose name looks secret."""
    names = set(base_keys)
    if not isinstance(opts, dict):
        return names
    for k, v in opts.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        lowered = k.lower()
        if any(p in lowered for p in _SENSITIVE_NAME_PATTERNS):
            names.add(k)
    return names

TEAM_SENSITIVE_KEYS = {"smtp_password"}

# Project options a TEMPLATE may carry across a tenant boundary.
#
# This is an ALLOWLIST, not a credential denylist. A template published `public`
# by one tenant is replayed into another tenant's project, and the dangerous
# options are not only the secret-valued ones: `guard_output` pointed at the
# publisher's project runs every victim answer through it, `webhook_url` and
# `sync_sources` reach outbound, `mcp_servers[].host` can be a stdio command,
# `browser_allow_eval` is privileged, and `*_default_to` re-addresses the
# victim's notifications. Enumerating what is SAFE means anything unlisted —
# including future fields — is dropped by default.
TEMPLATE_COPYABLE_OPTION_KEYS = frozenset({
    # retrieval / generation tuning
    "llm_rerank", "score", "k", "tables",
    # agent behaviour
    "max_iterations", "auto_plan", "agent_mode", "agent_loop", "tools",
    # logging + moderation policy
    "logging", "redact_inference_logs",
    "moderation_blocklist", "moderation_redact_pii",
    # guard BEHAVIOUR (guard_output — the project reference — is deliberately absent)
    "guard_mode",
    # knowledge graph
    "enable_knowledge_graph", "ner_model",
    # memory
    "memory_bank_enabled", "memory_bank_max_tokens", "memory_search_enabled",
    # limits
    "rate_limit", "budget",
    # browser allowlist RESTRICTS reachable domains; browser_allow_eval does not
    # and is deliberately absent.
    "browser_allowed_domains",
    # the point of a block template
    "blockly_workspace",
})


def filter_template_options(options_blob):
    """Keep only `TEMPLATE_COPYABLE_OPTION_KEYS`.

    Accepts a JSON string OR dict and returns the same shape; unparseable input
    is wiped rather than passed through. Subsumes credential scrubbing — no
    secret-bearing key is in the allowlist.
    """
    if not options_blob:
        return options_blob

    was_str = isinstance(options_blob, str)
    if was_str:
        try:
            opts = _json.loads(options_blob)
        except Exception:
            return "{}"
    elif isinstance(options_blob, dict):
        opts = options_blob
    else:
        return options_blob

    if not isinstance(opts, dict):
        return options_blob

    kept = {k: v for k, v in opts.items() if k in TEMPLATE_COPYABLE_OPTION_KEYS}
    return _json.dumps(kept) if was_str else kept


SETTINGS_ENCRYPTED_KEYS = {
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
    for key in sensitive_option_names(result, sensitive_keys):
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
    for key in sensitive_option_names(result, sensitive_keys):
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
