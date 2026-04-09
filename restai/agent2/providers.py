"""LLM provider implementations for agent2.

These are thin wrappers around the raw `anthropic` and `openai` SDKs. They
read configuration directly from RestAI's `LLMDatabase` rows (class_name +
options dict) and translate between agent2's `Message` representation and
the providers' wire formats.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Union
from uuid import uuid4

from .tool_adapter import AdaptedTool
from .types import ImageBlock, Message, TextBlock, ToolResultBlock, ToolUseBlock

logger = logging.getLogger(__name__)


class Agent2ProviderError(Exception):
    pass


class Agent2UnsupportedLLMError(Agent2ProviderError):
    pass


@dataclass
class ProviderConfig:
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_output_tokens: int = 4096
    temperature: Optional[float] = None
    context_window: Optional[int] = None


class Provider(ABC):
    @abstractmethod
    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> Message:
        ...

    async def stream_complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> AsyncIterator[Union[str, Message]]:
        """Yield text deltas as `str`, then the final assembled `Message`.

        Default implementation calls `complete()` and emits the full text as
        a single chunk followed by the message — provides a working (but
        non-streaming) fallback for providers that don't override.
        """
        msg = await self.complete(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            config=config,
        )
        text = msg.text_content()
        if text:
            yield text
        yield msg


def _build_user_payload(
    text_parts: list[str], image_parts: list[dict], has_image: bool
) -> dict:
    """OpenAI user message: list-form content when images are present, plain
    string otherwise. Used by both OpenAIProvider and its Azure subclass."""
    if not has_image:
        return {"role": "user", "content": "\n".join(text_parts)}
    content: list[dict] = []
    if text_parts:
        content.append({"type": "text", "text": "\n".join(text_parts)})
    content.extend(image_parts)
    return {"role": "user", "content": content}


# ====================== OpenAI / OpenAI-compatible ======================


class OpenAIProvider(Provider):
    """Works for OpenAI, Ollama, Groq, Grok, OpenAILike, LiteLLM — anything
    that exposes a `/v1/chat/completions` endpoint."""

    def __init__(self, config: ProviderConfig) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise Agent2ProviderError("openai package is required for OpenAIProvider") from e

        client_kwargs: dict = {"api_key": config.api_key or "not-needed"}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> Message:
        payload = self._serialize_messages(system_prompt, messages)
        kwargs: dict = {"model": config.model, "messages": payload}
        if tools:
            kwargs["tools"] = [self._serialize_tool(t) for t in tools]
            kwargs["tool_choice"] = "auto"
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        if config.max_output_tokens:
            kwargs["max_tokens"] = config.max_output_tokens

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0].message

        blocks = []
        content = choice.content
        if isinstance(content, str) and content:
            blocks.append(TextBlock(text=content))
        elif isinstance(content, list):
            text = "\n".join(
                getattr(item, "text", "")
                for item in content
                if getattr(item, "type", None) == "text"
            )
            if text:
                blocks.append(TextBlock(text=text))

        for tool_call in (getattr(choice, "tool_calls", None) or []):
            arguments = tool_call.function.arguments or "{}"
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = {"__raw_arguments": arguments}
            blocks.append(
                ToolUseBlock(
                    id=tool_call.id or f"call_{uuid4().hex}",
                    name=tool_call.function.name,
                    input=parsed,
                )
            )

        return Message(role="assistant", content=blocks)

    async def stream_complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> AsyncIterator[Union[str, Message]]:
        payload = self._serialize_messages(system_prompt, messages)
        kwargs: dict = {"model": config.model, "messages": payload, "stream": True}
        if tools:
            kwargs["tools"] = [self._serialize_tool(t) for t in tools]
            kwargs["tool_choice"] = "auto"
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        if config.max_output_tokens:
            kwargs["max_tokens"] = config.max_output_tokens

        text_parts: list[str] = []
        # OpenAI streams tool_calls fragmented by `index`; we accumulate
        # name + arguments per index and assemble ToolUseBlocks at the end.
        tool_acc: dict[int, dict] = {}

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                text_parts.append(text)
                yield text

            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc, "index", 0)
                slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments

        blocks: list = []
        if text_parts:
            blocks.append(TextBlock(text="".join(text_parts)))
        for slot in tool_acc.values():
            if not slot["name"]:
                continue
            try:
                parsed = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                parsed = {"__raw_arguments": slot["arguments"]}
            blocks.append(
                ToolUseBlock(
                    id=slot["id"] or f"call_{uuid4().hex}",
                    name=slot["name"],
                    input=parsed,
                )
            )

        yield Message(role="assistant", content=blocks)

    @staticmethod
    def _serialize_tool(tool: AdaptedTool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    @classmethod
    def _serialize_messages(
        cls, system_prompt: str, messages: Sequence[Message]
    ) -> list[dict]:
        payload: list[dict] = []
        if system_prompt:
            payload.append({"role": "system", "content": system_prompt})
        for message in messages:
            if message.role == "user":
                cls._append_user_message(payload, message)
            else:
                payload.append(cls._serialize_assistant_message(message))
        return payload

    @staticmethod
    def _append_user_message(payload: list[dict], message: Message) -> None:
        # OpenAI requires list-form content (text + image_url parts) when any
        # image is attached. Otherwise we keep the simple string form.
        has_image = any(isinstance(b, ImageBlock) for b in message.content)
        text_parts: list[str] = []
        image_parts: list[dict] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ImageBlock):
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{block.mime_type};base64,{block.data}"
                        },
                    }
                )
            elif isinstance(block, ToolResultBlock):
                if text_parts or image_parts:
                    payload.append(_build_user_payload(text_parts, image_parts, has_image))
                    text_parts = []
                    image_parts = []
                payload.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,
                        "content": block.content,
                    }
                )
        if text_parts or image_parts:
            payload.append(_build_user_payload(text_parts, image_parts, has_image))

    @staticmethod
    def _serialize_assistant_message(message: Message) -> dict:
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )
        payload: dict = {
            "role": "assistant",
            "content": "\n".join(text_parts) if text_parts else None,
        }
        if tool_calls:
            payload["tool_calls"] = tool_calls
        return payload


# ====================== Azure OpenAI ======================


class AzureOpenAIProvider(OpenAIProvider):
    """Azure OpenAI uses the same wire protocol as OpenAI but with a different
    client constructor (resource endpoint + deployment name + api-version).
    We inherit OpenAIProvider's serializers and only swap out the client.
    """

    def __init__(
        self,
        config: ProviderConfig,
        *,
        azure_endpoint: str,
        api_version: str,
        azure_deployment: Optional[str] = None,
    ) -> None:
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as e:
            raise Agent2ProviderError(
                "openai package is required for AzureOpenAIProvider"
            ) from e

        if not config.api_key:
            raise Agent2ProviderError("AzureOpenAI api_key is required")
        if not azure_endpoint:
            raise Agent2ProviderError("AzureOpenAI azure_endpoint is required")

        # Note: deliberately NOT calling super().__init__ — the parent would
        # construct an AsyncOpenAI; we need AsyncAzureOpenAI instead.
        client_kwargs: dict = {
            "api_key": config.api_key,
            "api_version": api_version,
            "azure_endpoint": azure_endpoint,
        }
        if azure_deployment:
            client_kwargs["azure_deployment"] = azure_deployment
        self._client = AsyncAzureOpenAI(**client_kwargs)


# ====================== Bedrock (Converse API) ======================


class BedrockProvider(Provider):
    """AWS Bedrock via the Converse API (supports tool calling natively).

    Uses `aioboto3` to talk to the bedrock-runtime service. Each `complete()`
    call opens a fresh boto client (cheap) and closes it on exit.
    """

    def __init__(
        self,
        config: ProviderConfig,
        *,
        region_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        profile_name: Optional[str] = None,
    ) -> None:
        try:
            import aioboto3
        except ImportError as e:
            raise Agent2ProviderError(
                "aioboto3 is required for BedrockProvider"
            ) from e

        self._region = region_name
        session_kwargs: dict = {}
        if aws_access_key_id:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key
        if aws_session_token:
            session_kwargs["aws_session_token"] = aws_session_token
        if profile_name:
            session_kwargs["profile_name"] = profile_name
        self._session = aioboto3.Session(**session_kwargs)

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> Message:
        async with self._session.client(
            "bedrock-runtime", region_name=self._region
        ) as client:
            kwargs: dict = {
                "modelId": config.model,
                "messages": [self._serialize_message(m) for m in messages],
            }
            if system_prompt:
                kwargs["system"] = [{"text": system_prompt}]
            if tools:
                kwargs["toolConfig"] = {
                    "tools": [self._serialize_tool(t) for t in tools]
                }

            inference_config: dict = {}
            if config.max_output_tokens:
                inference_config["maxTokens"] = config.max_output_tokens
            if config.temperature is not None:
                inference_config["temperature"] = config.temperature
            if inference_config:
                kwargs["inferenceConfig"] = inference_config

            response = await client.converse(**kwargs)
            return self._parse_response(response)

    @staticmethod
    def _serialize_tool(tool: AdaptedTool) -> dict:
        return {
            "toolSpec": {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {"json": tool.input_schema},
            }
        }

    @classmethod
    def _serialize_message(cls, message: Message) -> dict:
        return {
            "role": message.role,
            "content": [cls._serialize_block(b) for b in message.content],
        }

    @staticmethod
    def _serialize_block(block) -> dict:
        if isinstance(block, TextBlock):
            return {"text": block.text}
        if isinstance(block, ImageBlock):
            import base64 as _b64
            # Bedrock Converse expects raw bytes + a short format string.
            fmt = block.mime_type.split("/", 1)[-1].lower()
            if fmt == "jpg":
                fmt = "jpeg"
            return {
                "image": {
                    "format": fmt,
                    "source": {"bytes": _b64.b64decode(block.data)},
                }
            }
        if isinstance(block, ToolUseBlock):
            return {
                "toolUse": {
                    "toolUseId": block.id,
                    "name": block.name,
                    "input": block.input or {},
                }
            }
        if isinstance(block, ToolResultBlock):
            return {
                "toolResult": {
                    "toolUseId": block.tool_use_id,
                    "content": [{"text": block.content or ""}],
                    "status": "error" if block.is_error else "success",
                }
            }
        raise TypeError(f"Unknown block type for Bedrock: {type(block)}")

    @staticmethod
    def _parse_response(response: dict) -> Message:
        out_msg = (response or {}).get("output", {}).get("message", {})
        blocks: list = []
        for c in out_msg.get("content", []) or []:
            if "text" in c and c["text"]:
                blocks.append(TextBlock(text=c["text"]))
            elif "toolUse" in c:
                tu = c["toolUse"]
                blocks.append(
                    ToolUseBlock(
                        id=tu.get("toolUseId") or f"call_{uuid4().hex}",
                        name=tu.get("name", ""),
                        input=dict(tu.get("input") or {}),
                    )
                )
        return Message(role="assistant", content=blocks)


# ====================== Anthropic ======================


class AnthropicProvider(Provider):
    def __init__(self, config: ProviderConfig) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise Agent2ProviderError("anthropic package is required for AnthropicProvider") from e

        if not config.api_key:
            raise Agent2ProviderError("ANTHROPIC_API_KEY (or options.api_key) is required for AnthropicProvider")

        client_kwargs: dict = {"api_key": config.api_key}
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self._client = AsyncAnthropic(**client_kwargs)

    async def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> Message:
        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_output_tokens,
            "messages": [self._serialize_message(m) for m in messages],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [self._serialize_tool(t) for t in tools]
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        response = await self._client.messages.create(**kwargs)

        blocks = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                blocks.append(TextBlock(text=getattr(block, "text", "")))
            elif block_type == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=getattr(block, "id", f"call_{uuid4().hex}"),
                        name=getattr(block, "name", ""),
                        input=dict(getattr(block, "input", {}) or {}),
                    )
                )

        return Message(role="assistant", content=blocks)

    async def stream_complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Message],
        tools: Sequence[AdaptedTool],
        config: ProviderConfig,
    ) -> AsyncIterator[Union[str, Message]]:
        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_output_tokens,
            "messages": [self._serialize_message(m) for m in messages],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = [self._serialize_tool(t) for t in tools]
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature

        # Anthropic's `messages.stream(...)` is an async context manager that
        # exposes `text_stream` for incremental deltas plus `get_final_message()`
        # for the fully-assembled response (text + tool_use blocks).
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text
            final = await stream.get_final_message()

        blocks: list = []
        for block in final.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                blocks.append(TextBlock(text=getattr(block, "text", "")))
            elif block_type == "tool_use":
                blocks.append(
                    ToolUseBlock(
                        id=getattr(block, "id", f"call_{uuid4().hex}"),
                        name=getattr(block, "name", ""),
                        input=dict(getattr(block, "input", {}) or {}),
                    )
                )
        yield Message(role="assistant", content=blocks)

    @staticmethod
    def _serialize_tool(tool: AdaptedTool) -> dict:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    @classmethod
    def _serialize_message(cls, message: Message) -> dict:
        return {
            "role": message.role,
            "content": [cls._serialize_block(b) for b in message.content],
        }

    @staticmethod
    def _serialize_block(block) -> dict:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ImageBlock):
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": block.mime_type,
                    "data": block.data,
                },
            }
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        if isinstance(block, ToolResultBlock):
            return {
                "type": "tool_result",
                "tool_use_id": block.tool_use_id,
                "content": block.content,
                "is_error": block.is_error,
            }
        raise TypeError(f"Unknown block type: {type(block)}")


# ====================== Provider factory ======================


# Cache: keyed by (class_name, options-string, context_window) so the cache
# entry naturally invalidates when an LLM is edited via the admin UI (the new
# DB row produces a different key, missing the cache and rebuilding). The
# stale entry stays in memory until process restart — bounded by edit
# frequency, acceptable.
_provider_cache: dict[tuple, tuple["Provider", "ProviderConfig"]] = {}


def _provider_cache_key(llm_db_row: Any) -> tuple:
    raw_options = getattr(llm_db_row, "options", "") or ""
    if not isinstance(raw_options, str):
        try:
            raw_options = json.dumps(raw_options, sort_keys=True)
        except Exception:
            raw_options = str(raw_options)
    return (
        getattr(llm_db_row, "class_name", "") or "",
        raw_options,
        getattr(llm_db_row, "context_window", None) or 0,
    )


def build_provider_for_llm(llm_db_row: Any) -> tuple[Provider, ProviderConfig]:
    """Build an agent2 Provider + ProviderConfig from a RestAI LLMDatabase row.

    Cached on `(class_name, options, context_window)` — calls with the same
    LLM row reuse the same Provider instance (and its underlying SDK client +
    HTTP connection pool), saving ~13ms per call plus enabling HTTP keep-alive.
    """
    if llm_db_row is None:
        raise Agent2ProviderError("LLM database row is None")

    cache_key = _provider_cache_key(llm_db_row)
    cached = _provider_cache.get(cache_key)
    if cached is not None:
        return cached

    result = _build_provider_for_llm_uncached(llm_db_row)
    _provider_cache[cache_key] = result
    return result


def _build_provider_for_llm_uncached(llm_db_row: Any) -> tuple[Provider, ProviderConfig]:
    """Uncached implementation. Called by `build_provider_for_llm` on cache miss."""
    from restai.models.models import LLMModel

    llm_model = LLMModel.model_validate(llm_db_row)
    class_name = llm_model.class_name or ""
    options = llm_model.options or {}

    model = options.get("model") or options.get("model_name") or ""
    api_key = options.get("api_key")
    base_url = options.get("base_url") or options.get("api_base")
    temperature = options.get("temperature")
    max_tokens = int(options.get("max_tokens") or 4096)
    context_window = llm_model.context_window

    if class_name in ("OpenAI",):
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
        cfg = ProviderConfig(
            model=model or "gpt-4o-mini",
            api_key=api_key,
            base_url=base_url,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name in ("OpenAILike", "LiteLLM"):
        cfg = ProviderConfig(
            model=model,
            api_key=api_key or os.environ.get("OPENAI_API_KEY") or "not-needed",
            base_url=base_url,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name in ("Ollama", "OllamaMultiModal", "OllamaMultiModal2"):
        # Ollama exposes an OpenAI-compatible /v1 endpoint
        ollama_base = base_url or "http://localhost:11434"
        if not ollama_base.rstrip("/").endswith("/v1"):
            ollama_base = ollama_base.rstrip("/") + "/v1"
        cfg = ProviderConfig(
            model=model,
            api_key="ollama",
            base_url=ollama_base,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name == "Groq":
        cfg = ProviderConfig(
            model=model,
            api_key=api_key or os.environ.get("GROQ_API_KEY"),
            base_url=base_url or "https://api.groq.com/openai/v1",
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name == "Grok":
        cfg = ProviderConfig(
            model=model or "grok-beta",
            api_key=api_key or os.environ.get("XAI_API_KEY"),
            base_url=base_url or "https://api.x.ai/v1",
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name == "Anthropic":
        cfg = ProviderConfig(
            model=model or "claude-3-5-sonnet-latest",
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url=base_url,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return AnthropicProvider(cfg), cfg

    if class_name == "vLLM":
        # vLLM exposes a native OpenAI-compatible /v1 endpoint
        vllm_url = (
            options.get("api_url")
            or options.get("api_base")
            or base_url
            or "http://localhost:8000/v1"
        )
        if not vllm_url.rstrip("/").endswith("/v1"):
            vllm_url = vllm_url.rstrip("/") + "/v1"
        cfg = ProviderConfig(
            model=model,
            api_key=api_key or "EMPTY",
            base_url=vllm_url,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name in ("Gemini", "GeminiMultiModal"):
        # Google's Gemini exposes an OpenAI-compatible endpoint that supports
        # tool calling. Strip the optional "models/" prefix llamaindex sometimes uses.
        gemini_model = model
        if gemini_model.startswith("models/"):
            gemini_model = gemini_model[len("models/") :]
        cfg = ProviderConfig(
            model=gemini_model or "gemini-2.0-flash",
            api_key=(
                api_key
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
            ),
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai/",
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return OpenAIProvider(cfg), cfg

    if class_name == "AzureOpenAI":
        azure_endpoint = (
            options.get("azure_endpoint")
            or options.get("base_url")
            or os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        api_version = (
            options.get("api_version")
            or os.environ.get("OPENAI_API_VERSION")
            or "2024-08-01-preview"
        )
        # Azure routes by deployment name, not by model name. Fall back to the
        # 'model' field for backwards compatibility with how it's stored today.
        deployment = (
            options.get("azure_deployment")
            or options.get("deployment_name")
            or options.get("engine")
            or model
        )
        cfg = ProviderConfig(
            model=deployment,
            api_key=api_key or os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=azure_endpoint,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return (
            AzureOpenAIProvider(
                cfg,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                azure_deployment=deployment,
            ),
            cfg,
        )

    if class_name == "Bedrock":
        region = (
            options.get("region_name")
            or options.get("aws_region")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        cfg = ProviderConfig(
            model=model,
            api_key=None,
            base_url=None,
            max_output_tokens=max_tokens,
            temperature=temperature,
            context_window=context_window,
        )
        return (
            BedrockProvider(
                cfg,
                region_name=region,
                aws_access_key_id=options.get("aws_access_key_id"),
                aws_secret_access_key=options.get("aws_secret_access_key"),
                aws_session_token=options.get("aws_session_token"),
                profile_name=options.get("profile_name"),
            ),
            cfg,
        )

    raise Agent2UnsupportedLLMError(
        f"agent2 does not support LLM class '{class_name}' yet. "
        "Supported: OpenAI, OpenAILike, LiteLLM, Ollama, OllamaMultiModal, "
        "OllamaMultiModal2, Groq, Grok, Anthropic, vLLM, Gemini, "
        "GeminiMultiModal, AzureOpenAI, Bedrock."
    )
