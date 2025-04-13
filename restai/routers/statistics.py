import logging
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from restai import config
from restai.auth import (
    get_current_username,
)
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import (
    User,
)
from restai.models.databasemodels import OutputDatabase, ProjectDatabase, users_projects
from sqlalchemy import func, or_


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()

@router.get("/statistics/top-projects")
async def get_top_projects_by_tokens(
    limit: int = 10,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        query = (
            db_wrapper.db.query(
                ProjectDatabase,
                func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).label("total_tokens"),
                func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost).label("total_cost")
            )
            .join(OutputDatabase, ProjectDatabase.id == OutputDatabase.project_id)
        )

        # Filter based on user access
        if not user.is_admin:
            # Get projects user has access to (either owned or public)
            query = query.filter(
                or_(
                    ProjectDatabase.id.in_(
                        db_wrapper.db.query(users_projects.c.project_id)
                        .filter(users_projects.c.user_id == user.id)
                    ),
                    ProjectDatabase.public == True
                )
            )

        top_projects = (
            query
            .group_by(ProjectDatabase.id)
            .order_by(func.sum(OutputDatabase.input_tokens + OutputDatabase.output_tokens).desc())
            .limit(limit)
            .all()
        )

        return {
            "projects": [
                {
                    "id": project.ProjectDatabase.id,
                    "name": project.ProjectDatabase.name,
                    "type": project.ProjectDatabase.type,
                    "total_tokens": project.total_tokens,
                    "total_cost": project.total_cost
                }
                for project in top_projects
            ]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")