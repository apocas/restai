import time
import socket
import ipaddress
from typing import AsyncGenerator, Any, Dict
from urllib.parse import urlparse

from starlette.responses import StreamingResponse
from requests import Response
from fastapi import BackgroundTasks
from restai.database import DBWrapper
from restai.project import Project
from restai.projects.agent import Agent
from restai.projects.app import App
from restai.projects.block import Block
from restai.projects.rag import RAG
from restai.models.models import QuestionModel, User, ChatModel
from restai.brain import Brain
import requests
from fastapi import HTTPException, Request
import re
import logging
from restai.models.models import InteractionModel
import base64
from restai.tools import log_inference
from restai.config import LOG_LEVEL
import json

from restai.projects.base import ProjectBase
from restai.budget import check_budget, check_rate_limit, check_api_key_quota, record_api_key_tokens

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_URL_PATTERN = re.compile(
    r"https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(),]|%[0-9a-fA-F][0-9a-fA-F])+"
)


def _is_private_ip(hostname: str) -> bool:
    """Resolve hostname and check if any resolved IP falls within blocked networks."""
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for addrinfo in addrinfos:
        ip = ipaddress.ip_address(addrinfo[4][0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return True
    return False


def resolve_image(image: str) -> str:
    """If image is a URL, fetch it and return base64-encoded data. Otherwise return as-is."""
    if re.match(_URL_PATTERN, image):
        parsed = urlparse(image)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL has no valid hostname.")

        if _is_private_ip(hostname):
            logger.warning("Blocked SSRF attempt to internal address: %s", hostname)
            raise ValueError(f"Access to internal/private addresses is not allowed: {hostname}")

        response = requests.get(image, timeout=10, stream=True)
        response.raise_for_status()

        chunks = []
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            downloaded += len(chunk)
            if downloaded > MAX_IMAGE_SIZE:
                response.close()
                raise ValueError(f"Image exceeds maximum allowed size of {MAX_IMAGE_SIZE} bytes.")
            chunks.append(chunk)

        content = b"".join(chunks)
        if not content:
            raise ValueError("Content is null.")
        return base64.b64encode(content).decode("utf-8")
    return image


_IMAGE_ATTACHMENT_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _is_image_attachment(att) -> bool:
    mime = (getattr(att, "mime_type", None) or "").lower()
    if mime.startswith("image/"):
        return True
    name = (getattr(att, "name", "") or "").lower()
    return name.endswith(_IMAGE_ATTACHMENT_EXTS)


def _attachment_meta(files):
    """Strip attachment bytes down to logging-safe metadata. `files` is the
    optional `FileAttachment[]` on Chat/QuestionModel."""
    if not files:
        return []
    meta = []
    for f in files:
        try:
            size = len(f.content or "") if isinstance(f.content, str) else 0
        except Exception:
            size = 0
        meta.append({
            "name": getattr(f, "name", None) or "",
            "mime_type": getattr(f, "mime_type", None),
            "size": size,
        })
    return meta


def _normalize_image_inputs(model) -> None:
    """Canonicalize image input on a Chat/QuestionModel in place.

    Historically a user could attach an image either via `.image` (the
    single-image slot) or via `.files[]` (a FileAttachment whose mime or
    filename marks it as an image). These two paths were drifting apart:

    - The log viewer persisted only `.image`.
    - `FileAttachment.content` had no size cap while `.image` did.
    - Block projects only read `.image`, so an image sent via `.files[]`
      silently vanished.
    - Inside the agent, `_route_attachments` promoted the first image file
      into `image_url` locally, but never propagated that back to `.image`.

    This helper collapses `files[<image>]` into `.image` at the helper
    boundary so every downstream path sees a single source of truth.

    Rules (preserving today's agent behavior):
    - Explicit `.image` wins. If set, files-images are dropped.
    - Only the first image in `files[]` is promoted. Subsequent images
      are dropped (same as `_route_attachments` today).
    - Non-image files pass through untouched — they still go to the
      Docker sandbox when `terminal` is enabled.
    """
    files = getattr(model, "files", None) or []
    if not files:
        return

    first_image = None
    remaining = []
    for f in files:
        if _is_image_attachment(f):
            if first_image is None:
                first_image = f
            # Drop image files from `files` regardless — either we
            # promoted it to `.image` or we're discarding a second+ image.
            continue
        remaining.append(f)

    if first_image is not None and not getattr(model, "image", None):
        mime = first_image.mime_type or "image/png"
        model.image = f"data:{mime};base64,{first_image.content}"

    # Always rewrite `files` to the image-free remainder so downstream
    # code (agent's `_route_attachments`, attachment-meta logging, sandbox
    # upload) doesn't see the image twice.
    model.files = remaining


def _pick_image_for_log(explicit_image, files):
    """Return the image to persist in `output.image`.

    Post-`_normalize_image_inputs`, `.image` is the canonical source and
    `files` no longer contains images. Kept as a thin helper for symmetry
    with `_attachment_meta` and to stay resilient to direct-callers that
    skip the normalization step.
    """
    if explicit_image:
        return explicit_image
    if not files:
        return None
    # Defensive fallback — only fires if a caller bypassed the normalizer.
    for f in files:
        if _is_image_attachment(f) and getattr(f, "content", None):
            mime = getattr(f, "mime_type", None) or "image/png"
            return f"data:{mime};base64,{f.content}"
    return None


def _log_inference_error(
    project: Project,
    user: User,
    db: DBWrapper,
    *,
    question: str,
    image: str = None,
    attachments: list = None,
    status: str,
    error: str,
    system_prompt: str = None,
    context: dict = None,
    start_time: float = None,
):
    """Synchronously write an error row to the inference log before letting
    an HTTPException propagate. Never raises — logging failures are
    swallowed with a traceback so the original error still reaches the client."""
    latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
    output = {
        "question": question or "",
        "answer": "",
        "tokens": {"input": 0, "output": 0},
        "status": status,
        "error": str(error) if error is not None else None,
        "image": image,
        "attachments": attachments or [],
    }
    try:
        log_inference(
            project, user, output, db,
            latency_ms=latency_ms,
            system_prompt=system_prompt,
            context=context,
        )
    except Exception:
        logging.exception("Failed to write error row to inference log")


async def create_streaming_response_with_logging(
    generator,
    project: Project,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
    system_prompt: str = None,
    context: dict = None,
    question: str = None,
    image: str = None,
    attachments: list = None,
) -> StreamingResponse:

    async def stream_with_logging():
        final_output = None
        completed = False

        try:
            try:
                async for chunk in generator:
                    if isinstance(chunk, dict):
                        # Safety: if the generator yields a dict (e.g. error fallback),
                        # wrap it as an SSE data line instead of yielding raw.
                        final_output = chunk
                        yield "data: " + json.dumps(chunk) + "\n"
                        continue
                    if isinstance(chunk, str) and chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk.replace("data: ", ""))
                            if "answer" in data and "type" in data:
                                final_output = data
                        except:
                            pass
                    yield chunk
                completed = True
            except Exception as e:
                # Error mid-stream: record it, send a final SSE dict the
                # frontend can render, and stop iterating.
                logging.exception("Streaming inference failed: %s", e)
                err_output = {
                    "question": question or "",
                    "answer": f"Internal error: {e}",
                    "tokens": {"input": 0, "output": 0},
                    "type": project.props.type,
                    "status": "error",
                    "error": str(e),
                    "image": image,
                    "attachments": attachments or [],
                }
                final_output = err_output
                # The yields below can themselves fail with ClientDisconnect /
                # CancelledError if the client already left — swallow so the
                # finally block below still runs the log write.
                try:
                    yield "data: " + json.dumps({"text": err_output["answer"]}) + "\n\n"
                    yield "data: " + json.dumps(err_output) + "\n"
                except Exception:
                    pass

            # Best-effort close marker. Wrapped because yielding from a
            # generator the runtime is trying to cancel can re-raise — and
            # we don't want that to skip the finally block that does the
            # actual log write.
            try:
                yield "event: close\n\n"
            except Exception:
                pass
        finally:
            # Run log_inference SYNCHRONOUSLY here instead of via
            # background_tasks.add_task. BackgroundTasks only fire after the
            # response body finishes sending, so a client that disconnects
            # mid-stream (CancelledError / GeneratorExit propagates into
            # this generator) skips them entirely — losing the audit row,
            # the cost attribution, and the per-API-key quota counter.
            # The finally block runs regardless of how the generator exited
            # (success, mid-stream error, client cancel, server cancel),
            # so logging is guaranteed for any inference that actually
            # consumed model tokens.
            try:
                if final_output:
                    if image and not final_output.get("image"):
                        final_output["image"] = image
                    if attachments and not final_output.get("attachments"):
                        final_output["attachments"] = attachments
                    latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                    log_inference(
                        project, user, final_output, db,
                        latency_ms=latency_ms, system_prompt=system_prompt, context=context,
                    )
                elif not completed:
                    # Client disconnected before the model finished — record
                    # a stub so the call still appears in the inference log
                    # (tokens are not known here; kept zero on purpose so we
                    # don't double-count cost vs whatever the model actually
                    # consumed before being cut off).
                    _log_inference_error(
                        project, user, db,
                        question=question, image=image, attachments=attachments,
                        status="disconnected",
                        error="Client disconnected before stream completed",
                        system_prompt=system_prompt, context=context,
                        start_time=start_time,
                    )
            except Exception:
                logging.exception("log_inference failed in stream_with_logging finally")

    return StreamingResponse(
        stream_with_logging(),
        media_type="text/event-stream",
    )


def _apply_context(project: Project, interaction: InteractionModel) -> Project:
    """If the request includes context, apply it to the project's system prompt."""
    if not interaction.context:
        return project
    return project.with_context(interaction.context)


async def chat_main(
    _: Request,
    brain: Brain,
    project: Project,
    chat_input: ChatModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    # Canonicalize image input: folds `.files[<image>]` into `.image` so
    # every downstream path (agent vision flow, block interpreter, log
    # viewer) sees a single source of truth. Does nothing if `.image` was
    # already set or if `.files[]` has no image.
    _normalize_image_inputs(chat_input)

    # Capture request metadata up front so every error path below can
    # write a log row tagged with what the user actually sent.
    _files = getattr(chat_input, "files", None)
    _image = _pick_image_for_log(chat_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = chat_input.question
    _sys = project.props.system
    _ctx = chat_input.context

    try:
        check_budget(project, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="budget", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    try:
        check_rate_limit(project, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="rate_limit", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    try:
        check_api_key_quota(user, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="quota", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    try:
        project = _apply_context(project, chat_input)

        proj_logic: ProjectBase
        match project.props.type:
            case "rag":
                proj_logic = RAG(brain)
            case "agent":
                proj_logic = Agent(brain)
                if chat_input.image:
                    chat_input.image = resolve_image(chat_input.image)
                    _image = chat_input.image  # keep log-image in sync with resolved form
            case "block":
                proj_logic = Block(brain)
            case "app":
                proj_logic = App(brain)
            case _:
                raise HTTPException(status_code=400, detail="Invalid project type")

        if chat_input.stream:
            return await create_streaming_response_with_logging(
                proj_logic.chat(project, chat_input, user, db),
                project,
                user,
                db,
                background_tasks,
                start_time=start_time,
                system_prompt=_sys,
                context=_ctx,
                question=_question,
                image=_image,
                attachments=_attachments,
            )
        else:
            output_generator = proj_logic.chat(project, chat_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                # Splice request metadata into the output dict so the log
                # row carries the image + attachments without each project
                # type having to remember to copy them in.
                if _image and not line.get("image"):
                    line["image"] = _image
                if _attachments and not line.get("attachments"):
                    line["attachments"] = _attachments
                # Log synchronously, NOT via background_tasks.add_task —
                # those only fire after the response body has been
                # successfully written, so a client disconnect between
                # `return line` and serialization would skip them and
                # silently lose audit / cost / quota counting.
                log_inference(
                    project, user, line, db,
                    latency_ms=latency_ms, system_prompt=_sys, context=_ctx,
                )
                return line
            return None
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise
    except Exception as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=str(e),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise


async def question_main(
    request: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    # Canonicalize image input: see `_normalize_image_inputs` doc. Ensures
    # `.image` is the single source of truth for every project type.
    _normalize_image_inputs(q_input)

    # Request metadata captured so every error path can log a row that
    # reflects what the user sent (including images + attachments that
    # the LLM never saw because we rejected the request up-front).
    _files = getattr(q_input, "files", None)
    _image = _pick_image_for_log(q_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = q_input.question
    _sys = project.props.system
    _ctx = q_input.context

    try:
        check_budget(project, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="budget", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    try:
        check_rate_limit(project, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="rate_limit", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    try:
        check_api_key_quota(user, db)
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="quota", error=getattr(e, "detail", str(e)),
            system_prompt=_sys, context=_ctx, start_time=start_time,
        )
        raise

    project = _apply_context(project, q_input)

    # Check cache for all project types
    cached = await process_cache(project, q_input)
    if cached:
        latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
        if _image and not cached.get("image"):
            cached["image"] = _image
        if _attachments and not cached.get("attachments"):
            cached["attachments"] = _attachments
        # Sync log — see note in chat_main: BackgroundTasks fire only
        # after the body is sent, so client disconnect would lose this.
        log_inference(
            project, user, cached, db,
            latency_ms=latency_ms, system_prompt=_sys, context=_ctx,
        )
        return cached

    result = None
    match project.props.type:
        case "rag":
            result = await question_rag(
                request, brain, project, q_input, user, db, background_tasks, start_time, _sys, _ctx
            )
        case "agent":
            result = await question_agent(
                brain, project, q_input, user, db, background_tasks, start_time, _sys, _ctx
            )
        case "block":
            result = await question_block(
                brain, project, q_input, user, db, background_tasks, start_time, _sys, _ctx
            )
        case "app":
            result = await question_app(
                brain, project, q_input, user, db, background_tasks, start_time, _sys, _ctx
            )
        case _:
            _log_inference_error(
                project, user, db,
                question=_question, image=_image, attachments=_attachments,
                status="error", error="Invalid project type",
                system_prompt=_sys, context=_ctx, start_time=start_time,
            )
            raise HTTPException(status_code=400, detail="Invalid project type")

    # Populate cache with the result
    if result and project.cache and isinstance(result, dict) and "answer" in result:
        try:
            project.cache.add(q_input.question, result["answer"])
        except Exception:
            pass

    # Log retrieval events for RAG source analytics
    if result and isinstance(result, dict) and result.get("sources") and project.props.type == "rag":
        from restai.tools import log_retrieval_events
        background_tasks.add_task(log_retrieval_events, project, result["sources"], db)

    return result


async def question_rag(
    _: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
    system_prompt: str = None,
    context: dict = None,
):
    _files = getattr(q_input, "files", None)
    _image = _pick_image_for_log(q_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = q_input.question

    try:
        proj_logic = RAG(brain)

        if project.props.type != "rag":
            raise HTTPException(
                status_code=400, detail="Only available for RAG projects."
            )

        if q_input.stream:
            return await create_streaming_response_with_logging(
                proj_logic.question(project, q_input, user, db),
                project,
                user,
                db,
                background_tasks,
                start_time=start_time,
                system_prompt=system_prompt,
                context=context,
                question=_question,
                image=_image,
                attachments=_attachments,
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                if _image and not line.get("image"):
                    line["image"] = _image
                if _attachments and not line.get("attachments"):
                    line["attachments"] = _attachments
                # Sync log — see chat_main note. BackgroundTasks would lose
                # this row on client disconnect.
                log_inference(
                    project, user, line, db,
                    latency_ms=latency_ms, system_prompt=system_prompt, context=context,
                )
                return line
    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=getattr(e, "detail", str(e)),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise
    except Exception as e:
        logging.exception(e)
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=str(e),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_cache(project: Project, q_input: QuestionModel):
    output = {
        "question": q_input.question,
        "type": "question",
        "sources": [],
        "tokens": {"input": 0, "output": 0},
    }

    if project.cache:
        answer = project.cache.verify(q_input.question)
        if answer is not None:
            output.update(
                {
                    "answer": answer,
                    "cached": True,
                }
            )

            return output

    return None


async def question_agent(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
    system_prompt: str = None,
    context: dict = None,
):
    _files = getattr(q_input, "files", None)
    _image = _pick_image_for_log(q_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = q_input.question

    try:
        proj_logic: Agent = Agent(brain)

        if project.props.type != "agent":
            raise HTTPException(
                status_code=400, detail="Only available for AGENT projects."
            )

        if q_input.image:
            q_input.image = resolve_image(q_input.image)
            _image = q_input.image

        if q_input.stream:
            return await create_streaming_response_with_logging(
                proj_logic.question(project, q_input, user, db),
                project,
                user,
                db,
                background_tasks,
                start_time=start_time,
                system_prompt=system_prompt,
                context=context,
                question=_question,
                image=_image,
                attachments=_attachments,
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                if _image and not line.get("image"):
                    line["image"] = _image
                if _attachments and not line.get("attachments"):
                    line["attachments"] = _attachments
                # Sync log — see chat_main note. BackgroundTasks would lose
                # this row on client disconnect.
                log_inference(
                    project, user, line, db,
                    latency_ms=latency_ms, system_prompt=system_prompt, context=context,
                )
                return line

    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=getattr(e, "detail", str(e)),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise
    except Exception as e:
        logging.exception(e)
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=str(e),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


async def question_block(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
    system_prompt: str = None,
    context: dict = None,
):
    _files = getattr(q_input, "files", None)
    _image = _pick_image_for_log(q_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = q_input.question

    try:
        proj_logic = Block(brain)

        if project.props.type != "block":
            raise HTTPException(
                status_code=400, detail="Only available for BLOCK projects."
            )

        if q_input.image:
            q_input.image = resolve_image(q_input.image)
            _image = q_input.image

        output_generator = proj_logic.question(project, q_input, user, db)
        async for line in output_generator:
            latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
            if _image and not line.get("image"):
                line["image"] = _image
            if _attachments and not line.get("attachments"):
                line["attachments"] = _attachments
            # Sync log — see chat_main note. BackgroundTasks would lose
            # this row on client disconnect.
            log_inference(
                project, user, line, db,
                latency_ms=latency_ms, system_prompt=system_prompt, context=context,
            )
            return line

    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=getattr(e, "detail", str(e)),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise
    except Exception as e:
        logging.exception(e)
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=str(e),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


async def question_app(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
    system_prompt: str = None,
    context: dict = None,
):
    _files = getattr(q_input, "files", None)
    _image = _pick_image_for_log(q_input.image, _files)
    _attachments = _attachment_meta(_files)
    _question = q_input.question

    try:
        proj_logic = App(brain)

        if project.props.type != "app":
            raise HTTPException(
                status_code=400, detail="Only available for APP projects."
            )

        output_generator = proj_logic.question(project, q_input, user, db)
        async for line in output_generator:
            latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
            if _image and not line.get("image"):
                line["image"] = _image
            if _attachments and not line.get("attachments"):
                line["attachments"] = _attachments
            log_inference(
                project, user, line, db,
                latency_ms=latency_ms, system_prompt=system_prompt, context=context,
            )
            return line

    except HTTPException as e:
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=getattr(e, "detail", str(e)),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise
    except Exception as e:
        logging.exception(e)
        _log_inference_error(
            project, user, db,
            question=_question, image=_image, attachments=_attachments,
            status="error", error=str(e),
            system_prompt=system_prompt, context=context, start_time=start_time,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


