def draw_image(generator: str, prompt: str, **kwargs) -> str:
    """Generate an image and show it to the user in the chat.

    Use this when the user asks for an image, drawing, picture, illustration,
    photo, etc. The image is rendered inline by the chat UI via the markdown
    URL this tool returns — emit that markdown verbatim in your reply so the
    user actually sees the image.

    Args:
        generator (str): Name of an image generator registered in
            `/admin/image_generators`. Pass an empty string to fall back to
            the first enabled generator the platform knows about.
        prompt (str): The text prompt describing the image to generate. Be
            specific and visual — describe subject, style, lighting, framing.
    """
    brain = kwargs.get("_brain")
    if not brain:
        return "ERROR: draw_image requires a brain context."
    if not prompt or not prompt.strip():
        return "ERROR: prompt is required."

    from restai.database import get_db_wrapper
    from restai.image.dispatch import (
        GeneratorDisabledError,
        UnknownGeneratorError,
        generate_image,
        list_available_generators,
    )
    from restai.models.models import ImageModel

    db = get_db_wrapper()
    try:
        chosen = (generator or "").strip()
        if not chosen:
            available = list_available_generators(db)
            if not available:
                return (
                    "ERROR: no image generator is enabled. Ask the admin "
                    "to add one in /admin/image_generators."
                )
            chosen = available[0]

        try:
            image_bytes, mime = generate_image(chosen, ImageModel(prompt=prompt), brain, db)
        except UnknownGeneratorError:
            available = list_available_generators(db)
            return (
                f"ERROR: unknown image generator '{generator}'. "
                f"Available: {', '.join(available) if available else '(none configured)'}."
            )
        except GeneratorDisabledError:
            return f"ERROR: image generator '{chosen}' is disabled."
        except Exception as e:
            return f"ERROR: image generation failed: {e}"

        filename = brain.cache_image(image_bytes, mime_type=mime)
    finally:
        db.db.close()

    # Prefer an absolute URL when the deployment knows its public host —
    # required so non-browser clients (Android app, widget embeds on a
    # different origin, MCP consumers) can resolve the image. Falls back to
    # a relative path which the playground / same-origin browser handles
    # natively.
    from restai import config as _config
    public_url = (getattr(_config, "RESTAI_URL", None) or "").rstrip("/")
    url = f"{public_url}/image/cache/{filename}" if public_url else f"/image/cache/{filename}"

    # Return the markdown image line as the tool result. The agent runtime
    # post-processes tool results in `_drive_runtime` to guarantee any
    # `![](…/image/cache/…)` URL ends up in the final answer even when the
    # LLM summarizes the tool output instead of echoing it. So we don't
    # need to lecture the model about what to do with the result.
    return f"![]({url})"
