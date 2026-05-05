def terminal(command: str, secret_refs=None, **kwargs) -> str:
    """Execute a command in a sandboxed Docker container. Use this as a terminal.
    The container persists across commands within the same conversation,
    so you can build complex operations step by step (install packages, write files, run scripts, etc).

    For sensitive values like API tokens or passwords, use `secret_refs`
    to pull them from the project's Secrets store. Each name listed there
    is resolved server-side and exposed to the command as an environment
    variable of the same name — the plaintext NEVER enters your context.
    Reference them in the command with normal shell `$NAME` syntax.

    Example:
        secret_refs=["HA_TOKEN"]
        command='curl -fsS -H "Authorization: Bearer $HA_TOKEN" http://192.168.1.120:8123/api/'

    Args:
        command (str): Shell command to execute. Use `$NAME` to reference any
            secret listed in `secret_refs`.
        secret_refs (list[str] | str): One secret name, or a list of secret
            names, to inject as environment variables. Names must match
            entries in the project's Secrets tab.
    """
    brain = kwargs.get("_brain")
    chat_id = kwargs.get("_chat_id")
    project_id = kwargs.get("_project_id")

    if not brain or not getattr(brain, "docker_manager", None):
        return "ERROR: Docker is not configured. An admin must configure Docker in Settings to use the terminal tool."

    # Normalize secret_refs into a clean list of names. Accept str /
    # list / comma-separated string / JSON-stringified list for
    # ergonomics — Ollama-style tool calls in particular sometimes
    # ship list args as `'["HA_TOKEN"]'` rather than a real array, so
    # be liberal in what we accept and strict about what we look up.
    refs: list[str] = []
    if isinstance(secret_refs, (list, tuple)):
        refs = [str(s) for s in secret_refs]
    elif isinstance(secret_refs, str):
        s = secret_refs.strip()
        # Try JSON first — handles `'["HA_TOKEN", "OTHER"]'`.
        if s.startswith("[") and s.endswith("]"):
            try:
                import json as _json
                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    refs = [str(x) for x in parsed]
            except Exception:
                pass
        # Fallback / non-JSON: comma-separated or single name.
        if not refs:
            refs = s.split(",")
    # Scrub stray quotes / brackets / whitespace each model variant adds.
    refs = [r.strip().strip("\"'[]") for r in refs]
    refs = [r for r in refs if r]

    env: dict[str, str] = {}
    if refs:
        if project_id is None:
            return "ERROR: secret_refs requires project context — only available inside an agent project."
        from restai.database import open_db_wrapper

        db = open_db_wrapper()
        try:
            missing = []
            for name in refs:
                plaintext = db.resolve_project_secret(int(project_id), name)
                if plaintext is None:
                    missing.append(name)
                else:
                    env[name] = plaintext
            if missing:
                return (
                    f"ERROR: project secret(s) not found: {', '.join(missing)}. "
                    "Add them under Project → Secrets."
                )
        finally:
            db.close()

    return brain.docker_manager.exec_command(chat_id or "ephemeral", command, env=env or None)
