"""Extended tests for restai/agent2/providers.py — message/tool serialization,
complete()/stream_complete() with faked SDK clients, and the remaining
build_provider_for_llm branches. No network calls."""
import asyncio
import base64
import types

import pytest

from restai.agent2.providers import (
    Agent2ProviderError,
    AnthropicProvider,
    AzureOpenAIProvider,
    BedrockProvider,
    OpenAIProvider,
    Provider,
    ProviderConfig,
    _build_user_payload,
    _provider_cache,
    _provider_cache_key,
    build_provider_for_llm,
)
from restai.agent2.tool_adapter import AdaptedTool
from restai.agent2.types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


def _make_llm_row(
    name="test",
    class_name="OpenAI",
    options='{"model":"gpt-4o","api_key":"sk-fake"}',
    context_window=4096,
):
    return types.SimpleNamespace(
        id=1,
        name=name,
        class_name=class_name,
        options=options,
        context_window=context_window,
        privacy="public",
        description=None,
        input_cost=0.0,
        output_cost=0.0,
        teams=[],
    )


def _build(row):
    _provider_cache.pop(_provider_cache_key(row), None)
    try:
        return build_provider_for_llm(row)
    finally:
        _provider_cache.pop(_provider_cache_key(row), None)


def _tool(name="t"):
    return AdaptedTool(
        name=name,
        description="desc",
        input_schema={"type": "object", "properties": {"a": {"type": "string"}}},
        fn=lambda **kw: "ok",
    )


# ─── serialization: OpenAI ──────────────────────────────────────────────

def test_build_user_payload_plain_string():
    out = _build_user_payload(["hello", "world"], [], has_image=False)
    assert out == {"role": "user", "content": "hello\nworld"}


def test_build_user_payload_with_image_list_form():
    img = {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}
    out = _build_user_payload(["hi"], [img], has_image=True)
    assert isinstance(out["content"], list)
    assert out["content"][0] == {"type": "text", "text": "hi"}
    assert out["content"][1] is img


def test_openai_serialize_tool():
    ser = OpenAIProvider._serialize_tool(_tool("weather"))
    assert ser["type"] == "function"
    assert ser["function"]["name"] == "weather"
    assert ser["function"]["parameters"]["type"] == "object"


def test_openai_serialize_messages_system_and_text():
    msgs = [Message(role="user", content=[TextBlock(text="hi")])]
    out = OpenAIProvider._serialize_messages("be nice", msgs)
    assert out[0] == {"role": "system", "content": "be nice"}
    assert out[1] == {"role": "user", "content": "hi"}


