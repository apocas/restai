"""Tests for restai.agent2.types — block types, serialization, image MIME detection."""
import base64

from restai.agent2.types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    block_from_dict,
    block_to_dict,
    detect_image_mime,
    message_from_dict,
    message_to_dict,
    user_text_message,
)


# ---------- construction ----------


def test_text_block_construction():
    b = TextBlock(text="hello")
    assert b.text == "hello"


def test_tool_use_block_construction():
    b = ToolUseBlock(id="t1", name="search", input={"q": "test"})
    assert b.id == "t1"
    assert b.name == "search"
    assert b.input == {"q": "test"}


def test_tool_result_block_construction():
    b = ToolResultBlock(tool_use_id="t1", content="result text")
    assert b.tool_use_id == "t1"
    assert b.content == "result text"
    assert b.is_error is False


def test_tool_result_block_error():
    b = ToolResultBlock(tool_use_id="t1", content="oops", is_error=True)
    assert b.is_error is True


def test_image_block_construction():
    b = ImageBlock(data="abc123", mime_type="image/png")
    assert b.data == "abc123"
    assert b.mime_type == "image/png"


# ---------- Message.text_content ----------


def test_message_text_content_joins_text_blocks():
    msg = Message(
        role="user",
        content=[TextBlock(text="hello"), TextBlock(text="world")],
    )
    assert msg.text_content() == "hello\nworld"


def test_message_text_content_ignores_non_text_blocks():
    msg = Message(
        role="assistant",
        content=[
            TextBlock(text="start"),
            ToolUseBlock(id="t1", name="x", input={}),
            TextBlock(text="end"),
        ],
    )
    assert msg.text_content() == "start\nend"


def test_message_text_content_empty():
    msg = Message(role="user", content=[])
    assert msg.text_content() == ""


# ---------- block_to_dict / block_from_dict round-trip ----------


def test_text_block_roundtrip():
    original = TextBlock(text="hello world")
    d = block_to_dict(original)
    assert d["type"] == "text"
    restored = block_from_dict(d)
    assert isinstance(restored, TextBlock)
    assert restored.text == original.text


def test_tool_use_block_roundtrip():
    original = ToolUseBlock(id="abc", name="search", input={"q": "test"})
    d = block_to_dict(original)
    assert d["type"] == "tool_use"
    restored = block_from_dict(d)
    assert isinstance(restored, ToolUseBlock)
    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.input == original.input


def test_tool_result_block_roundtrip():
    original = ToolResultBlock(tool_use_id="abc", content="done", is_error=True)
    d = block_to_dict(original)
    assert d["type"] == "tool_result"
    restored = block_from_dict(d)
    assert isinstance(restored, ToolResultBlock)
    assert restored.tool_use_id == original.tool_use_id
    assert restored.content == original.content
    assert restored.is_error == original.is_error


def test_image_block_roundtrip():
    original = ImageBlock(data="iVBOR", mime_type="image/png")
    d = block_to_dict(original)
    assert d["type"] == "image"
    restored = block_from_dict(d)
    assert isinstance(restored, ImageBlock)
    assert restored.data == original.data
    assert restored.mime_type == original.mime_type


# ---------- message_to_dict / message_from_dict round-trip ----------


def test_message_roundtrip():
    original = Message(
        role="assistant",
        content=[
            TextBlock(text="thinking..."),
            ToolUseBlock(id="t1", name="calc", input={"expr": "1+1"}),
        ],
    )
    d = message_to_dict(original)
    assert d["role"] == "assistant"
    assert len(d["content"]) == 2
    restored = message_from_dict(d)
    assert restored.role == original.role
    assert len(restored.content) == 2
    assert isinstance(restored.content[0], TextBlock)
    assert isinstance(restored.content[1], ToolUseBlock)
    assert restored.content[0].text == "thinking..."
    assert restored.content[1].name == "calc"


# ---------- detect_image_mime ----------


def test_detect_image_mime_png():
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 56
    b64 = base64.b64encode(raw).decode()
    assert detect_image_mime(b64) == "image/png"


def test_detect_image_mime_jpeg():
    raw = b"\xff\xd8\xff" + b"\x00" * 61
    b64 = base64.b64encode(raw).decode()
    assert detect_image_mime(b64) == "image/jpeg"


def test_detect_image_mime_gif():
    raw = b"GIF89a" + b"\x00" * 58
    b64 = base64.b64encode(raw).decode()
    assert detect_image_mime(b64) == "image/gif"


def test_detect_image_mime_unknown_fallback():
    raw = b"\x00\x01\x02\x03" + b"\x00" * 60
    b64 = base64.b64encode(raw).decode()
    assert detect_image_mime(b64) == "image/png"


# ---------- ImageBlock.from_data_url ----------


def test_image_block_from_data_url_with_prefix():
    raw = b"\xff\xd8\xff" + b"\x00" * 61
    b64 = base64.b64encode(raw).decode()
    url = f"data:image/jpeg;base64,{b64}"
    block = ImageBlock.from_data_url(url)
    assert block.mime_type == "image/jpeg"
    assert block.data == b64


def test_image_block_from_data_url_plain_base64():
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00" * 56
    b64 = base64.b64encode(raw).decode()
    block = ImageBlock.from_data_url(b64)
    assert block.mime_type == "image/png"
    assert block.data == b64


# ---------- user_text_message helper ----------


def test_user_text_message():
    msg = user_text_message("hi there")
    assert msg.role == "user"
    assert len(msg.content) == 1
    assert isinstance(msg.content[0], TextBlock)
    assert msg.content[0].text == "hi there"
