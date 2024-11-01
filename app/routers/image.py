import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app import config
from app.auth import get_current_username
from app.database import get_db_wrapper, DBWrapper
from app.models.models import ImageModel, User
from app.tools import load_generators

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()

@router.get("/image")
async def route_list_generators(request: Request,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
    generators = request.app.state.brain.get_generators()
  
    return {"generators": [generator.__module__.split("app.image.workers.")[1] for generator in generators]}

@router.post("/image/{generator}/generate")
async def route_generate_image(request: Request,
                             generator: str,
                             imageModel: ImageModel,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
  
  
    match generator:
        case "dalle" | "dalle3":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from app.image.external.dalle3 import generate
            image = generate(imageModel)
        case _:
            generators = request.app.state.brain.get_generators([generator])
            if len(generators) > 0:
                from app.image.runner import generate
                image = generate(generators[0], imageModel)
            else:
              raise HTTPException(status_code=400, detail="Invalid generator")
    
    return {"image": image}