def test_openai_serialize_user_with_image():
    msgs = [Message(role="user", content=[
        TextBlock(text="what is this?"),
        ImageBlock(data="QUJD", mime_type="image/jpeg"),
    ])]
    out = OpenAIProvider._serialize_messages("", msgs)
    assert len(out) == 1
    content = out[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"


def test_openai_serialize_user_tool_result_splits_payload():
    msgs = [Message(role="user", content=[
        TextBlock(text="context"),
        ToolResultBlock(tool_use_id="tc1", content="result text"),
    ])]
    out = OpenAIProvider._serialize_messages("", msgs)
    assert out[0] == {"role": "user", "content": "context"}
    assert out[1] == {"role": "tool", "tool_call_id": "tc1", "content": "result text"}


def test_openai_serialize_tool_result_only():
    msgs = [Message(role="user", content=[
        ToolResultBlock(tool_use_id="tc1", content="only result"),
    ])]
    out = OpenAIProvider._serialize_messages("", msgs)
    assert out == [{"role": "tool", "tool_call_id": "tc1", "content": "only result"}]


def test_openai_serialize_assistant_tool_calls_empty_content():
    msg = Message(role="assistant", content=[
        ToolUseBlock(id="c1", name="t", input={"x": 1}),
    ])
    out = OpenAIProvider._serialize_assistant_message(msg)
    # Must be "" not None (Ollama compat).
    assert out["content"] == ""
    assert out["tool_calls"][0]["function"]["name"] == "t"
    assert out["tool_calls"][0]["function"]["arguments"] == '{"x": 1}'


def test_openai_serialize_assistant_text_and_tools():
    msg = Message(role="assistant", content=[
        TextBlock(text="thinking"),
        ToolUseBlock(id="c1", name="t", input={}),
    ])
    out = OpenAIProvider._serialize_assistant_message(msg)
    assert out["content"] == "thinking"
    assert len(out["tool_calls"]) == 1


# ─── serialization: Anthropic ───────────────────────────────────────────

def test_anthropic_serialize_blocks():
    assert AnthropicProvider._serialize_block(TextBlock(text="x")) == {"type": "text", "text": "x"}
    img = AnthropicProvider._serialize_block(ImageBlock(data="QUJD", mime_type="image/png"))
    assert img["source"]["media_type"] == "image/png"
    tu = AnthropicProvider._serialize_block(ToolUseBlock(id="i", name="n", input={"a": 1}))
    assert tu["type"] == "tool_use"
    tr = AnthropicProvider._serialize_block(ToolResultBlock(tool_use_id="i", content="c", is_error=True))
    assert tr["is_error"] is True


def test_anthropic_serialize_unknown_block_raises():
    with pytest.raises(TypeError):
        AnthropicProvider._serialize_block(object())


def test_anthropic_serialize_tool():
    ser = AnthropicProvider._serialize_tool(_tool("search"))
    assert ser == {
        "name": "search",
        "description": "desc",
        "input_schema": {"type": "object", "properties": {"a": {"type": "string"}}},
    }


def test_anthropic_requires_api_key():
    with pytest.raises(Agent2ProviderError):
        AnthropicProvider(ProviderConfig(model="claude", api_key=None))


# ─── serialization: Bedrock ─────────────────────────────────────────────

def test_bedrock_serialize_blocks():
    assert BedrockProvider._serialize_block(TextBlock(text="x")) == {"text": "x"}
    raw = base64.b64encode(b"imgbytes").decode()
    img = BedrockProvider._serialize_block(ImageBlock(data=raw, mime_type="image/jpg"))
    assert img["image"]["format"] == "jpeg"
    assert img["image"]["source"]["bytes"] == b"imgbytes"
    tu = BedrockProvider._serialize_block(ToolUseBlock(id="i", name="n", input=None))
    assert tu["toolUse"]["input"] == {}
    tr = BedrockProvider._serialize_block(ToolResultBlock(tool_use_id="i", content="c", is_error=True))
    assert tr["toolResult"]["status"] == "error"


def test_bedrock_serialize_unknown_block_raises():
    with pytest.raises(TypeError):
        BedrockProvider._serialize_block(object())


def test_bedrock_serialize_tool():
    ser = BedrockProvider._serialize_tool(_tool("calc"))
    assert ser["toolSpec"]["name"] == "calc"
    assert "json" in ser["toolSpec"]["inputSchema"]


def test_bedrock_parse_response():
    resp = {"output": {"message": {"content": [
        {"text": "answer"},
        {"toolUse": {"toolUseId": "id1", "name": "calc", "input": {"n": 2}}},
    ]}}}
    msg = BedrockProvider._parse_response(resp)
    assert msg.role == "assistant"
    assert isinstance(msg.content[0], TextBlock)
    assert msg.content[0].text == "answer"
    tu = msg.content[1]
    assert isinstance(tu, ToolUseBlock)
    assert tu.input == {"n": 2}


def test_bedrock_parse_response_empty():
    msg = BedrockProvider._parse_response({})
    assert msg.content == []
    msg = BedrockProvider._parse_response(None)
    assert msg.content == []


# ─── OpenAIProvider.complete with faked client ──────────────────────────

def _fake_openai_client(response=None, chunks=None):
    async def create(**kwargs):
        create.kwargs = kwargs
        if chunks is not None:
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()
        return response
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    ), create


def _delta(content=None, reasoning=None, tool_calls=None):
    return types.SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        reasoning=None,
        tool_calls=tool_calls,
    )


def _chunk(delta=None):
    if delta is None:
        return types.SimpleNamespace(choices=[])
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


def test_openai_complete_text_and_bad_json_tool_args():
    provider = OpenAIProvider(ProviderConfig(model="m", api_key="k"))
    response = types.SimpleNamespace(choices=[types.SimpleNamespace(
        message=types.SimpleNamespace(
            content="hello",
            tool_calls=[types.SimpleNamespace(
                id="c1",
                function=types.SimpleNamespace(name="t", arguments="{not json"),
            )],
        )
    )])
    client, create = _fake_openai_client(response=response)
    provider._client = client

    msg = asyncio.run(provider.complete(
        system_prompt="sys",
        messages=[Message(role="user", content=[TextBlock(text="q")])],
        tools=[_tool()],
        config=ProviderConfig(model="m", temperature=0.3, max_output_tokens=99),
    ))
    assert msg.text_content() == "hello"
    tu = [b for b in msg.content if isinstance(b, ToolUseBlock)][0]
    assert tu.input == {"__raw_arguments": "{not json"}
    assert create.kwargs["temperature"] == 0.3
    assert create.kwargs["max_tokens"] == 99
    assert create.kwargs["tool_choice"] == "auto"


