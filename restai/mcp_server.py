"""
MCP Server that exposes user projects as consumable tools.

This module creates an MCP server that converts all projects a user has access to
into tools, using the human_description, human_name, and name from each project.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence
from fastmcp import FastMCP
from pydantic import BaseModel
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username
from restai.models.models import User, QuestionModel, ChatModel
from restai.helper import question_main, chat_main
from restai.brain import Brain
from fastapi import HTTPException, Request, BackgroundTasks, Depends
import json

logger = logging.getLogger(__name__)


class ProjectToolInput(BaseModel):
    """Input schema for project tools."""
    question: str
    chat_mode: bool = False
    chat_id: Optional[str] = None
    image: Optional[str] = None
    negative: Optional[str] = None


class MCPProjectServer:
    """MCP Server that exposes user projects as tools."""
    
    def __init__(self, app, brain: Brain):
        self.app = app
        self.brain = brain
        self.mcp = FastMCP("restai-projects")
        self._setup_tools()
    
    def _setup_tools(self):
        """Setup the dynamic project tools."""
        
        @self.mcp.tool()
        async def get_user_projects(username: str) -> Dict[str, Any]:
            """
            Get all projects accessible by a user.
            
            Args:
                username: The username to get projects for
                
            Returns:
                Dictionary containing user's projects information
            """
            try:
                db_wrapper = get_db_wrapper()
                user = db_wrapper.get_user_by_username(username)
                if not user:
                    return {"error": "User not found"}
                
                # Get user's projects through teams and direct associations
                user_projects = []
                
                # Get directly associated projects
                for project in user.projects:
                    if project not in user_projects:
                        user_projects.append(project)
                
                projects_info = []
                for project in user_projects:
                    projects_info.append({
                        "id": project.id,
                        "name": project.name,
                        "human_name": project.human_name,
                        "human_description": project.human_description,
                        "type": project.type,
                        "public": project.public
                    })
                
                return {
                    "username": username,
                    "projects": projects_info,
                    "total_projects": len(projects_info)
                }
                
            except Exception as e:
                logger.error(f"Error getting user projects: {e}")
                return {"error": str(e)}
        
        # This will be populated dynamically when the server starts
        self._register_project_tools()
    
    def _register_project_tools(self):
        """Register project-specific tools dynamically."""
        
        @self.mcp.tool()
        async def query_project(
            project_identifier: str,
            question: str,
            username: str,
            chat_mode: bool = False,
            chat_id: Optional[str] = None,
            image: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Query a specific project with a question or chat message.
            
            Args:
                project_identifier: Project name or ID
                question: The question to ask the project
                username: Username of the person making the request
                chat_mode: Whether to use chat mode (stateful) or question mode (stateless)
                chat_id: Chat session ID for chat mode
                image: Base64 encoded image for vision projects
                
            Returns:
                Dictionary containing the project's response
            """
            try:
                db_wrapper = get_db_wrapper()
                user = db_wrapper.get_user_by_username(username)
                if not user:
                    return {"error": "User not found"}
                
                # Find the project
                project = db_wrapper.get_project_by_id(int(project_identifier))
                
                if not project:
                    return {"error": f"Project '{project_identifier}' not found"}
                
                # Check if user has access to this project
                user_has_access = False
                
                # Check direct association
                if project in user.projects:
                    user_has_access = True
                
                # Check if project is public
                if not user_has_access and project.public:
                    user_has_access = True
                
                if not user_has_access:
                    return {"error": f"Access denied to project '{project_identifier}'"}
                
                # Create a mock request object
                class MockRequest:
                    def __init__(self, app):
                        self.app = app
                
                request = MockRequest(self.app)
                background_tasks = BackgroundTasks()
                
                # Use question mode (stateless)
                question_input = QuestionModel(
                    question=question,
                    image=image
                )
                
                result = await question_main(
                    request,
                    self.brain,
                    project,
                    question_input,
                    user,
                    db_wrapper,
                    background_tasks
                )
                
                # Convert result to dictionary if it's not already
                if hasattr(result, 'dict'):
                    result = result.dict()
                elif hasattr(result, '__dict__'):
                    result = result.__dict__
                
                return {
                    "project_id": project.id,
                    "project_name": project.name,
                    "project_human_name": project.human_name,
                    "project_type": project.type,
                    "result": result
                }
                
            except HTTPException as e:
                return {"error": f"HTTP {e.status_code}: {e.detail}"}
            except Exception as e:
                logger.error(f"Error querying project {project_identifier}: {e}")
                return {"error": str(e)}
    
    def get_mcp_app(self):
        """Get the FastMCP application."""
        return self.mcp


def create_mcp_server(app, brain: Brain) -> FastMCP:
    """
    Create and configure the MCP server.
    
    Args:
        app: FastAPI application instance
        brain: Brain instance for project logic
        
    Returns:
        Configured FastMCP instance
    """
    server = MCPProjectServer(app, brain)
    return server.get_mcp_app()
