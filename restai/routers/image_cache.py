"""GET /image/cache/{filename} — serves images stashed in Brain by tools.

Unauthenticated by design: the URLs hand out 32-char unguessable hex ids,
the cache TTL is 24h, and the only way an id ever lands in front of a user
is via that user's own chat response. We mount this independently of the
GPU-gated image router so the `draw_image` builtin tool works on every
deployment.
"""
from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import Response


router = APIRouter()


@router.get("/image/cache/{filename}")
async def get_cached_image(request: Request, filename: str = Path(description="Cached image filename, '<id>.<ext>'")):
    # Strip optional extension — the id is the cache key.
    image_id = filename.split(".", 1)[0]
    if not image_id or len(image_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid image id")

    brain = request.app.state.brain
    entry = brain.get_cached_image(image_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Image not found or expired")

    data, mime_type = entry
    return Response(content=data, media_type=mime_type or "image/png")
