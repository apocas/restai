"""Google image generation via google-generativeai.

Covers Imagen 3 / 4, Nano Banana, and anything else reachable through
`google.generativeai.ImageGenerationModel`. `options.model` is the model id
the SDK expects (e.g. `"imagen-3.0-generate-001"`). The admin can also set
per-generation knobs (`aspect_ratio`, `safety_filter_level`,
`person_generation`) in options; defaults stay permissive enough for
most prompts.

Options recognized:
- `model`                 (required) — Google model id.
- `api_key`               (required) — Google AI Studio key.
- `n`                     (optional, default 1) — number of images.
- `aspect_ratio`          (optional) — e.g. `"3:4"`, `"16:9"`, `"1:1"`.
- `safety_filter_level`   (optional, default `"block_only_high"`).
- `person_generation`     (optional, default `"allow_adult"`).
"""
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

    # `configure` is module-global — safe to call per-invocation because
    # the call just re-sets the api_key on the module's default client.
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

    # The SDK returns a PIL image in `_pil_image`. Re-encode as PNG to get
    # raw bytes we can cache + serve.
    pil = result.images[0]._pil_image
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue(), "image/png"
