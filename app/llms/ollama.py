from llama_index.llms.ollama import Ollama

from typing import Any, Sequence


from llama_index.core.bridge.pydantic import Field
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen,
)
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback

class Ollama(Ollama):
    system: str = Field(
        default="", description="Default system message to send to the model."
    )

    request_timeout: float = 120.0


    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        if self.system and len(messages) > 0 and messages[0].role != "system":
            messages.insert(
                0, ChatMessage(role="system", content=self.system)
            )
        kwargs["keep_alive"] = self.keep_alive
        return super().chat(messages, **kwargs)
    
    @llm_chat_callback()
    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        if self.system and len(messages) > 0 and messages[0].role != "system":
            messages.insert(
                0, ChatMessage(role="system", content=self.system)
            )
        kwargs["keep_alive"] = self.keep_alive
        yield from super().stream_chat(messages, **kwargs)
    
    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        if self.system:
            kwargs["system"] = self.system
        kwargs["keep_alive"] = self.keep_alive
        return super().complete(prompt, formatted, **kwargs)
    
    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseGen:
        if self.system:
            kwargs["system"] = self.system
        kwargs["keep_alive"] = self.keep_alive
        yield from super().stream_complete(prompt, formatted, **kwargs)