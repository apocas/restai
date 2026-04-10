def terminal(command: str, **kwargs) -> str:
    """Execute a command in a sandboxed Docker container. Use this as a terminal.
    The container persists across commands within the same conversation,
    so you can build complex operations step by step (install packages, write files, run scripts, etc).

    Args:
        command (str): Shell command to execute.
    """
    brain = kwargs.get("_brain")
    chat_id = kwargs.get("_chat_id")

    if not brain or not getattr(brain, "docker_manager", None):
        return "ERROR: Docker is not configured. An admin must configure Docker in Settings to use the terminal tool."

    return brain.docker_manager.exec_command(chat_id or "ephemeral", command)
