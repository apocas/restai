def create_routine(name: str, message: str, schedule_minutes: int, enabled: bool = True, **kwargs) -> str:
    """Create a new scheduled routine on the project this agent belongs to.

    A routine is a message that auto-fires on the project on a fixed
    cadence. The cron runner picks up routines whose `schedule_minutes`
    has elapsed since their last run and fires the `message` through the
    project's normal chat pipeline (so any tool the agent has access to
    runs on each tick).

    Args:
        name (str): Short label for the routine (shown in the UI). Required.
        message (str): The message text that gets fired as a user message
            on each tick. Required.
        schedule_minutes (int): How often to fire, in minutes. Minimum 1.
            Practical floor is 5–10 to avoid hammering the LLM.
        enabled (bool): If False, the routine is created but won't fire
            until re-enabled via the UI / API. Defaults to True.
    """
    project_id = kwargs.get("_project_id")
    if project_id is None:
        return "ERROR: create_routine requires a project context."

    if not name or not name.strip():
        return "ERROR: name is required."
    if not message or not message.strip():
        return "ERROR: message is required."
    try:
        sched = int(schedule_minutes)
    except (TypeError, ValueError):
        return "ERROR: schedule_minutes must be an integer (minutes between firings)."
    if sched < 1:
        return "ERROR: schedule_minutes must be at least 1."

    from restai.database import get_db_wrapper

    db = get_db_wrapper()
    try:
        routine = db.create_project_routine(
            project_id=int(project_id),
            name=name.strip(),
            message=message.strip(),
            schedule_minutes=sched,
            enabled=bool(enabled),
        )
    except Exception as e:
        db.db.close()
        return f"ERROR: failed to create routine: {e}"

    try:
        return (
            f"Created routine id={routine.id} name='{routine.name}' "
            f"every={routine.schedule_minutes}min "
            f"({'enabled' if routine.enabled else 'disabled'}). "
            f"It will first fire within ~{routine.schedule_minutes} minute(s)."
        )
    finally:
        db.db.close()
