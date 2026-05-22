"""Google image generation via google-generativeai."""
from __future__ import annotations

import io

from restai.models.models import ImageModel


def generate(options: dict, image_model: ImageModel) -> tuple[bytes, str]:
    api_key = (options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Google image generator: `api_key` is required in options.")

    model = (options.get("model") or "").strip()
    if not model:
        raise RuntimeError("Google image generator: `model` is required in options.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)

    imagen = genai.ImageGenerationModel(model)
    result = imagen.generate_images(
        prompt=image_model.prompt,
        number_of_images=int(options.get("n") or 1),
        safety_filter_level=options.get("safety_filter_level") or "block_only_high",
        person_generation=options.get("person_generation") or "allow_adult",
        aspect_ratio=options.get("aspect_ratio") or "1:1",
    )
    if not result.images:
        raise RuntimeError("Google image generator returned no images.")

    pil = result.images[0]._pil_image
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue(), "image/png"
