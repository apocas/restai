"""OpenAI Whisper API + OpenAI-compat transcription.

Works against:
- OpenAI proper (`whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`).
- Any OpenAI-spec-compatible endpoint (Groq, Together, vLLM transcription
  servers, self-hosted gateways) when admin sets `options.base_url`.

Options recognized:
- `model`     (required) — e.g. `"whisper-1"`.
- `api_key`   (required).
- `base_url`  (optional) — overrides the default `https://api.openai.com/v1`.
"""
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

    # The SDK expects a file-like with a name. Wrap bytes in BytesIO and
    # tag the name so the server picks the right MIME by extension.
    buf = io.BytesIO(audio_bytes)
    buf.name = filename or "audio.mp3"

    call_kwargs = {"file": buf, "model": model}
    if language:
        call_kwargs["language"] = language

    result = client.audio.transcriptions.create(**call_kwargs)
    return getattr(result, "text", "") or ""
