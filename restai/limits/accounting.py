"""Token-usage accounting helpers for the inference paths that don't go through
`helper.chat_main` (guard checks, nested tools, System-LLM platform helpers).

Everything still funnels into the two canonical sinks — `tools.log_inference`
(project chat) and `direct_access.log_direct_usage` (project-less/direct). These
helpers just produce honest token counts (preferring provider-reported usage)
and, for platform System-LLM work, write an attribution-only row that bills no
team and no API-key quota.
"""
import logging

from restai.database import DBWrapper
from restai.tools import tokens_from_string


def cost_for_tokens(tokens, input_cost_per_m: float, output_cost_per_m: float) -> dict:
    """`{input, output, total}` USD cost for a `{input, output}` token dict, given
    the LLM's per-million-token prices. Mirrors `tools.log_inference`'s math."""
    in_tok = int((tokens or {}).get("input", 0) or 0)
    out_tok = int((tokens or {}).get("output", 0) or 0)
    in_cost = in_tok * (input_cost_per_m or 0.0) / 1_000_000
    out_cost = out_tok * (output_cost_per_m or 0.0) / 1_000_000
    return {"input": in_cost, "output": out_cost, "total": in_cost + out_cost}


def attach_cost(output: dict, project, db: DBWrapper) -> dict:
    """Set `output['cost'] = {input, output, total}` (USD) from `output['tokens']`
    and the project LLM's pricing, so every response that reports token counts also
    reports what they cost. Idempotent (skips if `cost` already present) and
    best-effort — a pricing lookup failure leaves the response untouched rather than
    breaking the turn. A project with no LLM (e.g. block) yields zero cost."""
    try:
        if not isinstance(output, dict) or "tokens" not in output or "cost" in output:
            return output
        input_cost_per_m = 0.0
        output_cost_per_m = 0.0
        llm_name = getattr(project.props, "llm", None)
        if llm_name:
            llm_db = db.get_llm_by_name(llm_name)
            if llm_db is not None:
                from restai.models.models import LLMModel
                props = LLMModel.model_validate(llm_db)
                input_cost_per_m = props.input_cost
                output_cost_per_m = props.output_cost
        output["cost"] = cost_for_tokens(output.get("tokens"), input_cost_per_m, output_cost_per_m)
    except Exception:
        logging.debug("attach_cost failed", exc_info=True)
    return output


def count_usage(response, prompt_text: str = "", answer_text: str = ""):
    """Return `(input_tokens, output_tokens)`, preferring the provider's real
    usage carried on `response` (via `openai_compat.usage_from_response`), else a
    tiktoken estimate of the given prompt / answer text."""
    if response is not None:
        try:
            from restai.utils.openai_compat import usage_from_response
            real = usage_from_response(response)
            if real:
                return int(real[0]), int(real[1])
        except Exception:
            pass
    return tokens_from_string(prompt_text or ""), tokens_from_string(answer_text or "")


def log_platform_usage(db: DBWrapper, feature: str, sys_llm, prompt: str, answer: str, user_id=None):
    """Record a System-LLM (platform) inference as an attribution-only
    `OutputDatabase` row: `team_id=None` and `api_key_id=None`, so it appears in
    statistics / admin logs but charges no team wallet and no api-key quota.

    `sys_llm` is the `LLM` wrapper from `brain.get_system_llm(db)` (has `.props`
    with `name` / `input_cost` / `output_cost`). Never raises — accounting must
    not break a platform helper."""
    try:
        from restai.integrations.direct_access import log_direct_usage
        props = getattr(sys_llm, "props", None)
        name = getattr(props, "name", None) or "system"
        in_tok, out_tok = count_usage(None, prompt, answer)
        in_cost = in_tok * (getattr(props, "input_cost", 0.0) or 0.0) / 1_000_000
        out_cost = out_tok * (getattr(props, "output_cost", 0.0) or 0.0) / 1_000_000
        log_direct_usage(
            db, user_id, None, name,
            f"(platform:{feature})", "(generated)",
            in_tok, out_tok, in_cost, out_cost, None,
        )
    except Exception:
        logging.exception("Failed to log platform usage for %s", feature)
