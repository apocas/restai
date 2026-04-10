import os

from restai import config
from restai.models.databasemodels import SettingDatabase

# Mapping: setting_key -> (env_var_name_or_None, default_value)
SETTINGS_DEFAULTS = {
    "app_name": ("RESTAI_NAME", "RESTai"),
    "hide_branding": ("RESTAI_HIDE", "false"),
    "proxy_enabled": (None, "false"),
    "proxy_url": ("PROXY_URL", ""),
    "proxy_key": ("PROXY_KEY", ""),
    "proxy_team_id": ("PROXY_TEAM_ID", ""),
    "agent_max_iterations": ("AGENT_MAX_ITERATIONS", "20"),
    "max_audio_upload_size": ("MAX_AUDIO_UPLOAD_SIZE", "10"),
    "currency": ("CURRENCY", "EUR"),
    "redis_host": ("REDIS_HOST", ""),
    "redis_port": ("REDIS_PORT", "6379"),
    "redis_password": ("REDIS_PASSWORD", ""),
    "redis_database": ("REDIS_DATABASE", "0"),
    # Authentication
    "auth_disable_local": ("RESTAI_AUTH_DISABLE_LOCAL", "false"),
    "sso_auto_create_user": ("AUTO_CREATE_USER", "false"),
    "sso_allowed_domains": ("OAUTH_ALLOWED_DOMAINS", "*"),
    "sso_auto_restricted": (None, "true"),
    "sso_auto_team_id": (None, ""),
    # Google OAuth
    "sso_google_client_id": ("GOOGLE_CLIENT_ID", ""),
    "sso_google_client_secret": ("GOOGLE_CLIENT_SECRET", ""),
    "sso_google_redirect_uri": ("GOOGLE_REDIRECT_URI", ""),
    "sso_google_scope": ("GOOGLE_OAUTH_SCOPE", "openid email profile"),
    # Microsoft OAuth
    "sso_microsoft_client_id": ("MICROSOFT_CLIENT_ID", ""),
    "sso_microsoft_client_secret": ("MICROSOFT_CLIENT_SECRET", ""),
    "sso_microsoft_tenant_id": ("MICROSOFT_CLIENT_TENANT_ID", ""),
    "sso_microsoft_redirect_uri": ("MICROSOFT_REDIRECT_URI", ""),
    "sso_microsoft_scope": ("MICROSOFT_OAUTH_SCOPE", "openid email profile"),
    # GitHub OAuth
    "sso_github_client_id": ("GITHUB_CLIENT_ID", ""),
    "sso_github_client_secret": ("GITHUB_CLIENT_SECRET", ""),
    "sso_github_redirect_uri": ("GITHUB_CLIENT_REDIRECT_URI", ""),
    "sso_github_scope": ("GITHUB_CLIENT_SCOPE", "user:email"),
    # Generic OIDC
    "sso_oidc_client_id": ("OAUTH_CLIENT_ID", ""),
    "sso_oidc_client_secret": ("OAUTH_CLIENT_SECRET", ""),
    "sso_oidc_provider_url": ("OPENID_PROVIDER_URL", ""),
    "sso_oidc_redirect_uri": ("OPENID_REDIRECT_URI", ""),
    "sso_oidc_scopes": ("OAUTH_SCOPES", "openid email profile"),
    "sso_oidc_provider_name": ("OAUTH_PROVIDER_NAME", "SSO"),
    "sso_oidc_email_claim": ("OAUTH_EMAIL_CLAIM", "email"),
    # GPU
    "gpu_enabled": (None, None),  # default derived at seed time
    "gpu_worker_devices": ("GPU_WORKER_DEVICES", ""),
    # MCP
    "mcp_enabled": ("MCP_SERVER", "false"),
    # Docker
    "docker_enabled": (None, "false"),
    "docker_url": ("DOCKER_URL", ""),
    "docker_image": ("DOCKER_IMAGE", "python:3.12-slim"),
    "docker_timeout": ("DOCKER_TIMEOUT", "900"),
    "docker_network": ("DOCKER_NETWORK", "none"),
    # Retention
    "data_retention_days": (None, "0"),
    # 2FA
    "enforce_2fa": (None, "false"),
}

