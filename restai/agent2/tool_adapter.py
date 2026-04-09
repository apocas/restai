"""Adapt RestAI's existing FunctionTool objects (which are llamaindex wrappers
around plain Python functions) into a llamaindex-free representation usable by
the agent2 runtime.

We extract the underlying callable + name + description from each tool and
build a JSON schema from the function signature using only stdlib introspection.
The agent2 layer never imports llamaindex types directly.
"""
from __future__ import annotations

import inspect
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

    async def call(self, args: dict) -> str:
        try:
            if self.is_async:
                result = await self.fn(**args)
            else:
                result = self.fn(**args)
        except TypeError as e:
            return f"Error calling tool ({self.name}): {e}"
        if result is None:
            return ""
        return str(result)


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
    """Best-effort mapping from a Python type hint to a JSON schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[X] / Union[X, None] → unwrap and treat as X (LLMs handle nullable poorly)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_type(non_none[0])
        # Multi-type union → fall back to string
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

    # Unknown / custom class — fall back to string
    return {"type": "string"}


def build_json_schema(fn: Callable) -> dict:
    """Build a flat OpenAI-compatible JSON schema from a Python function signature."""
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
            # Mention the default in the description so the LLM has context
            try:
                prop = {**prop, "description": f"Default: {param.default!r}"}
            except Exception:
                pass

        properties[name] = prop

    return {"type": "object", "properties": properties, "required": required}


def _extract_metadata(
    tool: Any,
) -> tuple[Optional[str], Optional[str], Optional[Callable], Optional[dict]]:
    """Pull (name, description, fn, schema) out of a llamaindex FunctionTool.

    The schema is preferred from the tool's existing pydantic-derived metadata
    (`metadata.get_parameters_dict()`) — that handles complex type hints,
    Optional, nested models, Field descriptions, etc. correctly. Falls back to
    None so the caller can synthesize one with `build_json_schema`.
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


# Cache fully-built AdaptedTools by source-tool identity. Built-in tools live
# on `brain.tools` for the process lifetime so identity is stable, and the
# expensive part of adaptation (`metadata.get_parameters_dict()` → pydantic
# `model_json_schema()`) is uncached upstream — repeating it on every
# request is the dominant per-request cost in `_build_runtime`.
_adapted_tool_cache: dict[int, AdaptedTool] = {}


def adapt_function_tools(tools: list) -> list[AdaptedTool]:
    """Convert RestAI/llamaindex FunctionTools into AdaptedTools for agent2."""
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

        adapted_tool = AdaptedTool(
            name=name,
            description=description,
            input_schema=schema,
            fn=fn,
            is_async=inspect.iscoroutinefunction(fn),
        )
        _adapted_tool_cache[key] = adapted_tool
        adapted.append(adapted_tool)
    return adapted
