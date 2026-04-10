"""Tests for restai.agent2.tool_adapter — schema building and AdaptedTool invocation."""
import asyncio
from typing import Optional

from restai.agent2.tool_adapter import (
    AdaptedTool,
    _python_type_to_json_type,
    build_json_schema,
)


# ---------- build_json_schema ----------


def test_build_json_schema_simple_function():
    def foo(x: str, y: int = 5) -> str:
        return x * y

    schema = build_json_schema(foo)
    assert schema["type"] == "object"
    assert "x" in schema["properties"]
    assert "y" in schema["properties"]
    assert schema["properties"]["x"]["type"] == "string"
    assert schema["properties"]["y"]["type"] == "integer"
    assert "x" in schema["required"]
    assert "y" not in schema["required"]


def test_build_json_schema_optional_params():
    def bar(a: str, b: Optional[int] = None) -> str:
        return a

    schema = build_json_schema(bar)
    assert "a" in schema["properties"]
    assert "b" in schema["properties"]
    assert "a" in schema["required"]
    assert "b" not in schema["required"]
    # Optional[int] unwraps to integer
    assert schema["properties"]["b"]["type"] == "integer"


def test_build_json_schema_no_annotations():
    def baz(x, y=10):
        return x

    schema = build_json_schema(baz)
    assert "x" in schema["properties"]
    assert "y" in schema["properties"]
    assert "x" in schema["required"]
    assert "y" not in schema["required"]


# ---------- _python_type_to_json_type ----------


def test_type_mapping_str():
    assert _python_type_to_json_type(str) == {"type": "string"}


def test_type_mapping_int():
    assert _python_type_to_json_type(int) == {"type": "integer"}


def test_type_mapping_float():
    assert _python_type_to_json_type(float) == {"type": "number"}


def test_type_mapping_bool():
    assert _python_type_to_json_type(bool) == {"type": "boolean"}


def test_type_mapping_list():
    assert _python_type_to_json_type(list)["type"] == "array"


def test_type_mapping_dict():
    assert _python_type_to_json_type(dict) == {"type": "object"}


# ---------- AdaptedTool.call ----------


def test_adapted_tool_call_sync():
    def add(a: int, b: int) -> int:
        return a + b

    tool = AdaptedTool(
        name="add",
        description="Add two numbers",
        input_schema=build_json_schema(add),
        fn=add,
        is_async=False,
    )
    result = asyncio.run(tool.call({"a": 3, "b": 4}))
    assert result == "7"


def test_adapted_tool_call_async():
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = AdaptedTool(
        name="greet",
        description="Greet someone",
        input_schema=build_json_schema(greet),
        fn=greet,
        is_async=True,
    )
    result = asyncio.run(tool.call({"name": "World"}))
    assert result == "Hello, World!"


def test_adapted_tool_call_returns_empty_for_none():
    def noop() -> None:
        return None

    tool = AdaptedTool(
        name="noop",
        description="No-op",
        input_schema={},
        fn=noop,
        is_async=False,
    )
    result = asyncio.run(tool.call({}))
    assert result == ""


def test_adapted_tool_call_bad_args_returns_error():
    def strict(x: int) -> int:
        return x + 1

    tool = AdaptedTool(
        name="strict",
        description="Strict",
        input_schema=build_json_schema(strict),
        fn=strict,
        is_async=False,
    )
    result = asyncio.run(tool.call({"wrong_param": 1}))
    assert "Error calling tool" in result
