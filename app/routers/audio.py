import logging
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, Form
from app import config
from app.auth import get_current_username
from app.database import get_db_wrapper, DBWrapper
from app.models.models import ImageModel, User
from app.tools import load_generators

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/audio")
async def route_list_generators(request: Request,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    generators = request.app.state.brain.get_audio_generators()
    generators_names = [generator.__module__.split("app.audio.workers.")[1] for generator in generators]
  
    return {"generators": generators_names}

@router.post("/audio/{generator}/transcript")
async def route_generate_transcript(request: Request,
                             generator: str,
                             file: UploadFile,
                             prompt: str = Form("sentence"),
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    generators = request.app.state.brain.get_audio_generators([generator])
    if len(generators) > 0:
        from app.audio.runner import generate
        transcript = generate(request.app.state.manager, generators[0], "", file)
    else:
      raise HTTPException(status_code=400, detail="Invalid generator")
  
    return {"answer": transcript}