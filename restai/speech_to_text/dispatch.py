"""Speech-to-text dispatch — look up a model by name in the registry and
route to its provider.

Callers:
- `restai/routers/audio.py` — `POST /audio/{generator}/transcript`.

The dispatch takes a path to an audio file on disk (the router writes the
upload to a tempfile, ffmpeg-converts to mp3 if needed, and hands us the
final path). External providers (OpenAI, Google, Deepgram, AssemblyAI)
read the bytes; the local branch hands the path to the existing
`restai.audio.runner.generate` which spawns a worker subprocess.
"""
from __future__ import annotations

import json
import logging
import os

from restai.models.databasemodels import SpeechToTextDatabase

logger = logging.getLogger(__name__)


class UnknownModelError(Exception):
    """Raised when no enabled STT model matches the requested name."""


class ModelDisabledError(Exception):
    """Raised when a matching model exists but `enabled=False`."""


def _load_options(row: SpeechToTextDatabase) -> dict:
    from restai.utils.crypto import decrypt_sensitive_options, LLM_SENSITIVE_KEYS

    try:
        raw = json.loads(row.options) if row.options else {}
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        try:
            raw = decrypt_sensitive_options(raw, LLM_SENSITIVE_KEYS)
        except Exception:
            pass
    return raw if isinstance(raw, dict) else {}


def list_available_stt_models(db_wrapper) -> list[str]:
    rows = db_wrapper.get_speech_to_text()
    return [r.name for r in rows if r.enabled]


def transcribe_audio(
    name: str,
    audio_path: str,
    filename: str,
    language: str | None,
    brain,
    db_wrapper,
) -> str:
    """Resolve `name` to a model row and run transcription on the file at
    `audio_path`. Returns the transcript string."""
    row = db_wrapper.get_speech_to_text_by_name(name)
    if row is None:
        raise UnknownModelError(name)
    if not row.enabled:
        raise ModelDisabledError(name)

    options = _load_options(row)

    # External providers operate on raw bytes — slurp the file once.
    if row.class_name in ("openai", "google", "deepgram", "assemblyai"):
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        if row.class_name == "openai":
            from restai.speech_to_text.providers.openai import transcribe as _t
        elif row.class_name == "google":
            from restai.speech_to_text.providers.google import transcribe as _t
        elif row.class_name == "deepgram":
            from restai.speech_to_text.providers.deepgram import transcribe as _t
        else:
            from restai.speech_to_text.providers.assemblyai import transcribe as _t
        return _t(options, audio_bytes, filename, language)

    if row.class_name == "local":
        manager = getattr(brain, "audio_manager", None) or getattr(brain, "image_manager", None)
        generators = brain.get_audio_generators([name]) if hasattr(brain, "get_audio_generators") else []
        if not generators:
            raise UnknownModelError(name)
        if manager is None:
            raise RuntimeError(
                f"Local STT model '{name}' needs the torch multiprocessing manager "
                "(GPU mode). Start the API with RESTAI_GPU=true."
            )
        # The legacy runner expects a FastAPI UploadFile. Wrap the file
        # path in a minimal stand-in so we don't have to rewrite it.
        from restai.audio.runner import generate as _runner

        class _DiskUpload:
            def __init__(self, path: str, name: str):
                self.filename = name
                self.file = open(path, "rb")

            def __del__(self):
                try:
                    self.file.close()
                except Exception:
                    pass

        upload = _DiskUpload(audio_path, filename or os.path.basename(audio_path))
        try:
            return _runner(manager, generators[0], language or "", upload)
        finally:
            try:
                upload.file.close()
            except Exception:
                pass

    raise UnknownModelError(name)
