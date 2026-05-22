"""Speech-to-text registry CRUD endpoints."""
import json
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path

from restai import config
from restai.auth import get_current_username, get_current_username_admin
from restai.database import DBWrapper, get_db_wrapper
from restai.models.databasemodels import SpeechToTextDatabase
from restai.models.models import (
    SpeechToTextModel,
    SpeechToTextModelCreate,
    SpeechToTextModelUpdate,
    User,
)

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


_SENSITIVE_OPT_KEYS = {"api_key", "key", "password", "secret"}


def _mask_options(options: Optional[dict]) -> Optional[dict]:
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


@router.get("/speech_to_text", response_model=list[SpeechToTextModel])
async def list_speech_to_text(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List speech-to-text models, filtered by team access for non-admins."""
    rows = db_wrapper.get_speech_to_text()

    if not user.is_admin:
        allowed_names = set()
        for team in user.teams or []:
            for ag in (team.audio_generators or []):
                allowed_names.add(getattr(ag, "generator_name", ag))
        rows = [r for r in rows if r.name in allowed_names]

    out: list[SpeechToTextModel] = []
    for r in rows:
        m = SpeechToTextModel.model_validate(r)
        m.options = _mask_options(m.options)
        out.append(m)
    return out


@router.get("/speech_to_text/{model_id}", response_model=SpeechToTextModel)
async def get_speech_to_text(
    model_id: int = Path(description="Speech-to-text model ID"),
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    row = db_wrapper.get_speech_to_text_by_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Speech-to-text model not found")
    m = SpeechToTextModel.model_validate(row)
    m.options = _mask_options(m.options)
    return m


@router.post("/speech_to_text", status_code=201, response_model=SpeechToTextModel)
async def create_speech_to_text(
    body: SpeechToTextModelCreate,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Register a new STT model (admin only)."""
    if db_wrapper.get_speech_to_text_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"Speech-to-text model '{body.name}' already exists")
    if body.class_name == "local":
        raise HTTPException(
            status_code=400,
            detail="Local models are auto-discovered from restai/audio/workers/*; you can't create them manually.",
        )
    try:
        opts = body.options if isinstance(body.options, dict) else (json.loads(body.options) if body.options else {})
        row = db_wrapper.create_speech_to_text(
            name=body.name,
            class_name=body.class_name,
            options=opts,
            privacy=body.privacy,
            description=body.description,
            enabled=body.enabled,
        )
        m = SpeechToTextModel.model_validate(row)
        m.options = _mask_options(m.options)
        return m
    except HTTPException:
        raise
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=f"Failed to create speech-to-text model '{body.name}'")


@router.patch("/speech_to_text/{model_id}", response_model=SpeechToTextModel)
async def update_speech_to_text(
    model_id: int = Path(description="Speech-to-text model ID"),
    body: SpeechToTextModelUpdate = ...,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Update a speech-to-text model (admin only); local rows ignore provider/options changes."""
    row: Optional[SpeechToTextDatabase] = db_wrapper.get_speech_to_text_by_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Speech-to-text model not found")

    if row.class_name == "local":
        body.class_name = None
        body.options = None

    db_wrapper.edit_speech_to_text(row, body)
    m = SpeechToTextModel.model_validate(row)
    m.options = _mask_options(m.options)
    return m


@router.delete("/speech_to_text/{model_id}")
async def delete_speech_to_text(
    model_id: int = Path(description="Speech-to-text model ID"),
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a speech-to-text model (admin only); local models cannot be deleted."""
    row: Optional[SpeechToTextDatabase] = db_wrapper.get_speech_to_text_by_id(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Speech-to-text model not found")
    if row.class_name == "local":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete local model '{row.name}'. Set enabled=false instead.",
        )
    name = row.name
    db_wrapper.delete_speech_to_text(row)
    return {"deleted": name}
