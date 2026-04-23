def browser_download(selector: str, timeout: int = 30, **kwargs) -> str:
    """Click something that triggers a file download. The file lands in
    `/home/user/downloads/<name>` inside the browser container — use the
    `terminal` tool (if enabled) to inspect/move it.

    Args:
        selector (str): CSS selector of the download link / button.
        timeout (int): Max seconds to wait for the download to complete.
            Default 30.
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
            t = max(5, min(int(timeout), 300))
        except (TypeError, ValueError):
            t = 30
        try:
            result = brain.browser_manager.call(
                chat_id, "/download", {"selector": selector, "timeout": t}
            )
        except Exception as e:
            return f"ERROR: download failed: {e}"
        path = result.get("path")
        size = result.get("size")
        mime = result.get("mime")
        name = result.get("filename")
        return (
            f"Downloaded {name!r} ({size} bytes, {mime}) → {path}\n"
            "Use the `terminal` tool to open/move this file inside the sandbox."
        )
    finally:
        db.db.close()
