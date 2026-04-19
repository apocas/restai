"""GET /image/cache/{filename} — serves images stashed in Brain by tools.

Disk-backed (see `Brain.cache_image`), so the same file is visible from
every worker. Unauthenticated by design: the URLs hand out 32-char
unguessable hex ids, the cache TTL is 24h, and the only way an id ever
lands in front of a user is via that user's own chat response.
"""
from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import Response


router = APIRouter()


@router.get("/image/cache/{filename}")
async def get_cached_image(
    request: Request,
    filename: str = Path(description="Cached image filename, '<id>.<ext>'"),
):
    if not filename or len(filename) > 64 or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    brain = request.app.state.brain
    entry = brain.get_cached_image(filename)
    if entry is None:
        raise HTTPException(status_code=404, detail="Image not found or expired")

    data, mime_type = entry
    return Response(content=data, media_type=mime_type or "image/png")
