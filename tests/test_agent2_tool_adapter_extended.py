"""Extended tests for restai/agent2/tool_adapter.py — the branches not
covered by test_agent2_tool_adapter.py: adapt_function_tools metadata
extraction, caching, hidden-param stripping, and complex type mapping.
"""
import asyncio
import types
from typing import Any, Optional, Union

from restai.agent2.tool_adapter import (
    AdaptedTool,
    _adapted_tool_cache,
    _python_type_to_json_type,
    adapt_function_tools,
    build_json_schema,
)


def run(coro):
    return asyncio.run(coro)


# ─── _python_type_to_json_type edge branches ────────────────────────────

def test_type_optional_unwrapped():
    assert _python_type_to_json_type(Optional[int]) == {"type": "integer"}


def test_type_multi_union_defaults_string():
    assert _python_type_to_json_type(Union[str, int]) == {"type": "string"}


def test_type_parametrized_list():
    assert _python_type_to_json_type(list[int]) == {
        "type": "array", "items": {"type": "integer"}
    }


def test_type_bare_generic_list_defaults_string_items():
    # list with no args via origin path
    assert _python_type_to_json_type(list) == {"type": "array"}
    import typing
    assert _python_type_to_json_type(typing.List) == {
        "type": "array", "items": {"type": "string"}
    }


def test_type_parametrized_dict_is_object():
    assert _python_type_to_json_type(dict[str, int]) == {"type": "object"}


def test_type_any_and_unknown_default_string():
    assert _python_type_to_json_type(Any) == {"type": "string"}

    class Custom:
        pass

    assert _python_type_to_json_type(Custom) == {"type": "string"}


def test_type_tuple_parametrized():
    assert _python_type_to_json_type(tuple[str, ...]) == {
        "type": "array", "items": {"type": "string"}
    }


# ─── build_json_schema edge branches ────────────────────────────────────

def test_schema_skips_var_args_and_defaults_in_description():
    def fn(a: str, b: int = 5, *args, **kwargs):
        return a

    schema = build_json_schema(fn)
    assert set(schema["properties"]) == {"a", "b"}
    assert schema["required"] == ["a"]
    assert schema["properties"]["b"]["description"] == "Default: 5"


def test_schema_skips_self_cls():
    class K:
        def method(self, x: str):
            return x

        @classmethod
        def cmeth(cls, y: int):
            return y

    assert list(build_json_schema(K.method)["properties"]) == ["x"]
    assert list(build_json_schema(K.cmeth)["properties"]) == ["y"]


def test_schema_unsignaturable_object():
    schema = build_json_schema(type)  # inspect.signature(type) raises
    assert schema == {"type": "object", "properties": {}, "required": []}


# ─── AdaptedTool.call context injection ─────────────────────────────────

def test_call_context_injected_only_with_accepts_kwargs():
    seen = {}

    def fn(a, **kwargs):
        seen.update(kwargs)
        return "ok"

    tool = AdaptedTool(name="t", description="", input_schema={}, fn=fn,
                       accepts_kwargs=True)
    run(tool.call({"a": 1}, context={"chat_id": "c9", "brain": "B"}))
    assert seen == {"_chat_id": "c9", "_brain": "B"}


def test_call_context_ignored_without_accepts_kwargs():
    def fn(a):
        return f"a={a}"

    tool = AdaptedTool(name="t", description="", input_schema={}, fn=fn)
    out = run(tool.call({"a": 1}, context={"chat_id": "c9"}))
    assert out == "a=1"


def test_call_type_error_soft_message():
    tool = AdaptedTool(name="t", description="", input_schema={},
                       fn=lambda a: a)
    out = run(tool.call({"wrong": 1}))
    assert out.startswith("Error calling tool (t):")


# ─── adapt_function_tools ───────────────────────────────────────────────

class FakeMetadata:
    def __init__(self, name=None, description=None, schema=None, raise_params=False):
        self.name = name
        self.description = description
        self._schema = schema
        self._raise = raise_params

    def get_parameters_dict(self):
        if self._raise:
            raise RuntimeError("pydantic exploded")
        return self._schema


class FakeFunctionTool:
    def __init__(self, metadata=None, fn=None, **extra):
        if metadata is not None:
            self.metadata = metadata
        if fn is not None:
            self.fn = fn
        for k, v in extra.items():
            setattr(self, k, v)


def _clear_cache(*tools):
    for t in tools:
        _adapted_tool_cache.pop(id(t), None)


def test_adapt_uses_metadata_schema():
    schema = {"type": "object", "properties": {"q": {"type": "string"}},
              "required": ["q"]}
    tool = FakeFunctionTool(
        metadata=FakeMetadata(name="lookup", description="find", schema=schema),
        fn=lambda q: q,
    )
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert adapted.name == "lookup"
    assert adapted.description == "find"
    assert adapted.input_schema["properties"] == {"q": {"type": "string"}}
    _clear_cache(tool)


