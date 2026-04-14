import json
import time
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from starlette.responses import StreamingResponse

from restai.auth import get_widget_from_request
from restai.database import get_db_wrapper, DBWrapper
from restai.models.models import ChatModel, User, WidgetChatRequest, WidgetChatResponse

router = APIRouter()

# Per-widget-key rate limiter
_widget_requests = defaultdict(list)
_widget_lock = threading.Lock()
_WIDGET_MAX_REQUESTS = 30
_WIDGET_WINDOW_SECONDS = 60


_widget_last_cleanup = datetime.now(timezone.utc)


def _check_widget_rate_limit(widget_key_prefix: str):
    global _widget_last_cleanup
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_WIDGET_WINDOW_SECONDS)
    with _widget_lock:
        if (now - _widget_last_cleanup).total_seconds() > _WIDGET_WINDOW_SECONDS:
            stale = [k for k, v in _widget_requests.items() if not v or v[-1] < cutoff]
            for k in stale:
                del _widget_requests[k]
            _widget_last_cleanup = now
        _widget_requests[widget_key_prefix] = [t for t in _widget_requests[widget_key_prefix] if t > cutoff]
        if len(_widget_requests[widget_key_prefix]) >= _WIDGET_MAX_REQUESTS:
            raise HTTPException(status_code=429, detail="Widget rate limit exceeded")
        _widget_requests[widget_key_prefix].append(now)


@router.get("/widget/config", tags=["Widget"])
async def widget_config(
    request: Request,
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Get widget visual configuration. Authenticated via X-Widget-Key header."""
    widget = get_widget_from_request(request, db_wrapper)
    config = json.loads(widget.config) if widget.config else {}

    # Apply context placeholders to welcome message
    context_header = request.headers.get("X-Widget-Context")
    if context_header and widget.context_secret and config.get("welcomeMessage"):
        try:
            from restai.utils.crypto import decrypt_field
            from restai.utils.widget_context import verify_widget_context, apply_widget_context

            secret = decrypt_field(widget.context_secret)
            context = verify_widget_context(context_header, secret)
            config["welcomeMessage"] = apply_widget_context(
                config["welcomeMessage"], context, prepend_block=False,
            )
        except ValueError:
            pass  # invalid token — return config as-is without substitution

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
    _check_widget_rate_limit(widget.key_prefix)
    brain = request.app.state.brain
    w_config = json.loads(widget.config) if widget.config else {}

    project = brain.find_project(widget.project_id, db_wrapper)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Handle signed context injection
    context_header = request.headers.get("X-Widget-Context")
    if context_header and widget.context_secret:
        from restai.utils.crypto import decrypt_field
        from restai.utils.widget_context import verify_widget_context, apply_widget_context
        from restai.project import Project

        try:
            secret = decrypt_field(widget.context_secret)
            context = verify_widget_context(context_header, secret)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired context token")

        # Inject context into system prompt on a per-request copy
        prepend = w_config.get("context_prefix", True)
        modified_props = project.props.model_copy(deep=True)
        modified_props.system = apply_widget_context(
            modified_props.system or "", context, prepend_block=prepend,
        )
        project = Project(modified_props)
        project.widget_context = context

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

    use_stream = body.stream if body.stream is not None else w_config.get("stream", False)

    chat_input = ChatModel(
        question=body.question,
        id=body.id,
        stream=use_stream,
    )

    from restai.helper import chat_main
    start_time = time.perf_counter()

    try:
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
            if result is None:
                return WidgetChatResponse(answer="No response generated.", id=body.id)
            if isinstance(result, dict):
                return WidgetChatResponse(
                    answer=result.get("answer", ""),
                    id=result.get("id"),
                )
            return WidgetChatResponse(answer=str(result))
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Widget chat failed for project %s", widget.project_id)
        raise HTTPException(status_code=500, detail="Chat failed")


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
