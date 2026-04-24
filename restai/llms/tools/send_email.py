def send_email(subject: str, body: str, **kwargs) -> str:
    """Send an email to the project's pre-configured recipient via SMTP.

    The recipient address is fixed (``email_default_to`` on the project),
    typically the admin's own inbox for proactive notifications. The
    SMTP relay is also configured per-project (``smtp_host``,
    ``smtp_port``, ``smtp_user``, ``smtp_password``, ``smtp_from``).

    Use this when the agent needs to push a status update, alert, or
    finished-job notification to a known email address.

    Args:
        subject (str): Email subject line.
        body (str): Plain-text body of the email.
    """
    import json
    import smtplib
    from email.message import EmailMessage

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    if not brain or project_id is None:
        return "ERROR: send_email requires a project context — it can only be used by an agent project."

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

        host = opts.get("smtp_host") or ""
        port = int(opts.get("smtp_port") or 587)
        user = opts.get("smtp_user") or ""
        password = decrypt_field(opts.get("smtp_password") or "")
        sender = opts.get("smtp_from") or user
        to = opts.get("email_default_to") or ""

        if not host or not sender:
            return (
                "ERROR: Email is not configured for this project. "
                "Set smtp_host and smtp_from in project edit → Integrations."
            )
        if not to:
            return (
                "ERROR: No default email recipient configured. "
                "Set email_default_to in project options."
            )

        msg = EmailMessage()
        msg["Subject"] = subject or "(no subject)"
        msg["From"] = sender
        msg["To"] = to
        msg.set_content(body or "")

        try:
            # Port 465 means implicit TLS; everything else assumes
            # STARTTLS on a plaintext socket (the modern default that
            # Gmail, SES, Mailgun, Postmark, etc. all support).
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                    if user and password:
                        s.login(user, password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=15) as s:
                    s.ehlo()
                    try:
                        s.starttls()
                        s.ehlo()
                    except smtplib.SMTPNotSupportedError:
                        # Some local relays don't offer STARTTLS — fall
                        # through and send unencrypted. The admin chose
                        # this host on purpose.
                        pass
                    if user and password:
                        s.login(user, password)
                    s.send_message(msg)
        except Exception as e:
            return f"ERROR: SMTP send failed: {e}"

        return f"OK: email sent to {to}."
    finally:
        db.db.close()
