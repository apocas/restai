def send_telegram(text: str, **kwargs) -> str:
    """Send a message to the project's pre-configured Telegram chat.

    Telegram bots cannot initiate conversations — the message goes to the
    chat configured by the admin in project options (`telegram_default_chat_id`).
    Use this when the agent needs to push a notification or status update
    to a known Telegram destination.

    Args:
        text (str): Message text to send. Long messages are split automatically
            at Telegram's 4096-character limit.
    """
    import json

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    if not brain or project_id is None:
        return "ERROR: send_telegram requires a project context — it can only be used by an agent project."

    from restai.database import get_db_wrapper
    from restai.utils.crypto import decrypt_field
    from restai.telegram import send_message

    db = get_db_wrapper()
    try:
        proj = db.get_project_by_id(int(project_id))
        if proj is None:
            return f"ERROR: Project {project_id} not found."

        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            opts = {}

        token = decrypt_field(opts.get("telegram_token") or "")
        if not token:
            return (
                "ERROR: Telegram is not configured for this project. "
                "Set the bot token in project edit → Integrations."
            )

        chat_id = opts.get("telegram_default_chat_id")
        if not chat_id:
            return (
                "ERROR: No default Telegram chat configured. "
                "Set telegram_default_chat_id in project options "
                "(message the bot with /chatid in Telegram to find it)."
            )

        try:
            send_message(token, int(chat_id), text)
        except Exception as e:
            return f"ERROR: Telegram send failed: {e}"

        return f"OK: message sent to Telegram chat {chat_id}."
    finally:
        db.db.close()
