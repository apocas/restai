import time
import socket
import ipaddress
from typing import AsyncGenerator, Any, Dict
from urllib.parse import urljoin, urlparse

from starlette.responses import StreamingResponse
from requests import Response
from fastapi import BackgroundTasks
from restai.database import DBWrapper
from restai.project import Project
from restai.projects.agent import Agent
from restai.projects.app import App
from restai.projects.block import Block
from restai.projects.rag import RAG
from restai.models.models import User, ChatModel
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
from restai.limits.budget import enforce_cost_budgets, check_rate_limit, check_api_key_quota, record_api_key_tokens
from restai.models.databasemodels import ApiKeyDatabase

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
    # IPv4-mapped IPv6 space -- covers ::ffff:10.x, ::ffff:192.168.x, ::ffff:169.254.x etc.
    # Without this, ip_address('::ffff:169.254.169.254') is an IPv6Address not contained in
    # '169.254.0.0/16' (an IPv4Network), bypassing the blocklist on dual-stack Linux hosts.
    ipaddress.ip_network("::ffff:0:0/96"),
]

_URL_PATTERN = re.compile(
    r"https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(),]|%[0-9a-fA-F][0-9a-fA-F])+"
)


def _is_private_ip(hostname: str) -> bool:
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

    for addrinfo in addrinfos:
        ip = ipaddress.ip_address(addrinfo[4][0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return True
    # Secondary check: unwrap IPv4-mapped IPv6 addresses and recheck against IPv4 blocklists.
    # Handles the case where getaddrinfo returns ::ffff:<private-ip> on dual-stack systems.
    for addrinfo in addrinfos:
        ip = ipaddress.ip_address(addrinfo[4][0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            for network in _BLOCKED_NETWORKS:
                if ip.ipv4_mapped in network:
                    return True
    return False


def _safe_get(url: str, max_redirects: int = 5, **kwargs):
    """`requests.get` that re-validates the target host against the SSRF
    blocklist on the initial request AND on every redirect hop (auto-redirect
    disabled). Closes the redirect→internal bypass (e.g. a public URL that 302s
    to 169.254.169.254). Raises ValueError on a private/internal target."""
    kwargs["allow_redirects"] = False
    current = url
    for _ in range(max_redirects + 1):
        hostname = urlparse(current).hostname
        if not hostname:
            raise ValueError("URL has no valid hostname.")
        if _is_private_ip(hostname):
            logger.warning("Blocked SSRF attempt to internal address: %s", hostname)
            raise ValueError(f"Access to internal/private addresses is not allowed: {hostname}")
        response = requests.get(current, **kwargs)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect without a Location header.")
            current = urljoin(current, location)
            continue
        return response
    raise ValueError("Too many redirects.")


def resolve_image(image: str) -> str:
    if re.match(_URL_PATTERN, image):
        parsed = urlparse(image)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("URL has no valid hostname.")

        # _safe_get re-checks the host on every redirect hop too.
        response = _safe_get(image, timeout=10, stream=True)
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
    """Strip attachment bytes down to logging-safe metadata."""
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
    """Canonicalize image input on a ChatModel in place.

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
    # Resilient to callers that skip `_normalize_image_inputs`.
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
    # The session may already be in a failed state — the original error
    # path likely rolled the transaction back on the way out, but if it
    # didn't, SQLAlchemy refuses any further work with PendingRollback-
    # Error. Rolling back here is safe (no-op when there's nothing to
    # roll back) and lets the log_inference write actually land instead
    # of being silently swallowed by the except below.
    try:
        db.db.rollback()
    except Exception:
        pass
    try:
        log_inference(
            project, user, output, db,
            latency_ms=latency_ms,
            system_prompt=system_prompt,
            context=context,
        )
    except Exception:
        logging.exception("Failed to write error row to inference log")
        try:
            db.db.rollback()
        except Exception:
            pass


async def _drain_generator_into_session(
    generator,
    resume_session,
    *,
    project: Project,
    user: User,
    system_prompt: str = None,
    context: dict = None,
    question: str = None,
    image: str = None,
    attachments: list = None,
    start_time: float = None,
) -> None:
    """Background producer: iterate the agent generator, push each SSE
    chunk into `resume_session`, finalize logging. Designed to run as
    an `asyncio.create_task(...)` so the agent run survives the HTTP
    request that kicked it off — a dropped SSE connection no longer
    cancels the agent. The HTTP response side just subscribes to the
    session and replays/tails.

    Opens its OWN DBWrapper because the request-scoped one closes when
    FastAPI tears the request down (which can happen mid-run for the
    very disconnect cases this resume path is meant to handle).
    """
    from restai.database import open_db_wrapper as _open_db

    db_local = _open_db()
    final_output = None
    completed = False
    try:
        try:
            async for chunk in generator:
                if isinstance(chunk, dict):
                    final_output = chunk
                    await resume_session.append("data: " + json.dumps(chunk) + "\n")
                    continue
                if isinstance(chunk, str) and chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk.replace("data: ", ""))
                        if "answer" in data and "type" in data:
                            final_output = data
                    except Exception:
                        pass
                await resume_session.append(chunk)
            completed = True
        except Exception as e:
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
            try:
                await resume_session.append("data: " + json.dumps({"text": err_output["answer"]}) + "\n\n")
                await resume_session.append("data: " + json.dumps(err_output) + "\n")
            except Exception:
                pass

        try:
            await resume_session.append("event: close\n\n")
        except Exception:
            pass
    finally:
        try:
            await resume_session.finish()
        except Exception:
            pass
        try:
            if final_output:
                if image and not final_output.get("image"):
                    final_output["image"] = image
                if attachments and not final_output.get("attachments"):
                    final_output["attachments"] = attachments
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                log_inference(
                    project, user, final_output, db_local,
                    latency_ms=latency_ms, system_prompt=system_prompt, context=context,
                )
            elif not completed:
                _log_inference_error(
                    project, user, db_local,
                    question=question, image=image, attachments=attachments,
                    status="error", error="Agent generator stopped before completion",
                    system_prompt=system_prompt, context=context, start_time=start_time,
                )
        except Exception:
            logging.exception("log_inference failed in _drain_generator_into_session")
        try:
            db_local.close()
        except Exception:
            pass


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
    chat_id: str = None,
) -> StreamingResponse:
    # Resume path: when a chat_id is set, the agent run is detached
    # from the HTTP request. A background task drains the generator
    # into a per-chat-id session buffer; the HTTP response is just a
    # subscriber. So if the client disconnects (tab hidden, network
    # drop, fetchEventSource reconnect), the agent keeps producing
    # into the buffer, and the next POST resumes from `Last-Event-ID`
    # without re-running the LLM or duplicating side-effects.
    if chat_id:
        import asyncio as _asyncio
        from restai import chat_resume as _resume
        resume_session, is_new = await _resume.get_or_create(chat_id)
        if is_new:
            task = _asyncio.create_task(_drain_generator_into_session(
                generator, resume_session,
                project=project, user=user,
                system_prompt=system_prompt, context=context,
                question=question, image=image, attachments=attachments,
                start_time=start_time,
            ))
            # Hold a strong ref on the session so asyncio doesn't GC the
            # task while it's running (the request task that spawned it
            # may already be torn down before the first chunk lands).
            resume_session.producer_task = task
        else:
            # Re-POST while a producer is already running — we don't
            # need a second producer, and we MUST close the generator
            # we were handed so its tools/llm coroutines unwind cleanly.
            try:
                await generator.aclose()
            except Exception:
                pass

        async def _subscribe():
            async for chunk in resume_session.subscribe(last_event_id=0):
                yield chunk
        return StreamingResponse(_subscribe(), media_type="text/event-stream")

    # Non-resume path (no chat_id): legacy direct streaming. Generator
    # is driven by the request itself; cancellation kills the agent.
    async def stream_with_logging():
        final_output = None
        completed = False
        try:
            try:
                async for chunk in generator:
                    if isinstance(chunk, dict):
                        final_output = chunk
                        yield "data: " + json.dumps(chunk) + "\n"
                        continue
                    if isinstance(chunk, str) and chunk.startswith("data: "):
                        try:
                            data = json.loads(chunk.replace("data: ", ""))
                            if "answer" in data and "type" in data:
                                final_output = data
                        except Exception:
                            pass
                    yield chunk
                completed = True
            except Exception as e:
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
                try:
                    yield "data: " + json.dumps({"text": err_output["answer"]}) + "\n\n"
                    yield "data: " + json.dumps(err_output) + "\n"
                except Exception:
                    pass

            try:
                yield "event: close\n\n"
            except Exception:
                pass
        finally:
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
        api_key_row = (
            db.db.query(ApiKeyDatabase).filter(ApiKeyDatabase.id == user.api_key_id).first()
            if getattr(user, "api_key_id", None) else None
        )
        enforce_cost_budgets(
            db, project=project, user=user,
            team=project.props.team, api_key_row=api_key_row,
        )
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
                    _image = chat_input.image
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
                chat_id=chat_input.id,
            )
        else:
            output_generator = proj_logic.chat(project, chat_input, user, db)
            async for line in output_generator:
                if not isinstance(line, dict):
                    continue
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                if _image and not line.get("image"):
                    line["image"] = _image
                if _attachments and not line.get("attachments"):
                    line["attachments"] = _attachments
                # A logging failure (e.g. an oversized column) must never turn
                # a successful answer into a 500 — swallow it, roll back the
                # poisoned transaction, and still return the answer.
                try:
                    log_inference(
                        project, user, line, db,
                        latency_ms=latency_ms, system_prompt=_sys, context=_ctx,
                    )
                except Exception:
                    logging.exception("log_inference failed in chat_main (non-streaming); returning answer anyway")
                    try:
                        db.db.rollback()
                    except Exception:
                        pass
                # RAG-only retrieval-event logging.
                if (
                    isinstance(line, dict)
                    and line.get("sources")
                    and project.props.type == "rag"
                ):
                    from restai.tools import log_retrieval_events
                    background_tasks.add_task(log_retrieval_events, project, line["sources"], db)
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


