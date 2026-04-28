def delete_routine(routine_id: int, **kwargs) -> str:
    """Delete a scheduled routine on the project this agent belongs to.

    Use `list_routines` first to find the id of the routine to delete.
    The tool will refuse to delete a routine that belongs to a different
    project — agents can only manage their own.

    Args:
        routine_id (int): The id of the routine to delete (from
            list_routines).
    """
    project_id = kwargs.get("_project_id")
    if project_id is None:
        return "ERROR: delete_routine requires a project context."

    try:
        rid = int(routine_id)
    except (TypeError, ValueError):
        return "ERROR: routine_id must be an integer."

    from restai.database import open_db_wrapper

    db = open_db_wrapper()
    try:
        routine = db.get_project_routine_by_id(rid)
        if routine is None:
            return f"ERROR: routine {rid} not found."
        if routine.project_id != int(project_id):
            # Defense in depth — the tool's project context comes from the
            # agent runtime and shouldn't ever leak across projects, but
            # double-check before mutating.
            return f"ERROR: routine {rid} does not belong to this project."
        name = routine.name
        ok = db.delete_project_routine(rid)
        if not ok:
            return f"ERROR: failed to delete routine {rid}."
        return f"Deleted routine id={rid} name='{name}'."
    except Exception as e:
        return f"ERROR: failed to delete routine: {e}"
    finally:
        db.db.close()
