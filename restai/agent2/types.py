"""Pure-data types for the agent2 runtime. No llamaindex imports."""
from __future__ import annotations

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


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock]


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
    type: Literal["assistant", "tool_result", "final"]
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
    raise ValueError(f"Unknown block dict: {d!r}")


def message_to_dict(msg: Message) -> dict:
    return {"role": msg.role, "content": [block_to_dict(b) for b in msg.content]}


def message_from_dict(d: dict) -> Message:
    return Message(
        role=d["role"],
        content=[block_from_dict(b) for b in d.get("content", [])],
    )
