"""Ollama Cloud (https://ollama.com) LLM wrapper.

Thin subclass of llama-index's `Ollama` that knows how to talk to the
hosted Ollama Cloud service. Cloud auth differs from a local daemon in
exactly one way — every request needs an `Authorization: Bearer <key>`
header — but the underlying `Ollama` class doesn't expose a `headers` /
`api_key` kwarg of its own. It does accept a pre-built `client` /
`async_client`, so we build authenticated `ollama.Client` instances at
init time and hand them in.

Keeping this in `restai/llms/` (next to `OllamaMultiModalInternal`)
instead of branching inside `Brain.load_llm` keeps the load path
class-name → instantiate symmetric across providers — no special cases
in the orchestrator that have to grow every time a new "X Cloud"
variant ships.
"""
from typing import Any, Optional

from ollama import AsyncClient, Client
from llama_index.llms.ollama import Ollama

DEFAULT_CLOUD_BASE_URL = "https://ollama.com"
DEFAULT_REQUEST_TIMEOUT = 120.0


class OllamaCloud(Ollama):
    """Ollama LLM authenticated against Ollama Cloud.

    Stored in the LLM `options` blob:

        {
            "model": "gpt-oss:120b-cloud",
            "api_key": "<ollama_...>",      # required, encrypted at rest
            "base_url": "https://ollama.com" # optional override
            # ...standard Ollama kwargs
        }

    `api_key` is in `LLM_SENSITIVE_KEYS`, so DBWrapper encrypts it with
    Fernet on write and decrypts on read.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = DEFAULT_CLOUD_BASE_URL,
        request_timeout: Optional[float] = DEFAULT_REQUEST_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        if not api_key:
            raise ValueError(
                "OllamaCloud requires an `api_key`. Set one in the LLM "
                "options or import the model via the Ollama Cloud tab on "
                "the import page."
            )
        headers = {"Authorization": f"Bearer {api_key}"}
        timeout = request_timeout or DEFAULT_REQUEST_TIMEOUT
        client = Client(host=base_url, headers=headers, timeout=timeout)
        async_client = AsyncClient(host=base_url, headers=headers, timeout=timeout)
        super().__init__(
            model=model,
            base_url=base_url,
            request_timeout=timeout,
            client=client,
            async_client=async_client,
            **kwargs,
        )

    @classmethod
    def class_name(cls) -> str:
        return "OllamaCloud_llm"
