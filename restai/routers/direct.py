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
    OpenAIToolCall,
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
    "tool": MessageRole.TOOL,
}

# Parameters forwarded directly to the LLM provider as kwargs
_FORWARD_PARAMS = (
    "temperature", "top_p", "frequency_penalty", "presence_penalty",
    "stop", "seed", "response_format", "logprobs", "top_logprobs",
)


def _convert_messages(messages: list[OpenAIChatMessage]) -> list[ChatMessage]:
    result = []
    for m in messages:
        additional_kwargs = {}
        if m.tool_call_id:
            additional_kwargs["tool_call_id"] = m.tool_call_id
        if m.name:
            additional_kwargs["name"] = m.name
        if m.tool_calls:
            additional_kwargs["tool_calls"] = [tc.model_dump() for tc in m.tool_calls]
        result.append(ChatMessage(
            role=ROLE_MAP.get(m.role, MessageRole.USER),
            content=m.content or "",
            additional_kwargs=additional_kwargs if additional_kwargs else {},
        ))
    return result


def _build_kwargs(body: OpenAIChatCompletionRequest) -> dict:
    """Build kwargs dict from request params to forward to the LLM."""
    kwargs = {}
    for param in _FORWARD_PARAMS:
        val = getattr(body, param, None)
        if val is not None:
            kwargs[param] = val
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens
    # Tool calling
    if body.tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.function.name,
                    "description": t.function.description or "",
                    "parameters": t.function.parameters or {"type": "object", "properties": {}},
                },
            }
            for t in body.tools
        ]
        if body.tool_choice is not None:
            kwargs["tool_choice"] = body.tool_choice
    return kwargs


def _extract_finish_reason(response) -> str:
    """Extract finish_reason from LlamaIndex response, falling back to 'stop'."""
    if hasattr(response, "raw") and response.raw:
        try:
            return response.raw.choices[0].finish_reason or "stop"
        except (AttributeError, IndexError, TypeError):
            pass
    # Check for tool calls in additional_kwargs
    if hasattr(response, "message") and hasattr(response.message, "additional_kwargs"):
        if response.message.additional_kwargs.get("tool_calls"):
            return "tool_calls"
    return "stop"


def _extract_tool_calls(response) -> Optional[list[dict]]:
    """Extract tool_calls from LlamaIndex response if present."""
    if not hasattr(response, "message") or not hasattr(response.message, "additional_kwargs"):
        return None
    raw_calls = response.message.additional_kwargs.get("tool_calls")
    if not raw_calls:
        return None
    result = []
    for tc in raw_calls:
        # Handle both dict and object forms
        if isinstance(tc, dict):
            func = tc.get("function", {})
            result.append({
                "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", "{}"),
                },
            })
        else:
            # Object with attributes (e.g. openai ChatCompletionMessageToolCall)
            result.append({
                "id": getattr(tc, "id", f"call_{uuid.uuid4().hex[:8]}"),
                "type": "function",
                "function": {
                    "name": getattr(tc.function, "name", ""),
                    "arguments": getattr(tc.function, "arguments", "{}"),
                },
            })
    return result


def _build_response_message(response, tool_calls: Optional[list[dict]]) -> OpenAIChatMessage:
    """Build the response message, including tool_calls if present."""
    content = str(response.message.content) if response.message.content else None
    tc_models = None
    if tool_calls:
        tc_models = [
            OpenAIToolCall(id=tc["id"], type=tc["type"], function=tc["function"])
            for tc in tool_calls
        ]
    return OpenAIChatMessage(role="assistant", content=content, tool_calls=tc_models)


