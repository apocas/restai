def browser_content(selector: str = None, format: str = "markdown", **kwargs) -> str:
    """Read the current page's content (sanitized — scripts/styles/comments
    stripped before returning). Use `selector` to zoom in on one element.

    Args:
        selector (str): Optional CSS selector. Leave empty for the whole page.
        format (str): 'markdown' (default, good for LLM reading), 'text',
            or 'html'.
    """
    from restai.llms.tools._browser_common import _browser_ctx

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, _, db = ctx
    try:
        payload = {"format": format}
        if selector:
            payload["selector"] = selector
        try:
            result = brain.browser_manager.call(chat_id, "/content", payload)
        except Exception as e:
            return f"ERROR: content read failed: {e}"
        content = result.get("content") or ""
        return content if content else "(empty page)"
    finally:
        db.db.close()
