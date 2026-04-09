import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from restai.auth import get_current_username, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.direct_access import (
    log_direct_usage,
    resolve_team_for_llm,
    resolve_team_for_image_generator,
    resolve_team_for_audio_generator,
    resolve_team_for_embedding,
)
from restai.models.models import (
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionUsage,
    OpenAIChatMessage,
    OpenAIEmbeddingRequest,
    OpenAIEmbeddingResponse,
    OpenAIEmbeddingData,
    OpenAIEmbeddingUsage,
    User,
)
from restai.tools import tokens_from_string

from llama_index.core.base.llms.types import ChatMessage, MessageRole

router = APIRouter()

ROLE_MAP = {
    "system": MessageRole.SYSTEM,
    "user": MessageRole.USER,
    "assistant": MessageRole.ASSISTANT,
}


def _convert_messages(messages: list[OpenAIChatMessage]) -> list[ChatMessage]:
    return [
        ChatMessage(role=ROLE_MAP.get(m.role, MessageRole.USER), content=m.content)
        for m in messages
    ]


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: OpenAIChatCompletionRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible chat completions endpoint for direct LLM access."""
    check_not_restricted(user)
    team_id = resolve_team_for_llm(user, body.model, db_wrapper)

    llm_obj = request.app.state.brain.get_llm(body.model, db_wrapper)
    if llm_obj is None:
        raise HTTPException(status_code=404, detail=f"Model '{body.model}' not found")

    llm = llm_obj.llm
    llm_model = llm_obj.props

    # Apply optional parameters
    kwargs = {}
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    messages = _convert_messages(body.messages)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    if not body.stream:
        response = llm.chat(messages, **kwargs)
        answer = str(response.message.content)

        input_tokens = tokens_from_string(
            " ".join(m.content for m in body.messages)
        )
        output_tokens = tokens_from_string(answer)
        input_cost = (input_tokens * llm_model.input_cost) / 1_000_000
        output_cost = (output_tokens * llm_model.output_cost) / 1_000_000

        background_tasks.add_task(
            log_direct_usage,
            db_wrapper,
            user.id,
            team_id,
            body.model,
            body.messages[-1].content if body.messages else "",
            answer,
            input_tokens,
            output_tokens,
            input_cost,
            output_cost,
        )

        return OpenAIChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=body.model,
            choices=[
                OpenAIChatCompletionChoice(
                    index=0,
                    message=OpenAIChatMessage(role="assistant", content=answer),
                    finish_reason="stop",
                )
            ],
            usage=OpenAIChatCompletionUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )
    else:
        # Streaming response
        async def generate():
            full_answer = ""
            try:
                stream_response = llm.stream_chat(messages, **kwargs)
                for token_response in stream_response:
                    delta = token_response.delta
                    if delta:
                        full_answer += delta
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": body.model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"

                # Send final chunk
                final_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                # Log after stream completes
                input_tokens = tokens_from_string(
                    " ".join(m.content for m in body.messages)
                )
                output_tokens = tokens_from_string(full_answer)
                input_cost = (input_tokens * llm_model.input_cost) / 1_000_000
                output_cost = (output_tokens * llm_model.output_cost) / 1_000_000
                try:
                    log_direct_usage(
                        db_wrapper,
                        user.id,
                        team_id,
                        body.model,
                        body.messages[-1].content if body.messages else "",
                        full_answer,
                        input_tokens,
                        output_tokens,
                        input_cost,
                        output_cost,
                    )
                except Exception:
                    logging.exception("Failed to log direct access usage")

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


@router.post("/v1/embeddings")
async def embeddings(
    request: Request,
    body: OpenAIEmbeddingRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible embeddings endpoint."""
    check_not_restricted(user)
    team_id = resolve_team_for_embedding(user, body.model, db_wrapper)

    embedding_obj = request.app.state.brain.get_embedding(body.model, db_wrapper)
    if embedding_obj is None:
        raise HTTPException(status_code=404, detail=f"Embedding model '{body.model}' not found")

    texts = [body.input] if isinstance(body.input, str) else body.input

    results = embedding_obj.embedding.get_text_embedding_batch(texts)

    total_tokens = sum(tokens_from_string(t) for t in texts)

    background_tasks.add_task(
        log_direct_usage,
        db_wrapper, user.id, team_id, body.model,
        f"(embed {len(texts)} text(s))", "(embeddings generated)",
        total_tokens, 0, 0.0, 0.0,
    )

    return OpenAIEmbeddingResponse(
        model=body.model,
        data=[
            OpenAIEmbeddingData(embedding=emb, index=i)
            for i, emb in enumerate(results)
        ],
        usage=OpenAIEmbeddingUsage(
            prompt_tokens=total_tokens,
            total_tokens=total_tokens,
        ),
    )


@router.get("/direct/models")
async def list_accessible_models(
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all models/generators the user can access via direct endpoints."""
    import os

    if user.is_admin:
        # Admins see everything
        all_llms = db_wrapper.get_llms()
        llms = [{"name": l.name} for l in all_llms]

        all_embeddings = db_wrapper.get_embeddings()
        embeddings_list = [{"name": e.name, "dimension": e.dimension} for e in all_embeddings]

        image_generators = []
        audio_generators = []
        if hasattr(request.app.state.brain, "generators"):
            image_generators = [
                g.__module__.split("restai.image.workers.")[1]
                for g in request.app.state.brain.get_generators()
            ]
            if not user.is_private:
                if os.environ.get("OPENAI_API_KEY"):
                    image_generators.append("dalle")
                if os.environ.get("GOOGLE_API_KEY"):
                    image_generators.append("imagen")

        if hasattr(request.app.state.brain, "audio_generators"):
            audio_generators = [
                g.__module__.split("restai.audio.workers.")[1]
                for g in request.app.state.brain.get_audio_generators()
            ]

        return {
            "llms": llms,
            "embeddings": embeddings_list,
            "image_generators": image_generators,
            "audio_generators": audio_generators,
        }

    # Non-admin: aggregate from teams
    teams = db_wrapper.get_teams_for_user(user.id)
    llm_names = set()
    embedding_names = set()
    image_gen_names = set()
    audio_gen_names = set()

    for team in teams:
        for llm in team.llms:
            llm_names.add(llm.name)
        for emb in team.embeddings:
            embedding_names.add((emb.name, emb.dimension))
        for ig in team.image_generators:
            image_gen_names.add(ig.generator_name)
        for ag in team.audio_generators:
            audio_gen_names.add(ag.generator_name)

    return {
        "llms": [{"name": n} for n in sorted(llm_names)],
        "embeddings": [{"name": n, "dimension": d} for n, d in embedding_names],
        "image_generators": sorted(image_gen_names),
        "audio_generators": sorted(audio_gen_names),
    }
