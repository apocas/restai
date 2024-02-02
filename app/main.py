import copy
import uuid
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.requests import Request
from unidecode import unidecode
from sqlalchemy.orm import Session
from fastapi import Depends, FastAPI, HTTPException
from modules.loaders import LOADERS
from modules.llms import LLMS
from modules.embeddings import EMBEDDINGS
from llama_index import Document
from app.vectordb import vector_delete_source, vector_find_source, vector_info, vector_list_source, vector_reset, vector_save, vector_list, vector_find_id
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.models import ChatResponse, FindModel, InferenceModel, InferenceResponse, IngestResponse, ProjectInfo, ProjectModel, ProjectModelUpdate, QuestionModel, ChatModel, QuestionResponse, RagSqlModel, RagSqlResponse, TextIngestModel, URLIngestModel, User, UserCreate, UserUpdate, VisionModel, VisionResponse
from llama_index.retrievers import VectorIndexRetriever
from app.loaders.url import SeleniumWebReader
import urllib.parse
from app.database import dbc, get_db
from app.brain import Brain
from app.auth import create_access_token, get_current_username, get_current_username_admin, get_current_username_project, get_current_username_user
import requests
from llama_index.postprocessor import SimilarityPostprocessor
from llama_index.query_engine import RetrieverQueryEngine
import httpx
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
import traceback
from tempfile import NamedTemporaryFile
import re
from pathlib import Path
import jwt
import os
import logging
import json
import base64
from datetime import timedelta
import secrets
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from app.tools import FindFileLoader, IndexDocuments, ExtractKeywordsForMetadata, get_logger, loadEnvVars

load_dotenv()
loadEnvVars()


logging.basicConfig(level=os.environ["LOG_LEVEL"])

