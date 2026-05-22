"""Ollama Cloud LLM wrapper.

llama-index's Ollama class doesn't expose `headers`/`api_key` kwargs but
accepts a pre-built `client`/`async_client`, so we build authenticated
ollama.Client instances at init time and hand them in.
"""
from typing import Any, Optional

from ollama import AsyncClient, Client
from llama_index.llms.ollama import Ollama

DEFAULT_CLOUD_BASE_URL = "https://ollama.com"
DEFAULT_REQUEST_TIMEOUT = 120.0


class OllamaCloud(Ollama):
    """Ollama LLM authenticated against Ollama Cloud. api_key is Fernet-encrypted at rest."""

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
