"""Natural-language admin search endpoint backed by the system LLM."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from restai.auth import get_current_username
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User


router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(max_length=1000, description="Natural-language search query")


@router.post("/search", tags=["Search"])
async def smart_search(
    request: Request,
    body: SearchRequest,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Translate a natural-language query into a structured search using the system LLM."""
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    from restai.utils.search_ai import run_search
    try:
        return await run_search(request.app.state.brain, db_wrapper, user, body.query)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
