def browser_eval(js: str, **kwargs) -> str:
    """Run arbitrary JavaScript in the current page context.

    **Admin opt-in required** — the project option `browser_allow_eval`
    must be explicitly set to true, because a prompt-injected page could
    use this to execute anything the current origin permits (including
    stealing cookies, hitting authed APIs, etc.). Kept available as an
    escape hatch for workflows that legitimately need it.

    Args:
        js (str): The JavaScript expression / statement to evaluate.
            Result must be JSON-serializable.
    """
    from restai.llms.tools._browser_common import _browser_ctx, _browser_allow_eval

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, project, db = ctx
    try:
        if not js or not js.strip():
            return "ERROR: js is required."
        if not _browser_allow_eval(project):
            return (
                "ERROR: browser_eval is disabled for this project. An admin "
                "must set `browser_allow_eval: true` in the project options "
                "to enable it (dangerous — read the docstring)."
            )
        try:
            result = brain.browser_manager.call(chat_id, "/eval", {"js": js})
        except Exception as e:
            return f"ERROR: eval failed: {e}"
        import json as _json
        try:
            rendered = _json.dumps(result.get("result"), indent=2, default=str)
        except Exception:
            rendered = str(result.get("result"))
        if len(rendered) > 10_000:
            rendered = rendered[:10_000] + "\n… (truncated)"
        return f"```\n{rendered}\n```"
    finally:
        db.db.close()
