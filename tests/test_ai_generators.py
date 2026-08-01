"""System-LLM platform helpers: restai/utils/prompt_ai.py (system-prompt
generator) and restai/utils/blockly_ai.py (Blockly workspace generator),
with the System LLM faked. No DB, no network."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from restai.utils import blockly_ai, prompt_ai


def _brain_emitting(text):
    calls = []

    def complete(prompt):
        calls.append(prompt)
        if isinstance(text, Exception):
            raise text
        return SimpleNamespace(text=text)
    llm = SimpleNamespace(llm=SimpleNamespace(complete=complete))
    return SimpleNamespace(get_system_llm=lambda db: llm), calls


def _no_llm_brain():
    return SimpleNamespace(get_system_llm=lambda db: None)


# ─── prompt_ai: build_prompt ────────────────────────────────────────────

def test_build_prompt_includes_type_hint():
    p = prompt_ai.build_prompt("support bot", "rag")
    assert "Retrieval-Augmented Generation" in p
    assert "support bot" in p
    p = prompt_ai.build_prompt("helper", "agent")
    assert "call tools" in p


def test_build_prompt_unknown_type_has_no_hint():
    p = prompt_ai.build_prompt("thing", None)
    assert "Retrieval-Augmented" not in p
    assert "call tools" not in p
    assert "thing" in p


# ─── prompt_ai: generate_system_prompt ──────────────────────────────────

def _gen_prompt(brain, description="a support assistant", ptype="agent"):
    with patch("restai.limits.accounting.log_platform_usage",
               side_effect=RuntimeError("accounting down")):
        return asyncio.run(prompt_ai.generate_system_prompt(brain, None, description, ptype))


def test_generate_system_prompt_happy_path():
    brain, calls = _brain_emitting("You are a helpful support assistant.")
    out = _gen_prompt(brain)
    assert out == "You are a helpful support assistant."
    assert "a support assistant" in calls[0]


def test_generate_system_prompt_strips_wrapping_quotes():
    brain, _ = _brain_emitting('"You are an agent."')
    assert _gen_prompt(brain) == "You are an agent."
    brain, _ = _brain_emitting("'You are an agent.'")
    assert _gen_prompt(brain) == "You are an agent."


def test_generate_system_prompt_no_system_llm():
    with pytest.raises(ValueError, match="No system LLM"):
        asyncio.run(prompt_ai.generate_system_prompt(_no_llm_brain(), None, "x"))


def test_generate_system_prompt_llm_crash_wrapped():
    brain, _ = _brain_emitting(RuntimeError("provider down"))
    with pytest.raises(ValueError, match="System LLM call failed"):
        _gen_prompt(brain)


# ─── blockly_ai: build_generation_prompt ────────────────────────────────

def test_build_generation_prompt_lists_callable_projects():
    p = blockly_ai.build_generation_prompt("echo bot", ["proj_a", "proj_b"])
    assert "proj_a, proj_b" in p
    assert "echo bot" in p
    assert "restai_get_input" in p  # block reference included


def test_build_generation_prompt_without_projects():
    p = blockly_ai.build_generation_prompt("echo bot", [])
    assert "use one of these exact names" not in p


# ─── blockly_ai: parse_workspace_json ───────────────────────────────────

def _workspace():
    return {"blocks": {"blocks": [{"type": "restai_set_output"}]}, "variables": []}


def test_parse_workspace_plain_json():
    assert blockly_ai.parse_workspace_json(json.dumps(_workspace())) == _workspace()


def test_parse_workspace_fenced():
    text = "```json\n" + json.dumps(_workspace()) + "\n```"
    assert blockly_ai.parse_workspace_json(text) == _workspace()


def test_parse_workspace_embedded_in_prose():
    text = "Here is your workspace: " + json.dumps(_workspace()) + " enjoy!"
    assert blockly_ai.parse_workspace_json(text) == _workspace()


def test_parse_workspace_single_block_gets_wrapped():
    out = blockly_ai.parse_workspace_json('{"type": "restai_get_input"}')
    assert out == {"blocks": {"blocks": [{"type": "restai_get_input"}]}, "variables": []}


def test_parse_workspace_missing_variables_added():
    out = blockly_ai.parse_workspace_json('{"blocks": {"blocks": []}}')
    assert out["variables"] == []


def test_parse_workspace_rejects_non_workspace():
    assert blockly_ai.parse_workspace_json("") is None
    assert blockly_ai.parse_workspace_json("not json") is None
    assert blockly_ai.parse_workspace_json("[1, 2, 3]") is None  # not a dict
    assert blockly_ai.parse_workspace_json('{"neither": "blocks nor type"}') is None
    assert blockly_ai.parse_workspace_json("prose {not: json} prose") is None


# ─── blockly_ai: generate_workspace_from_description ────────────────────

def _gen_workspace(brain, description="echo the input"):
    with patch("restai.limits.accounting.log_platform_usage"):
        return asyncio.run(blockly_ai.generate_workspace_from_description(
            brain, None, description, ["other_proj"]))


def test_generate_workspace_happy_path():
    brain, calls = _brain_emitting(json.dumps(_workspace()))
    out = _gen_workspace(brain)
    assert out == _workspace()
    assert "echo the input" in calls[0]
    assert "other_proj" in calls[0]


def test_generate_workspace_no_system_llm():
    with pytest.raises(ValueError, match="No system LLM"):
        asyncio.run(blockly_ai.generate_workspace_from_description(
            _no_llm_brain(), None, "x"))


def test_generate_workspace_invalid_json():
    brain, _ = _brain_emitting("I refuse to emit JSON")
    with pytest.raises(ValueError, match="invalid workspace JSON"):
        _gen_workspace(brain)


def test_generate_workspace_llm_crash_wrapped():
    brain, _ = _brain_emitting(RuntimeError("down"))
    with pytest.raises(ValueError, match="System LLM call failed"):
        _gen_workspace(brain)
