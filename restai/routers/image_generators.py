"""Image-generator registry CRUD endpoints.

Mirrors `restai/routers/llms.py` so the admin UX (list / create / edit /
delete + team grants) carries over without surprises. The registry holds
both:

- **Local** workers (auto-seeded on startup from `restai/image/workers/*`).
  Always selectable; admin can flip `enabled` and rename for display, but
  cannot delete (re-seeded next boot).
- **External** providers — `openai` (incl. OpenAI-spec compatibles via
  `options.base_url`) and `google` (Imagen / Nano Banana). Created freely
  by the admin with per-row encrypted credentials.

API key fields in `options` are masked as `"********"` on read; the PATCH
handler preserves the existing value when it sees that sentinel back.
"""
import json
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from restai import config
from restai.auth import get_current_username, get_current_username_admin
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import ImageGeneratorDatabase
from restai.models.models import (
    ImageGeneratorModel,
    ImageGeneratorModelCreate,
    ImageGeneratorModelUpdate,
    User,
)

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


_SENSITIVE_OPT_KEYS = {"api_key", "key", "password", "secret"}


def _mask_options(options: Optional[dict]) -> Optional[dict]:
    """Replace sensitive fields with the `"********"` sentinel before
    serializing to the client. Same set the encrypt helpers use."""
    if not options:
        return options
    try:
        masked = dict(options)
        for k in _SENSITIVE_OPT_KEYS:
            if k in masked and masked[k]:
                masked[k] = "********"
        return masked
    except Exception:
        return options


@router.get("/image_generators", response_model=list[ImageGeneratorModel])
async def list_image_generators(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List image generators. Non-admins see only those granted to a team
    they're a member of (matches the LLM listing pattern)."""
    rows = db_wrapper.get_image_generators()

    if not user.is_admin:
        allowed_names = set()
        for team in user.teams or []:
            for ig in (team.image_generators or []):
                allowed_names.add(getattr(ig, "generator_name", ig))
        rows = [r for r in rows if r.name in allowed_names]

    out: list[ImageGeneratorModel] = []
    for r in rows:
        m = ImageGeneratorModel.model_validate(r)
        m.options = _mask_options(m.options)
        out.append(m)
    return out


@router.get("/image_generators/{generator_id}", response_model=ImageGeneratorModel)
async def get_image_generator(
    generator_id: int = Path(description="Image generator ID"),
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    row = db_wrapper.get_image_generator_by_id(generator_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image generator not found")
    m = ImageGeneratorModel.model_validate(row)
    m.options = _mask_options(m.options)
    return m


@router.post("/image_generators", status_code=201, response_model=ImageGeneratorModel)
async def create_image_generator(
    body: ImageGeneratorModelCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Register a new image generator (admin only)."""
    if db_wrapper.get_image_generator_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"Image generator '{body.name}' already exists")
    if body.class_name == "local":
        # Local generators are auto-seeded; admin shouldn't create them
        # by hand (the name has to match a real worker module).
        raise HTTPException(
            status_code=400,
            detail="Local generators are auto-discovered from restai/image/workers/*; you can't create them manually.",
        )
    try:
        opts = body.options if isinstance(body.options, dict) else (json.loads(body.options) if body.options else {})
        row = db_wrapper.create_image_generator(
            name=body.name,
            class_name=body.class_name,
            options=opts,
            privacy=body.privacy,
            description=body.description,
            enabled=body.enabled,
        )
        m = ImageGeneratorModel.model_validate(row)
        m.options = _mask_options(m.options)
        return m
    except HTTPException:
        raise
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=f"Failed to create image generator '{body.name}'")


@router.patch("/image_generators/{generator_id}", response_model=ImageGeneratorModel)
async def update_image_generator(
    request: Request,
    generator_id: int = Path(description="Image generator ID"),
    body: ImageGeneratorModelUpdate = ...,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update an image generator (admin only). For local generators the
    `enabled`/`description`/`privacy` fields are accepted; `class_name` and
    `options` changes are ignored — those come from the worker module."""
    row: Optional[ImageGeneratorDatabase] = db_wrapper.get_image_generator_by_id(generator_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image generator not found")

    if row.class_name == "local":
        # Strip class_name + options changes for local rows so an admin
        # can't accidentally point a local row at an external provider.
        body.class_name = None
        body.options = None

    db_wrapper.edit_image_generator(row, body)
    m = ImageGeneratorModel.model_validate(row)
    m.options = _mask_options(m.options)
    return m


@router.delete("/image_generators/{generator_id}")
async def delete_image_generator(
    generator_id: int = Path(description="Image generator ID"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an image generator (admin only). Local generators cannot be
    deleted — they would just be re-seeded on the next boot. Disable them
    via `enabled=false` instead."""
    row: Optional[ImageGeneratorDatabase] = db_wrapper.get_image_generator_by_id(generator_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image generator not found")
    if row.class_name == "local":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete local generator '{row.name}'. Set enabled=false instead.",
        )
    name = row.name
    db_wrapper.delete_image_generator(row)
    return {"deleted": name}
