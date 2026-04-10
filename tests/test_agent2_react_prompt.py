"""Tests for restai.agent2.react_prompt — ReAct parser and prompt builder."""
from restai.agent2.react_prompt import (
    build_react_system_prompt,
    format_tool_for_react,
    parse_react_response,
)
from restai.agent2.tool_adapter import AdaptedTool


def _make_tool(name: str, description: str = "", schema: dict | None = None) -> AdaptedTool:
    return AdaptedTool(
        name=name,
        description=description or f"Tool {name}",
        input_schema=schema or {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        fn=lambda **kw: "ok",
    )


# ---------- parse_react_response ----------


def test_parse_action_basic():
    text = 'Thought: think\nAction: search\nAction Input: {"q": "hello"}'
    result = parse_react_response(text)
    assert result.kind == "action"
    assert result.thought == "think"
    assert result.action_name == "search"
    assert result.action_input == {"q": "hello"}


def test_parse_action_fenced_json():
    text = (
        "Thought: ok\n"
        "Action: foo\n"
        "Action Input:\n"
        "```json\n"
        '{"x": 1}\n'
        "```"
    )
    result = parse_react_response(text)
    assert result.kind == "action"
    assert result.action_name == "foo"
    assert result.action_input == {"x": 1}


def test_parse_final_answer():
    text = "Thought: done\nFinal Answer: 42"
    result = parse_react_response(text)
    assert result.kind == "final"
    assert result.thought == "done"
    assert result.final_text == "42"


def test_parse_plain_text():
    text = "Just some text without structure"
    result = parse_react_response(text)
    assert result.kind == "text"
    assert result.final_text == text.strip()


def test_parse_action_wins_over_final():
    text = "Thought: x\nAction: tool\nAction Input: {}\nFinal Answer: done"
    result = parse_react_response(text)
    assert result.kind == "action"
    assert result.action_name == "tool"


def test_parse_action_no_action_input():
    text = "Action: bar"
    result = parse_react_response(text)
    assert result.kind == "action"
    assert result.action_name == "bar"
    assert result.action_input == {}


# ---------- build_react_system_prompt ----------


def test_build_react_system_prompt_with_tools():
    tools = [_make_tool("search", "Search the web"), _make_tool("calc", "Calculate")]
    prompt = build_react_system_prompt("You are helpful.", tools)
    assert "search" in prompt
    assert "calc" in prompt
    assert "You are helpful." in prompt
    assert "Action:" in prompt
    assert "Final Answer:" in prompt


def test_build_react_system_prompt_empty_tools():
    prompt = build_react_system_prompt("You are helpful.", [])
    assert "You have no tools available" in prompt
    assert "Final Answer:" in prompt


def test_build_react_system_prompt_default_base():
    prompt = build_react_system_prompt("", [_make_tool("x")])
    assert "You are a helpful assistant." in prompt


# ---------- format_tool_for_react ----------


def test_format_tool_for_react_output():
    tool = _make_tool(
        "search",
        "Search the web",
        {
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["q"],
        },
    )
    output = format_tool_for_react(tool)
    assert "search" in output
    assert "Search the web" in output
    assert "q:" in output
    assert "limit?" in output  # optional param has ?


def test_format_tool_for_react_no_params():
    tool = AdaptedTool(
        name="noop",
        description="Does nothing",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=lambda: "ok",
    )
    output = format_tool_for_react(tool)
    assert "no arguments" in output
