import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from restai import config
from restai.auth import get_current_username
from restai.models.models import User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/audio")
async def route_list_generators(request: Request,
                                _: User = Depends(get_current_username)):
    generators = request.app.state.brain.get_audio_generators()
    generators_names = [generator.__module__.split("restai.audio.workers.")[1] for generator in generators]

    return {"generators": generators_names}


@router.post("/audio/{generator}/transcript")
async def route_generate_transcript(request: Request,
                                    generator: str,
                                    file: UploadFile):
    generators = request.app.state.brain.get_audio_generators([generator])
    if len(generators) > 0:
        from restai.audio.runner import generate
        transcript = generate(request.app.state.manager, generators[0], "", file)
    else:
        raise HTTPException(status_code=400, detail="Invalid generator")

    return {"answer": transcript}
