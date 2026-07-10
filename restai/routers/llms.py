import json
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Path, Query, Request
import traceback
import logging
from restai import config
from restai.models.databasemodels import LLMDatabase
from restai.models.models import LLMModel, LLMUpdate, User
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username, get_current_username_admin

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()

def mask_api_key(options: Optional[dict]) -> Optional[dict]:
    """Mask every sensitive credential key (api_key/key/password/secret), not
    just api_key, before returning options in an API response."""
    if options is None:
        return options
    try:
        from restai.utils.crypto import LLM_SENSITIVE_KEYS
        for k in LLM_SENSITIVE_KEYS:
            if k in options:
                options[k] = "********"
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


@router.get("/llms/{llm_id}/usage")
async def api_llm_usage(
    llm_id: int = Path(description="LLM ID"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Projects that reference this LLM (main LLM or eval/rerank override) — so the
    UI can offer a replacement before deletion (admin only)."""
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")
        projects = db_wrapper.get_llm_usage(llm.name)
        return {"llm": llm.name, "count": len(projects), "projects": projects}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/llms/{llm_id}")
async def api_delete_llm(
    llm_id: int = Path(description="LLM ID"),
    reassign_to: Optional[str] = Query(
        default=None,
        description="Name of the LLM to move dependent projects to before deletion.",
    ),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an LLM provider (admin only). If projects still reference it, the
    caller must pass `reassign_to` naming a replacement LLM; every dependent
    project (main LLM + eval/rerank overrides) is repointed before deletion so no
    project is left with a dangling model reference."""
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_id(llm_id)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")

        usage = db_wrapper.get_llm_usage(llm.name)
        reassigned = 0
        if usage:
            if not reassign_to:
                names = [p["name"] for p in usage]
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot delete LLM '{llm.name}': used by {len(names)} project(s): {', '.join(names)}. Pass reassign_to to move them to another LLM.",
                )
            if reassign_to == llm.name:
                raise HTTPException(status_code=400, detail="Replacement LLM must differ from the one being deleted")
            if db_wrapper.get_llm_by_name(reassign_to) is None:
                raise HTTPException(status_code=400, detail=f"Replacement LLM '{reassign_to}' not found")
            reassigned = db_wrapper.reassign_llm(llm.name, reassign_to)

        db_wrapper.delete_llm(llm)
        return {"deleted": llm.name, "reassigned": reassigned, "reassigned_to": reassign_to if reassigned else None}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
