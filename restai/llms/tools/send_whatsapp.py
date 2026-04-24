def send_whatsapp(text: str, **kwargs) -> str:
    """Send a WhatsApp message to the project's pre-configured recipient.

    WhatsApp's free-form messaging is constrained by Meta's 24-hour
    customer service window: you can only send free-form text to a
    number that has messaged the bot in the last 24 hours. Outside that
    window Meta requires a pre-approved template, which this tool does
    NOT support — the call will fail with the API error message.

    The recipient is fixed (``whatsapp_default_to`` on the project),
    typically the admin's own number for proactive notifications. Use
    this when the agent needs to push a status update to a known
    WhatsApp destination.

    Args:
        text (str): Message text to send. Long messages are split
            automatically at WhatsApp's 4096-character limit.
    """
    import json

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    if not brain or project_id is None:
        return "ERROR: send_whatsapp requires a project context — it can only be used by an agent project."

    from restai.database import get_db_wrapper
    from restai.utils.crypto import decrypt_field
    from restai.whatsapp import send_message

    db = get_db_wrapper()
    try:
        proj = db.get_project_by_id(int(project_id))
        if proj is None:
            return f"ERROR: Project {project_id} not found."

        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            opts = {}

        access_token = decrypt_field(opts.get("whatsapp_access_token") or "")
        phone_number_id = opts.get("whatsapp_phone_number_id") or ""
        to = (opts.get("whatsapp_default_to") or "").strip().lstrip("+")

        if not access_token or not phone_number_id:
            return (
                "ERROR: WhatsApp is not configured for this project. "
                "Set the access token and phone number id in project edit → Integrations."
            )
        if not to:
            return (
                "ERROR: No default WhatsApp recipient configured. "
                "Set whatsapp_default_to (E.164, no '+') in project options."
            )

        try:
            send_message(access_token, phone_number_id, to, text)
        except Exception as e:
            return f"ERROR: WhatsApp send failed: {e}"

        return f"OK: message sent to WhatsApp recipient {to}."
    finally:
        db.db.close()
