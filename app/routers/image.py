import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app import config
from app.auth import get_current_username
from app.models.models import ImageModel, User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/image")
async def route_list_generators(request: Request,
                                user: User = Depends(get_current_username)):
    generators = request.app.state.brain.get_generators()
    generators_names = [generator.__module__.split("app.image.workers.")[1] for generator in generators]

    if not user.is_private:
        generators_names.append("dalle")
        generators_names.append("imagen")

    return {"generators": generators_names}


@router.post("/image/{generator}/generate")
async def route_generate_image(request: Request,
                               generator: str,
                               imageModel: ImageModel,
                               user: User = Depends(get_current_username)):
    match generator:
        case "dalle" | "dalle3":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from app.image.external.dalle3 import generate
            image = generate(imageModel)
        case "imagen" | "imagen3":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from app.image.external.imagen3 import generate
            image = generate(imageModel)
        case _:
            generators = request.app.state.brain.get_generators([generator])
            if len(generators) > 0:
                from app.image.runner import generate
                image = generate(request.app.state.manager, generators[0], imageModel)
            else:
                raise HTTPException(status_code=400, detail="Invalid generator")

    return {"image": image}
