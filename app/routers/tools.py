import logging
import traceback

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Request

from app import config
from app.auth import get_current_username
from app.models.models import ClassifierModel, ClassifierResponse, Tool, User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()


@router.post("/tools/classifier", response_model=ClassifierResponse)
async def classifier(
    request: Request,
    input_model: ClassifierModel,
    _: User = Depends(get_current_username),
):
    try:
        return request.app.state.brain.classify(input_model)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/agent", response_model=list[Tool])
async def get_tools(request: Request, _: User = Depends(get_current_username)):

    _tools = []

    for tool in request.app.state.brain.get_tools():
        _tools.append(
            Tool(name=tool.metadata.name, description=tool.metadata.description)
        )

    return _tools
