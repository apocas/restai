import base64
import json
import logging
import struct
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from restai.auth import get_current_username, check_not_restricted
from restai.database import get_db_wrapper, DBWrapper
from restai.limits.budget import check_api_key_quota
from restai.integrations.direct_access import (
    log_direct_usage,
    resolve_team_for_llm,
    resolve_team_for_embedding,
)
from restai.models.models import (
    OpenAIChatCompletionRequest,
    OpenAIChatCompletionResponse,
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionUsage,
    OpenAIChatMessage,
    OpenAIToolCall,
    OpenAICompletionRequest,
    OpenAICompletionResponse,
    OpenAICompletionChoice,
    OpenAIEmbeddingRequest,
    OpenAIEmbeddingResponse,
    OpenAIEmbeddingData,
    OpenAIEmbeddingUsage,
    OpenAIModelObject,
    OpenAIModerationRequest,
    OpenAIModerationResponse,
    OpenAIModerationResult,
    User,
)
from restai.tools import tokens_from_string
from restai.utils import openai_compat as oc

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _bill(llm_model, in_tok: int, out_tok: int):
    return (
        (in_tok * (llm_model.input_cost or 0.0)) / 1_000_000,
        (out_tok * (llm_model.output_cost or 0.0)) / 1_000_000,
    )


def _estimate_prompt_tokens(messages) -> int:
    return tokens_from_string(" ".join(m.content or "" for m in messages))


def _user_llm_rows(user: User, db_wrapper: DBWrapper):
    """(name, class_name) for every LLM the caller can reach. Admins see all."""
    if user.is_admin:
        return [(l.name, l.class_name or "unknown") for l in db_wrapper.get_llms()]
    seen, out = set(), []
    for team in db_wrapper.get_teams_for_user(user.id):
        for llm in team.llms:
            if llm.name not in seen:
                seen.add(llm.name)
                out.append((llm.name, llm.class_name or "unknown"))
    return out


