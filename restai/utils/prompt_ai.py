"""System-LLM helper for generating project system prompts from a short description."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_TYPE_HINTS = {
    "rag": (
        "This is a Retrieval-Augmented Generation (RAG) project — the LLM will answer questions "
        "grounded in a knowledge base of ingested documents. The system prompt should steer the model "
        "to use the retrieved context faithfully and admit when information isn't in the documents."
    ),
    "agent": (
        "This is an agent project — the LLM can call tools (web search, calculator, APIs, MCP servers) "
        "to complete tasks. The system prompt should describe the agent's role, what tools it should prefer, "
        "and any constraints on behavior."
    ),
    "block": (
        "This is a block project that executes visual logic (Blockly workspace). The system prompt is usually "
        "unused for block projects — skip this field or leave it empty."
    ),
}


def build_prompt(description: str, project_type: Optional[str]) -> str:
    type_hint = _TYPE_HINTS.get(project_type or "", "")
    return f"""You are an expert at writing system prompts for LLM-powered AI assistants.

A user is creating a project and gave this short description:
"{description}"

{type_hint}

Write a complete, production-ready system prompt for this project. The system prompt should:
- Define the assistant's role and personality
- State the scope of what it should and shouldn't answer
- Give any relevant instructions about tone, format, or style
- Be concise but comprehensive (typically 3-8 sentences)
- Be written in second person ("You are...", "You should...")

Output ONLY the system prompt text. No markdown headings, no explanation, no preamble, no quotes around it.
"""


async def generate_system_prompt(
    brain: Any,
    db: Any,
    description: str,
    project_type: Optional[str] = None,
) -> str:
    """Use the system LLM to draft a project system prompt.

    Raises ValueError if no system LLM is configured or the call fails.
    """
    system_llm = brain.get_system_llm(db)
    if system_llm is None:
        raise ValueError("No system LLM is configured. Set one in Settings → Platform.")

    prompt = build_prompt(description, project_type)
    try:
        result = system_llm.llm.complete(prompt)
        text = result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        logger.exception("System LLM failed during system prompt generation")
        raise ValueError(f"System LLM call failed: {e}")

    text = text.strip()
    # Strip wrapping quotes if the LLM added them
    if len(text) >= 2 and text[0] in ('"', "'") and text[-1] == text[0]:
        text = text[1:-1].strip()
    return text
