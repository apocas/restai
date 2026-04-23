"""Google Cloud Speech-to-Text.

Uses the `google-cloud-speech` package via API-key auth. For service-account
auth set `GOOGLE_APPLICATION_CREDENTIALS` and leave `api_key` empty — the
client falls back to ADC.

Options recognized:
- `api_key`         (optional) — Google API key with STT enabled.
- `language_code`   (optional) — e.g. `"en-US"`. Falls back to the request's
                                 `language` parameter, then `"en-US"`.
- `model`           (optional) — `"latest_long"`, `"telephony"`, etc.
- `sample_rate_hz`  (optional) — e.g. 16000. If omitted, autodetect.
"""
from __future__ import annotations


def transcribe(options: dict, audio_bytes: bytes, filename: str, language: str | None) -> str:
    api_key = (options.get("api_key") or "").strip() or None
    language_code = (options.get("language_code") or language or "en-US").strip()

    try:
        from google.cloud import speech_v1 as speech
    except ImportError as e:
        raise RuntimeError("google-cloud-speech is not installed; add it to dependencies.") from e

    client_options = {"api_key": api_key} if api_key else None
    client = speech.SpeechClient(client_options=client_options) if client_options else speech.SpeechClient()

    audio = speech.RecognitionAudio(content=audio_bytes)
    config_kwargs = {
        "language_code": language_code,
        "enable_automatic_punctuation": True,
    }
    if options.get("model"):
        config_kwargs["model"] = options["model"]
    if options.get("sample_rate_hz"):
        config_kwargs["sample_rate_hertz"] = int(options["sample_rate_hz"])
    cfg = speech.RecognitionConfig(**config_kwargs)

    response = client.recognize(config=cfg, audio=audio)
    parts = []
    for result in response.results:
        if result.alternatives:
            parts.append(result.alternatives[0].transcript)
    return " ".join(parts).strip()
