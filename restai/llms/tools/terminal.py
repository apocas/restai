def terminal(command: str, **kwargs) -> str:
    """Execute a command in a sandboxed Docker container. Use this as a terminal.
    The container persists across commands within the same conversation,
    so you can build complex operations step by step (install packages, write files, run scripts, etc).

    Every project secret is injected into the container as an
    environment variable on each exec — reference them however your
    command prefers (shell `$HA_TOKEN`, Python `os.environ['HA_TOKEN']`,
    Node `process.env.HA_TOKEN`, etc.). The plaintext NEVER enters
    your context.

    Example:
        command='curl -fsS -H "Authorization: Bearer $HA_TOKEN" $HA_URL/api/'

    Looking at images / PDFs / other rich content:
        Save the file into the special directory `/artifacts/` and on
        your NEXT turn it will be visible to you as a multimodal block
        (vision input for images, document for PDFs, mention for other
        types). One mental model — no separate tool to call.

        Example: download a camera snapshot and look at it next turn:
            terminal(
                command='mkdir -p /artifacts && '
                        'curl -fsS -H "Authorization: Bearer $HA_TOKEN" '
                        'http://192.168.1.120:8123/api/camera_proxy/camera.front '
                        '-o /artifacts/snap.jpg'
            )

    Args:
        command (str): Shell command to execute. Use `$NAME` to reference
            any project secret (auto-resolved). Save artifacts you want
            to view next turn into `/artifacts/`.
    """
    brain = kwargs.get("_brain")
    chat_id = kwargs.get("_chat_id")
    project_id = kwargs.get("_project_id")

    if not brain or not getattr(brain, "docker_manager", None):
        return "ERROR: Docker is not configured. An admin must configure Docker in Settings to use the terminal tool."

    # Project secrets land in the exec env so the model can reference
    # them with whatever syntax suits the command. Plaintext goes
    # straight to the kernel, never to the LLM.
    env: dict[str, str] = {}
    if project_id is not None:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            env = db.resolve_all_project_secrets(int(project_id))
        finally:
            db.close()

    output = brain.docker_manager.exec_command(chat_id or "ephemeral", command, env=env or None)

    # /artifacts/ convention: new files staged for the next turn become
    # multimodal blocks (image / document / mention) via the agent loop.
    # Appended as a short text notice so the model knows about the
    # attachment without seeing the bytes.
    try:
        new_artifacts = brain.docker_manager.collect_new_artifacts(chat_id or "ephemeral")
    except Exception:
        new_artifacts = []
    if new_artifacts:
        from restai.agent2 import artifacts as _artifacts
        _artifacts.stage(chat_id or "ephemeral", new_artifacts)
        # Image artifacts get the same display path as `draw_image`: stash
        # bytes in Brain's image cache and emit `![](…/image/cache/…)` so
        # the chat UI renders them inline. `_drive_runtime` mirrors the
        # markdown into the final answer if the LLM forgets to echo it.
        from restai import config as _config
        public_url = (getattr(_config, "RESTAI_URL", None) or "").rstrip("/")
        notices = []
        image_lines = []
        for a in new_artifacts:
            kb = max(1, (a.get("size") or 0) // 1024)
            tag = " (too large — only mentioned, not attached)" if a.get("truncated") else ""
            notices.append(f"  - {a['name']} ({a['mime']}, ~{kb} KB){tag}")
            mime = (a.get("mime") or "").lower()
            data = a.get("bytes")
            if not a.get("truncated") and mime.startswith("image/") and data:
                try:
                    filename = brain.cache_image(data, mime_type=mime)
                except Exception:
                    continue
                url = f"{public_url}/image/cache/{filename}" if public_url else f"/image/cache/{filename}"
                image_lines.append(f"![{a['name']}]({url})")
        output = (output or "") + (
            "\n\n[artifacts] New files in /artifacts/ — visible to you next turn:\n"
            + "\n".join(notices)
        )
        if image_lines:
            output += "\n\n" + "\n".join(image_lines)
    return output
