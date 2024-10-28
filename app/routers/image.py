import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from app import config
from app.auth import get_current_username
from app.database import get_db_wrapper, DBWrapper
from app.models.models import ImageModel, User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()

@router.get("/image")
async def route_list_generators(request: Request,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):
    return {"generators": ["stablediffusion1", "stablediffusion3", "stablediffusion35", "flux1", "dalle3"]}

@router.post("/image/{generator}/generate")
async def route_generate_image(request: Request,
                             generator: str,
                             imageModel: ImageModel,
                             user: User = Depends(get_current_username),
                             db_wrapper: DBWrapper = Depends(get_db_wrapper)):

    match generator:
        case "stablediffusion1":
            from app.image.workers.stablediffusion import worker
            from app.image.runner import generate
        case "stablediffusion3":
            from app.image.workers.stablediffusion3 import worker
            from app.image.runner import generate
            image = generate(worker, imageModel)
        case "stablediffusion" | "stablediffusion35":
            from app.image.workers.stablediffusion35 import worker
            from app.image.runner import generate
            image = generate(worker, imageModel)
        case "flux" | "flux1":
            from app.image.workers.flux1 import worker
            from app.image.runner import generate
            image = generate(worker, imageModel)
        case "dalle" | "dalle3":
            from app.image.external.dalle3 import generate
            image = generate(imageModel)
        case _:
            raise HTTPException(status_code=400, detail="Invalid generator")
    
    return {"image": image}