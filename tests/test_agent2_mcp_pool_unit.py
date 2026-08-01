"""Unit tests for restai/agent2/mcp_client.py — MCPSessionPool with a fully
mocked `mcp` SDK (fake transports injected via sys.modules). No subprocesses,
no network.
"""
import asyncio
import sys
import types

import pytest

import restai.agent2.mcp_client as mc
from restai.agent2.mcp_client import (
    MCPSessionPool,
    _flatten_mcp_content,
    _make_mcp_adapted_tool,
    _parse_allowed_tools,
)


def run(coro):
    return asyncio.run(coro)


# ─── small helpers ──────────────────────────────────────────────────────

def test_parse_allowed_tools():
    assert _parse_allowed_tools(None) is None
    assert _parse_allowed_tools("") is None
    assert _parse_allowed_tools(" , ,") is None
    assert _parse_allowed_tools("a, b ,a") == {"a", "b"}


def test_flatten_mcp_content_variants():
    assert _flatten_mcp_content(None) == ""
    text_part = types.SimpleNamespace(text="hello")
    mime_part = types.SimpleNamespace(text=None, type="image", mimeType="image/png")
    out = _flatten_mcp_content([text_part, mime_part])
    assert out == "hello\n[image content: image/png]"


def test_flatten_mcp_content_fallback_repr():
    weird = types.SimpleNamespace(text=None, type=None, mimeType=None)
    out = _flatten_mcp_content([weird])
    assert "SimpleNamespace" in out or "namespace" in out


# ─── adapted MCP tool ───────────────────────────────────────────────────

class FakeSession:
    def __init__(self, result=None, raise_exc=None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if self.raise_exc:
            raise self.raise_exc
        return self.result


def _tool_result(text="ok", is_error=False):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(text=text)], isError=is_error
    )


def test_mcp_adapted_tool_success():
    session = FakeSession(result=_tool_result("weather: sunny"))
    tool = _make_mcp_adapted_tool(session, "get_weather", "desc", {"type": "object"})
    assert tool.is_async is True
    out = run(tool.call({"city": "lisbon"}))
    assert out == "weather: sunny"
    assert session.calls == [("get_weather", {"city": "lisbon"})]


def test_mcp_adapted_tool_is_error_flag():
    session = FakeSession(result=_tool_result("bad city", is_error=True))
    tool = _make_mcp_adapted_tool(session, "get_weather", "desc", {})
    out = run(tool.call({}))
    assert out == "Error from MCP tool 'get_weather': bad city"


def test_mcp_adapted_tool_exception_soft_error():
    session = FakeSession(raise_exc=RuntimeError("pipe closed"))
    tool = _make_mcp_adapted_tool(session, "t", "d", {})
    out = run(tool.call({}))
    assert out == "MCP tool 't' call failed: pipe closed"


# ─── pool lifecycle ─────────────────────────────────────────────────────

class TrackingCM:
    """Async CM registered on the pool's stack to observe cleanup."""

    def __init__(self, log, fail_exit=False):
        self.log = log
        self.fail_exit = fail_exit

    async def __aenter__(self):
        self.log.append("enter")
        return self

    async def __aexit__(self, *a):
        self.log.append("exit")
        if self.fail_exit:
            raise RuntimeError("cleanup blew up")


def test_pool_aexit_closes_stack():
    log = []

    async def scenario():
        async with MCPSessionPool() as pool:
            await pool._stack.enter_async_context(TrackingCM(log))
        assert log == ["enter", "exit"]

    run(scenario())


def test_pool_aexit_swallows_cleanup_errors():
    log = []

    async def scenario():
        async with MCPSessionPool() as pool:
            await pool._stack.enter_async_context(TrackingCM(log, fail_exit=True))
        # reaching here means __aexit__ swallowed the RuntimeError

    run(scenario())
    assert log == ["enter", "exit"]


# ─── connect_servers routing ────────────────────────────────────────────

def _srv(host, args=None, env=None, headers=None, tools=None):
    return types.SimpleNamespace(host=host, args=args, env=env,
                                 headers=headers, tools=tools)


