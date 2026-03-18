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
}

_BOOL_KEYS = {"hide_branding", "proxy_enabled"}
_INT_KEYS = {"agent_max_iterations", "max_audio_upload_size"}


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
            db_wrapper.upsert_setting(key, value)


def _sync_config_attr(key: str, value: str):
    attr = _CONFIG_ATTR_MAP.get(key)
    if attr is None:
        return
    if key in _BOOL_KEYS:
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
    }