# ── /v1/chat/completions ─────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    body: OpenAIChatCompletionRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible chat completions (native passthrough when possible)."""
    check_not_restricted(user)
    check_api_key_quota(user, db_wrapper)
    team_id = resolve_team_for_llm(user, body.model, db_wrapper)

    llm_obj = request.app.state.brain.get_llm(body.model, db_wrapper)
    if llm_obj is None:
        raise HTTPException(status_code=404, detail=f"Model '{body.model}' not found")

    llm = llm_obj.llm
    llm_model = llm_obj.props
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    fingerprint = oc.system_fingerprint()
    question = body.messages[-1].content if body.messages and body.messages[-1].content else ""

    # ── native passthrough for OpenAI-wire-compatible providers ──
    upstream = oc.resolve_upstream(llm_model) if oc.is_openai_native(llm_model.class_name) else None
    if upstream is not None:
        url, headers, upstream_model = upstream
        raw_body = body.model_dump(exclude_none=True)
        if upstream_model:
            raw_body["model"] = upstream_model
        return await _passthrough_chat(
            body, raw_body, url, headers, db_wrapper, user, team_id, llm_model, question, background_tasks
        )

    # ── translated fallback ──
    messages = oc.convert_messages(body.messages)
    kwargs = oc.build_kwargs(body)
    n = body.n or 1

    if not body.stream:
        choices, total_in, total_out = [], 0, 0
        for i in range(n):
            response = llm.chat(messages, **kwargs)
            tool_calls = oc.extract_tool_calls(response)
            finish_reason = oc.extract_finish_reason(response)
            content = str(response.message.content) if response.message.content else None
            tc_models = [OpenAIToolCall(**tc) for tc in tool_calls] if tool_calls else None
            msg = OpenAIChatMessage(role="assistant", content=content, tool_calls=tc_models)

            real = oc.usage_from_response(response)
            in_tok = real[0] if real else _estimate_prompt_tokens(body.messages)
            out_tok = real[1] if real else tokens_from_string(content or "")
            total_in += in_tok
            total_out += out_tok
            choices.append(OpenAIChatCompletionChoice(index=i, message=msg, finish_reason=finish_reason))

        in_cost, out_cost = _bill(llm_model, total_in, total_out)
        background_tasks.add_task(
            log_direct_usage, db_wrapper, user.id, team_id, body.model,
            question, choices[0].message.content or "",
            total_in, total_out, in_cost, out_cost, user.api_key_id,
        )
        return OpenAIChatCompletionResponse(
            id=completion_id, created=int(time.time()), model=body.model, choices=choices,
            usage=OpenAIChatCompletionUsage(
                prompt_tokens=total_in, completion_tokens=total_out, total_tokens=total_in + total_out,
            ),
            system_fingerprint=fingerprint,
        )

    include_usage = bool((body.stream_options or {}).get("include_usage"))

    async def generate():
        full_answer, last_finish = "", None
        last_response = None
        try:
            base = {"id": completion_id, "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": body.model, "system_fingerprint": fingerprint}
            # Leading role chunk (OpenAI always sends this first).
            yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})

            stream_response = llm.stream_chat(messages, **kwargs)
            for token_response in stream_response:
                last_response = token_response
                delta = token_response.delta
                if delta:
                    full_answer += delta
                    yield _sse({**base, "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]})
                fr = _finish_from_raw(token_response)
                if fr:
                    last_finish = fr

            tool_calls = oc.extract_tool_calls(last_response) if last_response is not None else None
            if tool_calls:
                last_finish = "tool_calls"
                yield _sse({**base, "choices": [{"index": 0, "delta": {
                    "tool_calls": [{"index": j, **tc} for j, tc in enumerate(tool_calls)]
                }, "finish_reason": None}]})

            yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": last_finish or "stop"}]})

            real = oc.usage_from_response(last_response) if last_response is not None else None
            in_tok = real[0] if real else _estimate_prompt_tokens(body.messages)
            out_tok = real[1] if real else tokens_from_string(full_answer)
            if include_usage:
                yield _sse({**base, "choices": [], "usage": {
                    "prompt_tokens": in_tok, "completion_tokens": out_tok, "total_tokens": in_tok + out_tok,
                }})
            yield "data: [DONE]\n\n"
        finally:
            real = oc.usage_from_response(last_response) if last_response is not None else None
            in_tok = real[0] if real else _estimate_prompt_tokens(body.messages)
            out_tok = real[1] if real else tokens_from_string(full_answer)
            in_cost, out_cost = _bill(llm_model, in_tok, out_tok)
            try:
                log_direct_usage(
                    db_wrapper, user.id, team_id, body.model, question, full_answer,
                    in_tok, out_tok, in_cost, out_cost, user.api_key_id,
                )
            except Exception:
                logging.exception("Failed to log direct access usage")

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _finish_from_raw(token_response) -> Optional[str]:
    raw = getattr(token_response, "raw", None)
    if not raw:
        return None
    try:
        choices = raw["choices"] if isinstance(raw, dict) else raw.choices
        c0 = choices[0]
        return c0["finish_reason"] if isinstance(c0, dict) else c0.finish_reason
    except (AttributeError, IndexError, TypeError, KeyError):
        return None


async def _passthrough_chat(body, raw_body, url, headers, db_wrapper, user, team_id, llm_model, question, background_tasks):
    if not body.stream:
        status, data = await oc.passthrough_json(url, headers, raw_body)
        if status < 400:
            usage = data.get("usage") or {}
            in_tok = int(usage.get("prompt_tokens") or 0)
            out_tok = int(usage.get("completion_tokens") or 0)
            try:
                answer = data["choices"][0]["message"].get("content") or ""
            except (KeyError, IndexError, TypeError):
                answer = ""
            data["model"] = body.model  # report the RESTai model name back
            in_cost, out_cost = _bill(llm_model, in_tok, out_tok)
            background_tasks.add_task(
                log_direct_usage, db_wrapper, user.id, team_id, body.model,
                question, answer, in_tok, out_tok, in_cost, out_cost, user.api_key_id,
            )
        return JSONResponse(content=data, status_code=status)

    include_usage = bool((body.stream_options or {}).get("include_usage"))
    usage_holder = {}

    async def generate():
        try:
            async for frame in oc.passthrough_sse(url, headers, raw_body, usage_holder, include_usage):
                yield frame
        finally:
            u = usage_holder.get("usage") or {}
            in_tok = int(u.get("prompt_tokens") or 0)
            out_tok = int(u.get("completion_tokens") or 0)
            in_cost, out_cost = _bill(llm_model, in_tok, out_tok)
            try:
                log_direct_usage(
                    db_wrapper, user.id, team_id, body.model, question,
                    "(streamed via passthrough)", in_tok, out_tok, in_cost, out_cost, user.api_key_id,
                )
            except Exception:
                logging.exception("Failed to log passthrough usage")

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── /v1/completions (legacy text completion, translated path) ────────────────

@router.post("/v1/completions")
async def completions(
    request: Request,
    body: OpenAICompletionRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible legacy text completions. Prompt is wrapped as a single
    user message and run through the model's chat interface."""
    check_not_restricted(user)
    check_api_key_quota(user, db_wrapper)
    team_id = resolve_team_for_llm(user, body.model, db_wrapper)

    llm_obj = request.app.state.brain.get_llm(body.model, db_wrapper)
    if llm_obj is None:
        raise HTTPException(status_code=404, detail=f"Model '{body.model}' not found")
    llm = llm_obj.llm
    llm_model = llm_obj.props
    completion_id = f"cmpl-{uuid.uuid4().hex[:24]}"
    fingerprint = oc.system_fingerprint()

    prompt = body.prompt if isinstance(body.prompt, str) else "\n".join(body.prompt)
    messages = oc.convert_messages([{"role": "user", "content": prompt}])
    kwargs = {}
    for p in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "stop", "seed", "logit_bias"):
        v = getattr(body, p, None)
        if v is not None:
            kwargs[p] = v
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    if not body.stream:
        response = llm.chat(messages, **kwargs)
        text = str(response.message.content) if response.message.content else ""
        finish_reason = oc.extract_finish_reason(response)
        real = oc.usage_from_response(response)
        in_tok = real[0] if real else tokens_from_string(prompt)
        out_tok = real[1] if real else tokens_from_string(text)
        in_cost, out_cost = _bill(llm_model, in_tok, out_tok)
        background_tasks.add_task(
            log_direct_usage, db_wrapper, user.id, team_id, body.model,
            prompt, text, in_tok, out_tok, in_cost, out_cost, user.api_key_id,
        )
        return OpenAICompletionResponse(
            id=completion_id, created=int(time.time()), model=body.model,
            choices=[OpenAICompletionChoice(text=text, index=0, finish_reason=finish_reason)],
            usage=OpenAIChatCompletionUsage(
                prompt_tokens=in_tok, completion_tokens=out_tok, total_tokens=in_tok + out_tok,
            ),
            system_fingerprint=fingerprint,
        )

    async def generate():
        full, last_finish, last = "", None, None
        try:
            base = {"id": completion_id, "object": "text_completion",
                    "created": int(time.time()), "model": body.model, "system_fingerprint": fingerprint}
            for tr in llm.stream_chat(messages, **kwargs):
                last = tr
                if tr.delta:
                    full += tr.delta
                    yield _sse({**base, "choices": [{"text": tr.delta, "index": 0, "logprobs": None, "finish_reason": None}]})
                fr = _finish_from_raw(tr)
                if fr:
                    last_finish = fr
            yield _sse({**base, "choices": [{"text": "", "index": 0, "logprobs": None, "finish_reason": last_finish or "stop"}]})
            yield "data: [DONE]\n\n"
        finally:
            real = oc.usage_from_response(last) if last is not None else None
            in_tok = real[0] if real else tokens_from_string(prompt)
            out_tok = real[1] if real else tokens_from_string(full)
            in_cost, out_cost = _bill(llm_model, in_tok, out_tok)
            try:
                log_direct_usage(db_wrapper, user.id, team_id, body.model, prompt, full,
                                 in_tok, out_tok, in_cost, out_cost, user.api_key_id)
            except Exception:
                logging.exception("Failed to log direct completion usage")

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── /v1/models + /v1/models/{id} ─────────────────────────────────────────────

@router.get("/v1/models")
async def list_models(
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible model listing."""
    created = int(time.time())
    data = [{"id": name, "object": "model", "created": created, "owned_by": owner}
            for name, owner in _user_llm_rows(user, db_wrapper)]
    return {"object": "list", "data": data}


@router.get("/v1/models/{model}", response_model=OpenAIModelObject)
async def retrieve_model(
    model: str,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """OpenAI-compatible retrieve-model."""
    for name, owner in _user_llm_rows(user, db_wrapper):
        if name == model:
            return OpenAIModelObject(id=name, created=int(time.time()), owned_by=owner)
    raise HTTPException(status_code=404, detail=f"Model '{model}' not found")


# ── /v1/embeddings ───────────────────────────────────────────────────────────

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
    check_api_key_quota(user, db_wrapper)
    team_id = resolve_team_for_embedding(user, body.model, db_wrapper)

    embedding_obj = request.app.state.brain.get_embedding(body.model, db_wrapper)
    if embedding_obj is None:
        raise HTTPException(status_code=404, detail=f"Embedding model '{body.model}' not found")

    texts = [body.input] if isinstance(body.input, str) else body.input
    results = embedding_obj.embedding.get_text_embedding_batch(texts)

    if body.dimensions:
        results = [vec[: body.dimensions] for vec in results]

    if body.encoding_format == "base64":
        data = [
            OpenAIEmbeddingData(
                embedding=base64.b64encode(struct.pack(f"<{len(vec)}f", *vec)).decode("ascii"),
                index=i,
            )
            for i, vec in enumerate(results)
        ]
    else:
        data = [OpenAIEmbeddingData(embedding=vec, index=i) for i, vec in enumerate(results)]

    total_tokens = sum(tokens_from_string(t) for t in texts)
    background_tasks.add_task(
        log_direct_usage, db_wrapper, user.id, team_id, body.model,
        f"(embed {len(texts)} text(s))", "(embeddings generated)",
        total_tokens, 0, 0.0, 0.0, user.api_key_id,
    )

    return OpenAIEmbeddingResponse(
        model=body.model, data=data,
        usage=OpenAIEmbeddingUsage(prompt_tokens=total_tokens, total_tokens=total_tokens),
    )


# ── /v1/moderations ──────────────────────────────────────────────────────────

_OPENAI_MODERATION_CATEGORIES = (
    "sexual", "hate", "harassment", "self-harm", "sexual/minors", "hate/threatening",
    "violence/graphic", "self-harm/intent", "self-harm/instructions",
    "harassment/threatening", "violence",
)


@router.post("/v1/moderations", response_model=OpenAIModerationResponse)
async def moderations(
    body: OpenAIModerationRequest,
    user: User = Depends(get_current_username),
):
    """OpenAI-compatible moderation. Backed by RESTai's regex `moderate_content`
    (PII / secrets / prompt-injection / blocklist) — best-effort; it does NOT
    classify OpenAI's hate/violence taxonomy, so those categories are always
    False and RESTai-specific signals are added as extra keys."""
    from restai.llms.tools.moderate_content import moderate_content

    inputs = [body.input] if isinstance(body.input, str) else body.input
    results = []
    for text in inputs:
        verdict = moderate_content(text or "")
        flagged = verdict.startswith("FLAGGED")
        head = verdict.split("\n", 1)[0]
        cats = {c: False for c in _OPENAI_MODERATION_CATEGORIES}
        cats["pii"] = ("pii_detected" in head) or ("api_key" in head)
        cats["prompt_injection"] = "possible_injection" in head
        cats["blocklist"] = "blocklist:" in head
        scores = {k: (1.0 if v else 0.0) for k, v in cats.items()}
        results.append(OpenAIModerationResult(flagged=flagged, categories=cats, category_scores=scores))

    return OpenAIModerationResponse(
        id=f"modr-{uuid.uuid4().hex[:24]}", model=body.model or "restai-moderation", results=results,
    )


# ── /direct/models (non-OpenAI: everything the user can reach) ────────────────

@router.get("/direct/models")
async def list_accessible_models(
    request: Request,
    user: User = Depends(get_current_username),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List all models/generators the user can access via direct endpoints."""
    if user.is_admin:
        llms = [{"name": l.name} for l in db_wrapper.get_llms()]
        embeddings_list = [{"name": e.name, "dimension": e.dimension} for e in db_wrapper.get_embeddings()]

        # List the *configured* generators from the DB (local + remote provider
        # rows), not the loaded local-worker FunctionTools — remote generators
        # (OpenAI, Google, Deepgram, …) are served without a GPU, so they must
        # show up on GPU-less deployments too.
        from restai.image.dispatch import list_available_generators
        from restai.audio.dispatch import list_available_stt_models
        return {
            "llms": llms, "embeddings": embeddings_list,
            "image_generators": list_available_generators(db_wrapper),
            "audio_generators": list_available_stt_models(db_wrapper),
        }

    teams = db_wrapper.get_teams_for_user(user.id)
    llm_names, embedding_names, image_gen_names, audio_gen_names = set(), set(), set(), set()
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
