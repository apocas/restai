"""Adapt RESTai FunctionTool objects into llamaindex-free AdaptedTools for agent2."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import typing
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union, get_args, get_origin

logger = logging.getLogger(__name__)


@dataclass
class AdaptedTool:
    name: str
    description: str
    input_schema: dict
    fn: Callable
    is_async: bool = False

    accepts_kwargs: bool = False

    async def call(self, args: dict, context: dict = None) -> str:
        try:
            call_args = dict(args)
            if context and self.accepts_kwargs:
                call_args.update({f"_{k}": v for k, v in context.items()})
            if self.is_async:
                result = await self.fn(**call_args)
            else:
                # Sync tools run in a worker thread. Calling them inline would
                # block the event loop: "parallel" tool batches would actually
                # serialize, and one slow sync tool (requests call, docker
                # exec) would freeze every concurrent chat on this worker.
                # Threading also makes asyncio.wait_for timeouts effective.
                result = await asyncio.to_thread(lambda: self.fn(**call_args))
        except TypeError as e:
            return f"Error calling tool ({self.name}): {e}"
        if result is None:
            return ""
        return str(result)


_TRUTHY_STRINGS = {"true", "1", "yes", "on"}
_FALSY_STRINGS = {"false", "0", "no", "off"}


def _coerce_value(value: Any, expected: str) -> tuple[Any, bool]:
    """Try to coerce `value` to JSON-schema type `expected`. Returns
    (coerced_value, ok). Fixes the classic small-model mistakes — "5" for an
    integer, "true" for a boolean, a JSON-encoded string for an array —
    instead of failing the tool call over them."""
    if expected == "string":
        if isinstance(value, str):
            return value, True
        if isinstance(value, (int, float, bool)):
            return str(value), True
        return value, False
    if expected == "integer":
        if isinstance(value, bool):
            return int(value), True
        if isinstance(value, int):
            return value, True
        if isinstance(value, float) and value.is_integer():
            return int(value), True
        if isinstance(value, str):
            try:
                return int(value.strip()), True
            except ValueError:
                return value, False
        return value, False
    if expected == "number":
        if isinstance(value, bool):
            return float(value), True
        if isinstance(value, (int, float)):
            return value, True
        if isinstance(value, str):
            try:
                return float(value.strip()), True
            except ValueError:
                return value, False
        return value, False
    if expected == "boolean":
        if isinstance(value, bool):
            return value, True
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value), True
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _TRUTHY_STRINGS:
                return True, True
            if lowered in _FALSY_STRINGS:
                return False, True
        return value, False
    if expected in ("array", "object"):
        target = list if expected == "array" else dict
        if isinstance(value, target):
            return value, True
        if expected == "array" and isinstance(value, tuple):
            return list(value), True
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value, False
            if isinstance(parsed, target):
                return parsed, True
        return value, False
    # Unknown/absent type declaration — accept as-is.
    return value, True


def coerce_and_validate_args(schema: Any, args: dict) -> tuple[dict, list[str]]:
    """Best-effort validation of tool-call args against a JSON-schema-ish dict.

    Returns (coerced_args, problems). Deliberately lenient: only plain
    `"type": "<primitive>"` declarations are enforced (anyOf/oneOf/$ref pass
    through untouched) and unknown keys are left alone — over-strict
    rejection would break **kwargs tools and complex MCP schemas. The goal is
    turning an opaque downstream TypeError into a crisp, self-correctable
    error message for the model, not full JSON Schema conformance.
    """
    if not isinstance(schema, dict) or not isinstance(args, dict):
        return args, []

    problems: list[str] = []
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = schema.get("required")
    required = required if isinstance(required, list) else []

    for name in required:
        if name not in args or args.get(name) is None:
            spec = props.get(name)
            type_hint = ""
            if isinstance(spec, dict) and isinstance(spec.get("type"), str):
                type_hint = f" ({spec['type']})"
            problems.append(f"missing required parameter '{name}'{type_hint}")

    coerced = dict(args)
    for name, value in args.items():
        spec = props.get(name)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        if isinstance(expected, list):
            # Nullable unions like ["string", "null"] — None passes, otherwise
            # validate against the first non-null member.
            if value is None and "null" in expected:
                continue
            expected = next((t for t in expected if t != "null"), None)
        if not isinstance(expected, str):
            continue
        if value is None:
            # None for a non-required param: leave it — the fn default applies.
            continue
        new_value, ok = _coerce_value(value, expected)
        if ok:
            coerced[name] = new_value
        else:
            problems.append(
                f"parameter '{name}' expected {expected}, "
                f"got {type(value).__name__}"
            )

    return coerced, problems


def describe_schema_for_error(schema: Any, max_chars: int = 400) -> str:
    """Compact one-line schema description appended to invalid-argument
    errors so the model can self-correct on the next attempt."""
    if not isinstance(schema, dict):
        return ""
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    required = set(schema.get("required") or [])
    parts = []
    for name, spec in props.items():
        t = spec.get("type") if isinstance(spec, dict) else None
        if isinstance(t, list):
            t = "/".join(str(x) for x in t)
        label = f"{name}: {t or 'any'}"
        if name in required:
            label += " (required)"
        parts.append(label)
    text = "{" + ", ".join(parts) + "}"
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


_PRIMITIVE_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    tuple: "array",
}


def _python_type_to_json_type(annotation: Any) -> dict:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[X] / Union[X, None] → unwrap as X (LLMs handle nullable poorly)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_type(non_none[0])
        return {"type": "string"}

    if origin in (list, tuple):
        inner = args[0] if args else None
        if inner is not None:
            return {"type": "array", "items": _python_type_to_json_type(inner)}
        return {"type": "array", "items": {"type": "string"}}

    if origin is dict:
        return {"type": "object"}

    if annotation in _PRIMITIVE_TYPE_MAP:
        return {"type": _PRIMITIVE_TYPE_MAP[annotation]}

    return {"type": "string"}


def build_json_schema(fn: Callable) -> dict:
    """Build an OpenAI-compatible JSON schema from a function signature."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "required": []}

    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}

    properties: dict = {}
    required: list = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = hints.get(name, param.annotation)
        prop = _python_type_to_json_type(annotation)
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            # Surface default in description so the LLM has context.
            try:
                prop = {**prop, "description": f"Default: {param.default!r}"}
            except Exception:
                pass

        properties[name] = prop

    return {"type": "object", "properties": properties, "required": required}


