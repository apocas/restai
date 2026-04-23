def browser_fill(selector: str, value: str = None, secret_ref: str = None, **kwargs) -> str:
    """Type text into an input/textarea.

    Exactly one of `value` or `secret_ref` must be provided. Use
    `secret_ref` for passwords / API keys / anything you should NOT
    echo into the conversation: the tool resolves the stored plaintext
    server-side and types it into the browser without the value ever
    entering your context. Admin-managed secrets live under
    Project → Secrets.

    Args:
        selector (str): CSS / text selector of the input.
        value (str): Literal text to type. Leave empty if using `secret_ref`.
        secret_ref (str): Name of a project secret to resolve. Leave empty
            if using `value`.
    """
    from restai.llms.tools._browser_common import _browser_ctx

    ctx, err = _browser_ctx(kwargs)
    if ctx is None:
        return err
    brain, chat_id, project_id, _, db = ctx
    try:
        if not selector or not selector.strip():
            return "ERROR: selector is required."
        has_value = value is not None and value != ""
        has_ref = secret_ref is not None and secret_ref != ""
        if has_value == has_ref:  # both or neither
            return "ERROR: provide exactly one of `value` or `secret_ref`."

        if has_ref:
            plaintext = db.resolve_project_secret(project_id, secret_ref)
            if plaintext is None:
                return (
                    f"ERROR: secret '{secret_ref}' not found on this project. "
                    "Add it under Project → Secrets."
                )
            typed = plaintext
        else:
            typed = value

        try:
            brain.browser_manager.call(chat_id, "/fill", {"selector": selector, "value": typed})
        except Exception as e:
            return f"ERROR: fill failed: {e}"
        if has_ref:
            # Crucial: never echo the plaintext back to the LLM.
            return f"Filled {selector!r} with secret '{secret_ref}'."
        # Echo ok for literal values — the agent already had it in context.
        return f"Filled {selector!r} with {len(typed)}-char value."
    finally:
        db.db.close()
