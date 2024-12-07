from typing import Any, MutableSequence

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen, MessageRole,
)
from llama_index.core.bridge.pydantic import Field
from llama_index.core.llms.callbacks import llm_chat_callback, llm_completion_callback
from llama_index.llms.ollama import Ollama as ImportedOllama


class Ollama(ImportedOllama):
    system: str = Field(
        default="", description="Default system message to send to the model."
    )

    request_timeout: float = 120.0


    @llm_chat_callback()
    def chat(self, messages: MutableSequence[ChatMessage], **kwargs: Any):
        if self.system and len(messages) > 0 and messages[0].role != MessageRole.SYSTEM:
            messages.insert(
                0, ChatMessage(role=MessageRole.SYSTEM, content=self.system)
            )
        kwargs["keep_alive"] = self.keep_alive
        return super().chat(messages, **kwargs)
    
    @llm_chat_callback()
    def stream_chat(self, messages: MutableSequence[ChatMessage], **kwargs: Any) -> ChatResponseGen:
        if self.system and len(messages) > 0 and messages[0].role != MessageRole.SYSTEM:
            messages.insert(
                0, ChatMessage(role=MessageRole.SYSTEM, content=self.system)
            )
        kwargs["keep_alive"] = self.keep_alive
        yield from super().stream_chat(messages, **kwargs)
    
    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        if self.system:
            kwargs[MessageRole.SYSTEM] = self.system
        kwargs["keep_alive"] = self.keep_alive
        return super().complete(prompt, formatted, **kwargs)
    
    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseGen:
        if self.system:
            kwargs[MessageRole.SYSTEM] = self.system
        kwargs["keep_alive"] = self.keep_alive
        yield from super().stream_complete(prompt, formatted, **kwargs)