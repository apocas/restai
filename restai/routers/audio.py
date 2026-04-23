"""Audio transcription endpoints — `/audio/{generator}/transcript` and the
OpenAI-compatible `/v1/audio/transcriptions`. Both go through the
registry-backed dispatch (`restai/speech_to_text/dispatch.py`).
"""
import logging
import os
import shutil
import subprocess
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Path, Request, UploadFile, Form

from restai import config
from restai.auth import get_current_username, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.direct_access import resolve_team_for_audio_generator, log_direct_usage
from restai.models.models import User, sanitize_filename
from restai.speech_to_text.dispatch import (
    ModelDisabledError,
    UnknownModelError,
    list_available_stt_models,
    transcribe_audio,
)

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/audio")
async def route_list_generators(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List speech-to-text models available to the caller (legacy path —
    the new admin page uses /speech_to_text)."""
    names = list_available_stt_models(db_wrapper)
    if not user.is_admin:
        teams = db_wrapper.get_teams_for_user(user.id)
        allowed = set()
        for team in teams:
            for ag in team.audio_generators:
                allowed.add(ag.generator_name)
        names = [g for g in names if g in allowed]
    return {"generators": names}


def _normalize_to_mp3(input_path: str, original_filename: str) -> tuple[str, str, bool]:
    """Return ``(mp3_path, mp3_filename, owns_temp)``. Re-encodes via ffmpeg
    when the input isn't already mp3. `owns_temp` is True when the caller
    must delete `mp3_path` after use."""
    file_ext = os.path.splitext(original_filename or "")[-1].lower()
    if file_ext == ".mp3":
        return input_path, original_filename, False

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_out:
        output_path = temp_out.name
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", output_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        try:
            os.remove(output_path)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"Failed to convert file to mp3: {result.stderr.decode()}")
    return output_path, "converted.mp3", True


def _do_transcribe(
    request: Request,
    db_wrapper: DBWrapper,
    generator: str,
    file: UploadFile,
    contents: bytes,
    language: str | None,
) -> str:
    """Common path: validate size, write upload to a tempfile, normalize to
    mp3, hand to the registry dispatch, return the transcript."""
    max_audio_mb = int(db_wrapper.get_setting_value("max_audio_upload_size", "10"))
    max_size_bytes = max_audio_mb * 1024 * 1024
    if len(contents) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size allowed is {max_audio_mb} MB.",
        )

    safe_name = sanitize_filename(file.filename or "audio")
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(safe_name)[-1] or ".bin") as temp_in:
        temp_in.write(contents)
        temp_in.flush()
        input_path = temp_in.name

    mp3_path, mp3_name, owns_mp3 = (None, None, False)
    try:
        mp3_path, mp3_name, owns_mp3 = _normalize_to_mp3(input_path, safe_name)
        try:
            return transcribe_audio(
                generator,
                mp3_path,
                mp3_name,
                language,
                request.app.state.brain,
                db_wrapper,
            )
        except UnknownModelError:
            raise HTTPException(status_code=400, detail=f"Unknown speech-to-text model '{generator}'")
        except ModelDisabledError:
            raise HTTPException(status_code=403, detail=f"Speech-to-text model '{generator}' is disabled")
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in (input_path, mp3_path if owns_mp3 else None):
            if not p:
                continue
            try:
                os.remove(p)
            except Exception:
                pass


@router.post("/audio/{generator}/transcript")
async def route_generate_transcript(
    request: Request,
    generator: str = Path(description="Speech-to-text model name"),
    file: UploadFile = ...,
    language: str = Form(..., description="Language code for transcription"),
    _: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Transcribe an audio file using the specified STT model."""
    contents = await file.read()
    transcript = _do_transcribe(request, db_wrapper, generator, file, contents, language)
    return {"answer": transcript}


@router.post("/v1/audio/transcriptions")
async def openai_compatible_transcription(
    request: Request,
    model: str = Form(..., description="Speech-to-text model name"),
    file: UploadFile = ...,
    language: str = Form(default="en", description="Language code for transcription"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible audio transcription endpoint."""
    check_not_restricted(user)
    team_id = resolve_team_for_audio_generator(user, model, db_wrapper)

    contents = await file.read()
    transcript = _do_transcribe(request, db_wrapper, model, file, contents, language)

    log_direct_usage(
        db_wrapper, user.id, team_id, model,
        "(audio file)", transcript,
        0, 0, 0.0, 0.0,
    )
    return {"text": transcript}