def _fake_list_result(*names):
    return types.SimpleNamespace(tools=[
        types.SimpleNamespace(
            name=n,
            description=f"{n} desc",
            inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        for n in names
    ])


class ListingSession:
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise = raise_exc

    async def list_tools(self):
        if self._raise:
            raise self._raise
        return self._result


def test_connect_servers_skips_hostless_and_continues(monkeypatch):
    opened = []

    async def fake_stdio(self, command, args, env):
        opened.append(command)
        return ListingSession(_fake_list_result("tool_a"))

    monkeypatch.setattr(MCPSessionPool, "_open_stdio_session", fake_stdio)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([
                _srv(None),
                _srv(""),
                _srv("npx", args=["-y", "server"]),
            ])

    tools = run(scenario())
    assert [t.name for t in tools] == ["tool_a"]
    assert opened == ["npx"]


def test_connect_servers_rejects_shell_metachars_in_stdio_args(monkeypatch):
    async def fake_stdio(self, command, args, env):
        raise AssertionError("must never open a session for bad args")

    monkeypatch.setattr(MCPSessionPool, "_open_stdio_session", fake_stdio)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([_srv("npx", args=["a; rm -rf /"])])

    assert run(scenario()) == []


def test_connect_servers_ssrf_block_on_http(monkeypatch):
    import restai.helper as helper
    monkeypatch.setattr(helper, "is_blocked_network_host", lambda h: True)

    async def fake_http(self, url, headers):
        raise AssertionError("blocked host must never be opened")

    monkeypatch.setattr(MCPSessionPool, "_open_http_session", fake_http)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([_srv("http://169.254.169.254/mcp")])

    assert run(scenario()) == []


def test_connect_servers_http_allowed(monkeypatch):
    import restai.helper as helper
    monkeypatch.setattr(helper, "is_blocked_network_host", lambda h: False)
    seen = {}

    async def fake_http(self, url, headers):
        seen["url"] = url
        seen["headers"] = headers
        return ListingSession(_fake_list_result("web_tool"))

    monkeypatch.setattr(MCPSessionPool, "_open_http_session", fake_http)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers(
                [_srv("https://mcp.example.com", headers={"Authorization": "Bearer x"})]
            )

    tools = run(scenario())
    assert [t.name for t in tools] == ["web_tool"]
    assert seen["url"] == "https://mcp.example.com"
    assert seen["headers"] == {"Authorization": "Bearer x"}


def test_connect_servers_open_failure_never_aborts_run(monkeypatch):
    async def failing_stdio(self, command, args, env):
        if command == "broken":
            raise RuntimeError("spawn failed")
        return ListingSession(_fake_list_result("good_tool"))

    monkeypatch.setattr(MCPSessionPool, "_open_stdio_session", failing_stdio)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([_srv("broken"), _srv("good")])

    tools = run(scenario())
    assert [t.name for t in tools] == ["good_tool"]


def test_connect_servers_list_failure_skips_server(monkeypatch):
    async def fake_stdio(self, command, args, env):
        return ListingSession(raise_exc=RuntimeError("list_tools broke"))

    monkeypatch.setattr(MCPSessionPool, "_open_stdio_session", fake_stdio)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([_srv("srv")])

    assert run(scenario()) == []


def test_connect_servers_allowed_tools_filter(monkeypatch):
    async def fake_stdio(self, command, args, env):
        return ListingSession(_fake_list_result("keep", "drop", "also_drop"))

    monkeypatch.setattr(MCPSessionPool, "_open_stdio_session", fake_stdio)

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool.connect_servers([_srv("srv", tools="keep")])

    tools = run(scenario())
    assert [t.name for t in tools] == ["keep"]


def test_list_session_tools_defaults_and_skips_nameless():
    listing = types.SimpleNamespace(tools=[
        types.SimpleNamespace(name=None, description=None, inputSchema=None),
        types.SimpleNamespace(name="minimal", description=None, inputSchema=None),
    ])

    async def scenario():
        async with MCPSessionPool() as pool:
            return await pool._list_session_tools(ListingSession(listing), None)

    tools = run(scenario())
    assert len(tools) == 1
    assert tools[0].name == "minimal"
    assert tools[0].description == "minimal"  # falls back to name
    assert tools[0].input_schema == {"type": "object", "properties": {}}


# ─── transports with a mocked mcp SDK ───────────────────────────────────

class FakeTransportCM:
    def __init__(self, value, log, tag, fail=False):
        self.value = value
        self.log = log
        self.tag = tag
        self.fail = fail

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError(f"{self.tag} transport failed")
        self.log.append(f"{self.tag}:enter")
        return self.value

    async def __aexit__(self, *a):
        self.log.append(f"{self.tag}:exit")


class FakeClientSession:
    def __init__(self, read, write):
        self.read = read
        self.write = write
        self.initialized = False
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        self.closed = True

    async def initialize(self):
        self.initialized = True


def _install_fake_mcp(monkeypatch, log, *, http_fail=False, sse_fail=False):
    """Inject fake mcp.client.* modules into sys.modules."""
    session_mod = types.ModuleType("mcp.client.session")
    session_mod.ClientSession = FakeClientSession

    http_mod = types.ModuleType("mcp.client.streamable_http")
    http_mod.streamablehttp_client = lambda url, headers=None: FakeTransportCM(
        ("r", "w", "get_id"), log, "http", fail=http_fail)

    sse_mod = types.ModuleType("mcp.client.sse")
    sse_mod.sse_client = lambda url, headers=None: FakeTransportCM(
        ("r", "w"), log, "sse", fail=sse_fail)

    stdio_mod = types.ModuleType("mcp.client.stdio")
    params_seen = {}

    class FakeStdioParams:
        def __init__(self, command=None, args=None, env=None):
            params_seen.update(command=command, args=args, env=env)

    stdio_mod.StdioServerParameters = FakeStdioParams
    stdio_mod.stdio_client = lambda params: FakeTransportCM(("r", "w"), log, "stdio")

    for name, mod in [
        ("mcp.client.session", session_mod),
        ("mcp.client.streamable_http", http_mod),
        ("mcp.client.sse", sse_mod),
        ("mcp.client.stdio", stdio_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)
    return params_seen


def test_open_http_session_streamable_preferred(monkeypatch):
    log = []
    _install_fake_mcp(monkeypatch, log)

    async def scenario():
        async with MCPSessionPool() as pool:
            session = await pool._open_http_session("https://x", None)
            assert session.initialized is True
            assert pool._sessions == [session]
            return session

    session = run(scenario())
    assert session.closed is True  # closed by pool aexit
    assert "http:enter" in log
    assert "sse" not in "".join(log)


def test_open_http_session_falls_back_to_sse(monkeypatch):
    log = []
    _install_fake_mcp(monkeypatch, log, http_fail=True)

    async def scenario():
        async with MCPSessionPool() as pool:
            session = await pool._open_http_session("https://x", {"h": "v"})
            assert session.initialized is True

    run(scenario())
    assert "sse:enter" in log


def test_open_http_session_both_transports_fail(monkeypatch):
    log = []
    _install_fake_mcp(monkeypatch, log, http_fail=True, sse_fail=True)

    async def scenario():
        async with MCPSessionPool() as pool:
            with pytest.raises(RuntimeError, match="sse transport failed"):
                await pool._open_http_session("https://x", None)

    run(scenario())


def test_open_stdio_session_builds_params(monkeypatch):
    log = []
    params_seen = _install_fake_mcp(monkeypatch, log)

    async def scenario():
        async with MCPSessionPool() as pool:
            session = await pool._open_stdio_session(
                "npx", ["-y", "some-server"], {"KEY": "V"})
            assert session.initialized is True

    run(scenario())
    assert params_seen == {"command": "npx", "args": ["-y", "some-server"],
                           "env": {"KEY": "V"}}
    assert log == ["stdio:enter", "stdio:exit"]


def test_transports_unwound_in_reverse_order(monkeypatch):
    log = []
    _install_fake_mcp(monkeypatch, log)

    async def scenario():
        async with MCPSessionPool() as pool:
            await pool._open_http_session("https://a", None)
            await pool._open_stdio_session("cmd", [], None)
            assert len(pool._sessions) == 2

    run(scenario())
    assert log == ["http:enter", "stdio:enter", "stdio:exit", "http:exit"]


def test_validate_stdio_args_none_ok():
    mc._validate_stdio_args(None)
    mc._validate_stdio_args([])
    with pytest.raises(ValueError):
        mc._validate_stdio_args(["$(evil)"])
