from typing import Optional, AsyncGenerator, Any, Dict

from starlette.responses import StreamingResponse
from requests import Response
from fastapi import BackgroundTasks
from restai.database import DBWrapper
from restai.project import Project
from restai.projects.agent import Agent
from restai.projects.inference import Inference
from restai.projects.rag import RAG
from restai.projects.ragsql import RAGSql
from restai.projects.router import Router
from restai.models.models import QuestionModel, User, ChatModel
from restai.brain import Brain
import requests
from fastapi import HTTPException, Request
import traceback
import re
import logging
import base64
from restai.tools import log_inference
from restai.config import LOG_LEVEL
import json

from restai.projects.base import ProjectBase

logging.basicConfig(level=LOG_LEVEL)


def resolve_image(image: str) -> str:
    """If image is a URL, fetch it and return base64-encoded data. Otherwise return as-is."""
    url_pattern = re.compile(
        r"https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(),]|%[0-9a-fA-F][0-9a-fA-F])+"
    )
    if re.match(url_pattern, image):
        response = requests.get(image)
        response.raise_for_status()
        if response.content is None:
            raise ValueError("Content is null.")
        return base64.b64encode(response.content).decode("utf-8")
    return image


async def create_streaming_response_with_logging(
    generator,
    project: Project,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
) -> StreamingResponse:
    """
    Creates a streaming response with logging of the final output.

    Args:
        generator: The generator that yields streaming chunks
        project: The project
        user: The user
        db: The database wrapper
        background_tasks: Background tasks

    Returns:
        A StreamingResponse
    """

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
            background_tasks.add_task(log_inference, project, user, final_output, db)

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
):
    proj_logic: ProjectBase
    match project.props.type:
        case "rag":
            proj_logic = RAG(brain)
        case "router":
            proj_logic = Router(brain)
        case "inference":
            proj_logic = Inference(brain)
            if chat_input.image:
                chat_input.image = resolve_image(chat_input.image)
        case "agent":
            proj_logic = Agent(brain)
        case _:
            raise HTTPException(status_code=400, detail="Invalid project type")

    if chat_input.stream:
        return await create_streaming_response_with_logging(
            proj_logic.chat(project, chat_input, user, db),
            project,
            user,
            db,
            background_tasks,
        )
    else:
        # Handle the async generator for non-streaming case
        output_generator = proj_logic.chat(project, chat_input, user, db)
        async for line in output_generator:
            background_tasks.add_task(log_inference, project, user, line, db)
            return line


async def question_main(
    request: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
):
    match project.props.type:
        case "rag":
            cached = await process_cache(project, q_input)
            if cached:
                background_tasks.add_task(log_inference, project, user, cached, db)
                return cached
            return await question_rag(
                request, brain, project, q_input, user, db, background_tasks
            )
        case "inference":
            return await question_inference(
                brain, project, q_input, user, db, background_tasks
            )
        case "ragsql":
            return await question_query_sql(
                request, brain, project, q_input, user, db, background_tasks
            )
        case "router":
            return await question_router(
                request, brain, project, q_input, user, db, background_tasks
            )
        case "agent":
            return await question_agent(
                brain, project, q_input, user, db, background_tasks
            )
        case _:
            raise HTTPException(status_code=400, detail="Invalid project type")


async def question_rag(
    _: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
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
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                background_tasks.add_task(log_inference, project, user, line, db)
                return line
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


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


async def question_router(
    request: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
):
    try:
        projLogic = Router(brain)

        if project.props.type != "router":
            raise HTTPException(
                status_code=400, detail="Only available for ROUTER projects."
            )

        proj_dest_name: str = projLogic.question(project, q_input, user, db)
        proj_dest: Optional[Project] = brain.find_project(proj_dest_name, db)

        if proj_dest is None:
            raise HTTPException(status_code=404, detail="No destination project found.")
        else:
            return await question_main(
                request, brain, proj_dest, q_input, user, db, background_tasks
            )

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


async def question_inference(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
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
            )
        else:
            output_generator = proj_logic.question(project, q_input, user, db)
            async for line in output_generator:
                background_tasks.add_task(log_inference, project, user, line, db)
                return line

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


async def question_agent(
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
):
    try:
        projLogic: Agent = Agent(brain)

        if project.props.type != "agent":
            raise HTTPException(
                status_code=400, detail="Only available for AGENT projects."
            )

        if q_input.stream:
            return await create_streaming_response_with_logging(
                projLogic.question(project, q_input, user, db),
                project,
                user,
                db,
                background_tasks,
            )
        else:
            output_generator = projLogic.question(project, q_input, user, db)
            async for line in output_generator:
                background_tasks.add_task(log_inference, project, user, line, db)
                return line

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


async def question_query_sql(
    _: Request,
    brain: Brain,
    project: Project,
    q_input: QuestionModel,
    user: User,
    db: DBWrapper,
    background_tasks: BackgroundTasks,
):
    try:
        projLogic: RAGSql = RAGSql(brain)

        if project.props.type != "ragsql":
            raise HTTPException(
                status_code=400, detail="Only available for RAGSQL projects."
            )

        output = projLogic.question(project, q_input, user, db)

        background_tasks.add_task(log_inference, project, user, output, db)

        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


