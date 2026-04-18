import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request
from typing import Literal, Optional
from pydantic import BaseModel

from restai import config
from restai.auth import get_current_username, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.direct_access import resolve_team_for_image_generator, log_direct_usage
from restai.models.models import ImageModel, User

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/image")
async def route_list_generators(
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List available image generators."""
    generators = request.app.state.brain.get_generators()
    generators_names = [generator.__module__.split("restai.image.workers.")[1] for generator in generators]

    if not user.is_private:
        from restai.image.external._openai import has_openai_api_key
        if has_openai_api_key(db_wrapper):
            generators_names.append("dalle")
            generators_names.append("gpt-image-1.5")
        if os.environ.get("GOOGLE_API_KEY"):
            generators_names.append("imagen")

    if not user.is_admin:
        teams = db_wrapper.get_teams_for_user(user.id)
        allowed = set()
        for team in teams:
            for ig in team.image_generators:
                allowed.add(ig.generator_name)
        generators_names = [g for g in generators_names if g in allowed]

    return {"generators": generators_names}


@router.post("/image/{generator}/generate")
async def route_generate_image(request: Request,
                               generator: str = Path(description="Image generator name"),
                               imageModel: ImageModel = ...,
                               user: User = Depends(get_current_username)):
    """Generate an image using the specified generator."""
    match generator:
        case "dalle" | "dalle3":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.dalle3 import generate
            image = generate(imageModel)
        case "gpt-image-1.5" | "gpt_image_15" | "gptimage15":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.gpt_image_15 import generate
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
    model: Optional[str] = "dalle3"
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
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible image generation endpoint."""
    check_not_restricted(user)
    import time

    generator = body.model.lower().replace("-", "")
    team_id = resolve_team_for_image_generator(user, generator, db_wrapper)

    imageModel = ImageModel(prompt=body.prompt)
    
    match generator:
        case "dalle3" | "dalle":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.dalle3 import generate
            image = generate(imageModel)
        case "gptimage15" | "gpt_image_15":
            if user.is_private:
                raise HTTPException(status_code=403, detail="User is private")
            from restai.image.external.gpt_image_15 import generate
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

    background_tasks.add_task(
        log_direct_usage,
        db_wrapper,
        user.id,
        team_id,
        generator,
        body.prompt,
        "(image generated)",
        0, 0, 0.0, 0.0,
    )

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
