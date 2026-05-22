"""Expose platform builtin tools as an in-process Claude Agent SDK MCP server."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


logger = logging.getLogger("restai.claude_loop.sdk_tools")


# Internal parameters that must never reach the LLM's tool schema. `kwargs`
# covers the **kwargs catch-all llama-index auto-includes for signatures
# like `terminal(command, **kwargs)`: exposing it makes the LLM send
# `"kwargs": "{}"` and the SDK rejects because `kwargs` has no declared type.
_INTERNAL_PARAM_NAMES = {"kwargs", "_brain", "_chat_id", "_project_id"}


def _strip_internal_params(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    props = dict(schema.get("properties") or {})
    required = [r for r in (schema.get("required") or []) if r not in _INTERNAL_PARAM_NAMES]
    for name in _INTERNAL_PARAM_NAMES:
        props.pop(name, None)
    cleaned = dict(schema)
    cleaned["properties"] = props
    if required:
        cleaned["required"] = required
    else:
        cleaned.pop("required", None)
    return cleaned


def _function_tool_input_schema(ft) -> dict:
    schema = None
    try:
        meta = ft.metadata
        if hasattr(meta, "get_parameters_dict"):
            schema = meta.get_parameters_dict()
        if not schema and hasattr(meta, "fn_schema_str") and meta.fn_schema_str:
            try:
                schema = json.loads(meta.fn_schema_str)
            except Exception:
                pass
        if not schema and hasattr(meta, "fn_schema") and meta.fn_schema is not None:
            schema = meta.fn_schema.schema()
    except Exception:
        logger.debug("Failed to extract input_schema for tool %s", getattr(ft.metadata, "name", "?"))
    if not schema:
        return {"type": "object", "properties": {}}
    return _strip_internal_params(schema)


def _wrap_response(value: Any) -> dict:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, default=str)
    else:
        text = str(value)
    return {"content": [{"type": "text", "text": text}]}


def _wrap_function_tool(ft, *, brain, chat_id, project_id):
    name = ft.metadata.name
    description = ft.metadata.description or name
    schema = _function_tool_input_schema(ft)
    inner = ft.fn

    is_async = inspect.iscoroutinefunction(inner)
    sig = inspect.signature(inner)
    has_var_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    accepts_brain = "_brain" in sig.parameters or has_var_kwargs
    accepts_chat = "_chat_id" in sig.parameters or has_var_kwargs
    accepts_project = "_project_id" in sig.parameters or has_var_kwargs

    @tool(name, description, schema)
    async def _sdk_handler(args):
        kwargs = dict(args or {})
        if accepts_brain and "_brain" not in kwargs:
            kwargs["_brain"] = brain
        if accepts_chat and "_chat_id" not in kwargs:
            kwargs["_chat_id"] = chat_id
        if accepts_project and "_project_id" not in kwargs:
            kwargs["_project_id"] = project_id
        try:
            result = await inner(**kwargs) if is_async else inner(**kwargs)
        except Exception as e:
            logger.exception("Platform tool %s raised", name)
            return {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}
        return _wrap_response(result)

    return _sdk_handler


def _wrap_project_tool(tool_row, *, brain, chat_id):
    """ProjectToolDatabase row → SDK tool (mirrors agent._make_project_tool_adapted)."""
    name = tool_row.name
    description = tool_row.description or name
    try:
        schema = (
            json.loads(tool_row.parameters)
            if isinstance(tool_row.parameters, str)
            else (tool_row.parameters or {"type": "object", "properties": {}})
        )
    except (json.JSONDecodeError, TypeError):
        schema = {"type": "object", "properties": {}}

    tool_code = tool_row.code

    @tool(name, description, schema)
    async def _sdk_handler(args):
        if not brain or not getattr(brain, "docker_manager", None):
            return {"content": [{"type": "text", "text": "ERROR: Docker is not configured."}], "isError": True}
        args_json = json.dumps(args or {})
        script = (
            "import json, sys\n"
            "args = json.loads(sys.stdin.readline() or '{}')\n"
            f"{tool_code}"
        )
        try:
            result = brain.docker_manager.run_script(
                chat_id or "ephemeral", script, stdin_data=args_json
            )
        except Exception as e:
            logger.exception("Project tool %s raised", name)
            return {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}
        return _wrap_response(result)

    return _sdk_handler


def _enabled_builtin_tools(project, brain) -> list:
    enabled_raw = (getattr(project.props.options, "tools", None) or "")
    enabled = {t.strip().lower() for t in enabled_raw.split(",") if t.strip()}
    if not enabled:
        return []
    all_tools = brain.get_tools() if hasattr(brain, "get_tools") else []
    return [ft for ft in all_tools if getattr(ft.metadata, "name", "").lower() in enabled]


def build_builtins_mcp(project, db, brain, chat_id: str):
    """Returns (server, allowed_names) for ClaudeAgentOptions.allowed_tools."""
    project_id = project.props.id

    sdk_tools = []
    allowed: list[str] = []

    for ft in _enabled_builtin_tools(project, brain):
        try:
            sdk_tools.append(_wrap_function_tool(ft, brain=brain, chat_id=chat_id, project_id=project_id))
            allowed.append(f"mcp__restai_builtins__{ft.metadata.name}")
        except Exception as e:
            logger.warning("Failed to wrap builtin %s: %s", getattr(ft.metadata, "name", "?"), e)

    try:
        project_tool_rows = db.get_project_tools(project_id) or []
    except Exception:
        project_tool_rows = []
    for row in project_tool_rows:
        if not getattr(row, "enabled", True):
            continue
        try:
            sdk_tools.append(_wrap_project_tool(row, brain=brain, chat_id=chat_id))
            allowed.append(f"mcp__restai_builtins__{row.name}")
        except Exception as e:
            logger.warning("Failed to wrap project tool %s: %s", row.name, e)

    if not sdk_tools:
        return None, []

    server = create_sdk_mcp_server(name="restai_builtins", version="1.0.0", tools=sdk_tools)
    return server, allowed
