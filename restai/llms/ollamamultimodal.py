from typing import Any, Sequence

from pydantic import Field
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseGen,
    MessageRole,
)
from llama_index.core.schema import ImageNode
from llama_index.core.base.llms.types import ImageBlock, TextBlock
from llama_index.multi_modal_llms.ollama import OllamaMultiModal


class OllamaMultiModalInternal(OllamaMultiModal):
    system: str = Field(
        default="", description="Default system message to send to the model."
    )

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        if self.system and len(messages) > 0 and messages[0].role != MessageRole.SYSTEM:
            messages = list(messages)
            messages.insert(
                0, ChatMessage(role=MessageRole.SYSTEM, content=self.system)
            )
        return super().chat(messages, **kwargs)

    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseGen:
        if self.system and len(messages) > 0 and messages[0].role != MessageRole.SYSTEM:
            messages = list(messages)
            messages.insert(
                0, ChatMessage(role=MessageRole.SYSTEM, content=self.system)
            )
        return super().stream_chat(messages, **kwargs)