def test_adapt_cache_hit_returns_same_object():
    tool = FakeFunctionTool(
        metadata=FakeMetadata(name="cached", description="d",
                              schema={"type": "object", "properties": {}}),
        fn=lambda: "x",
    )
    _clear_cache(tool)
    first = adapt_function_tools([tool])[0]
    second = adapt_function_tools([tool])[0]
    assert first is second
    _clear_cache(tool)


def test_adapt_skips_nameless_and_fnless_and_uncallable():
    no_name = FakeFunctionTool(metadata=FakeMetadata(), fn=lambda: "x")
    no_fn = FakeFunctionTool(metadata=FakeMetadata(name="nofn"))
    not_callable = FakeFunctionTool(metadata=FakeMetadata(name="bad"), fn="string")
    _clear_cache(no_name, no_fn, not_callable)
    assert adapt_function_tools([no_name, no_fn, not_callable]) == []
    _clear_cache(no_name, no_fn, not_callable)


def test_adapt_falls_back_to_plain_attrs_and_docstring():
    def documented(x: str):
        """Does something documented."""
        return x

    tool = FakeFunctionTool(name="plain", fn=documented)
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert adapted.name == "plain"
    assert adapted.description == "Does something documented."
    assert adapted.input_schema["properties"] == {"x": {"type": "string"}}
    _clear_cache(tool)


def test_adapt_metadata_get_params_raising_falls_back_to_signature():
    def fn(city: str, days: int = 3):
        return city

    tool = FakeFunctionTool(
        metadata=FakeMetadata(name="wx", description="weather", raise_params=True),
        fn=fn,
    )
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert set(adapted.input_schema["properties"]) == {"city", "days"}
    assert adapted.input_schema["required"] == ["city"]
    _clear_cache(tool)


def test_adapt_strips_kwargs_and_underscore_params_from_pydantic_schema():
    """The pydantic path surfaces **kwargs / _context params; adapt must hide
    them from the model and mark accepts_kwargs."""
    def fn(query: str, _secret=None, **kwargs):
        return query

    leaky_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kwargs": {"type": "object"},
            "_secret": {"type": "string"},
        },
        "required": ["query", "kwargs"],
    }
    tool = FakeFunctionTool(
        metadata=FakeMetadata(name="leaky", description="d", schema=leaky_schema),
        fn=fn,
    )
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert set(adapted.input_schema["properties"]) == {"query"}
    assert adapted.input_schema["required"] == ["query"]
    assert adapted.accepts_kwargs is True
    _clear_cache(tool)


def test_adapt_async_fn_detected():
    async def afn(x: str):
        return x

    tool = FakeFunctionTool(name="async_tool", fn=afn)
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert adapted.is_async is True
    assert run(adapted.call({"x": "v"})) == "v"
    _clear_cache(tool)


def test_adapt_fn_fallback_attrs():
    """fn can live on `_fn` or `func` when `fn` is absent."""
    t1 = FakeFunctionTool(name="via_fn_attr", _fn=lambda: "a")
    t2 = FakeFunctionTool(name="via_func_attr", func=lambda: "b")
    _clear_cache(t1, t2)
    adapted = adapt_function_tools([t1, t2])
    assert [a.name for a in adapted] == ["via_fn_attr", "via_func_attr"]
    _clear_cache(t1, t2)


def test_adapt_description_defaults_to_name_when_no_doc():
    tool = FakeFunctionTool(name="bare", fn=lambda: None)
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert adapted.description == "bare"
    _clear_cache(tool)


def test_adapt_result_none_returns_empty_string():
    tool = FakeFunctionTool(name="none_tool", fn=lambda: None)
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert run(adapted.call({})) == ""
    _clear_cache(tool)


def test_adapt_metadata_none_schema_uses_signature():
    tool = FakeFunctionTool(
        metadata=FakeMetadata(name="ns", description="d", schema=None),
        fn=lambda flag: flag,
    )
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert "flag" in adapted.input_schema["properties"]
    _clear_cache(tool)


def test_adapt_unsignaturable_fn_keeps_pydantic_schema():
    """A builtin without a signature must not crash the hidden-param scan."""
    tool = FakeFunctionTool(
        metadata=FakeMetadata(
            name="len_tool", description="d",
            schema={"type": "object", "properties": {"obj": {"type": "string"}},
                    "required": ["obj"]},
        ),
        fn=types.SimpleNamespace,  # signature() raises ValueError for some objects
    )
    # Use `type` which raises in inspect.signature
    tool.fn = type
    _clear_cache(tool)
    [adapted] = adapt_function_tools([tool])
    assert adapted.input_schema["properties"] == {"obj": {"type": "string"}}
    _clear_cache(tool)
