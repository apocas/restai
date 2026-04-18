"""Generator-name → image-bytes dispatch for the `draw_image` builtin tool.

Resolves a generator name (with the same aliases the API router accepts) to
raw image bytes plus a mime type. Only handles the external generators
(DALL-E 3, gpt-image-1.5, Imagen) — GPU-loaded workers need an IPC `manager`
which the tool path doesn't have, and that's intentional: agents needing
local-GPU generation can use the `/image/{generator}/generate` API directly.
"""
from __future__ import annotations

import base64

from restai.models.models import ImageModel


_EXTERNAL_ALIASES: dict[str, str] = {
    # DALL-E 3
    "dalle": "dalle3",
    "dalle3": "dalle3",
    "dall-e-3": "dalle3",
    # gpt-image-1.5
    "gpt-image-1.5": "gpt_image_15",
    "gptimage15": "gpt_image_15",
    "gpt_image_15": "gpt_image_15",
    # Imagen
    "imagen": "imagen3",
    "imagen3": "imagen3",
}


class UnknownGeneratorError(Exception):
    """Raised when no external generator alias matches the requested name."""


def list_known_external_generators() -> list[str]:
    """Public-facing names the tool advertises in error messages."""
    return ["dalle", "gpt-image-1.5", "imagen"]


def generate_image(name: str, image_model: ImageModel) -> tuple[bytes, str]:
    """Run the named generator and return ``(raw_bytes, mime_type)``."""
    canonical = _EXTERNAL_ALIASES.get((name or "").lower().strip())
    if canonical == "dalle3":
        from restai.image.external.dalle3 import generate as _gen
    elif canonical == "gpt_image_15":
        from restai.image.external.gpt_image_15 import generate as _gen
    elif canonical == "imagen3":
        from restai.image.external.imagen3 import generate as _gen
    else:
        raise UnknownGeneratorError(name)
    b64 = _gen(image_model)
    return base64.b64decode(b64), "image/png"