# Which config attrs map to which setting keys
_CONFIG_ATTR_MAP = {
    "app_name": "RESTAI_NAME",
    "hide_branding": "HIDE_BRANDING",
    "proxy_url": "PROXY_URL",
    "proxy_key": "PROXY_KEY",
    "proxy_team_id": "PROXY_TEAM_ID",
    "agent_max_iterations": "AGENT_MAX_ITERATIONS",
    "max_audio_upload_size": "MAX_AUDIO_UPLOAD_SIZE",
    "currency": "CURRENCY",
    "redis_host": "REDIS_HOST",
    "redis_port": "REDIS_PORT",
    "redis_password": "REDIS_PASSWORD",
    "redis_database": "REDIS_DATABASE",
    # Auth
    "auth_disable_local": "RESTAI_AUTH_DISABLE_LOCAL",
    "sso_auto_create_user": "AUTO_CREATE_USER",
    "sso_allowed_domains": "OAUTH_ALLOWED_DOMAINS",
    "sso_auto_restricted": "SSO_AUTO_RESTRICTED",
    "sso_auto_team_id": "SSO_AUTO_TEAM_ID",
    # Google
    "sso_google_client_id": "GOOGLE_CLIENT_ID",
    "sso_google_client_secret": "GOOGLE_CLIENT_SECRET",
    "sso_google_redirect_uri": "GOOGLE_REDIRECT_URI",
    "sso_google_scope": "GOOGLE_OAUTH_SCOPE",
    # Microsoft
    "sso_microsoft_client_id": "MICROSOFT_CLIENT_ID",
    "sso_microsoft_client_secret": "MICROSOFT_CLIENT_SECRET",
    "sso_microsoft_tenant_id": "MICROSOFT_CLIENT_TENANT_ID",
    "sso_microsoft_redirect_uri": "MICROSOFT_REDIRECT_URI",
    "sso_microsoft_scope": "MICROSOFT_OAUTH_SCOPE",
    # GitHub
    "sso_github_client_id": "GITHUB_CLIENT_ID",
    "sso_github_client_secret": "GITHUB_CLIENT_SECRET",
    "sso_github_redirect_uri": "GITHUB_CLIENT_REDIRECT_URI",
    "sso_github_scope": "GITHUB_CLIENT_SCOPE",
    # OIDC
    "sso_oidc_client_id": "OAUTH_CLIENT_ID",
    "sso_oidc_client_secret": "OAUTH_CLIENT_SECRET",
    "sso_oidc_provider_url": "OPENID_PROVIDER_URL",
    "sso_oidc_redirect_uri": "OPENID_REDIRECT_URI",
    "sso_oidc_scopes": "OAUTH_SCOPES",
    "sso_oidc_provider_name": "OAUTH_PROVIDER_NAME",
    "sso_oidc_email_claim": "OAUTH_EMAIL_CLAIM",
    # GPU
    "gpu_enabled": "RESTAI_GPU",
    "gpu_worker_devices": "GPU_WORKER_DEVICES",
    # MCP
    "mcp_enabled": "RESTAI_MCP",
    # Docker
    "docker_enabled": "DOCKER_ENABLED",
    "docker_url": "DOCKER_URL",
    "docker_image": "DOCKER_IMAGE",
    "docker_timeout": "DOCKER_TIMEOUT",
    "docker_network": "DOCKER_NETWORK",
    # Retention
    "data_retention_days": "DATA_RETENTION_DAYS",
    # 2FA
    "enforce_2fa": "ENFORCE_2FA",
}

_BOOL_KEYS = {"hide_branding", "proxy_enabled", "auth_disable_local", "sso_auto_create_user", "sso_auto_restricted", "gpu_enabled", "mcp_enabled", "docker_enabled", "enforce_2fa"}
_INT_KEYS = {"agent_max_iterations", "max_audio_upload_size", "data_retention_days", "docker_timeout"}

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
    existing = {s.key for s in db_wrapper.get_settings()}
    for key, (env_var, default) in SETTINGS_DEFAULTS.items():
        if key not in existing:
            value = default
            if env_var:
                env_val = os.environ.get(env_var)
                if env_val is not None:
                    value = env_val
            # Derive proxy_enabled from proxy_url if not explicitly set
            if key == "proxy_enabled":
                proxy_url_setting = db_wrapper.get_setting("proxy_url")
                if proxy_url_setting and proxy_url_setting.value:
                    value = "true"
                elif os.environ.get("PROXY_URL"):
                    value = "true"
            # Derive gpu_enabled from auto-detected value
            if key == "gpu_enabled" and value is None:
                value = str(config.RESTAI_GPU).lower()
            db_wrapper.upsert_setting(key, value)


def _sync_config_attr(key: str, value: str):
    attr = _CONFIG_ATTR_MAP.get(key)
    if attr is None:
        return
    if key == "sso_allowed_domains":
        # Store as comma-separated string in DB, convert to list in config
        setattr(config, attr, [d.strip() for d in (value or "*").split(",")])
    elif key in _BOOL_KEYS:
        setattr(config, attr, _to_bool(value))
    elif key in _INT_KEYS:
        try:
            setattr(config, attr, int(value))
        except (ValueError, TypeError):
            pass
    else:
        setattr(config, attr, value if value else None)


def load_settings(db_wrapper):
    rows = db_wrapper.get_settings()
    for row in rows:
        _sync_config_attr(row.key, row.value or "")


def update_setting(db_wrapper, key: str, value: str):
    db_wrapper.upsert_setting(key, value)
    _sync_config_attr(key, value)


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
        "agent_max_iterations": int(rows.get("agent_max_iterations", "20")),
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
        # Docker
        "docker_enabled": _to_bool(rows.get("docker_enabled", "false")),
        "docker_url": rows.get("docker_url", ""),
        "docker_image": rows.get("docker_image", "python:3.12-slim"),
        "docker_timeout": int(rows.get("docker_timeout", "900") or "900"),
        "docker_network": rows.get("docker_network", "none"),
        # Retention
        "data_retention_days": int(rows.get("data_retention_days", "0") or "0"),
    }


def reinit_oauth(app):
    """Rebuild OAuth providers from current config and reinit manager."""
    config.load_oauth_providers()
    if hasattr(app.state, "oauth_manager"):
        app.state.oauth_manager.reinit()
