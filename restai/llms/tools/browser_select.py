def browser_select(selector: str, option: str, **kwargs) -> str:
    """Pick an option from a `<select>` dropdown.

    Args:
        selector (str): CSS selector of the `<select>` element.
        option (str): The option's value or visible label to select.
    """
    from restai.llms.tools._browser_common import _browser_ctx

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, _, db = ctx
    try:
        if not selector or option is None:
            return "ERROR: selector and option are required."
        try:
            brain.browser_manager.call(chat_id, "/select", {"selector": selector, "option": option})
        except Exception as e:
            return f"ERROR: select failed: {e}"
        return f"Selected {option!r} in {selector!r}."
    finally:
        db.db.close()
