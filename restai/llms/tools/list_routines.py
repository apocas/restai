def list_routines(**kwargs) -> str:
    """List all scheduled routines on the project this agent belongs to.

    Routines are scheduled messages that auto-fire on a fixed cadence via
    the cron runner. Use this tool when the user asks what's scheduled,
    when to know a routine's id (needed for delete_routine), or to confirm
    a routine you just created actually exists.

    Returns a human-readable line per routine: id, name, schedule (in
    minutes), enabled flag, last-run timestamp + result snippet, and the
    message that fires.
    """
    project_id = kwargs.get("_project_id")
    if project_id is None:
        return "ERROR: list_routines requires a project context."

    from restai.database import get_db_wrapper

    db = get_db_wrapper()
    try:
        routines = db.get_project_routines(int(project_id))
    finally:
        db.db.close()

    if not routines:
        return "No routines configured on this project."

    lines = [f"{len(routines)} routine(s):"]
    for r in routines:
        last = r.last_run.isoformat(timespec="seconds") if r.last_run else "never"
        result_snip = ""
        if r.last_result:
            snip = r.last_result.strip().replace("\n", " ")
            if len(snip) > 120:
                snip = snip[:120] + "…"
            result_snip = f' last_result="{snip}"'
        enabled = "enabled" if r.enabled else "disabled"
        lines.append(
            f"- id={r.id} name='{r.name}' every={r.schedule_minutes}min "
            f"{enabled} last_run={last}{result_snip} message='{r.message}'"
        )
    return "\n".join(lines)
