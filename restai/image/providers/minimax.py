"""MiniMax H3 text-to-image generation."""
from __future__ import annotations

import base64

import requests

from restai.image.dispatch import ImageProviderError
from restai.models.models import ImageModel


def generate(options: dict, image_model: ImageModel) -> tuple[bytes, str]:
    if image_model.image:
        raise ImageProviderError(400, "MiniMax H3 accepts text prompts only.")
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("MiniMax image generator: `api_key` is required in options.")
    base_url = (options.get("base_url") or "https://api.minimax.io/v1").rstrip("/")
    if base_url not in {"https://api.minimax.io/v1", "https://api.minimax.cn/v1"}:
        raise RuntimeError("MiniMax image generator: choose the global or China API base URL.")
    payload = {
        "model": options.get("model") or "MiniMax-H3-Image",
        "prompt": image_model.prompt,
        "response_format": "b64_json",
        "output_format": "png",
    }
    if options.get("size"):
        payload["size"] = options["size"]

    # Dispatch returns one image. Replaying the POST could incur a second charge.
    try:
        response = requests.post(
            f"{base_url}/images/generations", headers={"Authorization": f"Bearer {api_key}"},
            json=payload, timeout=600, allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise ImageProviderError(504, "MiniMax image generation timed out.") from exc
    except requests.RequestException as exc:
        raise ImageProviderError(502, "MiniMax image generation request failed.") from exc

    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if response.status_code != 200:
        error = body.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        status = response.status_code if 400 <= response.status_code < 500 else 502
        raise ImageProviderError(status, f"MiniMax image API: {message or 'generation failed'}")

    items = body.get("data")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise ImageProviderError(502, "MiniMax image API returned an unexpected image list.")
    item = items[0]
    if isinstance(item.get("error"), dict):
        raise ImageProviderError(502, f"MiniMax image API: {item['error'].get('message') or 'image failed'}")
    encoded = item.get("b64_json")
    if not isinstance(encoded, str) or not encoded or body.get("output_format", "png") != "png":
        raise ImageProviderError(502, "MiniMax image API returned no PNG image.")
    try:
        return base64.b64decode(encoded, validate=True), "image/png"
    except ValueError as exc:
        raise ImageProviderError(502, "MiniMax image API returned invalid base64.") from exc
