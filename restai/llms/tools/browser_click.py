def browser_click(selector: str, **kwargs) -> str:
    """Click an element in the current page.

    Args:
        selector (str): CSS selector (or Playwright text selector like
            `text=Log in` / `button:has-text('Save')`). Required.
    """
    from restai.llms.tools._browser_common import (
        _browser_ctx,
        _discard_if_landed_off_limits,
    )

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, project, db = ctx
    try:
        if not selector or not selector.strip():
            return "ERROR: selector is required."
        try:
            result = brain.browser_manager.call(chat_id, "/click", {"selector": selector})
        except Exception as e:
            return f"ERROR: click failed: {e}"
        url = result.get("url_after")
        # A click is a navigation primitive too — following a link to an
        # internal host bypassed the goto-time check entirely.
        land_err = _discard_if_landed_off_limits(brain, chat_id, project, url)
        if land_err:
            return land_err
        nearby = (result.get("nearby_text") or "").strip()
        if nearby:
            preview = nearby if len(nearby) <= 400 else (nearby[:400] + "…")
            return f"Clicked — url now {url}\n\n{preview}"
        return f"Clicked — url now {url}"
    finally:
        db.db.close()