app = FastAPI(
    title="RestAI",
    description="Modular REST API bootstrap on top of LangChain. Create embeddings associated with a project tenant and interact using a LLM. RAG as a service.",
    version="4.0.0",
    contact={
        "name": "Pedro Dias",
        "url": "https://github.com/apocas/restai",
        "email": "petermdias@gmail.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

if "RESTAI_DEV" in os.environ:
    print("Running in development mode!")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

brain = Brain()
logs_inference = get_logger("inference")


@app.get("/")
async def get(request: Request):
    return "RESTAI, so many 'A's and 'I's, so little time..."


@app.get("/info")
async def get_info(user: User = Depends(get_current_username)):
    output = {
        "version": app.version,
        "loaders": list(LOADERS.keys()),
        "embeddings": [],
        "llms": []
    }

    for llm in LLMS:
        llm_class, llm_args, prompt, privacy, description, typel, llm_node = LLMS[llm]
        output["llms"].append({
            "name": llm,
            "prompt": prompt,
            "privacy": privacy,
            "description": description,
            "type": typel,
            "node": llm_node
        })

    for embedding in EMBEDDINGS:
        embedding_class, embedding_args, privacy, description = EMBEDDINGS[embedding]
        output["embeddings"].append({
            "name": embedding,
            "privacy": privacy,
            "description": description
        })
    return output


@app.get("/sso")
async def get_sso(request: Request, db: Session = Depends(get_db)):
    params = dict(request.query_params)

    if "jwt" not in params:
        raise HTTPException(
            status_code=400, detail="Missing JWT token")

    try:
        data = jwt.decode(params["jwt"], os.environ["RESTAI_SSO_SECRET"], algorithms=[
            os.environ.get("RESTAI_SSO_ALG") or "HS512"])
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    user = dbc.get_user_by_username(db, data["preferred_username"])
    if user is None:
        user = dbc.create_user(db,
                               data["preferred_username"], None,
                               False,
                               False)
        user.sso = os.environ.get("RESTAI_SSO_CALLBACK")
        db.commit()

    new_token = create_access_token(
        data={"username": user.username}, expires_delta=timedelta(minutes=480))

    response = RedirectResponse("./admin")
    response.set_cookie(key="restai_token", value=new_token, samesite="strict", expires=28800)

    return response


@app.get("/users/{username}/sso")
async def get_user(username: str, db: Session = Depends(get_db)):
    try:
        user = dbc.get_user_by_username(db, username)
        if user is None:
            return {"sso": os.environ.get("RESTAI_SSO_CALLBACK")}
        return {"sso": user.sso}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.get("/users/{username}", response_model=User)
async def get_user(username: str, user: User = Depends(get_current_username_user), db: Session = Depends(get_db)):
    try:
        user_model = User.model_validate(
            dbc.get_user_by_username(db, username))
        user_model_copy = copy.deepcopy(user_model)
        user_model_copy.api_key = None
        return user_model
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.post("/users/{username}/apikey")
async def get_user(username: str, user: User = Depends(get_current_username_user), db: Session = Depends(get_db)):
    try:
        useru = dbc.get_user_by_username(db, username)
        if useru is None:
            raise Exception("User not found")

        apikey = uuid.uuid4().hex + secrets.token_urlsafe(32)
        dbc.update_user(db, useru, UserUpdate(api_key=apikey))
        return {"api_key": apikey}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.get("/users", response_model=list[User])
async def get_users(
        user: User = Depends(get_current_username_admin),
        db: Session = Depends(get_db)):
    users = dbc.get_users(db)
    return users


@app.post("/users", response_model=User)
async def create_user(userc: UserCreate,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        userc.username = unidecode(
            userc.username.strip().lower().replace(" ", "."))
        userc.username = re.sub(r'[^\w\-.]+', '', userc.username)

        user = dbc.create_user(db,
                               userc.username,
                               userc.password,
                               userc.is_admin,
                               userc.is_private)
        return user
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail='Failed to create user ' + userc.username)


@app.patch("/users/{username}", response_model=User)
async def update_user(
        username: str,
        userc: UserUpdate,
        user: User = Depends(get_current_username_user),
        db: Session = Depends(get_db)):
    try:
        useru = dbc.get_user_by_username(db, username)
        if useru is None:
            raise Exception("User not found")

        if not user.is_admin and userc.is_admin is True:
            raise Exception("Insuficient permissions")

        dbc.update_user(db, useru, userc)

        if userc.projects is not None:
            dbc.delete_userprojects(db, useru)
            for project in userc.projects:
                projectdb = dbc.get_project_by_name(db, project)
                if projectdb is None:
                    raise Exception("Project not found")
                dbc.add_userproject(db, useru, project, projectdb.id)
        return useru
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.delete("/users/{username}")
async def delete_user(username: str,
                      user: User = Depends(get_current_username_admin),
                      db: Session = Depends(get_db)):
    try:
        user = dbc.get_user_by_username(db, username)
        if user is None:
            raise Exception("User not found")
        dbc.delete_user(db, user)
        return {"deleted": username}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.get("/projects", response_model=list[ProjectModel])
async def get_projects(request: Request, user: User = Depends(get_current_username), db: Session = Depends(get_db)):
    if user.is_admin:
        projects = dbc.get_projects(db)
    else:
        projects = []
        for project in user.projects:
            for p in dbc.get_projects(db):
                if project.name == p.name:
                    projects.append(p)

    for project in projects:
        llm_class, llm_args, prompt, llm_privacy, description, llm_type, llm_node = LLMS[
            project.llm]
        project.llm_type = llm_type
        project.llm_privacy = llm_privacy

    return projects


@app.get("/projects/{projectName}", response_model=ProjectInfo)
async def get_project(projectName: str, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        llm_class, llm_args, prompt, llm_privacy, description, llm_type, llm_node = LLMS[
            project.model.llm]

        chunks = vector_info(project)

        output = ProjectInfo(
            name=project.model.name,
            embeddings=project.model.embeddings,
            llm=project.model.llm,
            llm_type=llm_type,
            llm_privacy=llm_privacy,
            system=project.model.system,
            sandboxed=project.model.sandboxed,
            censorship=project.model.censorship,
            score=project.model.score,
            k=project.model.k,
            vectorstore=project.model.vectorstore,
            type=project.model.type,
            connection=project.model.connection,)
        output.chunks = chunks

        if output.connection:
            output.connection = re.sub(
                r'(?<=://).+?(?=@)', "xxxx:xxxx", output.connection)

        return output
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.delete("/projects/{projectName}")
async def delete_project(projectName: str, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    try:
        if brain.deleteProject(projectName, db):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.patch("/projects/{projectName}")
async def edit_project(projectName: str, projectModelUpdate: ProjectModelUpdate, user: User = Depends(get_current_username_project), db: Session = Depends(get_db)):
    if projectModelUpdate.llm is not None and projectModelUpdate.llm not in LLMS:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    if user.is_private:
        llm_class, llm_args, prompt, privacy, description, type, llm_node = LLMS[
            projectModelUpdate.llm]
        if privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User not allowed to use public models')

    try:
        if brain.editProject(projectName, projectModelUpdate, db):
            return {"project": projectName}
        else:
            raise HTTPException(
                status_code=404, detail='Project not found')
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects")
async def create_project(projectModel: ProjectModel, user: User = Depends(get_current_username), db: Session = Depends(get_db)):
    projectModel.name = unidecode(
        projectModel.name.strip().lower().replace(" ", "_"))
    projectModel.name = re.sub(r'[^\w\-.]+', '', projectModel.name)

    if projectModel.type == "rag" and projectModel.embeddings not in EMBEDDINGS:
        raise HTTPException(
            status_code=404,
            detail='Embeddings not found')
    if projectModel.llm not in LLMS:
        raise HTTPException(
            status_code=404,
            detail='LLM not found')

    proj = brain.findProject(projectModel.name, db)
    if proj is not None:
        raise HTTPException(
            status_code=403,
            detail='Project already exists')

    if user.is_private:
        llm_class, llm_args, prompt, privacy, description, type, llm_node = LLMS[
            projectModel.llm]
        if privacy != "private":
            raise HTTPException(
                status_code=403,
                detail='User allowed to private models only')

        if projectModel.type == "rag":
            embedding_class, embedding_args, embedding_privacy, embedding_description = EMBEDDINGS[
                projectModel.embeddings]
            if embedding_privacy != "private":
                raise HTTPException(
                    status_code=403,
                    detail='User allowed to private models only')

    try:
        project = brain.createProject(projectModel, db)
        projectdb = dbc.get_project_by_name(db, project.model.name)
        dbc.add_userproject(db, user, projectModel.name, projectdb.id)
        return {"project": projectModel.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/reset")
async def reset_embeddings(
        projectName: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        vector_reset(brain, project)

        return {"project": project.model.name}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=404, detail=str(e))


@app.post("/projects/{projectName}/embeddings/search")
async def find_embedding(projectName: str, embedding: FindModel,
                         user: User = Depends(get_current_username_project),
                         db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    output = []

    if (embedding.text):
        k = embedding.k or project.model.k or 2

        if (embedding.score != None):
            threshold = embedding.score
        else:
            threshold = embedding.score or project.model.score or 0.2

        retriever = VectorIndexRetriever(
            index=project.db,
            similarity_top_k=k,
        )

        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=[SimilarityPostprocessor(
                similarity_cutoff=threshold)],
            response_mode="no_text"
        )

        response = query_engine.query(embedding.text)

        for node in response.source_nodes:
            output.append(
                {"source": node.metadata["source"], "score": node.score, "id": node.node_id})

    elif (embedding.source):
        output = vector_list_source(project, embedding.source)

    return {"embeddings": output}


@app.get("/projects/{projectName}/embeddings/source/{source}")
async def get_embedding(projectName: str, source: str,
                        user: User = Depends(get_current_username_project),
                        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    docs = vector_find_source(
        project, base64.b64decode(source).decode('utf-8'))

    if (len(docs['ids']) == 0):
        return {"ids": []}
    else:
        return docs


@app.get("/projects/{projectName}/embeddings/id/{id}")
async def get_embedding(projectName: str, id: str,
                        user: User = Depends(get_current_username_project),
                        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    chunk = vector_find_id(project, id)
    return chunk


@app.post("/projects/{projectName}/embeddings/ingest/text", response_model=IngestResponse)
async def ingest_text(projectName: str, ingest: TextIngestModel,
                      user: User = Depends(get_current_username_project),
                      db: Session = Depends(get_db)):

    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        metadata = {"source": ingest.source}
        documents = [Document(text=ingest.text, metadata=metadata)]

        if ingest.keywords and len(ingest.keywords) > 0:
            for document in documents:
                document.metadata["keywords"] = ", ".join(ingest.keywords)
        else:
            documents = ExtractKeywordsForMetadata(documents)

        # for document in documents:
        #    document.text = document.text.decode('utf-8')

        nchunks = IndexDocuments(
            brain, project, documents, ingest.splitter, ingest.chunks)
        vector_save(project)

        return {"source": ingest.source, "documents": len(documents), "chunks": nchunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/ingest/url", response_model=IngestResponse)
async def ingest_url(projectName: str, ingest: URLIngestModel,
                     user: User = Depends(get_current_username_project),
                     db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        urls = vector_list(project)["embeddings"]
        if (ingest.url in urls):
            raise Exception("URL already ingested. Delete first.")

        loader = SeleniumWebReader()

        documents = loader.load_data(urls=[ingest.url])
        documents = ExtractKeywordsForMetadata(documents)

        nchunks = IndexDocuments(
            brain, project, documents, ingest.splitter, ingest.chunks)
        vector_save(project)

        return {"source": ingest.url, "documents": len(documents), "chunks": nchunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/embeddings/ingest/upload", response_model=IngestResponse)
async def ingest_file(
        projectName: str,
        file: UploadFile,
        options: str = Form("{}"),
        chunks: int = Form(256),
        splitter: str = Form("sentence"),
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        _, ext = os.path.splitext(file.filename or '')
        temp = NamedTemporaryFile(delete=False, suffix=ext)
        try:
            contents = file.file.read()
            with temp as f:
                f.write(contents)
        except Exception:
            raise HTTPException(
                status_code=500, detail='{"error": "Error while saving file."}')
        finally:
            file.file.close()

        opts = json.loads(urllib.parse.unquote(options))

        loader = FindFileLoader(ext, opts)
        documents = loader.load_data(file=Path(temp.name))

        for document in documents:
            if "filename" in document.metadata:
                del document.metadata["filename"]
            document.metadata["source"] = file.filename

        documents = ExtractKeywordsForMetadata(documents)

        nchunks = IndexDocuments(brain, project, documents, splitter, chunks)
        vector_save(project)

        return {
            "source": file.filename,
            "documents": len(documents), "chunks": nchunks}
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)

        raise HTTPException(
            status_code=500, detail=str(e))


@app.get('/projects/{projectName}/embeddings')
async def get_embeddings(
        projectName: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    output = vector_list(project)

    return output


@app.delete('/projects/{projectName}/embeddings/{source}')
async def delete_embedding(
        projectName: str,
        source: str,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    project = brain.findProject(projectName, db)

    if project.model.type != "rag":
        raise HTTPException(
            status_code=400, detail='{"error": "Only available for RAG projects."}')

    ids = vector_delete_source(
        project, base64.b64decode(source).decode('utf-8'))

    return {"deleted": len(ids)}


@app.post("/projects/{projectName}/vision", response_model=VisionResponse)
async def vision_query(
        projectName: str,
        input: VisionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):

    try:
        project = brain.findProject(projectName, db)

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

        answer, docs, image = brain.entryVision(
            projectName, input, user.is_private, db)

        output = {
            "question": input.question,
            "answer": answer,
            "image": image,
            "sources": docs,
            "type": "vision"
        }

        output_copy = dict(output)
        output_copy["image"] = "..."
        logs_inference.info(
            {"user": user.username, "project": projectName, "output": output_copy})

        return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_query(
        request: Request,
        projectName: str,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        llm_class, llm_args, llm_prompt, llm_privacy, llm_description, llm_type, llm_node = LLMS[
            project.model.llm]
        if llm_node != "node1" and llm_node != os.environ["RESTAI_NODE"]:
            client = httpx.AsyncClient(
                base_url="http://" + llm_node + os.environ["RESTAI_HOST"] + "/", timeout=120.0)
            url = httpx.URL(path=request.url.path.lstrip("/"),
                            query=request.url.query.encode("utf-8"))
            rp_req = client.build_request(request.method, url,
                                          headers=request.headers.raw,
                                          content=await request.body())
            rp_req.headers["host"] = llm_node + os.environ["RESTAI_HOST"]
            rp_resp = await client.send(rp_req, stream=True)
            return StreamingResponse(
                rp_resp.aiter_raw(),
                status_code=rp_resp.status_code,
                headers=rp_resp.headers,
                background=BackgroundTask(rp_resp.aclose),
            )
        else:
            output, censored = brain.entryQuestion(projectName, input, db)

            logs_inference.info(
                {"user": user.username, "project": projectName, "output": output})

            return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))

@app.post("/projects/{projectName}/question", response_model=QuestionResponse)
async def question_query_endpoint(
        request: Request,
        projectName: str,
        input: QuestionModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)
        if project.model.type == "rag":
            return await question_query(request, projectName, input, user, db)
        elif project.model.type == "inference":
            return await question_inference(request, projectName, InferenceModel(question=input.question, system=input.system), user, db)
        else:
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG and INFERENCE projects."}')
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/chat", response_model=ChatResponse)
async def chat_query(
        request: Request,
        projectName: str,
        input: ChatModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "rag":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAG projects."}')

        llm_class, llm_args, llm_prompt, llm_privacy, llm_description, llm_type, llm_node = LLMS[
            project.model.llm]
        if llm_node != "node1" and llm_node != os.environ["RESTAI_NODE"]:
            client = httpx.AsyncClient(
                base_url="http://" + llm_node + os.environ["RESTAI_HOST"] + "/", timeout=120.0)
            url = httpx.URL(path=request.url.path.lstrip("/"),
                            query=request.url.query.encode("utf-8"))
            rp_req = client.build_request(request.method, url,
                                          headers=request.headers.raw,
                                          content=await request.body())
            rp_req.headers["host"] = llm_node + os.environ["RESTAI_HOST"]
            rp_resp = await client.send(rp_req, stream=True)
            return StreamingResponse(
                rp_resp.aiter_raw(),
                status_code=rp_resp.status_code,
                headers=rp_resp.headers,
                background=BackgroundTask(rp_resp.aclose),
            )
        else:
            output, censored = brain.entryChat(projectName, input, db)

            logs_inference.info(
                {"user": user.username, "project": projectName, "output": output})

            return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))



@app.post("/projects/{projectName}/inference", response_model=InferenceResponse)
async def question_inference_endpoint(
        request: Request,
        projectName: str,
        input: InferenceModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "inference":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for INFERENCE projects."}')
        
        return await question_inference(request, projectName, input, user, db)
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


async def question_inference(
        request: Request,
        projectName: str,
        input: InferenceModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "inference":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for INFERENCE projects."}')

        llm_class, llm_args, llm_prompt, llm_privacy, llm_description, llm_type, llm_node = LLMS[
            project.model.llm]
        if llm_node != "node1" and llm_node != os.environ["RESTAI_NODE"]:
            client = httpx.AsyncClient(
                base_url="http://" + llm_node + os.environ["RESTAI_HOST"] + "/", timeout=120.0)
            url = httpx.URL(path=request.url.path.lstrip("/"),
                            query=request.url.query.encode("utf-8"))
            rp_req = client.build_request(request.method, url,
                                          headers=request.headers.raw,
                                          content=await request.body())
            rp_req.headers["host"] = llm_node + os.environ["RESTAI_HOST"]
            rp_resp = await client.send(rp_req, stream=True)
            return StreamingResponse(
                rp_resp.aiter_raw(),
                status_code=rp_resp.status_code,
                headers=rp_resp.headers,
                background=BackgroundTask(rp_resp.aclose),
            )
        else:
            output = brain.inference(projectName, input, db)

            logs_inference.info(
                {"user": user.username, "project": projectName, "output": output})

            return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))


@app.post("/projects/{projectName}/questionsql", response_model=RagSqlResponse)
async def question_query_sql(
        request: Request,
        projectName: str,
        input: RagSqlModel,
        user: User = Depends(get_current_username_project),
        db: Session = Depends(get_db)):
    try:
        project = brain.findProject(projectName, db)

        if project.model.type != "ragsql":
            raise HTTPException(
                status_code=400, detail='{"error": "Only available for RAGSQL projects."}')

        llm_class, llm_args, llm_prompt, llm_privacy, llm_description, llm_type, llm_node = LLMS[
            project.model.llm]
        if llm_node != "node1" and llm_node != os.environ["RESTAI_NODE"]:
            client = httpx.AsyncClient(
                base_url="http://" + llm_node + os.environ["RESTAI_HOST"] + "/", timeout=120.0)
            url = httpx.URL(path=request.url.path.lstrip("/"),
                            query=request.url.query.encode("utf-8"))
            rp_req = client.build_request(request.method, url,
                                          headers=request.headers.raw,
                                          content=await request.body())
            rp_req.headers["host"] = llm_node + os.environ["RESTAI_HOST"]
            rp_resp = await client.send(rp_req, stream=True)
            return StreamingResponse(
                rp_resp.aiter_raw(),
                status_code=rp_resp.status_code,
                headers=rp_resp.headers,
                background=BackgroundTask(rp_resp.aclose),
            )
        else:
            output = brain.ragSQL(projectName, input, db)

            logs_inference.info(
                {"user": user.username, "project": projectName, "output": output})

            return output
    except Exception as e:
        try:
            brain.semaphore.release()
        except ValueError:
            pass
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, detail=str(e))

try:
    app.mount("/admin/", StaticFiles(directory="frontend/html/",
              html=True), name="static_admin")
    app.mount(
        "/admin/static/js",
        StaticFiles(
            directory="frontend/html/static/js"),
        name="static_js")
    app.mount(
        "/admin/static/css",
        StaticFiles(
            directory="frontend/html/static/css"),
        name="static_css")
    app.mount(
        "/admin/static/media",
        StaticFiles(
            directory="frontend/html/static/media"),
        name="static_media")
except BaseException:
    print("Admin interface not available. Did you run 'make frontend'?")
