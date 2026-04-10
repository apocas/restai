"""Tests for agent2 provider factory and caching."""

import types

import pytest

from restai.agent2.providers import (
    Agent2UnsupportedLLMError,
    AnthropicProvider,
    OpenAIProvider,
    ProviderConfig,
    _provider_cache,
    _provider_cache_key,
    build_provider_for_llm,
)


def _make_llm_row(
    name="test",
    class_name="OpenAI",
    options='{"model":"gpt-4o","api_key":"sk-fake"}',
    context_window=4096,
    privacy="public",
    description=None,
    input_cost=0.0,
    output_cost=0.0,
):
    return types.SimpleNamespace(
        id=1,
        name=name,
        class_name=class_name,
        options=options,
        context_window=context_window,
        privacy=privacy,
        description=description,
        input_cost=input_cost,
        output_cost=output_cost,
        teams=[],
    )


def _clear_cache_for_row(row):
    """Remove a specific row's entry from the provider cache."""
    key = _provider_cache_key(row)
    _provider_cache.pop(key, None)


def test_provider_config_construction():
    cfg = ProviderConfig(model="gpt-4o", api_key="sk-test")
    assert cfg.model == "gpt-4o"
    assert cfg.api_key == "sk-test"
    assert cfg.max_output_tokens == 4096
    assert cfg.base_url is None


def test_build_provider_openai():
    row = _make_llm_row(class_name="OpenAI")
    _clear_cache_for_row(row)
    provider, cfg = build_provider_for_llm(row)
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(cfg, ProviderConfig)
    assert cfg.model == "gpt-4o"
    _clear_cache_for_row(row)


def test_build_provider_anthropic():
    row = _make_llm_row(
        class_name="Anthropic",
        options='{"model":"claude-3-5-sonnet-latest","api_key":"sk-ant-fake"}',
    )
    _clear_cache_for_row(row)
    provider, cfg = build_provider_for_llm(row)
    assert isinstance(provider, AnthropicProvider)
    assert cfg.api_key == "sk-ant-fake"
    _clear_cache_for_row(row)


def test_build_provider_ollama():
    row = _make_llm_row(
        class_name="Ollama",
        options='{"model":"llama3","base_url":"http://localhost:11434"}',
    )
    _clear_cache_for_row(row)
    provider, cfg = build_provider_for_llm(row)
    assert isinstance(provider, OpenAIProvider)
    assert cfg.base_url.endswith("/v1")
    _clear_cache_for_row(row)


def test_build_provider_unsupported():
    row = _make_llm_row(class_name="FakeProvider")
    _clear_cache_for_row(row)
    with pytest.raises(Exception):
        # class_name validation in LLMModel will reject "FakeProvider"
        build_provider_for_llm(row)


def test_provider_cache_hit():
    row = _make_llm_row(
        name="cache_test",
        class_name="OpenAI",
        options='{"model":"gpt-4o-mini","api_key":"sk-cache"}',
    )
    _clear_cache_for_row(row)
    provider1, cfg1 = build_provider_for_llm(row)
    provider2, cfg2 = build_provider_for_llm(row)
    assert id(provider1) == id(provider2), "Expected same provider instance from cache"
    assert id(cfg1) == id(cfg2), "Expected same config instance from cache"
    _clear_cache_for_row(row)


def test_provider_cache_key_consistency():
    row = _make_llm_row()
    key1 = _provider_cache_key(row)
    key2 = _provider_cache_key(row)
    assert key1 == key2
    assert isinstance(key1, tuple)


def test_provider_config_context_window():
    row = _make_llm_row(context_window=128000)
    _clear_cache_for_row(row)
    _, cfg = build_provider_for_llm(row)
    assert cfg.context_window == 128000
    _clear_cache_for_row(row)
