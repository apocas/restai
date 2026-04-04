import json
import time
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from starlette.responses import StreamingResponse

from restai.auth import get_widget_from_request
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import ChatModel, User, WidgetChatRequest, WidgetChatResponse

router = APIRouter()


@router.get("/widget/config", tags=["Widget"])
async def widget_config(
    request: Request,
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get widget visual configuration. Authenticated via X-Widget-Key header."""
    widget = get_widget_from_request(request, db_wrapper)
    config = json.loads(widget.config) if widget.config else {}
    return config


@router.post("/widget/chat", tags=["Widget"])
async def widget_chat(
    request: Request,
    body: WidgetChatRequest,
    background_tasks: BackgroundTasks,
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Chat via an embedded widget. Returns sanitized response (answer + chat_id only)."""
    widget = get_widget_from_request(request, db_wrapper)
    brain = request.app.state.brain

    project = brain.find_project(widget.project_id, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Use project creator as synthetic user
    creator = db_wrapper.get_user_by_id(widget.creator_id)
    if creator is None:
        raise HTTPException(status_code=500, detail="Widget creator not found")

    user = User(
        id=creator.id,
        username=creator.username,
        is_admin=False,
        is_private=creator.is_private,
        projects=[],
        teams=[],
        admin_teams=[],
        api_key_allowed_projects=[widget.project_id],
        api_key_read_only=True,
    )

    # Use stream from widget config if not specified in request
    widget_config = json.loads(widget.config) if widget.config else {}
    use_stream = body.stream if body.stream is not None else widget_config.get("stream", False)

    chat_input = ChatModel(
        question=body.question,
        id=body.id,
        stream=use_stream,
    )

    from restai.helper import chat_main
    start_time = time.perf_counter()

    if use_stream:
        # Streaming: wrap the SSE response to sanitize output
        response = await chat_main(
            request, brain, project, chat_input, user, db_wrapper, background_tasks, start_time=start_time,
        )
        # response is a StreamingResponse — wrap its body_iterator
        return StreamingResponse(
            _sanitize_stream(response.body_iterator),
            media_type="text/event-stream",
        )
    else:
        result = await chat_main(
            request, brain, project, chat_input, user, db_wrapper, background_tasks, start_time=start_time,
        )
        if isinstance(result, dict):
            return WidgetChatResponse(
                answer=result.get("answer", ""),
                id=result.get("id"),
            )
        return WidgetChatResponse(answer=str(result))


async def _sanitize_stream(body_iterator):
    """Filter SSE stream to only emit text chunks and sanitized final event."""
    async for chunk in body_iterator:
        if not isinstance(chunk, str):
            chunk = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

        for line in chunk.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line == "event: close":
                yield "event: close\n\n"
                continue
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "text" in data and "answer" not in data:
                        # Incremental text chunk — safe to forward
                        yield f"data: {json.dumps({'text': data['text']})}\n\n"
                    elif "answer" in data:
                        # Final summary — sanitize
                        yield f"data: {json.dumps({'answer': data.get('answer', ''), 'id': data.get('id')})}\n\n"
                except (json.JSONDecodeError, TypeError):
                    pass
