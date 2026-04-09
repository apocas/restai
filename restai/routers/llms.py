import json
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Path, Request
import traceback
import logging
from restai import config
from restai.models.databasemodels import LLMDatabase, ProjectDatabase
from restai.models.models import LLMModel, LLMUpdate, User
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username, get_current_username_admin

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

def mask_api_key(options: Optional[dict]) -> Optional[dict]:
    if options is None:
        return options
    try:
        if "api_key" in options:
            options["api_key"] = "********"
        return options
    except Exception as e:
        logging.exception(e)
        return options


@router.get("/llms/{llm_id}", response_model=LLMModel)
async def api_get_llm(
    llm_id: int = Path(description="LLM ID"),
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get LLM configuration by ID."""
    try:
        llm_db = db_wrapper.get_llm_by_id(llm_id)
        if llm_db is None:
            raise HTTPException(status_code=404, detail="LLM not found")
        llm = LLMModel.model_validate(llm_db)
        llm.options = mask_api_key(llm.options)
        return llm
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/llms", response_model=list[LLMModel])
async def api_get_llms(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List registered LLMs. Non-admin users only see LLMs accessible via their teams."""
    all_llms = db_wrapper.get_llms()

    if not user.is_admin:
        # Get LLM names accessible via user's teams
        allowed_names = set()
        for team in user.teams:
            for llm in (team.llms if hasattr(team, 'llms') and team.llms else []):
                allowed_names.add(llm.name if hasattr(llm, 'name') else llm)
        all_llms = [llm for llm in all_llms if llm.name in allowed_names]

    llms: list[Optional[LLMModel]] = [
        LLMModel.model_validate(llm) for llm in all_llms
    ]
    for llm in llms:
        llm.options = mask_api_key(llm.options)
    return llms


@router.post("/llms", status_code=201)
async def api_create_llm(
    llmc: LLMModel,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Register a new LLM provider (admin only)."""
    try:
        if db_wrapper.get_llm_by_name(llmc.name):
            raise HTTPException(status_code=409, detail=f"LLM '{llmc.name}' already exists")
        llm_db: LLMDatabase = db_wrapper.create_llm(
            llmc.name,
            llmc.class_name,
            json.dumps(llmc.options),
            llmc.privacy,
            llmc.description,
            llmc.context_window,
            llmc.input_cost,
            llmc.output_cost,
        )
        llm = LLMModel.model_validate(llm_db)
        llm.options = mask_api_key(llm.options)
        return llm
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail="Failed to create LLM " + llmc.name)


@router.patch("/llms/{llm_id}")
async def api_edit_llm(
    request: Request,
    llm_id: int = Path(description="LLM ID"),
    llmUpdate: LLMUpdate = ...,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update LLM configuration (admin only)."""
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")
        if db_wrapper.update_llm(llm, llmUpdate):
            request.app.state.brain.load_llm(llm.name, db_wrapper)
            return {"llm": llm.name}
        else:
            raise HTTPException(status_code=404, detail="LLM not found")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/llms/{llm_id}")
async def api_delete_llm(
    llm_id: int = Path(description="LLM ID"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an LLM provider (admin only)."""
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")

        projects_using = db_wrapper.db.query(ProjectDatabase).filter(
            (ProjectDatabase.llm == llm.name) | (ProjectDatabase.guard == llm.name)
        ).all()
        if projects_using:
            names = [p.name for p in projects_using]
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete LLM '{llm.name}': used by projects: {', '.join(names)}"
            )

        db_wrapper.delete_llm(llm)
        return {"deleted": llm.name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
