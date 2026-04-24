def send_sms(text: str, **kwargs) -> str:
    """Send an SMS to the project's pre-configured recipient via Twilio.

    The recipient phone number is fixed (``sms_default_to`` on the
    project, E.164 format with the leading '+'). Twilio credentials
    (``twilio_account_sid``, ``twilio_auth_token``,
    ``twilio_from_number``) come from the project's options.

    Use this when the agent needs to push a notification or status
    update to a known mobile number. SMS bodies are split at 1600
    characters to stay within Twilio's per-request limit.

    Args:
        text (str): Message text to send.
    """
    import json
    import requests

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    if not brain or project_id is None:
        return "ERROR: send_sms requires a project context — it can only be used by an agent project."

    from restai.database import get_db_wrapper
    from restai.utils.crypto import decrypt_field

    db = get_db_wrapper()
    try:
        proj = db.get_project_by_id(int(project_id))
        if proj is None:
            return f"ERROR: Project {project_id} not found."

        try:
            opts = json.loads(proj.options) if proj.options else {}
        except Exception:
            opts = {}

        sid = opts.get("twilio_account_sid") or ""
        token = decrypt_field(opts.get("twilio_auth_token") or "")
        from_number = opts.get("twilio_from_number") or ""
        to = opts.get("sms_default_to") or ""

        if not sid or not token or not from_number:
            return (
                "ERROR: SMS is not configured for this project. "
                "Set twilio_account_sid, twilio_auth_token, and twilio_from_number "
                "in project edit → Integrations."
            )
        if not to:
            return (
                "ERROR: No default SMS recipient configured. "
                "Set sms_default_to (E.164 with leading '+') in project options."
            )
        if not text:
            return "ERROR: empty SMS body."

        # Twilio's per-request body limit is 1600 chars; longer messages
        # get split into multiple sends so the agent doesn't see a
        # confusing partial-truncation failure.
        chunks = [text[i:i + 1600] for i in range(0, len(text), 1600)]
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        last_sid = None
        for chunk in chunks:
            try:
                resp = requests.post(
                    url,
                    auth=(sid, token),
                    data={"From": from_number, "To": to, "Body": chunk},
                    timeout=15,
                )
            except requests.RequestException as e:
                return f"ERROR: Twilio request failed: {e}"
            if resp.status_code >= 400:
                # Twilio's error JSON has {"message": "...", "code": NN}.
                try:
                    detail = resp.json().get("message", resp.text)
                except Exception:
                    detail = resp.text
                return f"ERROR: Twilio rejected SMS (HTTP {resp.status_code}): {detail}"
            try:
                last_sid = resp.json().get("sid")
            except Exception:
                last_sid = None

        return f"OK: SMS sent to {to} (sid={last_sid})."
    finally:
        db.db.close()
