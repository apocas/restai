"""AssemblyAI speech-to-text."""
from __future__ import annotations


def transcribe(options: dict, audio_bytes: bytes, filename: str, language: str | None) -> str:
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("AssemblyAI STT: `api_key` is required in options.")

    try:
        import assemblyai as aai
    except ImportError as e:
        raise RuntimeError("assemblyai is not installed; add it to dependencies.") from e

    aai.settings.api_key = api_key

    cfg_kwargs = {}
    speech_model = options.get("speech_model")
    if speech_model:
        cfg_kwargs["speech_model"] = (
            aai.SpeechModel.nano if speech_model == "nano" else aai.SpeechModel.best
        )
    language_code = options.get("language_code") or language
    if language_code:
        cfg_kwargs["language_code"] = language_code
    if options.get("language_detection"):
        cfg_kwargs["language_detection"] = True

    config = aai.TranscriptionConfig(**cfg_kwargs) if cfg_kwargs else None
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_bytes, config=config)
    if getattr(transcript, "status", None) == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")
    return getattr(transcript, "text", "") or ""
