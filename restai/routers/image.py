import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Literal, Optional
from pydantic import BaseModel

from restai import config
from restai.auth import get_current_username
from restai.models.models import ImageModel, User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

router = APIRouter()


@router.get("/image")
async def route_list_generators(request: Request,
                                user: User = Depends(get_current_username)):
    generators = request.app.state.brain.get_generators()
    generators_names = [generator.__module__.split("restai.image.workers.")[1] for generator in generators]

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
            from restai.image.external.dalle3 import generate
            image = generate(imageModel)
        case "imagen" | "imagen3":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.imagen3 import generate
            image = generate(imageModel)
        case _:
            generators = request.app.state.brain.get_generators([generator])
            if len(generators) > 0:
                from restai.image.runner import generate
                image = generate(request.app.state.manager, generators[0], imageModel)
            else:
                raise HTTPException(status_code=400, detail="Invalid generator")

    return {"image": image}


class OpenAIImageGenerateRequest(BaseModel):
    model: Optional[str] = "dall-e-3"
    prompt: str
    n: Optional[int] = 1
    quality: Optional[Literal["standard", "hd"]] = "standard"
    response_format: Optional[Literal["url", "b64_json"]] = "b64_json"
    size: Optional[Literal["512x512", "1024x1024", "1024x1792", "1792x1024"]] = "1024x1024"
    style: Optional[Literal["natural", "vivid"]] = "vivid"
    user: Optional[str] = None


class OpenAIImageResponse(BaseModel):
    created: int
    data: list[dict]


@router.post("/v1/images/generations")
async def openai_compatible_generate(
    request: Request,
    body: OpenAIImageGenerateRequest,
    user: User = Depends(get_current_username)
):
    """OpenAI-compatible image generation endpoint"""
    import time

    # Convert OpenAI request to our internal format
    imageModel = ImageModel(prompt=body.prompt)

    # Map model parameter to generator
    generator = body.model.lower().replace("-", "")
    
    # Use the existing generator selection logic
    match generator:
        case "dalle3" | "dalle":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.dalle3 import generate
            image = generate(imageModel)
        case "imagen3" | "imagen":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.imagen3 import generate
            image = generate(imageModel)
        case _:
            generators = request.app.state.brain.get_generators([generator])
            if len(generators) > 0:
                from restai.image.runner import generate
                image = generate(request.app.state.manager, generators[0], imageModel)
            else:
                raise HTTPException(status_code=400, detail=f"Invalid model: {body.model}")

    output = {
        "created": int(time.time()),
        "data": [{
            "revised_prompt": body.prompt,
            "model": body.model
        }]
    }
    
    if body.response_format == "url":
      output["data"][0]["url"] = f"data:image/jpeg;base64,{image}"
    elif body.response_format == "b64_json":
      output["data"][0]["b64_json"] = image
    
    return output