def test_openai_complete_list_content():
    provider = OpenAIProvider(ProviderConfig(model="m", api_key="k"))
    response = types.SimpleNamespace(choices=[types.SimpleNamespace(
        message=types.SimpleNamespace(
            content=[
                types.SimpleNamespace(type="text", text="part1"),
                types.SimpleNamespace(type="other", text="skipped"),
                types.SimpleNamespace(type="text", text="part2"),
            ],
            tool_calls=None,
        )
    )])
    client, _ = _fake_openai_client(response=response)
    provider._client = client
    msg = asyncio.run(provider.complete(
        system_prompt="", messages=[], tools=[], config=ProviderConfig(model="m"),
    ))
    assert msg.text_content() == "part1\npart2"


def _collect_stream(provider, **kw):
    async def _run():
        out = []
        async for item in provider.stream_complete(**kw):
            out.append(item)
        return out
    return asyncio.run(_run())


def test_openai_stream_thinking_text_and_tool_fragments():
    provider = OpenAIProvider(ProviderConfig(model="m", api_key="k"))
    chunks = [
        _chunk(),  # empty choices tolerated
        _chunk(_delta(reasoning="pondering")),
        _chunk(_delta(content="Hello")),
        _chunk(_delta(tool_calls=[types.SimpleNamespace(
            index=0, id="call1",
            function=types.SimpleNamespace(name="get_x", arguments='{"x"'),
        )])),
        _chunk(_delta(tool_calls=[types.SimpleNamespace(
            index=0, id=None,
            function=types.SimpleNamespace(name=None, arguments=":1}"),
        )])),
    ]
    client, _ = _fake_openai_client(chunks=chunks)
    provider._client = client

    items = _collect_stream(
        provider,
        system_prompt="s",
        messages=[Message(role="user", content=[TextBlock(text="q")])],
        tools=[_tool()],
        config=ProviderConfig(model="m"),
    )
    text_deltas = [i for i in items if isinstance(i, str)]
    assert text_deltas == ["<think>", "pondering", "</think>", "Hello"]

    final = items[-1]
    assert isinstance(final, Message)
    assert final.text_content() == "<think>pondering</think>Hello"
    tu = [b for b in final.content if isinstance(b, ToolUseBlock)][0]
    assert tu.id == "call1"
    assert tu.name == "get_x"
    assert tu.input == {"x": 1}


def test_openai_stream_closes_dangling_think_tag():
    provider = OpenAIProvider(ProviderConfig(model="m", api_key="k"))
    chunks = [_chunk(_delta(reasoning="only thoughts"))]
    client, _ = _fake_openai_client(chunks=chunks)
    provider._client = client
    items = _collect_stream(
        provider, system_prompt="", messages=[], tools=[],
        config=ProviderConfig(model="m"),
    )
    text_deltas = [i for i in items if isinstance(i, str)]
    assert text_deltas == ["<think>", "only thoughts", "</think>"]
    assert items[-1].text_content().endswith("</think>")


def test_openai_stream_drops_nameless_tool_slot():
    provider = OpenAIProvider(ProviderConfig(model="m", api_key="k"))
    chunks = [_chunk(_delta(tool_calls=[types.SimpleNamespace(
        index=0, id="c", function=types.SimpleNamespace(name=None, arguments="{}"),
    )]))]
    client, _ = _fake_openai_client(chunks=chunks)
    provider._client = client
    items = _collect_stream(
        provider, system_prompt="", messages=[], tools=[],
        config=ProviderConfig(model="m"),
    )
    final = items[-1]
    assert final.content == []


# ─── AnthropicProvider.complete with faked client ───────────────────────

def test_anthropic_complete_parses_blocks():
    provider = AnthropicProvider(ProviderConfig(model="claude", api_key="sk-ant"))

    async def create(**kwargs):
        create.kwargs = kwargs
        return types.SimpleNamespace(content=[
            types.SimpleNamespace(type="text", text="hi"),
            types.SimpleNamespace(type="tool_use", id="tu1", name="calc", input={"n": 1}),
            types.SimpleNamespace(type="mystery"),
        ])
    provider._client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=create)
    )

    msg = asyncio.run(provider.complete(
        system_prompt="sys",
        messages=[Message(role="user", content=[TextBlock(text="q")])],
        tools=[_tool()],
        config=ProviderConfig(model="claude", temperature=0.1),
    ))
    assert msg.text_content() == "hi"
    tu = [b for b in msg.content if isinstance(b, ToolUseBlock)][0]
    assert tu.name == "calc"
    assert create.kwargs["system"] == "sys"
    assert create.kwargs["temperature"] == 0.1
    assert len(create.kwargs["tools"]) == 1


