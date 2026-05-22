"""Text-based ReAct fallback for LLMs without native function calling."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Sequence

from .tool_adapter import AdaptedTool


REACT_SYSTEM_TEMPLATE = """\
{base_system}

You have access to the following tools. Use them when needed to answer the user.

{tool_descriptions}

To use a tool, respond using EXACTLY this format (one action at a time):

Thought: <your reasoning about what to do next>
Action: <tool name — must be one of: {tool_names}>
Action Input: <a single JSON object matching the tool's input schema>

After you call a tool, you will receive an Observation in the next turn. Then continue with another Thought/Action, or if you have enough information, respond with:

Thought: <final reasoning>
Final Answer: <your answer to the user>

Rules:
- Only ONE Action per response.
- Action Input MUST be a single valid JSON object on a single line OR inside a ```json``` fenced block.
- If you don't need any tool, skip straight to "Final Answer:".
- Never include both an Action and a Final Answer in the same response.
"""


def _condense_property(name: str, prop: dict) -> str:
    ptype = prop.get("type", "any")
    if ptype == "array":
        items = prop.get("items") or {}
        item_type = items.get("type", "any") if isinstance(items, dict) else "any"
        ptype = f"array<{item_type}>"
    desc = prop.get("description")
    if desc:
        return f"{name}: {ptype} ({desc})"
    return f"{name}: {ptype}"


def format_tool_for_react(tool: AdaptedTool) -> str:
    schema = tool.input_schema or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    if properties:
        param_lines = []
        for name, prop in properties.items():
            marker = "" if name in required else "?"
            param_lines.append("    - " + _condense_property(name + marker, prop or {}))
        params_block = "\n" + "\n".join(param_lines)
    else:
        params_block = " (no arguments)"

    description = (tool.description or "").strip() or tool.name
    return f"- {tool.name}: {description}\n  Arguments:{params_block}"


def build_react_system_prompt(base_system: str, tools: Sequence[AdaptedTool]) -> str:
    base = (base_system or "You are a helpful assistant.").strip()

    if not tools:
        return (
            base
            + "\n\nYou have no tools available. Respond directly with:\n"
            "Thought: <your reasoning>\nFinal Answer: <your answer>"
        )

    descriptions = "\n\n".join(format_tool_for_react(t) for t in tools)
    names = ", ".join(t.name for t in tools)
    return REACT_SYSTEM_TEMPLATE.format(
        base_system=base,
        tool_descriptions=descriptions,
        tool_names=names,
    )


@dataclass
class ReactParseResult:
    kind: Literal["action", "final", "text"]
    thought: str = ""
    action_name: Optional[str] = None
    action_input: dict = field(default_factory=dict)
    final_text: str = ""


_THOUGHT_RE = re.compile(r"(?im)^\s*thought\s*:\s*(.+?)(?=^\s*(?:action|final\s*answer|action\s*input)\s*:|\Z)", re.DOTALL)
_ACTION_RE = re.compile(r"(?im)^\s*action\s*:\s*([^\n\r]+)")
_ACTION_INPUT_RE = re.compile(
    r"(?im)^\s*action\s*input\s*:\s*(.+?)(?=^\s*(?:observation|thought|action|final\s*answer)\s*:|\Z)",
    re.DOTALL,
)
_FINAL_RE = re.compile(
    r"(?im)^\s*final\s*answer\s*:\s*(.+?)\Z",
    re.DOTALL,
)
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_fences(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1)
    return text


_JSON_DECODER = json.JSONDecoder()


def _try_load_json(text: str) -> Optional[dict]:
    """Parse one JSON object from text; tolerates trailing junk via raw_decode."""
    text = (text or "").strip()
    if not text:
        return None

    candidate = _strip_fences(text)
    try:
        loaded = json.loads(candidate)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    if start < 0:
        return None
    try:
        obj, _ = _JSON_DECODER.raw_decode(candidate[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_react_response(text: str) -> ReactParseResult:
    """Parse a raw LLM response in ReAct format."""
    if not text:
        return ReactParseResult(kind="text", final_text="")

    thought_match = _THOUGHT_RE.search(text)
    thought = thought_match.group(1).strip() if thought_match else ""

    action_match = _ACTION_RE.search(text)
    action_input_match = _ACTION_INPUT_RE.search(text)

    # If both Action and Final Answer appear, action wins (model is still working)
    if action_match:
        name = action_match.group(1).strip()
        name = name.strip().strip("`'\"")
        name = name.split("\n", 1)[0].strip()

        input_dict: dict = {}
        if action_input_match:
            input_text = action_input_match.group(1).strip()
            parsed_input = _try_load_json(input_text)
            if parsed_input is not None:
                input_dict = parsed_input
        else:
            # No explicit "Action Input:" label — try to find a JSON object after the Action line
            after_action = text[action_match.end():]
            parsed_input = _try_load_json(after_action)
            if parsed_input is not None:
                input_dict = parsed_input

        if name:
            return ReactParseResult(
                kind="action",
                thought=thought,
                action_name=name,
                action_input=input_dict,
            )

    final_match = _FINAL_RE.search(text)
    if final_match:
        return ReactParseResult(
            kind="final",
            thought=thought,
            final_text=final_match.group(1).strip(),
        )

    # Fall back to treating the whole response as final so the loop terminates
    # instead of hanging.
    return ReactParseResult(kind="text", final_text=text.strip())
