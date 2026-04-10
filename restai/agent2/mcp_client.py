"""MCP (Model Context Protocol) integration for agent2.

Uses the raw `mcp` Python SDK directly — no llamaindex involvement. The
existing agent type uses `llama_index.tools.mcp.BasicMCPClient` and
`McpToolSpec`; agent2 talks to the same MCP servers via the underlying
`mcp.client.session.ClientSession` and the various transports
(`sse_client`, `stdio_client`, `streamablehttp_client`).

Sessions are stateful and use async context managers, so we use
`AsyncExitStack` to keep them alive for the duration of an agent run and
clean them up regardless of how the run terminates.
"""
from __future__ import annotations

import contextlib
import json
import logging
from typing import Any, Iterable, Optional

from .tool_adapter import AdaptedTool

logger = logging.getLogger(__name__)


ALLOWED_MCP_STDIO_COMMANDS = {"npx", "uvx", "python", "python3", "node", "deno", "bun"}


def _is_http_host(host: str) -> bool:
    return host.startswith(("http://", "https://"))


def _validate_stdio_host(host: str, args: list = None):
    """Validate stdio MCP command — only allow known safe executables."""
    import os as _os
    import re as _re
    cmd = _os.path.basename(host)
    if cmd not in ALLOWED_MCP_STDIO_COMMANDS:
        raise ValueError(
            f"MCP stdio command '{cmd}' is not allowed. "
            f"Permitted: {', '.join(sorted(_ALLOWED_STDIO_COMMANDS))}"
        )
    if args:
        for arg in args:
            if _re.search(r'[;&|`$(){}]', str(arg)):
                raise ValueError(f"MCP argument contains disallowed characters: {arg}")


def _parse_allowed_tools(csv: Optional[str]) -> Optional[set[str]]:
    if not csv:
        return None
    parts = {t.strip() for t in csv.split(",") if t.strip()}
    return parts or None


class MCPSessionPool:
    """Holds open MCP sessions for the duration of one agent2 run.

    Use as an async context manager:

        async with MCPSessionPool() as pool:
            tools = await pool.connect_servers(servers_config)
            ...

    All sessions are closed automatically on exit (success or exception).
    """

    def __init__(self) -> None:
        self._stack = contextlib.AsyncExitStack()
        self._sessions: list = []

    async def __aenter__(self) -> "MCPSessionPool":
        await self._stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await self._stack.__aexit__(exc_type, exc, tb)
        except Exception as e:
            logger.warning("Error while closing MCP sessions: %s", e)

    async def connect_servers(self, servers: Iterable[Any]) -> list[AdaptedTool]:
        """Connect to every configured MCP server and return their tools as
        AdaptedTools, ready to be merged with the built-in tool list.

        Each `server` is expected to expose `host`, `args`, `env`, `headers`,
        and `tools` attributes (matching `restai.models.models.MCPServer`).
        Connection failures for individual servers are logged but do not abort
        the run — agent2 will simply have fewer tools.
        """
        adapted: list[AdaptedTool] = []
        for srv in servers or []:
            host = getattr(srv, "host", None)
            if not host:
                continue
            args = getattr(srv, "args", None) or []
            env = getattr(srv, "env", None) or None
            headers = getattr(srv, "headers", None) or None
            allowed = _parse_allowed_tools(getattr(srv, "tools", None))

            try:
                if _is_http_host(host):
                    session = await self._open_http_session(host, headers)
                else:
                    _validate_stdio_host(host, args)
                    session = await self._open_stdio_session(host, args, env)
            except Exception as e:
                logger.warning("Failed to open MCP session for '%s': %s", host, e)
                continue

            try:
                server_tools = await self._list_session_tools(session, allowed)
            except Exception as e:
                logger.warning("Failed to list MCP tools from '%s': %s", host, e)
                continue

            adapted.extend(server_tools)

        return adapted

    # ---------- transport helpers ----------

    async def _open_http_session(self, url: str, headers: Optional[dict]):
        """Try streamable HTTP first (newer MCP transport) and fall back to SSE."""
        from mcp.client.session import ClientSession

        # Streamable HTTP — preferred for new servers
        try:
            from mcp.client.streamable_http import streamablehttp_client

            ctx = streamablehttp_client(url, headers=headers or None)
            transport = await self._stack.enter_async_context(ctx)
            # streamablehttp_client yields (read, write) or (read, write, get_session_id)
            read, write = transport[0], transport[1]
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions.append(session)
            return session
        except Exception as http_err:
            logger.debug("streamable HTTP failed for %s, trying SSE: %s", url, http_err)

        # SSE — older MCP transport
        from mcp.client.sse import sse_client

        ctx = sse_client(url, headers=headers or None)
        read, write = await self._stack.enter_async_context(ctx)
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions.append(session)
        return session

    async def _open_stdio_session(self, command: str, args: list, env: Optional[dict]):
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(command=command, args=list(args or []), env=env)
        ctx = stdio_client(params)
        read, write = await self._stack.enter_async_context(ctx)
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions.append(session)
        return session

    # ---------- tool listing / wrapping ----------

    async def _list_session_tools(self, session, allowed: Optional[set[str]]) -> list[AdaptedTool]:
        result = await session.list_tools()
        adapted: list[AdaptedTool] = []
        for tool in getattr(result, "tools", []) or []:
            name = getattr(tool, "name", None)
            if not name:
                continue
            if allowed and name not in allowed:
                continue
            description = getattr(tool, "description", None) or name
            input_schema = getattr(tool, "inputSchema", None) or {
                "type": "object",
                "properties": {},
            }
            adapted.append(_make_mcp_adapted_tool(session, name, description, input_schema))
        return adapted


def _flatten_mcp_content(content) -> str:
    """Convert an MCP CallToolResult.content list into a plain text string."""
    if content is None:
        return ""
    parts: list[str] = []
    for c in content:
        text = getattr(c, "text", None)
        if text:
            parts.append(text)
            continue
        # Non-text content (image / resource / etc) — stringify metadata
        ctype = getattr(c, "type", None) or type(c).__name__
        mime = getattr(c, "mimeType", None)
        if mime:
            parts.append(f"[{ctype} content: {mime}]")
        else:
            try:
                parts.append(json.dumps(c, default=str))
            except Exception:
                parts.append(str(c))
    return "\n".join(parts)


def _make_mcp_adapted_tool(session, name: str, description: str, input_schema: dict) -> AdaptedTool:
    """Build an AdaptedTool whose `fn` calls back into the live MCP session."""

    async def call_via_mcp(**kwargs):
        try:
            result = await session.call_tool(name, kwargs)
        except Exception as e:
            return f"MCP tool '{name}' call failed: {e}"
        text = _flatten_mcp_content(getattr(result, "content", None))
        if getattr(result, "isError", False):
            return f"Error from MCP tool '{name}': {text}"
        return text

    return AdaptedTool(
        name=name,
        description=description,
        input_schema=input_schema,
        fn=call_via_mcp,
        is_async=True,
    )
