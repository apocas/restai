import json
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Request
import traceback
import logging
from restai import config
from restai.models.databasemodels import LLMDatabase
from restai.models.models import LLMModel, LLMUpdate, User
from restai.database import get_db_wrapper, DBWrapper
from restai.auth import get_current_username, get_current_username_admin

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()

def mask_api_key(options: Optional[str]) -> Optional[str]:
    if options is None:
        return options
    try:
        if "api_key" in options:
            options["api_key"] = "********"
        return options
    except Exception as e:
        logging.exception(e)
        return options

@router.get("/llms/{llm_name}", response_model=LLMModel)
async def api_get_llm(
    llm_name: str,
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        llm = LLMModel.model_validate(db_wrapper.get_llm_by_name(llm_name))
        llm.options = mask_api_key(llm.options)
        return llm
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/llms", response_model=list[LLMModel])
async def api_get_llms(
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    llms: list[Optional[LLMModel]] = [
        LLMModel.model_validate(llm) for llm in db_wrapper.get_llms()
    ]
    for llm in llms:
        llm.options = mask_api_key(llm.options)
    return llms


@router.post("/llms")
async def api_create_llm(
    llmc: LLMModel,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        llm: LLMDatabase = db_wrapper.create_llm(
            llmc.name,
            llmc.class_name,
            json.dumps(llmc.options),
            llmc.privacy,
            llmc.description,
            llmc.type,
        )
        return llm
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail="Failed to create LLM " + llmc.name)


@router.patch("/llms/{llm_name}")
async def api_edit_llm(
    request: Request,
    llm_name: str,
    llmUpdate: LLMUpdate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_name(llm_name)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")
        if db_wrapper.update_llm(llm, llmUpdate):
            request.app.state.brain.load_llm(llm_name, db_wrapper)
            return {"llm": llm_name}
        else:
            raise HTTPException(status_code=404, detail="LLM not found")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/llms/{llm_name}")
async def api_delete_llm(
    llm_name: str,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    try:
        llm: Optional[LLMDatabase] = db_wrapper.get_llm_by_name(llm_name)
        if llm is None:
            raise HTTPException(status_code=404, detail="LLM not found")
        db_wrapper.delete_llm(llm)
        return {"deleted": llm_name}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")
