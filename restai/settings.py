"""Settings persistence and seeding.

GUI-managed settings live in the `settings` DB table. Consumers read them
through `restai.config.<NAME>` — the `__getattr__` in `restai/config.py`
translates that to a DB lookup on every access, so multi-worker uvicorn
deployments see admin changes immediately without any in-process mirror.

Why no env-var fallback / no `setattr(config, ...)` mirror anymore:
  Earlier versions seeded these settings from env vars on first install AND
  pushed each updated value back onto the `restai.config` module via setattr.
  The mirror only landed in the worker that handled the PATCH, so other
  workers still saw the old value (or the empty default) — that's the
  multi-worker drift that broke `POST /settings/docker/test` intermittently.
  Settings are now DB-only and admins set them in the platform Settings page.
"""
from restai.models.databasemodels import SettingDatabase

# Mapping: setting_key -> default_value (string form). Env vars no longer
# bootstrap these — admins set everything in the GUI.
SETTINGS_DEFAULTS = {
    "app_name": "RESTai",
    "hide_branding": "false",
    "proxy_enabled": "false",
    "proxy_url": "",
    "proxy_key": "",
    "proxy_team_id": "",
    "max_audio_upload_size": "10",
    "currency": "EUR",
    "redis_host": "",
    "redis_port": "6379",
    "redis_password": "",
    "redis_database": "0",
    # Authentication
    "auth_disable_local": "false",
    "sso_auto_create_user": "false",
    "sso_allowed_domains": "*",
    "sso_auto_restricted": "true",
    "sso_auto_team_id": "",
    # Google OAuth
    "sso_google_client_id": "",
    "sso_google_client_secret": "",
    "sso_google_redirect_uri": "",
    "sso_google_scope": "openid email profile",
    # Microsoft OAuth
    "sso_microsoft_client_id": "",
    "sso_microsoft_client_secret": "",
    "sso_microsoft_tenant_id": "",
    "sso_microsoft_redirect_uri": "",
    "sso_microsoft_scope": "openid email profile",
    # GitHub OAuth
    "sso_github_client_id": "",
    "sso_github_client_secret": "",
    "sso_github_redirect_uri": "",
    "sso_github_scope": "user:email",
    # Generic OIDC
    "sso_oidc_client_id": "",
    "sso_oidc_client_secret": "",
    "sso_oidc_provider_url": "",
    "sso_oidc_redirect_uri": "",
    "sso_oidc_scopes": "openid email profile",
    "sso_oidc_provider_name": "SSO",
    "sso_oidc_email_claim": "email",
    # GPU. Empty string means "auto-detect" — config.RESTAI_GPU resolves it.
    "gpu_enabled": "",
    "gpu_worker_devices": "",
    # MCP
    "mcp_enabled": "false",
    # System LLM
    "system_llm": "",
    # Docker
    "docker_enabled": "false",
    "docker_url": "",
    "docker_image": "python:3.12-slim",
    "docker_timeout": "900",
    "docker_network": "none",
    "docker_read_only": "true",
    # Agentic Browser (Playwright-backed per-chat Chromium container)
    "browser_enabled": "false",
    "browser_image": "mcr.microsoft.com/playwright/python:v1.48.0-jammy",
    "browser_network": "bridge",
    "browser_timeout": "900",
    # App Builder (per-project PHP+Node+esbuild preview container)
    "app_docker_enabled": "false",
    "app_docker_image": "restai/app-runtime:1",
    "app_docker_idle_timeout": "1800",
    # Retention
    "data_retention_days": "0",
    # 2FA
    "enforce_2fa": "false",
    # Password rotation reminder. 0 = disabled (no warning ever).
    # Soft-only — passwords stay valid past the threshold; the login
    # response just includes a `password_warning` field so the UI can
    # nudge the user to rotate.
    "password_max_age_days": "0",
    # Telemetry
    "telemetry_instance_id": "",
}

_BOOL_KEYS = {"hide_branding", "proxy_enabled", "auth_disable_local", "sso_auto_create_user", "sso_auto_restricted", "gpu_enabled", "mcp_enabled", "docker_enabled", "docker_read_only", "browser_enabled", "app_docker_enabled", "enforce_2fa"}
_INT_KEYS = {"max_audio_upload_size", "data_retention_days", "docker_timeout", "browser_timeout", "app_docker_idle_timeout", "password_max_age_days"}

# Secret keys that should be masked in API responses
_SECRET_KEYS = {
    "proxy_key", "redis_password",
    "sso_google_client_secret", "sso_microsoft_client_secret",
    "sso_github_client_secret", "sso_oidc_client_secret",
}


def _to_bool(val: str) -> bool:
    return val.lower() in ("true", "1")


def ensure_settings_table(engine):
    SettingDatabase.__table__.create(engine, checkfirst=True)


def seed_defaults(db_wrapper):
    """Insert any missing default rows. Safe to run on every boot — never
    overwrites existing values."""
    existing = {s.key for s in db_wrapper.get_settings()}
    for key, default in SETTINGS_DEFAULTS.items():
        if key not in existing:
            db_wrapper.upsert_setting(key, default)


def update_setting(db_wrapper, key: str, value: str):
    """Persist a single setting. No process-local mirror — every consumer
    reads through `restai.config` which routes to the DB on demand."""
    db_wrapper.upsert_setting(key, value)


def mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) > 4:
        return "****" + value[-4:]
    return "****"


