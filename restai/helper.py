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
from restai.projects.agent2 import Agent2
from restai.projects.block import Block
from restai.projects.inference import Inference
from restai.projects.rag import RAG
from restai.models.models import QuestionModel, User, ChatModel
from restai.brain import Brain
import requests
from fastapi import HTTPException, Request
import re
import logging
import base64
from restai.tools import log_inference
from restai.config import LOG_LEVEL
import json

from restai.projects.base import ProjectBase
from restai.budget import check_budget, check_rate_limit

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


async def create_streaming_response_with_logging(
    generator,
    project: Project,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
) -> StreamingResponse:

    async def stream_with_logging():
        final_output = None

        async for chunk in generator:
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    data = json.loads(chunk.replace("data: ", ""))
                    if "answer" in data and "type" in data:
                        final_output = data
                except:
                    pass
            yield chunk

        if final_output:
            latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
            background_tasks.add_task(log_inference, project, user, final_output, db, latency_ms=latency_ms)

    return StreamingResponse(
        stream_with_logging(),
        media_type="text/event-stream",
    )


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
    check_budget(project, db)
    check_rate_limit(project, db)

    proj_logic: ProjectBase
    match project.props.type:
        case "rag":
            proj_logic = RAG(brain)
        case "inference":
            proj_logic = Inference(brain)
            if chat_input.image:
                chat_input.image = resolve_image(chat_input.image)
        case "agent":
            proj_logic = Agent(brain)
        case "agent2":
            proj_logic = Agent2(brain)
        case "block":
            proj_logic = Block(brain)
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
        )
    else:
        output_generator = proj_logic.chat(project, chat_input, user, db)
        async for line in output_generator:
            latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
            background_tasks.add_task(log_inference, project, user, line, db, latency_ms=latency_ms)
            return line


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
    check_budget(project, db)
    check_rate_limit(project, db)

    # Check cache for all project types
    cached = await process_cache(project, q_input)
    if cached:
        latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
        background_tasks.add_task(log_inference, project, user, cached, db, latency_ms=latency_ms)
        return cached

    result = None
    match project.props.type:
        case "rag":
            result = await question_rag(
                request, brain, project, q_input, user, db, background_tasks, start_time
            )
        case "inference":
            result = await question_inference(
                brain, project, q_input, user, db, background_tasks, start_time
            )
        case "agent":
            result = await question_agent(
                brain, project, q_input, user, db, background_tasks, start_time
            )
        case "agent2":
            result = await question_agent2(
                brain, project, q_input, user, db, background_tasks, start_time
            )
        case "block":
            result = await question_block(
                brain, project, q_input, user, db, background_tasks, start_time
            )
        case _:
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
):
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
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                background_tasks.add_task(log_inference, project, user, line, db, latency_ms=latency_ms)
                return line
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
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


async def question_inference(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    try:
        proj_logic: Inference = Inference(brain)

        if project.props.type != "inference":
            raise HTTPException(
                status_code=400, detail="Only available for INFERENCE projects."
            )

        if q_input.image:
            q_input.image = resolve_image(q_input.image)

        if q_input.stream:
            return await create_streaming_response_with_logging(
                proj_logic.question(project, q_input, user, db),
                project,
                user,
                db,
                background_tasks,
                start_time=start_time,
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                background_tasks.add_task(log_inference, project, user, line, db, latency_ms=latency_ms)
                return line

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


async def _question_agent_like(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float,
    *,
    logic_cls: type[ProjectBase],
    expected_type: str,
):
    try:
        proj_logic = logic_cls(brain)

        if project.props.type != expected_type:
            raise HTTPException(
                status_code=400,
                detail=f"Only available for {expected_type.upper()} projects.",
            )

        if q_input.stream:
            return await create_streaming_response_with_logging(
                proj_logic.question(project, q_input, user, db),
                project,
                user,
                db,
                background_tasks,
                start_time=start_time,
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
                background_tasks.add_task(log_inference, project, user, line, db, latency_ms=latency_ms)
                return line

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


async def question_agent(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    return await _question_agent_like(
        brain, project, q_input, user, db, background_tasks, start_time,
        logic_cls=Agent, expected_type="agent",
    )


async def question_agent2(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    return await _question_agent_like(
        brain, project, q_input, user, db, background_tasks, start_time,
        logic_cls=Agent2, expected_type="agent2",
    )


async def question_block(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
    start_time: float = None,
):
    try:
        proj_logic = Block(brain)

        if project.props.type != "block":
            raise HTTPException(
                status_code=400, detail="Only available for BLOCK projects."
            )

        if q_input.image:
            q_input.image = resolve_image(q_input.image)

        output_generator = proj_logic.question(project, q_input, user, db)
        async for line in output_generator:
            latency_ms = int((time.perf_counter() - start_time) * 1000) if start_time else None
            background_tasks.add_task(log_inference, project, user, line, db, latency_ms=latency_ms)
            return line

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Internal server error")


