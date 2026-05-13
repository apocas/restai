def send_email(subject: str, body: str, to: str = None, **kwargs) -> str:
    """Send an email via SMTP.

    SMTP credentials and the default recipient come from the project's
    owning team (Settings → Integrations → Email) and fall back to the
    platform-level Notifications settings. Nothing has to be configured
    on the project itself — the agent inherits whatever its team or
    platform admin has set.

    Args:
        subject (str): Email subject line.
        body (str): Plain-text body of the email.
        to (str, optional): Recipient address. If omitted, uses the
            team / platform `email_default_to`.
    """
    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    if not brain or project_id is None:
        return "ERROR: send_email requires a project context — it can only be used by an agent project."

    from restai.database import open_db_wrapper
    from restai.utils.email import send_email as _send

    db = open_db_wrapper()
    try:
        proj = db.get_project_by_id(int(project_id))
        if proj is None:
            return f"ERROR: Project {project_id} not found."

        team_id = getattr(proj, "team_id", None)
        ok, detail = _send(subject=subject, body=body, to=to, team_id=team_id, db=db)
        return f"OK: {detail}" if ok else f"ERROR: {detail}"
    finally:
        db.db.close()