def get_all_settings(db_wrapper) -> dict:
    rows = {s.key: s.value or "" for s in db_wrapper.get_settings()}
    return {
        "app_name": rows.get("app_name", "RESTai"),
        "hide_branding": _to_bool(rows.get("hide_branding", "false")),
        "proxy_enabled": _to_bool(rows.get("proxy_enabled", "false")),
        "proxy_url": rows.get("proxy_url", ""),
        "proxy_key": mask_key(rows.get("proxy_key", "")),
        "proxy_team_id": rows.get("proxy_team_id", ""),
        "max_audio_upload_size": int(rows.get("max_audio_upload_size", "10")),
        "currency": rows.get("currency", "EUR"),
        "redis_host": rows.get("redis_host", ""),
        "redis_port": rows.get("redis_port", "6379"),
        "redis_password": mask_key(rows.get("redis_password", "")),
        "redis_database": rows.get("redis_database", "0"),
        # Authentication
        "auth_disable_local": _to_bool(rows.get("auth_disable_local", "false")),
        "sso_auto_create_user": _to_bool(rows.get("sso_auto_create_user", "false")),
        "sso_allowed_domains": rows.get("sso_allowed_domains", "*"),
        "sso_auto_restricted": _to_bool(rows.get("sso_auto_restricted", "true")),
        "sso_auto_team_id": rows.get("sso_auto_team_id", ""),
        # Google OAuth
        "sso_google_client_id": rows.get("sso_google_client_id", ""),
        "sso_google_client_secret": mask_key(rows.get("sso_google_client_secret", "")),
        "sso_google_redirect_uri": rows.get("sso_google_redirect_uri", ""),
        "sso_google_scope": rows.get("sso_google_scope", "openid email profile"),
        # Microsoft OAuth
        "sso_microsoft_client_id": rows.get("sso_microsoft_client_id", ""),
        "sso_microsoft_client_secret": mask_key(rows.get("sso_microsoft_client_secret", "")),
        "sso_microsoft_tenant_id": rows.get("sso_microsoft_tenant_id", ""),
        "sso_microsoft_redirect_uri": rows.get("sso_microsoft_redirect_uri", ""),
        "sso_microsoft_scope": rows.get("sso_microsoft_scope", "openid email profile"),
        # GitHub OAuth
        "sso_github_client_id": rows.get("sso_github_client_id", ""),
        "sso_github_client_secret": mask_key(rows.get("sso_github_client_secret", "")),
        "sso_github_redirect_uri": rows.get("sso_github_redirect_uri", ""),
        "sso_github_scope": rows.get("sso_github_scope", "user:email"),
        # Generic OIDC
        "sso_oidc_client_id": rows.get("sso_oidc_client_id", ""),
        "sso_oidc_client_secret": mask_key(rows.get("sso_oidc_client_secret", "")),
        "sso_oidc_provider_url": rows.get("sso_oidc_provider_url", ""),
        "sso_oidc_redirect_uri": rows.get("sso_oidc_redirect_uri", ""),
        "sso_oidc_scopes": rows.get("sso_oidc_scopes", "openid email profile"),
        "sso_oidc_provider_name": rows.get("sso_oidc_provider_name", "SSO"),
        "sso_oidc_email_claim": rows.get("sso_oidc_email_claim", "email"),
        # GPU
        "gpu_enabled": _to_bool(rows.get("gpu_enabled", "false")),
        "gpu_worker_devices": rows.get("gpu_worker_devices", ""),
        # MCP
        "mcp_enabled": _to_bool(rows.get("mcp_enabled", "false")),
        # System LLM
        "system_llm": rows.get("system_llm", ""),
        # Docker
        "docker_enabled": _to_bool(rows.get("docker_enabled", "false")),
        "docker_url": rows.get("docker_url", ""),
        "docker_image": rows.get("docker_image", "python:3.12-slim"),
        "docker_timeout": int(rows.get("docker_timeout", "900") or "900"),
        "docker_network": rows.get("docker_network", "none"),
        "docker_read_only": _to_bool(rows.get("docker_read_only", "true")),
        # Agentic Browser
        "browser_enabled": _to_bool(rows.get("browser_enabled", "false")),
        "browser_image": rows.get("browser_image", "mcr.microsoft.com/playwright/python:v1.48.0-jammy"),
        "browser_network": rows.get("browser_network", "bridge"),
        "browser_timeout": int(rows.get("browser_timeout", "900") or "900"),
        # App Builder
        "app_docker_enabled": _to_bool(rows.get("app_docker_enabled", "false")),
        "app_docker_image": rows.get("app_docker_image", "restai/app-runtime:1"),
        "app_docker_idle_timeout": int(rows.get("app_docker_idle_timeout", "1800") or "1800"),
        # Retention
        "data_retention_days": int(rows.get("data_retention_days", "0") or "0"),
        # 2FA
        "enforce_2fa": _to_bool(rows.get("enforce_2fa", "false")),
        # Password rotation
        "password_max_age_days": int(rows.get("password_max_age_days", "0") or "0"),
    }


def reinit_oauth(app):
    """Rebuild OAuth providers from the current DB-backed settings.

    Each authlib client is per-process, so this only refreshes the worker
    handling the PATCH. Other workers pick up the change on their next OAuth
    request because `OAUTH_PROVIDERS` reads through `__getattr__` on every
    `register` invocation. (The cached `oauth_manager.oauth` instance on
    other workers may still hold stale clients until they are re-built —
    acceptable trade-off given OAuth flows are admin-frequency, not
    request-frequency.)
    """
    from restai import config
    config.load_oauth_providers()
    if hasattr(app.state, "oauth_manager"):
        app.state.oauth_manager.reinit()
