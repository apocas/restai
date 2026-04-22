"""Image generation REST endpoints.

Both the public `POST /image/{generator}/generate` and the
OpenAI-compatible `POST /v1/images/generations` route through the
registry-backed dispatch (`restai/image/dispatch.py`). No more hardcoded
provider switches — adding a new external provider means dropping a
module under `restai/image/providers/` and wiring it in `dispatch.py`.
"""
import base64 as _base64
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request
from typing import Literal, Optional
from pydantic import BaseModel

from restai import config
from restai.auth import get_current_username, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.direct_access import resolve_team_for_image_generator, log_direct_usage
from restai.image.dispatch import (
    GeneratorDisabledError,
    UnknownGeneratorError,
    generate_image,
    list_available_generators,
)
from restai.models.models import ImageModel, User

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/image")
async def route_list_generators(
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List image generators available to the caller."""
    names = list_available_generators(db_wrapper)

    if not user.is_admin:
        teams = db_wrapper.get_teams_for_user(user.id)
        allowed = set()
        for team in teams:
            for ig in team.image_generators:
                allowed.add(ig.generator_name)
        names = [g for g in names if g in allowed]

    return {"generators": names}


def _generate(generator: str, image_model: ImageModel, brain, db_wrapper) -> bytes:
    """Resolve + run a generator, surfacing dispatch errors as HTTPExceptions."""
    try:
        data, _mime = generate_image(generator, image_model, brain, db_wrapper)
        return data
    except UnknownGeneratorError:
        raise HTTPException(status_code=400, detail=f"Unknown image generator '{generator}'")
    except GeneratorDisabledError:
        raise HTTPException(status_code=403, detail=f"Image generator '{generator}' is disabled")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image/{generator}/generate")
async def route_generate_image(
    request: Request,
    generator: str = Path(description="Image generator name"),
    imageModel: ImageModel = ...,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Generate an image using the specified generator."""
    if user.is_private:
        # Local generators are still fine for private users; only block
        # external providers (which would leak the prompt to a third party).
        row = db_wrapper.get_image_generator_by_name(generator)
        if row is None or row.class_name != "local":
            raise HTTPException(status_code=403, detail="User is private")

    image_bytes = _generate(generator, imageModel, request.app.state.brain, db_wrapper)
    return {"image": _base64.b64encode(image_bytes).decode("utf-8")}


class OpenAIImageGenerateRequest(BaseModel):
    model: str
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
    """OpenAI-compatible image generation endpoint. The `model` field is
    matched against the registry by name (no normalization — the admin
    decides what name a generator is exposed under)."""
    check_not_restricted(user)

    if user.is_private:
        row = db_wrapper.get_image_generator_by_name(body.model)
        if row is None or row.class_name != "local":
            raise HTTPException(status_code=403, detail="User is private")

    team_id = resolve_team_for_image_generator(user, body.model, db_wrapper)
    imageModel = ImageModel(prompt=body.prompt)

    image_bytes = _generate(body.model, imageModel, request.app.state.brain, db_wrapper)
    image_b64 = _base64.b64encode(image_bytes).decode("utf-8")

    background_tasks.add_task(
        log_direct_usage,
        db_wrapper,
        user.id,
        team_id,
        body.model,
        body.prompt,
        "(image generated)",
        0, 0, 0.0, 0.0,
    )

    output = {
        "created": int(time.time()),
        "data": [{
            "revised_prompt": body.prompt,
            "model": body.model,
        }]
    }

    if body.response_format == "url":
        output["data"][0]["url"] = f"data:image/png;base64,{image_b64}"
    elif body.response_format == "b64_json":
        output["data"][0]["b64_json"] = image_b64

    return output
