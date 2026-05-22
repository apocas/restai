"""OpenAI Whisper API + OpenAI-compat transcription."""
from __future__ import annotations

import io
import os

from openai import OpenAI


def transcribe(options: dict, audio_bytes: bytes, filename: str, language: str | None) -> str:
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OpenAI STT: `api_key` is required in options.")

    model = (options.get("model") or "").strip()
    if not model:
        raise RuntimeError("OpenAI STT: `model` is required in options.")

    client_kwargs = {"api_key": api_key}
    base_url = (options.get("base_url") or "").strip()
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    # SDK needs a file-like with a `name` so the server picks MIME by extension.
    buf = io.BytesIO(audio_bytes)
    buf.name = filename or "audio.mp3"

    call_kwargs = {"file": buf, "model": model}
    if language:
        call_kwargs["language"] = language

    result = client.audio.transcriptions.create(**call_kwargs)
    return getattr(result, "text", "") or ""
