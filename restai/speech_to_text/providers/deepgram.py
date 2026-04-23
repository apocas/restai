"""Deepgram speech-to-text.

Uses the official `deepgram-sdk` (synchronous client). Reads the API key
from `options.api_key`; model + language + smart_format are configurable.

Options recognized:
- `api_key`        (required).
- `model`          (optional, default `"nova-2"`).
- `language`       (optional) — falls back to the request `language`.
- `smart_format`   (optional, default true).
"""
from __future__ import annotations


def transcribe(options: dict, audio_bytes: bytes, filename: str, language: str | None) -> str:
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Deepgram STT: `api_key` is required in options.")

    try:
        from deepgram import DeepgramClient, PrerecordedOptions
    except ImportError as e:
        raise RuntimeError("deepgram-sdk is not installed; add it to dependencies.") from e

    client = DeepgramClient(api_key)

    dg_options = PrerecordedOptions(
        model=options.get("model") or "nova-2",
        language=options.get("language") or language or "en",
        smart_format=options.get("smart_format", True),
    )

    payload = {"buffer": audio_bytes}
    response = client.listen.prerecorded.v("1").transcribe_file(payload, dg_options)
    try:
        return response["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError):
        # Newer SDK versions return objects, not dicts.
        try:
            return response.results.channels[0].alternatives[0].transcript
        except Exception:
            return ""
