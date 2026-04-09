"""agent2 — RestAI agent runtime that does NOT depend on llamaindex.

Pure-Python ReAct-style agent loop built on top of raw provider SDKs
(`anthropic`, `openai`). Adapted from the standalone_agent reference and
wired to RestAI's existing tool registry, LLM database rows, guards, and
streaming protocol.
"""
from .agent import Agent2Error, Agent2Runtime, Agent2UnsupportedLLMError
from .mcp_client import MCPSessionPool
from .providers import ProviderConfig, build_provider_for_llm
from .tool_adapter import AdaptedTool, adapt_function_tools
from .types import (
    AgentEvent,
    AgentSession,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    user_text_message,
)

__all__ = [
    "Agent2Runtime",
    "Agent2Error",
    "Agent2UnsupportedLLMError",
    "Message",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "AgentEvent",
    "AgentSession",
    "user_text_message",
    "AdaptedTool",
    "adapt_function_tools",
    "build_provider_for_llm",
    "ProviderConfig",
    "MCPSessionPool",
]
