"""System-LLM helpers for block projects: natural language → workspace, and debug explanation."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


BLOCK_REFERENCE = """
Available block types (produce valid Blockly serialized JSON using these):

RESTai custom blocks:
- restai_get_input (value, returns String): Returns the user's input text. No fields or inputs.
- restai_set_output (statement): Sets the project's answer. Input VALUE (String).
- restai_call_project (value, returns String): Calls another RESTai project. Field PROJECT_NAME (string, project name). Input TEXT (String).
- restai_classifier (value, returns String): Zero-shot text classification. Inputs TEXT (String), LABELS (String, comma-separated). Field MODEL (default "facebook/bart-large-mnli"). Returns the top matching label.
- restai_log (statement): Debug log. Input TEXT (String).

Standard Blockly blocks:
- text (value, returns String): Field TEXT (the literal string).
- text_join (value, returns String): extraState {"itemCount": N}. Inputs ADD0, ADD1, ..., ADDN-1 (all String).
- text_length (value, returns Number): Input VALUE (String).
- text_isEmpty (value, returns Boolean): Input VALUE (String).
- text_changeCase (value, returns String): Input TEXT (String). Field CASE ("UPPERCASE" | "LOWERCASE" | "TITLECASE").
- text_trim (value, returns String): Input TEXT (String). Field MODE ("LEFT" | "RIGHT" | "BOTH").
- text_contains (value, returns Boolean): Inputs VALUE (String), FIND (String).
- math_number (value, returns Number): Field NUM.
- math_arithmetic (value, returns Number): Inputs A, B. Field OP ("ADD" | "MINUS" | "MULTIPLY" | "DIVIDE" | "POWER").
- logic_boolean (value, returns Boolean): Field BOOL ("TRUE" | "FALSE").
- logic_compare (value, returns Boolean): Inputs A, B. Field OP ("EQ" | "NEQ" | "LT" | "LTE" | "GT" | "GTE").
- logic_operation (value, returns Boolean): Inputs A, B. Field OP ("AND" | "OR").
- logic_negate (value, returns Boolean): Input BOOL (Boolean).
- controls_if (statement): extraState {"elseIfCount": N, "hasElse": bool}. Inputs IF0, DO0, IF1, DO1, ..., ELSE.
- controls_repeat_ext (statement): Input TIMES (Number). Input DO (statement).
- controls_whileUntil (statement): Field MODE ("WHILE" | "UNTIL"). Input BOOL (Boolean). Input DO (statement).
- variables_set (statement): Field VAR {"id": "<var_id>"}. Input VALUE.
- variables_get (value): Field VAR {"id": "<var_id>"}.

Workspace shape (what you must output):
{
  "blocks": {
    "blocks": [ <top-level statement block tree, chained via "next"> ]
  },
  "variables": [ { "id": "<var_id>", "name": "<varname>" }, ... ]
}

A block has:
- "type": string from the list above
- "fields": {FIELD_NAME: value}
- "inputs": {INPUT_NAME: {"block": {<nested block>}}}
- "next": {"block": {<next statement block>}}    (only on statement blocks)
- "extraState": {...}                              (only where noted)

RULES:
1. Every workspace MUST start with a chain of statement blocks. The very first block should use restai_get_input somewhere via inputs, or use variables.
2. Every useful workspace MUST contain exactly one restai_set_output block — this is how the answer is returned.
3. Only use the block types listed above. Do NOT invent new types.
4. Return valid JSON. Do not wrap in markdown code fences.
"""


EXAMPLE_ECHO = {
    "blocks": {
        "blocks": [
            {
                "type": "restai_set_output",
                "inputs": {
                    "VALUE": {
                        "block": {"type": "restai_get_input"}
                    }
                }
            }
        ]
    },
    "variables": []
}


EXAMPLE_CLASSIFIER = {
    "blocks": {
        "blocks": [
            {
                "type": "restai_set_output",
                "inputs": {
                    "VALUE": {
                        "block": {
                            "type": "restai_classifier",
                            "fields": {"MODEL": "facebook/bart-large-mnli"},
                            "inputs": {
                                "TEXT": {"block": {"type": "restai_get_input"}},
                                "LABELS": {"block": {"type": "text", "fields": {"TEXT": "billing, technical, sales"}}}
                            }
                        }
                    }
                }
            }
        ]
    },
    "variables": []
}


def build_generation_prompt(description: str, available_projects: list[str]) -> str:
    """Build the prompt that asks the LLM to produce a Blockly workspace JSON."""
    projects_hint = ""
    if available_projects:
        projects_hint = (
            "Other projects you can call via restai_call_project "
            f"(use one of these exact names): {', '.join(available_projects)}\n\n"
        )

    return f"""You are an expert at generating Blockly workspace JSON for RESTai block projects.

{BLOCK_REFERENCE}

{projects_hint}Two examples of valid output:

Example 1 — "Echo the input back to the user":
{json.dumps(EXAMPLE_ECHO, indent=2)}

Example 2 — "Classify user messages as billing, technical, or sales":
{json.dumps(EXAMPLE_CLASSIFIER, indent=2)}

User request: {description}

Output ONLY the workspace JSON. No explanation, no markdown fences, no commentary.
"""


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_workspace_json(text: str) -> Optional[dict]:
    """Extract a workspace dict from LLM output. Tolerant of code fences and surrounding prose."""
    if not text:
        return None
    text = text.strip()

    # Strip markdown code fences if present
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find the outermost JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    # Ensure minimal shape
    if not isinstance(parsed, dict):
        return None
    if "blocks" not in parsed:
        # If the LLM returned just the inner blocks structure, wrap it
        if "type" in parsed:
            parsed = {"blocks": {"blocks": [parsed]}, "variables": []}
        else:
            return None
    if "variables" not in parsed:
        parsed["variables"] = []
    return parsed


async def generate_workspace_from_description(
    brain: Any,
    db: Any,
    description: str,
    available_projects: list[str] = None,
) -> dict:
    """Use the system LLM to produce a Blockly workspace from a plain-English description.

    Raises ValueError if no system LLM configured or if parsing fails.
    """
    system_llm = brain.get_system_llm(db)
    if system_llm is None:
        raise ValueError("No system LLM is configured. Set one in Settings → Platform.")

    prompt = build_generation_prompt(description, available_projects or [])
    try:
        result = system_llm.llm.complete(prompt)
        text = result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        logger.exception("System LLM failed during workspace generation")
        raise ValueError(f"System LLM call failed: {e}")

    workspace = parse_workspace_json(text)
    if workspace is None:
        raise ValueError("System LLM returned invalid workspace JSON")
    return workspace
