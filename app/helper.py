from starlette.responses import StreamingResponse
from starlette.requests import Request
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from app.project import Project
from app.projects.agent import Agent
from app.projects.inference import Inference
from app.projects.rag import RAG
from app.projects.ragsql import RAGSql
from app.projects.router import Router
from app.projects.vision import Vision
from app.models.models import QuestionModel, User
from app.database import get_db
from app.brain import Brain
from app.auth import get_current_username_project
import requests
from fastapi import HTTPException, Request
import traceback
import re
import logging
import base64
from app.config import (
    LOG_LEVEL,
)
from app.tools import get_logger
from app.projects.base import Project as ProjectBase


logging.basicConfig(level=LOG_LEVEL)
logging.getLogger('passlib').setLevel(logging.ERROR)

logs_inference = get_logger("inference")


async def chat_main(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    
    projlogic: ProjectBase
    if project.model.type == "rag":
        projlogic = RAG(brain)
    elif project.model.type == "router":
        projlogic = Router(brain)
    elif project.model.type == "inference":
        projlogic = Inference(brain)

    if input.stream:
        return StreamingResponse(projlogic.chat(project, input, user, db), media_type='text/event-stream')
    else:
        output = projlogic.chat(project, input, user, db)
        for line in output:
            logs_inference.info({"user": user.username, "project": project.model.name, "output": line})
            return line
        
async def question_main(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    
    
    if project.model.type == "rag":
        cached = await processCache(project, input, db)
        if cached:
            logs_inference.info({"user": user.username, "project": project, "output": cached})
            return cached
        return await question_rag(request, brain, project, input, user, db)
    elif project.model.type == "inference":
        return await question_inference(request, brain, project, input, user, db)
    elif project.model.type == "ragsql":
        return await question_query_sql(request, brain, project, input, user, db)
    elif project.model.type == "router":
        return await question_router(request, brain, project, input, user, db)
    elif project.model.type == "vision":
        return await question_vision(project, brain, input, user, db)
    elif project.model.type == "agent":
        return await question_agent(request, brain, project, input, user, db)
    else:
        raise HTTPException(
            status_code=400, detail='{"error": "Invalid project type"}')

async def question_rag(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        projlogic = RAG(brain)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        if input.stream:
            return StreamingResponse(projlogic.question(project, input, user, db), media_type='text/event-stream')
        else:
            output = projlogic.question(project, input, user, db)
            for line in output:
                logs_inference.info({"user": user.username, "project": project.model.name, "output": line})
                return line
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))
        
async def processCache(project: Project, input: QuestionModel, db: Session): 
    output = {
      "question": input.question,
      "type": "question",
      "sources": [],
      "tokens": {
          "input": 0,
          "output": 0
      }
    }
    
    if project.cache:
        answer = project.cache.verify(input.question)
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
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        projLogic = Router(brain)

        if project.model.type != "router":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for ROUTER projects."}')

        projDestName = projLogic.question(project, input, user, db)
        projDest = brain.findProject(projDestName, db)
        
        if projDest is None:
            raise HTTPException(
                status_code=404, detail='{"error": "No destination project found."}')
        else:
            return await question_main(request, brain, projDest, input, user, db)

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_inference(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:                    
        projLogic = Inference(brain)

        if project.model.type != "inference":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for INFERENCE projects."}')

        if input.stream:
            return StreamingResponse(projLogic.question(project, input, user, db), media_type='text/event-stream')
        else:
            output = projLogic.question(project, input, user, db)
            for line in output:
                logs_inference.info({"user": user.username, "project": project.model.name, "output": line})
                return line

    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))

async def question_agent(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:      
        projLogic = Agent(brain)

        output = projLogic.question(project, input, user, db)
        
        for line in output:
            logs_inference.info({"user": user.username, "project": project.model.name, "output": line})
            return line
          
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))

async def question_query_sql(
        request: Request,
        brain: Brain,
        project: Project,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:      
        projLogic = RAGSql(brain)

        if project.model.type != "ragsql":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAGSQL projects."}')

        output = projLogic.question(project, input, user, db)

        logs_inference.info({"user": user.username, "project": project.model.name, "output": output})

        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_vision(
        project: Project,
        brain: Brain,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:            
        projLogic = Vision(brain)

        if project.model.type != "vision":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for VISION projects."}')

        if input.image:
            url_pattern = re.compile(
                r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
            is_url = re.match(url_pattern, input.image) is not None

            if is_url:
                response = requests.get(input.image)
                response.raise_for_status()
                image_data = response.content
                input.image = base64.b64encode(image_data).decode('utf-8')

        output = projLogic.question(
            project, input, user, db)
        
        if input.lite:
            del output["image"]

        #logs_inference.info({"user": user.username, "project": projectName, "output": output})
        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))