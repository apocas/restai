def draw_image(generator: str, prompt: str, **kwargs) -> str:
    """Generate an image and show it to the user in the chat.

    Use this when the user asks for an image, drawing, picture, illustration,
    photo, etc. The image is rendered inline by the chat UI via the markdown
    URL this tool returns — emit that markdown verbatim in your reply so the
    user actually sees the image.

    Args:
        generator (str): Which image generator to use. One of: 'dalle' (DALL-E 3),
            'gpt-image-1.5', 'imagen' (Imagen 3). Defaults to 'gpt-image-1.5'
            if you pass an empty / unknown value.
        prompt (str): The text prompt describing the image to generate. Be
            specific and visual — describe subject, style, lighting, framing.
    """
    brain = kwargs.get("_brain")
    if not brain:
        return "ERROR: draw_image requires a brain context."
    if not prompt or not prompt.strip():
        return "ERROR: prompt is required."

    from restai.image.dispatch import (
        UnknownGeneratorError,
        generate_image,
        list_known_external_generators,
    )
    from restai.models.models import ImageModel

    chosen = (generator or "").strip() or "gpt-image-1.5"

    try:
        image_bytes, mime = generate_image(chosen, ImageModel(prompt=prompt))
    except UnknownGeneratorError:
        return (
            f"ERROR: unknown image generator '{generator}'. "
            f"Available: {', '.join(list_known_external_generators())}."
        )
    except Exception as e:
        return f"ERROR: image generation failed: {e}"

    image_id = brain.cache_image(image_bytes, mime_type=mime)
    ext = "png" if mime == "image/png" else (mime.split("/", 1)[-1] or "png")

    # Prefer an absolute URL when the deployment knows its public host —
    # required so non-browser clients (Android app, widget embeds on a
    # different origin, MCP consumers) can resolve the image. Falls back to
    # a relative path which the playground / same-origin browser handles
    # natively.
    from restai import config as _config
    public_url = (getattr(_config, "RESTAI_URL", None) or "").rstrip("/")
    url = f"{public_url}/image/cache/{image_id}.{ext}" if public_url else f"/image/cache/{image_id}.{ext}"

    # Markdown the LLM should echo verbatim so the chat UI renders the image.
    # The tool result also includes a plain-text instruction so a confused
    # model is more likely to actually emit the markdown.
    return (
        f"Image generated successfully. Show it to the user with this exact "
        f"markdown line in your reply:\n\n![{prompt}]({url})"
    )
