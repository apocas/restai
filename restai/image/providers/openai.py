"""OpenAI + OpenAI-compatible image generation.

Works for:
- OpenAI proper (`gpt-image-1`, `gpt-image-1.5`, `dall-e-3`, etc.).
- Any OpenAI-spec-compatible endpoint (Together, Groq, vLLM image servers,
  self-hosted proxies) when the admin sets `options.base_url`.

Options recognized:
- `model`       (required) — model id passed to `client.images.generate`.
- `api_key`     (required) — bearer token for the endpoint.
- `base_url`    (optional) — overrides the default `https://api.openai.com/v1`.
- `size`        (optional) — e.g. `"1024x1024"`, forwarded verbatim.
- `quality`     (optional) — `"standard"` | `"hd"` (or provider-specific).
- `n`           (optional, default 1) — number of images; we only return the first.
"""
from __future__ import annotations

import base64

import logging

import requests
from openai import APIStatusError, OpenAI

from restai.image.dispatch import ImageProviderError
from restai.models.models import ImageModel

logger = logging.getLogger(__name__)


def _extract_openai_message(err: APIStatusError) -> str:
    """OpenAI proper returns `{"error": {"message": "..."}}`; compat
    servers often return something else. Fall back gracefully."""
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("message"), str):
            return inner["message"]
        if isinstance(body.get("message"), str):
            return body["message"]
    return getattr(err, "message", None) or str(err) or "OpenAI image API error"


def generate(options: dict, image_model: ImageModel) -> tuple[bytes, str]:
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("OpenAI image generator: `api_key` is required in options.")

    model = (options.get("model") or "").strip()
    if not model:
        raise RuntimeError("OpenAI image generator: `model` is required in options.")

    client_kwargs = {"api_key": api_key}
    base_url = (options.get("base_url") or "").strip()
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    call_kwargs = {"model": model, "prompt": image_model.prompt, "n": int(options.get("n") or 1)}
    if options.get("size"):
        call_kwargs["size"] = options["size"]
    if options.get("quality"):
        call_kwargs["quality"] = options["quality"]

    try:
        result = client.images.generate(**call_kwargs)
    except APIStatusError as e:
        message = _extract_openai_message(e)
        upstream = e.status_code or 502
        # Forward 4xx (caller config / auth / quota issue), translate 5xx
        # to 502 since the failure is upstream, not ours.
        status = upstream if 400 <= upstream < 500 else 502
        logger.warning("OpenAI image generation failed (%s): %s", upstream, message)
        raise ImageProviderError(status, f"OpenAI image API: {message}") from e

    data = result.data[0]

    # gpt-image-* defaults to b64_json; dall-e-3 returns a URL. Handle both.
    if getattr(data, "b64_json", None):
        return base64.b64decode(data.b64_json), "image/png"
    if getattr(data, "url", None):
        resp = requests.get(data.url, timeout=30)
        resp.raise_for_status()
        return resp.content, "image/png"
    raise RuntimeError("OpenAI image generator returned neither b64_json nor url.")
