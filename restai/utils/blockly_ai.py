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

Standard Blockly blocks (General-purpose, matching MIT App Inventor):

Logic:
- logic_boolean (value, Boolean): Field BOOL ("TRUE" | "FALSE").
- logic_null (value): Always returns null. No fields.
- logic_compare (value, Boolean): Inputs A, B. Field OP ("EQ" | "NEQ" | "LT" | "LTE" | "GT" | "GTE").
- logic_operation (value, Boolean): Inputs A, B. Field OP ("AND" | "OR").
- logic_negate (value, Boolean): Input BOOL (Boolean).
- logic_ternary (value): Inputs IF (Boolean), THEN, ELSE.

Control:
- controls_if (statement): extraState {"elseIfCount": N, "hasElse": bool}. Inputs IF0, DO0, IF1, DO1, ..., ELSE.
- controls_repeat_ext (statement): Input TIMES (Number). Input DO (statement).
- controls_whileUntil (statement): Field MODE ("WHILE" | "UNTIL"). Input BOOL. Input DO.
- controls_for (statement): Field VAR {"id": ...}. Inputs FROM, TO, BY, DO.
- controls_forEach (statement): Field VAR {"id": ...}. Inputs LIST, DO.
- controls_flow_statements (statement): Field FLOW ("BREAK" | "CONTINUE"). Use inside a loop only.

Math:
- math_number (value, Number): Field NUM.
- math_arithmetic (value, Number): Inputs A, B. Field OP ("ADD" | "MINUS" | "MULTIPLY" | "DIVIDE" | "POWER").
- math_single (value, Number): Input NUM. Field OP ("ROOT" | "ABS" | "NEG" | "LN" | "LOG10" | "EXP" | "POW10").
- math_trig (value, Number, degrees): Input NUM. Field OP ("SIN" | "COS" | "TAN" | "ASIN" | "ACOS" | "ATAN").
- math_constant (value, Number): Field CONSTANT ("PI" | "E" | "GOLDEN_RATIO" | "SQRT2" | "SQRT1_2" | "INFINITY").
- math_number_property (value, Boolean): Input NUMBER_TO_CHECK. Field PROPERTY ("EVEN" | "ODD" | "PRIME" | "WHOLE" | "POSITIVE" | "NEGATIVE" | "DIVISIBLE_BY"). For DIVISIBLE_BY also input DIVISOR.
- math_round (value, Number): Input NUM. Field OP ("ROUND" | "ROUNDUP" | "ROUNDDOWN").
- math_on_list (value): Input LIST. Field OP ("SUM" | "MIN" | "MAX" | "AVERAGE" | "MEDIAN" | "MODE" | "STD_DEV" | "RANDOM").
- math_modulo (value, Number): Inputs DIVIDEND, DIVISOR.
- math_constrain (value, Number): Inputs VALUE, LOW, HIGH.
- math_random_int (value, Number): Inputs FROM, TO.
- math_random_float (value, Number between 0 and 1): No inputs.
- math_atan2 (value, Number, degrees): Inputs X, Y.

Text:
- text (value, String): Field TEXT.
- text_join (value, String): extraState {"itemCount": N}. Inputs ADD0, ADD1, ..., ADDN-1.
- text_append (statement): Field VAR {"id": ...}. Input TEXT. Appends TEXT to the variable.
- text_length (value, Number): Input VALUE.
- text_isEmpty (value, Boolean): Input VALUE.
- text_indexOf (value, Number, 1-based or -1): Inputs VALUE, FIND. Field END ("FIRST" | "LAST").
- text_charAt (value, String): Input VALUE. Field WHERE ("FROM_START" | "FROM_END" | "FIRST" | "LAST" | "RANDOM"). For FROM_START/FROM_END also input AT.
- text_getSubstring (value, String): Input STRING. Fields WHERE1, WHERE2 (same values as charAt). Inputs AT1, AT2 as applicable. 1-based inclusive/inclusive.
- text_changeCase (value, String): Input TEXT. Field CASE ("UPPERCASE" | "LOWERCASE" | "TITLECASE").
- text_trim (value, String): Input TEXT. Field MODE ("LEFT" | "RIGHT" | "BOTH").
- text_contains (value, Boolean): Inputs VALUE, FIND.
- text_count (value, Number): Inputs SUB, TEXT.
- text_replace (value, String): Inputs FROM, TO, TEXT.
- text_reverse (value, String): Input TEXT.
- text_print (statement): Input TEXT. Logs the text for debugging.

Lists:
- lists_create_with (value, List): extraState {"itemCount": N}. Inputs ADD0, ADD1, ..., ADDN-1.
- lists_create_empty (value, List): No inputs.
- lists_repeat (value, List): Inputs ITEM, NUM.
- lists_length (value, Number): Input VALUE.
- lists_isEmpty (value, Boolean): Input VALUE.
- lists_indexOf (value, Number, 1-based or 0): Inputs VALUE, FIND. Field END ("FIRST" | "LAST").
- lists_getIndex (value, or statement in REMOVE mode): Input VALUE. Fields MODE ("GET" | "GET_REMOVE" | "REMOVE"), WHERE ("FROM_START" | "FROM_END" | "FIRST" | "LAST" | "RANDOM"). Input AT for FROM_START/FROM_END.
- lists_setIndex (statement): Input LIST. Fields MODE ("SET" | "INSERT"), WHERE. Input AT, TO.
- lists_getSublist (value, List): Input LIST. Fields WHERE1, WHERE2. Inputs AT1, AT2 as applicable.
- lists_split (value, List or String): Input INPUT. Input DELIM. Field MODE ("SPLIT" | "JOIN").
- lists_sort (value, List): Input LIST. Fields TYPE ("NUMERIC" | "TEXT" | "IGNORE_CASE"), DIRECTION ("1" | "-1").
- lists_reverse (value, List): Input LIST.

Variables:
- variables_set (statement): Field VAR {"id": "<var_id>"}. Input VALUE.
- variables_get (value): Field VAR {"id": "<var_id>"}.

Procedures (user-defined functions):
- procedures_defnoreturn (statement, top-level): Field NAME. extraState {"params": [{"name": "x", "id": "<var_id>"}, ...]}. Input STACK (the body).
- procedures_defreturn (statement, top-level): Same as above + Input RETURN (the expression returned on fall-through).
- procedures_callnoreturn (statement): extraState {"name": "<proc name>", "params": [<ids>]}. Inputs ARG0, ARG1, ... in order.
- procedures_callreturn (value): Same shape as callnoreturn but returns the procedure's RETURN value.
- procedures_ifreturn (statement, inside defreturn only): Input CONDITION. Input VALUE. Returns VALUE early when CONDITION is true.

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
