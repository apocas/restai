from fastapi import APIRouter
from sqlalchemy.orm import Session
from fastapi import Depends
from fastapi import HTTPException, Request
import traceback
import logging
from app import config

from app.models.models import LLMModel, LLMUpdate, User
from app.database import get_db, get_llm_by_name, update_llm, delete_llm, create_llm, get_llms
from app.auth import get_current_username, get_current_username_admin

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/llms/{llm_name}", response_model=LLMModel)
async def api_get_llm(llm_name: str, _: User = Depends(get_current_username), db: Session = Depends(get_db)):
    try:
        return LLMModel.model_validate(get_llm_by_name(db, llm_name))
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/llms", response_model=list[LLMModel])
async def api_get_llms(
        _: User = Depends(get_current_username),
        db: Session = Depends(get_db)):
    users = get_llms(db)
    return users


@router.post("/llms")
async def api_create_llm(llmc: LLMModel,
                     _: User = Depends(get_current_username_admin),
                     db: Session = Depends(get_db)):
    try:
        llm = create_llm(db, llmc.name, llmc.class_name, llmc.options, llmc.privacy, llmc.description, llmc.type)
        return llm
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create LLM ' + llmc.name)


@router.patch("/llms/{llm_name}")
async def api_edit_project(request: Request, llm_name: str, llmUpdate: LLMUpdate,
                       _: User = Depends(get_current_username_admin), db: Session = Depends(get_db)):
    try:
        llm = get_llm_by_name(db, llm_name)
        if llm is None:
            raise Exception("LLM not found")
        if update_llm(db, llm, llmUpdate):
            request.app.state.brain.load_llm(llm_name, db)
            return {"project": llm_name}
        else:
            raise HTTPException(
                status_code=404, detail='LLM not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.delete("/llms/{llm_name}")
async def api_delete_llm(llm_name: str,
                     _: User = Depends(get_current_username_admin),
                     db: Session = Depends(get_db)):
    try:
        llm = get_llm_by_name(db, llm_name)
        if llm is None:
            raise Exception("LLM not found")
        delete_llm(db, llm)
        return {"deleted": llm_name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
