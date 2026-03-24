import logging
import tempfile
import os
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Path, Request, UploadFile, Form

from restai import config
from restai.auth import get_current_username
from restai.database import get_db_wrapper, DBWrapper
from restai.direct_access import resolve_team_for_audio_generator, log_direct_usage
from restai.models.models import User

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/audio")
async def route_list_generators(
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List available audio transcription generators."""
    generators = request.app.state.brain.get_audio_generators()
    generators_names = [
        generator.__module__.split("restai.audio.workers.")[1]
        for generator in generators
    ]

    if not user.is_admin:
        teams = db_wrapper.get_teams_for_user(user.id)
        allowed = set()
        for team in teams:
            for ag in team.audio_generators:
                allowed.add(ag.generator_name)
        generators_names = [g for g in generators_names if g in allowed]

    return {"generators": generators_names}


@router.post("/audio/{generator}/transcript")
async def route_generate_transcript(
    request: Request,
    generator: str = Path(description="Audio transcription generator name"),
    file: UploadFile = ...,
    language: str = Form(..., description="Language code for transcription"),
    _: User = Depends(get_current_username)  # Require authentication
):
    """Transcribe an audio file using the specified generator."""
    # Read the uploaded file contents
    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)

    max_size_bytes = config.MAX_AUDIO_UPLOAD_SIZE * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size allowed is {config.MAX_AUDIO_UPLOAD_SIZE} MB.",
        )

    # Sanitize filename
    from restai.models.models import sanitize_filename
    file.filename = sanitize_filename(file.filename)

    # Save the uploaded file to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as temp_in:
        temp_in.write(contents)
        temp_in.flush()
        input_path = temp_in.name

    # Check if the file is already mp3
    file_ext = os.path.splitext(file.filename)[-1].lower()
    is_mp3 = file_ext == '.mp3'

    if is_mp3:
        # Use the uploaded file directly
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_mp3:
            temp_mp3.write(contents)
            temp_mp3.flush()
            mp3_path = temp_mp3.name
        try:
            with open(mp3_path, 'rb') as mp3_file:
                mp3_upload = UploadFile(filename=file.filename, file=mp3_file)
                generators = request.app.state.brain.get_audio_generators([generator])
                if len(generators) > 0:
                    opts = {}
                    if language:
                        opts["language"] = language
                    from restai.audio.runner import generate
                    transcript = generate(request.app.state.manager, generators[0], "", mp3_upload, opts)
                else:
                    raise HTTPException(status_code=400, detail="Invalid generator")
        finally:
            try:
                os.remove(mp3_path)
            except Exception:
                pass
    else:
        # Prepare a temporary output mp3 file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_out:
            output_path = temp_out.name

        # Convert the input file to mp3 using ffmpeg
        try:
            result = subprocess.run([
                'ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise HTTPException(status_code=400, detail=f"Failed to convert file to mp3: {result.stderr.decode()}")

            # Open the converted mp3 file as UploadFile for the runner
            with open(output_path, 'rb') as mp3_file:
                mp3_upload = UploadFile(filename='converted.mp3', file=mp3_file)
                generators = request.app.state.brain.get_audio_generators([generator])
                if len(generators) > 0:
                    from restai.audio.runner import generate
                    transcript = generate(request.app.state.manager, generators[0], "", mp3_upload)
                else:
                    raise HTTPException(status_code=400, detail="Invalid generator")
        finally:
            # Clean up temporary files
            try:
                os.remove(input_path)
            except Exception:
                pass
            try:
                os.remove(output_path)
            except Exception:
                pass

    return {"answer": transcript}


@router.post("/v1/audio/transcriptions")
async def openai_compatible_transcription(
    request: Request,
    model: str = Form(..., description="Audio transcription model name"),
    file: UploadFile = ...,
    language: str = Form(default="en", description="Language code for transcription"),
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible audio transcription endpoint."""
    team_id = resolve_team_for_audio_generator(user, model, db_wrapper)

    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)

    max_size_bytes = config.MAX_AUDIO_UPLOAD_SIZE * 1024 * 1024
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size allowed is {config.MAX_AUDIO_UPLOAD_SIZE} MB.",
        )

    file.filename = sanitize_filename(file.filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[-1]) as temp_in:
        temp_in.write(contents)
        temp_in.flush()
        input_path = temp_in.name

    file_ext = os.path.splitext(file.filename)[-1].lower()
    is_mp3 = file_ext == '.mp3'

    try:
        if is_mp3:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_mp3:
                temp_mp3.write(contents)
                temp_mp3.flush()
                mp3_path = temp_mp3.name
            try:
                with open(mp3_path, 'rb') as mp3_file:
                    mp3_upload = UploadFile(filename=file.filename, file=mp3_file)
                    generators = request.app.state.brain.get_audio_generators([model])
                    if len(generators) > 0:
                        opts = {"language": language} if language else {}
                        from restai.audio.runner import generate
                        transcript = generate(request.app.state.manager, generators[0], "", mp3_upload, opts)
                    else:
                        raise HTTPException(status_code=400, detail=f"Invalid model: {model}")
            finally:
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_out:
                output_path = temp_out.name
            try:
                result = subprocess.run([
                    'ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_path
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    raise HTTPException(status_code=400, detail=f"Failed to convert file to mp3: {result.stderr.decode()}")

                with open(output_path, 'rb') as mp3_file:
                    mp3_upload = UploadFile(filename='converted.mp3', file=mp3_file)
                    generators = request.app.state.brain.get_audio_generators([model])
                    if len(generators) > 0:
                        opts = {"language": language} if language else {}
                        from restai.audio.runner import generate
                        transcript = generate(request.app.state.manager, generators[0], "", mp3_upload, opts)
                    else:
                        raise HTTPException(status_code=400, detail=f"Invalid model: {model}")
            finally:
                try:
                    os.remove(output_path)
                except Exception:
                    pass
    finally:
        try:
            os.remove(input_path)
        except Exception:
            pass

    log_direct_usage(
        db_wrapper, user.id, team_id, model,
        "(audio file)", transcript,
        0, 0, 0.0, 0.0,
    )

    return {"text": transcript}
