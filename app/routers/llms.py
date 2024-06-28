from fastapi import APIRouter
from starlette.requests import Request
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from fastapi import HTTPException, Request
import traceback
import logging
from app import config

from app.models.models import LLMModel, LLMUpdate, User
from app.database import dbc, get_db
from app.auth import get_current_username, get_current_username_admin


logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/llms/{llmname}", response_model=LLMModel)
async def get_llm(llmname: str, user: User = Depends(get_current_username), db: Session = Depends(get_db)):
    try:
        return LLMModel.model_validate(dbc.get_llm_by_name(db, llmname))
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@router.get("/llms", response_model=list[LLMModel])
async def get_llms(
        user: User = Depends(get_current_username),
        db: Session = Depends(get_db)):
    users = dbc.get_llms(db)
    return users


@router.post("/llms")
async def create_llm(llmc: LLMModel,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        llm = dbc.create_llm(db, llmc.name, llmc.class_name, llmc.options, llmc.privacy, llmc.description, llmc.type)
        return llm
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create LLM ' + llmc.name)


@router.patch("/llms/{llmname}")
async def edit_project(request: Request, llmname: str, llmUpdate: LLMUpdate, user: User = Depends(get_current_username_admin), db: Session = Depends(get_db)):
    try:
        llm = dbc.get_llm_by_name(db, llmname)
        if llm is None:
            raise Exception("LLM not found")
        if dbc.update_llm(db, llm, llmUpdate):
            request.app.state.brain.loadLLM(llmname, db)
            return {"project": llmname}
        else:
            raise HTTPException(
                status_code=404, detail='LLM not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@router.delete("/llms/{llmname}")
async def delete_llm(llmname: str,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        llm = dbc.get_llm_by_name(db, llmname)
        if llm is None:
            raise Exception("LLM not found")
        dbc.delete_llm(db, llm)
        return {"deleted": llmname}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))