def _extract_metadata(
    tool: Any,
) -> tuple[Optional[str], Optional[str], Optional[Callable], Optional[dict]]:
    """Pull (name, description, fn, schema) from a llamaindex FunctionTool.

    Prefers pydantic-derived metadata via `metadata.get_parameters_dict()`
    since it handles complex hints / Optional / nested models / Field descriptions
    that `build_json_schema` would lose.
    """
    name = None
    description = None
    fn = None
    schema: Optional[dict] = None

    metadata = getattr(tool, "metadata", None)
    if metadata is not None:
        name = getattr(metadata, "name", None)
        description = getattr(metadata, "description", None)
        get_params = getattr(metadata, "get_parameters_dict", None)
        if callable(get_params):
            try:
                schema = get_params()
            except Exception:
                schema = None

    if name is None:
        name = getattr(tool, "name", None)
    if description is None:
        description = getattr(tool, "description", None)

    fn = getattr(tool, "fn", None)
    if fn is None:
        fn = getattr(tool, "_fn", None) or getattr(tool, "func", None)

    return name, description, fn, schema


# Cache by source-tool identity. Built-in tools live on `brain.tools` for the
# process lifetime so identity is stable; the per-request cost of repeating
# `metadata.get_parameters_dict()` → pydantic `model_json_schema()` is the
# dominant cost in `_build_runtime`.
_adapted_tool_cache: dict[int, AdaptedTool] = {}


def adapt_function_tools(tools: list) -> list[AdaptedTool]:
    """Convert llamaindex FunctionTools into AdaptedTools for agent2."""
    adapted: list[AdaptedTool] = []
    for tool in tools:
        key = id(tool)
        cached = _adapted_tool_cache.get(key)
        if cached is not None:
            adapted.append(cached)
            continue

        name, description, fn, schema = _extract_metadata(tool)
        if not name or fn is None:
            logger.warning("Skipping tool without name/fn: %r", tool)
            continue
        if not callable(fn):
            logger.warning("Skipping tool '%s': fn is not callable", name)
            continue

        if not description:
            description = (inspect.getdoc(fn) or name).strip()

        if schema is None:
            try:
                schema = build_json_schema(fn)
            except Exception:
                schema = {"type": "object", "properties": {}, "required": []}

        # Detect **kwargs for context injection, and collect param names the
        # model must never see: the VAR_KEYWORD/VAR_POSITIONAL catch-alls and
        # any `_`-prefixed context params. The pydantic-derived schema
        # (get_parameters_dict) surfaces `**kwargs` as a spurious `kwargs`
        # property the LLM then fills with "{}" — the signature-based builder
        # already skips these, but the preferred pydantic path does not.
        has_var_keyword = False
        hidden_params: set[str] = set()
        try:
            sig = inspect.signature(fn)
            for p in sig.parameters.values():
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    has_var_keyword = True
                    hidden_params.add(p.name)
                elif p.kind == inspect.Parameter.VAR_POSITIONAL or p.name.startswith("_"):
                    hidden_params.add(p.name)
        except (TypeError, ValueError):
            pass

        if hidden_params and isinstance(schema, dict):
            props = schema.get("properties")
            if isinstance(props, dict):
                for h in hidden_params:
                    props.pop(h, None)
            req = schema.get("required")
            if isinstance(req, list):
                schema["required"] = [r for r in req if r not in hidden_params]

        adapted_tool = AdaptedTool(
            name=name,
            description=description,
            input_schema=schema,
            fn=fn,
            is_async=inspect.iscoroutinefunction(fn),
            accepts_kwargs=has_var_keyword,
        )
        _adapted_tool_cache[key] = adapted_tool
        adapted.append(adapted_tool)
    return adapted
