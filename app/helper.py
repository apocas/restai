from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from app.database import DBWrapper
from app.project import Project
from app.projects.agent import Agent
from app.projects.inference import Inference
from app.projects.rag import RAG
from app.projects.ragsql import RAGSql
from app.projects.router import Router
from app.projects.vision import Vision
from app.models.models import QuestionModel, User, ChatModel
from app.brain import Brain
import requests
from fastapi import HTTPException, Request
import traceback
import re
import logging
import base64
from app.tools import log_inference
from app.config import LOG_LEVEL

from app.projects.base import ProjectBase

logging.basicConfig(level=LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)


async def chat_main(
        _: Request,
        brain: Brain,
        project: Project,
        chat_input: ChatModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    proj_logic: ProjectBase
    match project.model.type:
        case "rag":
            proj_logic = RAG(brain)
        case "router":
            proj_logic = Router(brain)
        case "inference":
            proj_logic = Inference(brain)
        case "agent":
            proj_logic = Agent(brain)
        case _:
            raise HTTPException(
                status_code=400, detail='{"error": "Invalid project type"}')

    if chat_input.stream:
        return StreamingResponse(proj_logic.chat(project, chat_input, user, db), media_type='text/event-stream')
    else:
        output = proj_logic.chat(project, chat_input, user, db)
        for line in output:
            background_tasks.add_task(log_inference, user, line, db)
            return line


async def question_main(
        request: Request,
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    match project.model.type:
        case "rag":
            cached = await process_cache(project, q_input)
            if cached:
                background_tasks.add_task(log_inference, user, cached, db)
                return cached
            return await question_rag(request, brain, project, q_input, user, db, background_tasks)
        case "inference":
            return await question_inference(brain, project, q_input, user, db, background_tasks)
        case "ragsql":
            return await question_query_sql(request, brain, project, q_input, user, db, background_tasks)
        case "router":
            return await question_router(request, brain, project, q_input, user, db, background_tasks)
        case "vision":
            return await question_vision(project, brain, q_input, user, db)
        case "agent":
            return await question_agent(brain, project, q_input, user, db, background_tasks)
        case _:
            raise HTTPException(
                status_code=400, detail='{"error": "Invalid project type"}')


async def question_rag(
        _: Request,
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    try:
        proj_logic = RAG(brain)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        if q_input.stream:
            return StreamingResponse(proj_logic.question(project, q_input, user, db), media_type='text/event-stream')
        else:
            output = proj_logic.question(project, q_input, user, db)
            for line in output:
                background_tasks.add_task(log_inference, user, line, db)
                return line
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def process_cache(project: Project, q_input: QuestionModel):
    output = {
        "question": q_input.question,
        "type": "question",
        "sources": [],
        "tokens": {
            "input": 0,
            "output": 0
        }
    }

    if project.cache:
        answer = project.cache.verify(q_input.question)
        if answer is not None:
            output.update({
                "answer": answer,
                "cached": True,
            })

            return output

    return None


async def question_router(
        request: Request,
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    try:
        projLogic = Router(brain)

        if project.model.type != "router":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for ROUTER projects."}')

        proj_dest_name = projLogic.question(project, q_input, user, db)
        proj_dest = brain.find_project(proj_dest_name, db)

        if proj_dest is None:
            raise HTTPException(
                status_code=404, detail='{"error": "No destination project found."}')
        else:
            return await question_main(request, brain, proj_dest, q_input, user, db, background_tasks)

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_inference(
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    try:
        proj_logic: Inference = Inference(brain)

        if project.model.type != "inference":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for INFERENCE projects."}')

        if q_input.stream:
            return StreamingResponse(proj_logic.question(project, q_input, user, db), media_type='text/event-stream')
        else:
            output = proj_logic.question(project, q_input, user, db)
            for line in output:
                background_tasks.add_task(log_inference, user, line, db)
                return line

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_agent(
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    try:
        projLogic = Agent(brain)

        output = projLogic.question(project, q_input, user, db)

        for line in output:
            background_tasks.add_task(log_inference, user, line, db)
            return line

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_query_sql(
        _: Request,
        brain: Brain,
        project: Project,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper,
        background_tasks: BackgroundTasks):
    try:
        projLogic = RAGSql(brain)

        if project.model.type != "ragsql":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAGSQL projects."}')

        output = projLogic.question(project, q_input, user, db)

        background_tasks.add_task(log_inference, user, output, db)

        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_vision(
        project: Project,
        brain: Brain,
        q_input: QuestionModel,
        user: User,
        db: DBWrapper):
    try:
        projLogic = Vision(brain)

        if project.model.type != "vision":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for VISION projects."}')

        if q_input.image:
            url_pattern = re.compile(
                r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(),]|%[0-9a-fA-F][0-9a-fA-F])+')
            is_url = re.match(url_pattern, q_input.image) is not None

            if is_url:
                response = requests.get(q_input.image)
                response.raise_for_status()
                image_data = response.content
                q_input.image = base64.b64encode(image_data).decode('utf-8')

        output = projLogic.question(
            project, q_input, user, db)

        if q_input.lite:
            del output["image"]

        # log_inference.info({"user": user.username, "project": projectName, "output": output})
        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