# ─── default (base-class) stream_complete fallback ──────────────────────

def test_provider_default_stream_falls_back_to_complete():
    class Simple(Provider):
        async def complete(self, *, system_prompt, messages, tools, config):
            return Message(role="assistant", content=[TextBlock(text="whole answer")])

    items = _collect_stream(
        Simple(), system_prompt="", messages=[], tools=[],
        config=ProviderConfig(model="m"),
    )
    assert items[0] == "whole answer"
    assert isinstance(items[1], Message)


# ─── build_provider_for_llm branches ────────────────────────────────────

def test_build_litellm_placeholder_key():
    row = _make_llm_row(class_name="LiteLLM", options='{"model":"m","base_url":"http://gw/v1"}')
    provider, cfg = _build(row)
    assert isinstance(provider, OpenAIProvider)
    assert cfg.api_key == "not-needed"
    assert cfg.base_url == "http://gw/v1"


def test_build_ollama_defaults_and_v1_suffix():
    row = _make_llm_row(class_name="Ollama", options='{"model":"llama3"}')
    _, cfg = _build(row)
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.api_key == "ollama"


def test_build_ollama_cloud_uses_real_key():
    row = _make_llm_row(
        class_name="OllamaCloud",
        options='{"model":"llama3","api_key":"real-key"}',
    )
    _, cfg = _build(row)
    assert cfg.base_url == "https://ollama.com/v1"
    assert cfg.api_key == "real-key"


def test_build_grok_default_base_url():
    row = _make_llm_row(class_name="Grok", options='{"api_key":"xai"}')
    _, cfg = _build(row)
    assert cfg.model == "grok-beta"
    assert cfg.base_url == "https://api.x.ai/v1"


def test_build_vllm_appends_v1():
    row = _make_llm_row(class_name="vLLM", options='{"model":"m","api_url":"http://vllm:8000"}')
    _, cfg = _build(row)
    assert cfg.base_url == "http://vllm:8000/v1"
    assert cfg.api_key == "EMPTY"


def test_build_gemini_strips_models_prefix():
    row = _make_llm_row(
        class_name="Gemini",
        options='{"model":"models/gemini-2.0-flash","api_key":"g"}',
    )
    _, cfg = _build(row)
    assert cfg.model == "gemini-2.0-flash"
    assert "generativelanguage.googleapis.com" in cfg.base_url


def test_build_azure_uses_deployment():
    row = _make_llm_row(
        class_name="AzureOpenAI",
        options='{"model":"gpt-4o","api_key":"k","azure_endpoint":"https://x.openai.azure.com","deployment_name":"my-dep"}',
    )
    provider, cfg = _build(row)
    assert isinstance(provider, AzureOpenAIProvider)
    assert cfg.model == "my-dep"


def test_build_bedrock_region_from_options():
    row = _make_llm_row(
        class_name="Bedrock",
        options='{"model":"anthropic.claude-3","region_name":"eu-west-1"}',
    )
    provider, cfg = _build(row)
    assert isinstance(provider, BedrockProvider)
    assert provider._region == "eu-west-1"
    assert cfg.api_key is None


def test_build_unknown_class_rejected_by_validation():
    """A class outside VALID_LLM_CLASSES fails Pydantic validation before the
    agent2 dispatch is even reached (the Agent2UnsupportedLLMError branch is
    only reachable for a class valid platform-wide but unhandled by agent2 —
    currently every valid class IS handled)."""
    import pydantic

    row = _make_llm_row(class_name="Groq", options="{}")
    with pytest.raises(pydantic.ValidationError) as exc:
        _build(row)
    assert "Groq" in str(exc.value)


def test_build_none_row_raises():
    with pytest.raises(Agent2ProviderError):
        build_provider_for_llm(None)


def test_provider_cache_key_handles_dict_options():
    row_a = _make_llm_row(options={"b": 2, "a": 1})
    row_b = _make_llm_row(options={"a": 1, "b": 2})
    # Sorted JSON dump makes key order irrelevant.
    assert _provider_cache_key(row_a) == _provider_cache_key(row_b)