def _system_fingerprint() -> str:
    try:
        from importlib.metadata import version
        return f"restai-{version('restai')}"
    except Exception:
        return "restai"


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

    kwargs = _build_kwargs(body)
    messages = _convert_messages(body.messages)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    fingerprint = _system_fingerprint()
    n = body.n or 1

    if not body.stream:
        choices = []
        total_input_tokens = 0
        total_output_tokens = 0

        for i in range(n):
            response = llm.chat(messages, **kwargs)
            tool_calls = _extract_tool_calls(response)
            finish_reason = _extract_finish_reason(response)
            msg = _build_response_message(response, tool_calls)

            answer = msg.content or ""
            input_tokens = tokens_from_string(" ".join(m.content or "" for m in body.messages))
            output_tokens = tokens_from_string(answer)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            choices.append(
                OpenAIChatCompletionChoice(
                    index=i,
                    message=msg,
                    finish_reason=finish_reason,
                )
            )

        input_cost = (total_input_tokens * llm_model.input_cost) / 1_000_000
        output_cost = (total_output_tokens * llm_model.output_cost) / 1_000_000

        background_tasks.add_task(
            log_direct_usage,
            db_wrapper,
            user.id,
            team_id,
            body.model,
            body.messages[-1].content if body.messages and body.messages[-1].content else "",
            choices[0].message.content or "",
            total_input_tokens,
            total_output_tokens,
            input_cost,
            output_cost,
        )

        return OpenAIChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=body.model,
            choices=choices,
            usage=OpenAIChatCompletionUsage(
                prompt_tokens=total_input_tokens,
                completion_tokens=total_output_tokens,
                total_tokens=total_input_tokens + total_output_tokens,
            ),
            system_fingerprint=fingerprint,
        )
    else:
        # Streaming response
        include_usage = (
            body.stream_options.get("include_usage", False)
            if body.stream_options else False
        )

        async def generate():
            full_answer = ""
            last_finish_reason = None
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
                            "system_fingerprint": fingerprint,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"

                    # Try to extract finish_reason from streaming chunks
                    if hasattr(token_response, "raw") and token_response.raw:
                        try:
                            fr = token_response.raw.choices[0].finish_reason
                            if fr:
                                last_finish_reason = fr
                        except (AttributeError, IndexError, TypeError):
                            pass

                # Check for tool calls in the final aggregated response
                tool_call_delta = None
                if hasattr(token_response, "message") and hasattr(token_response.message, "additional_kwargs"):
                    raw_calls = token_response.message.additional_kwargs.get("tool_calls")
                    if raw_calls:
                        last_finish_reason = "tool_calls"
                        tool_call_delta = _extract_tool_calls(token_response)

                # Send tool calls chunk if present
                if tool_call_delta:
                    tc_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": body.model,
                        "system_fingerprint": fingerprint,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": tool_call_delta,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(tc_chunk)}\n\n"

                # Send final chunk with finish_reason
                final_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.model,
                    "system_fingerprint": fingerprint,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": last_finish_reason or "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"

                # Send usage chunk if requested
                if include_usage:
                    input_tokens = tokens_from_string(
                        " ".join(m.content or "" for m in body.messages)
                    )
                    output_tokens = tokens_from_string(full_answer)
                    usage_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": body.model,
                        "system_fingerprint": fingerprint,
                        "choices": [],
                        "usage": {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        },
                    }
                    yield f"data: {json.dumps(usage_chunk)}\n\n"

                yield "data: [DONE]\n\n"
            finally:
                # Log after stream completes
                input_tokens = tokens_from_string(
                    " ".join(m.content or "" for m in body.messages)
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
                        body.messages[-1].content if body.messages and body.messages[-1].content else "",
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


@router.get("/v1/models")
async def list_models(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible model listing endpoint."""
    models = []
    if user.is_admin:
        for llm in db_wrapper.get_llms():
            models.append({
                "id": llm.name,
                "object": "model",
                "created": 0,
                "owned_by": llm.class_name or "unknown",
            })
    else:
        teams = db_wrapper.get_teams_for_user(user.id)
        seen = set()
        for team in teams:
            for llm in team.llms:
                if llm.name not in seen:
                    seen.add(llm.name)
                    models.append({
                        "id": llm.name,
                        "object": "model",
                        "created": 0,
                        "owned_by": llm.class_name or "unknown",
                    })
    return {"object": "list", "data": models}


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
