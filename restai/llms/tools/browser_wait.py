def browser_wait(selector: str, timeout: int = 10, **kwargs) -> str:
    """Wait for an element to become visible in the current page. Use this
    when a click triggers a slow load or an element takes time to render.

    Args:
        selector (str): CSS / text selector to wait for.
        timeout (int): Max seconds to wait before giving up. Default 10.
    """
    from restai.llms.tools._browser_common import _browser_ctx

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, _, db = ctx
    try:
        if not selector:
            return "ERROR: selector is required."
        try:
            t = max(1, min(int(timeout), 60))
        except (TypeError, ValueError):
            t = 10
        try:
            result = brain.browser_manager.call(chat_id, "/wait", {"selector": selector, "timeout": t})
        except Exception as e:
            return f"ERROR: wait failed: {e}"
        if result.get("found"):
            return f"Element {selector!r} is visible."
        return f"Timed out after {t}s waiting for {selector!r}."
    finally:
        db.db.close()
