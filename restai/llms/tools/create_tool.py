import json
import re


_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_MAX_CODE_SIZE = 10240  # 10KB


def create_tool(name: str, description: str, parameters: str, code: str, **kwargs) -> str:
    """Create a reusable tool for this project that runs in a sandboxed Docker container.
    The tool will be available in this and all future conversations for this project.

    Args:
        name (str): Tool name (letters, digits, underscore only, e.g. "fetch_page_title").
        description (str): What the tool does (shown to the LLM when deciding which tool to use).
        parameters (str): JSON schema string describing the tool's input parameters (e.g. '{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}').
        code (str): Python code that receives an `args` dict with the parameters and should print the result to stdout.
    """
    brain = kwargs.get("_brain")
    chat_id = kwargs.get("_chat_id")
    project_id = kwargs.get("_project_id")

    if not brain or not getattr(brain, "docker_manager", None):
        return "ERROR: Docker is not configured. An admin must configure Docker in Settings to create tools."

    if not project_id:
        return "ERROR: No project context available."

    # Validate name
    if not name or not _NAME_RE.match(name):
        return f"ERROR: Invalid tool name '{name}'. Use only letters, digits, and underscores. Must start with a letter or underscore."

    if not description or not description.strip():
        return "ERROR: Description is required."

    if not code or not code.strip():
        return "ERROR: Code is required."

    if len(code) > _MAX_CODE_SIZE:
        return f"ERROR: Code is too large ({len(code)} bytes). Maximum is {_MAX_CODE_SIZE} bytes."

    # Validate parameters JSON
    try:
        params_dict = json.loads(parameters) if isinstance(parameters, str) else parameters
    except json.JSONDecodeError as e:
        return f"ERROR: Invalid parameters JSON: {e}"

    # Test the code by running it in Docker with empty args
    script = f"import json, sys\nargs = json.loads(sys.stdin.readline() or '{{}}')\n{code}"
    test_result = brain.docker_manager.run_script(
        chat_id or "ephemeral",
        script,
        stdin_data="{}",
    )
    if test_result.startswith("ERROR:"):
        return f"ERROR: Code validation failed — {test_result}"

    # Save to database
    from restai.database import DBWrapper
    db = DBWrapper()
    try:
        db.upsert_project_tool(
            project_id=project_id,
            name=name,
            description=description,
            parameters=json.dumps(params_dict) if isinstance(params_dict, dict) else parameters,
            code=code,
        )
    finally:
        db.db.close()

    return f"Tool '{name}' created successfully. You can now call it by name."
