"""Internal MCP server exposing RESTai projects as tools."""

import json
import logging
from typing import Optional

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from restai.database import get_db_wrapper
from restai.models.models import QuestionModel, User
from restai.models.databasemodels import ProjectDatabase

logger = logging.getLogger(__name__)


def _authenticate():
    """Authenticate the current MCP request via Bearer API key.

    Uses FastMCP's get_http_request() to access the underlying HTTP request,
    then validates the API key against the database.

    Returns:
        Tuple of (User, DBWrapper) on success.
    Raises:
        PermissionError on authentication failure.
    """
    request = get_http_request()
    auth_header = request.headers.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        raise PermissionError("Missing or invalid Authorization header. Use: Bearer <api_key>")

    token = auth_header[7:]  # Strip "Bearer "
    db_wrapper = get_db_wrapper()
    user_db, api_key_row = db_wrapper.get_user_by_apikey(token)
    if user_db is None:
        db_wrapper.db.close()
        raise PermissionError("Invalid API key")

    user = User.model_validate(user_db)

    if api_key_row is not None:
        if api_key_row.allowed_projects:
            try:
                import json
                user.api_key_allowed_projects = json.loads(api_key_row.allowed_projects)
            except (json.JSONDecodeError, TypeError):
                pass
        user.api_key_read_only = api_key_row.read_only or False

    return user, db_wrapper


def create_mcp_server(app_ref) -> FastMCP:
    """Create the MCP server with project tools.

    Args:
        app_ref: FastAPI app instance (for accessing brain via app.state.brain).
    """
    mcp = FastMCP(
        name="RESTai",
        instructions=(
            "RESTai MCP Server. Use list_projects to discover available AI projects, "
            "then use query_project to interact with them."
        ),
    )

    @mcp.tool()
    async def list_projects() -> str:
        """List all AI projects you have access to.

        Returns a JSON list of projects with name, type, and description.
        Use the project name with query_project to send questions.
        """
        user, db_wrapper = _authenticate()
        try:
            query = db_wrapper.db.query(ProjectDatabase)
            if not user.is_admin:
                query = query.filter(ProjectDatabase.id.in_(user.get_project_ids()))
            projects = query.all()
            result = []
            for p in projects:
                entry = {"name": p.name, "type": p.type}
                if p.human_name:
                    entry["human_name"] = p.human_name
                if p.human_description:
                    entry["description"] = p.human_description
                result.append(entry)
            return json.dumps(result, indent=2)
        finally:
            db_wrapper.db.close()

    @mcp.tool()
    async def query_project(
        project_name: str,
        question: str = "",
        image: Optional[str] = None,
    ) -> str:
        """Send a question to an AI project and get the response.

        Args:
            project_name: Name of the project (from list_projects).
            question: The question or prompt to send.
            image: Optional base64-encoded image for vision-capable projects.
        """
        from fastapi import BackgroundTasks
        from restai.helper import question_main
        from restai.brain import Brain

        user, db_wrapper = _authenticate()
        try:
            project_db = db_wrapper.get_project_by_name(project_name)
            if project_db is None:
                return f"Error: Project '{project_name}' not found."

            if not user.has_project_access(project_db.id):
                return f"Error: Access denied to project '{project_name}'."

            brain: Brain = app_ref.state.brain
            project = brain.find_project(project_db.id, db_wrapper)
            if project is None:
                return f"Error: Could not load project '{project_name}'."

            q_input = QuestionModel(question=question, image=image, stream=False)
            background_tasks = BackgroundTasks()
            http_request = get_http_request()

            result = await question_main(
                http_request,
                brain,
                project,
                q_input,
                user,
                db_wrapper,
                background_tasks,
            )

            if isinstance(result, dict):
                return result.get("answer", json.dumps(result))
            return str(result)
        except PermissionError:
            raise
        except Exception as e:
            logger.exception("Error querying project '%s': %s", project_name, e)
            return f"Error: {e}"
        finally:
            db_wrapper.db.close()

    return mcp
