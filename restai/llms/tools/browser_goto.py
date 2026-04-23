def browser_goto(url: str, **kwargs) -> str:
    """Navigate the agent's browser to a URL.

    The project's `browser_allowed_domains` option is enforced: if the
    admin set an allowlist, only those domains (or suffix globs like
    `*.example.com`) are reachable.

    Args:
        url (str): Destination URL (must include scheme).
    """
    from restai.llms.tools._browser_common import _browser_ctx, _check_allowed_domain

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, project, db = ctx
    try:
        err = _check_allowed_domain(project, url or "")
        if err:
            return err
        try:
            result = brain.browser_manager.call(chat_id, "/goto", {"url": url})
        except Exception as e:
            return f"ERROR: navigation failed: {e}"
        return (
            f"Navigated to {result.get('final_url')} — title: "
            f"{result.get('title') or '(untitled)'}"
        )
    finally:
        db.db.close()
