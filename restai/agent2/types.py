"""Pure-data types for the agent2 runtime. No llamaindex imports."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Literal, Union

MessageRole = Literal["user", "assistant"]


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class ImageBlock:
    """A base64-encoded image attached to a user message.

    `data` is the raw base64 string (no data URL prefix). `mime_type` is the
    standard MIME (e.g. 'image/png', 'image/jpeg'). Use `from_data_url()` or
    `from_base64()` to construct one with auto-detection.
    """
    data: str
    mime_type: str

    @classmethod
    def from_data_url(cls, url: str) -> "ImageBlock":
        # data:image/png;base64,iVBORw0KG...
        if url.startswith("data:") and ";base64," in url:
            header, _, body = url.partition(";base64,")
            mime = header[len("data:"):] or "image/png"
            return cls(data=body, mime_type=mime)
        # Plain base64 — sniff
        return cls.from_base64(url)

    @classmethod
    def from_base64(cls, b64: str) -> "ImageBlock":
        return cls(data=b64, mime_type=detect_image_mime(b64))


def detect_image_mime(b64_data: str) -> str:
    """Sniff the MIME type from the leading bytes of a base64-encoded image.

    Falls back to 'image/png' if the magic bytes don't match anything known.
    """
    try:
        head = base64.b64decode(b64_data[:64], validate=False)
    except Exception:
        return "image/png"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ImageBlock]


@dataclass
class Message:
    role: MessageRole
    content: list

    def text_content(self) -> str:
        return "\n".join(
            block.text for block in self.content if isinstance(block, TextBlock)
        ).strip()


@dataclass
class AgentSession:
    messages: list = field(default_factory=list)
    turn_count: int = 0
    state: dict = field(default_factory=dict)


@dataclass
class AgentEvent:
    type: Literal["assistant", "tool_result", "final", "text_delta"]
    message: Union[Message, None] = None
    turn: int = 0
    data: dict = field(default_factory=dict)


def user_text_message(text: str) -> Message:
    return Message(role="user", content=[TextBlock(text=text)])


# ---------- JSON serialization (for memory persistence) ----------


def block_to_dict(block: ContentBlock) -> dict:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
        }
    if isinstance(block, ImageBlock):
        return {"type": "image", "data": block.data, "mime_type": block.mime_type}
    raise TypeError(f"Unknown block type: {type(block)}")


def block_from_dict(d: dict) -> ContentBlock:
    t = d.get("type")
    if t == "text":
        return TextBlock(text=d.get("text", ""))
    if t == "tool_use":
        return ToolUseBlock(id=d["id"], name=d["name"], input=d.get("input", {}))
    if t == "tool_result":
        return ToolResultBlock(
            tool_use_id=d["tool_use_id"],
            content=d.get("content", ""),
            is_error=bool(d.get("is_error", False)),
        )
    if t == "image":
        return ImageBlock(data=d.get("data", ""), mime_type=d.get("mime_type", "image/png"))
    raise ValueError(f"Unknown block dict: {d!r}")


def message_to_dict(msg: Message) -> dict:
    return {"role": msg.role, "content": [block_to_dict(b) for b in msg.content]}


def message_from_dict(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=[block_from_dict(b) for b in d.get("content", [])],
    )
