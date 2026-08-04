import re as _re
from uuid import uuid4 as _uuid4

# `$NAME`, `${NAME}`, and the os.environ['NAME'] / process.env.NAME forms the
# docstring tells the model to use.
_SECRET_REF_RE = _re.compile(
    r"""\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"""
    r"""|environ\[["']([A-Za-z_][A-Za-z0-9_]*)["']\]"""
    r"""|environ\.get\(["']([A-Za-z_][A-Za-z0-9_]*)["']"""
    r"""|process\.env\.([A-Za-z_][A-Za-z0-9_]*)"""
)


def _referenced_names(command: str) -> set:
    """Env-var names the command mentions. Only these get injected."""
    names = set()
    for groups in _SECRET_REF_RE.findall(command or ""):
        for g in groups:
            if g:
                names.add(g)
    return names


def _redact_secret_values(output: str, env: dict) -> str:
    """Replace any injected plaintext that echoed back with a placeholder.

    Defence in depth for the case where the command legitimately references a
    secret and then prints it (`echo $TOKEN`, a curl error quoting the URL, a
    stack trace). Very short values are skipped — redacting them would mangle
    unrelated output for no security gain.
    """
    if not output or not env:
        return output
    for name, value in env.items():
        if value and len(value) >= 6:
            output = output.replace(value, f"[REDACTED:{name}]")
    return output


def terminal(command: str, **kwargs) -> str:
    """Execute a command in a sandboxed Docker container. Use this as a terminal.
    The container persists across commands within the same conversation,
    so you can build complex operations step by step (install packages, write files, run scripts, etc).

    Project secrets you REFERENCE BY NAME in the command are injected into
    the container as environment variables for that exec — reference them
    however your command prefers (shell `$HA_TOKEN`, Python
    `os.environ['HA_TOKEN']`, Node `process.env.HA_TOKEN`). Only the names
    the command mentions are injected, and if a value shows up in the output
    it comes back as `[REDACTED:<name>]`. Do not try to print secrets — the
    plaintext never enters your context, and commands like `env` will not
    reveal secrets you did not name.

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

    # A literal "ephemeral" fallback is ONE container shared by every
    # project and user. When there is no conversation to scope to, use a
    # fresh per-call id instead; the idle-cleanup cron reaps it.
    sandbox_id = chat_id or f"ephemeral-{_uuid4().hex}"

    # Only the secrets this command actually references are injected, and any
    # that do appear in the output are redacted on the way back.
    #
    # Previously the ENTIRE project vault went into the exec env while
    # `exec_command` returns stdout+stderr verbatim to the model — so a single
    # turn of `terminal(command="env")` handed every credential to the LLM (and
    # thence to the chat transcript and inference log). The docstring's
    # "plaintext NEVER enters your context" was enforced by nothing.
    env: dict[str, str] = {}
    if project_id is not None:
        from restai.database import open_db_wrapper
        db = open_db_wrapper()
        try:
            all_secrets = db.resolve_all_project_secrets(int(project_id))
        finally:
            db.close()
        referenced = _referenced_names(command)
        env = {name: val for name, val in all_secrets.items() if name in referenced}

    output = brain.docker_manager.exec_command(sandbox_id, command, env=env or None)
    output = _redact_secret_values(output, env)

    # /artifacts/ convention: new files staged for the next turn become
    # multimodal blocks (image / document / mention) via the agent loop.
    # Appended as a short text notice so the model knows about the
    # attachment without seeing the bytes.
    try:
        new_artifacts = brain.docker_manager.collect_new_artifacts(sandbox_id)
    except Exception:
        new_artifacts = []
    if new_artifacts:
        from restai.agent2 import artifacts as _artifacts
        _artifacts.stage(sandbox_id, new_artifacts)
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
