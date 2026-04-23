def browser_screenshot(selector: str = None, **kwargs) -> str:
    """Take a screenshot of the current page (or one element) and return a
    markdown image link. The PNG is stored in the 24h image cache so the
    chat UI renders it inline — the agent runtime also splices the URL
    into the final answer if the LLM forgets to echo it.

    Args:
        selector (str): Optional CSS selector of a specific element to
            screenshot. Defaults to the current viewport.
    """
    import base64 as _b64

    from restai.llms.tools._browser_common import _browser_ctx

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, _, _, db = ctx
    try:
        payload = {}
        if selector:
            payload["selector"] = selector
        try:
            result = brain.browser_manager.call(chat_id, "/screenshot", payload)
        except Exception as e:
            return f"ERROR: screenshot failed: {e}"
        png_b64 = result.get("png_b64") or ""
        if not png_b64:
            return "ERROR: no screenshot returned."
        png_bytes = _b64.b64decode(png_b64)
        filename = brain.cache_image(png_bytes, mime_type="image/png")

        # Prefer absolute URLs when the deployment knows its public host,
        # matches the draw_image tool's approach.
        from restai import config as _config
        public_url = (getattr(_config, "RESTAI_URL", None) or "").rstrip("/")
        url = f"{public_url}/image/cache/{filename}" if public_url else f"/image/cache/{filename}"
        return f"![]({url})"
    finally:
        db.db.close()
