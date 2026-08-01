"""Tests for restai/helper.py plumbing — chat_main dispatch + accounting hooks,
streaming response assembly, SSE final-frame enrichment, image/attachment
normalization, and the SSRF address-category table. Project handlers, budget
checks and log_inference are all faked; no network, no LLM."""
import asyncio
import json
import types

import pytest
from fastapi import BackgroundTasks, HTTPException

import restai.helper as helper
from restai.helper import (
    _apply_context,
    _attachment_meta,
    _enrich_final_frame,
    _is_private_ip,
    _normalize_image_inputs,
    _pick_image_for_log,
    chat_main,
    resolve_image,
)
from restai.models.models import ChatModel, FileAttachment


# ─── SSRF address-category table ────────────────────────────────────────
# Complements tests/test_helper_security.py (loopback/RFC1918/link-local/
# mapped-IPv6) with the category-based rejections: unspecified, multicast,
# reserved/broadcast, CGNAT — IP literals only, no DNS.

@pytest.mark.parametrize("ip", [
    "0.0.0.0",           # unspecified / "this network"
    "0.1.2.3",           # 0.0.0.0/8
    "224.0.0.1",         # multicast
    "255.255.255.255",   # broadcast / reserved
    "240.0.0.1",         # Class E reserved
    "::",                # IPv6 unspecified
    "ff02::1",           # IPv6 multicast
    "fdff::1",           # ULA fc00::/7
])
def test_is_private_ip_blocked_categories(ip):
    assert _is_private_ip(ip) is True


@pytest.mark.parametrize("ip", [
    "93.184.216.34",     # example.com
    "9.9.9.9",
    "2606:4700::1111",
])
def test_is_private_ip_public(ip):
    assert _is_private_ip(ip) is False


# ─── resolve_image ──────────────────────────────────────────────────────

def test_resolve_image_non_url_passthrough():
    assert resolve_image("aGVsbG8=") == "aGVsbG8="


def test_resolve_image_data_url_passthrough():
    # data: URLs don't match the http(s) pattern → returned untouched.
    assert resolve_image("data:image/png;base64,QUJD") == "data:image/png;base64,QUJD"


# ─── attachment helpers ─────────────────────────────────────────────────

def _att(name, content="QUJD", mime=None):
    return FileAttachment(name=name, content=content, mime_type=mime)


def test_attachment_meta_strips_bytes():
    meta = _attachment_meta([_att("a.pdf", content="QUJDRA==", mime="application/pdf")])
    assert meta == [{"name": "a.pdf", "mime_type": "application/pdf", "size": 8}]


def test_attachment_meta_empty():
    assert _attachment_meta(None) == []
    assert _attachment_meta([]) == []


def test_pick_image_for_log_explicit_wins():
    files = [_att("x.png", mime="image/png")]
    assert _pick_image_for_log("explicit", files) == "explicit"


def test_pick_image_for_log_falls_back_to_file_image():
    files = [_att("doc.pdf", mime="application/pdf"), _att("x.png", mime="image/png")]
    out = _pick_image_for_log(None, files)
    assert out == "data:image/png;base64,QUJD"


def test_pick_image_for_log_none():
    assert _pick_image_for_log(None, None) is None
    assert _pick_image_for_log(None, [_att("a.txt", mime="text/plain")]) is None


# ─── _normalize_image_inputs ────────────────────────────────────────────

def test_normalize_promotes_first_image_file():
    m = ChatModel(question="q", files=[
        _att("doc.txt", mime="text/plain"),
        _att("a.png", mime="image/png"),
        _att("b.png", mime="image/png"),
    ])
    _normalize_image_inputs(m)
    assert m.image == "data:image/png;base64,QUJD"
    assert [f.name for f in m.files] == ["doc.txt"]  # both images removed


def test_normalize_explicit_image_wins_and_drops_file_images():
    m = ChatModel(question="q", image="data:keep", files=[_att("a.png", mime="image/png")])
    _normalize_image_inputs(m)
    assert m.image == "data:keep"
    assert m.files == []


def test_normalize_no_files_noop():
    m = ChatModel(question="q")
    _normalize_image_inputs(m)
    assert m.image is None
    assert m.files is None


def test_normalize_extension_detection():
    m = ChatModel(question="q", files=[_att("photo.WEBP")])
    _normalize_image_inputs(m)
    assert m.image.startswith("data:image/png;base64,")  # default mime
    assert m.files == []


# ─── _enrich_final_frame ────────────────────────────────────────────────

def _project(ptype="agent", system="sys", name="proj"):
    props = types.SimpleNamespace(
        type=ptype, system=system, name=name, id=1, team=None,
        # no `llm` attribute → attach_cost uses zero pricing without a db.
    )
    return types.SimpleNamespace(props=props)


def test_enrich_final_frame_passthrough_non_sse():
    chunk, parsed = _enrich_final_frame(b"bytes", _project(), None)
    assert (chunk, parsed) == (b"bytes", None)
    chunk, parsed = _enrich_final_frame("event: close\n\n", _project(), None)
    assert parsed is None


def test_enrich_final_frame_passthrough_text_delta():
    frame = "data: " + json.dumps({"text": "hi"}) + "\n"
    chunk, parsed = _enrich_final_frame(frame, _project(), None)
    assert chunk == frame
    assert parsed is None


def test_enrich_final_frame_passthrough_bad_json():
    frame = "data: {not json\n"
    chunk, parsed = _enrich_final_frame(frame, _project(), None)
    assert chunk == frame
    assert parsed is None


def test_enrich_final_frame_attaches_cost():
    final = {"answer": "a", "type": "agent", "tokens": {"input": 5, "output": 3}}
    frame = "data: " + json.dumps(final) + "\n"
    chunk, parsed = _enrich_final_frame(frame, _project(), None)
    assert parsed is not None
    assert parsed["cost"] == {"input": 0.0, "output": 0.0, "total": 0.0}
    assert json.loads(chunk[len("data: "):]) == parsed
    assert chunk.endswith("\n")


# ─── _apply_context ─────────────────────────────────────────────────────

def test_apply_context_none_returns_same_project():
    project = _project()
    chat = ChatModel(question="q")
    assert _apply_context(project, chat) is project


def test_apply_context_calls_with_context():
    seen = {}
    project = _project()

    def _with_context(ctx):
        seen["ctx"] = ctx
        return "NEW"

    project.with_context = _with_context
    chat = ChatModel(question="q", context={"k": "v"})
    out = _apply_context(project, chat)
    assert out == "NEW"
    assert seen["ctx"] == {"k": "v"}


# ─── chat_main dispatch (non-streaming) ────────────────────────────────

class _FakeDB:
    def __init__(self):
        self.rollbacks = 0
        outer = self

        class _Session:
            def rollback(self_inner):
                outer.rollbacks += 1
        self.db = _Session()


def _user():
    return types.SimpleNamespace(api_key_id=None, username="u")


def _fake_handler_class(chunks):
    class _Fake:
        def __init__(self, brain):
            pass

        async def chat(self, project, chat_input, user, db):
            for c in chunks:
                yield c
    return _Fake


@pytest.fixture()
def quiet_checks(monkeypatch):
    """Neutralize budget/rate/quota checks and capture log_inference calls."""
    logged = []
    monkeypatch.setattr(helper, "enforce_cost_budgets", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_api_key_quota", lambda *a, **k: None)
    monkeypatch.setattr(
        helper, "log_inference",
        lambda project, user, output, db, **kw: logged.append((output, kw)),
    )
    return logged


def _run_chat(project, chat_input, quiet=None):
    return asyncio.run(chat_main(
        None, types.SimpleNamespace(), project, chat_input,
        _user(), _FakeDB(), BackgroundTasks(), start_time=None,
    ))


def test_chat_main_agent_non_streaming(quiet_checks, monkeypatch):
    final = {"answer": "done", "tokens": {"input": 1, "output": 2}}
    monkeypatch.setattr(helper, "Agent", _fake_handler_class(["text-frame", final]))
    project = _project(ptype="agent")
    out = _run_chat(project, ChatModel(question="q", stream=False))
    assert out["answer"] == "done"
    assert out["cost"]["total"] == 0.0  # attach_cost ran (zero pricing)
    assert len(quiet_checks) == 1
    assert quiet_checks[0][0] is out


def test_chat_main_block_dispatch(quiet_checks, monkeypatch):
    final = {"answer": "block out", "tokens": {"input": 0, "output": 0}}
    monkeypatch.setattr(helper, "Block", _fake_handler_class([final]))
    out = _run_chat(_project(ptype="block"), ChatModel(question="q", stream=False))
    assert out["answer"] == "block out"


def test_chat_main_invalid_type_400(quiet_checks, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _run_chat(_project(ptype="bogus"), ChatModel(question="q", stream=False))
    assert exc.value.status_code == 400
    # An error row was written with the request metadata.
    output, _ = quiet_checks[-1]
    assert output["status"] == "error"
    assert output["question"] == "q"


def test_chat_main_budget_exhausted_logs_and_raises(monkeypatch):
    logged = []
    monkeypatch.setattr(helper, "log_inference",
                        lambda project, user, output, db, **kw: logged.append(output))

    def _broke(*a, **k):
        raise HTTPException(status_code=402, detail="Project budget exhausted")
    monkeypatch.setattr(helper, "enforce_cost_budgets", _broke)

    with pytest.raises(HTTPException) as exc:
        _run_chat(_project(), ChatModel(question="q"))
    assert exc.value.status_code == 402
    assert logged[0]["status"] == "budget"
    assert logged[0]["error"] == "Project budget exhausted"


def test_chat_main_rate_limit_logs_status(monkeypatch):
    logged = []
    monkeypatch.setattr(helper, "log_inference",
                        lambda project, user, output, db, **kw: logged.append(output))
    monkeypatch.setattr(helper, "enforce_cost_budgets", lambda *a, **k: None)

    def _limited(*a, **k):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    monkeypatch.setattr(helper, "check_rate_limit", _limited)

    with pytest.raises(HTTPException):
        _run_chat(_project(), ChatModel(question="q"))
    assert logged[0]["status"] == "rate_limit"


def test_chat_main_quota_logs_status(monkeypatch):
    logged = []
    monkeypatch.setattr(helper, "log_inference",
                        lambda project, user, output, db, **kw: logged.append(output))
    monkeypatch.setattr(helper, "enforce_cost_budgets", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_rate_limit", lambda *a, **k: None)

    def _over(*a, **k):
        raise HTTPException(status_code=429, detail="Monthly token quota exceeded")
    monkeypatch.setattr(helper, "check_api_key_quota", _over)

    with pytest.raises(HTTPException):
        _run_chat(_project(), ChatModel(question="q"))
    assert logged[0]["status"] == "quota"


def test_chat_main_empty_generator_returns_none(quiet_checks, monkeypatch):
    monkeypatch.setattr(helper, "Agent", _fake_handler_class(["only", "text", "frames"]))
    out = _run_chat(_project(), ChatModel(question="q", stream=False))
    assert out is None
    assert quiet_checks == []


def test_chat_main_logging_failure_still_returns_answer(monkeypatch):
    monkeypatch.setattr(helper, "enforce_cost_budgets", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_api_key_quota", lambda *a, **k: None)

    def _boom(*a, **k):
        raise RuntimeError("column too small")
    monkeypatch.setattr(helper, "log_inference", _boom)
    final = {"answer": "survived", "tokens": {"input": 1, "output": 1}}
    monkeypatch.setattr(helper, "Agent", _fake_handler_class([final]))

    db = _FakeDB()
    out = asyncio.run(chat_main(
        None, types.SimpleNamespace(), _project(), ChatModel(question="q", stream=False),
        _user(), db, BackgroundTasks(),
    ))
    assert out["answer"] == "survived"
    assert db.rollbacks >= 1


def test_chat_main_attaches_image_and_attachment_meta(quiet_checks, monkeypatch):
    final = {"answer": "ok", "tokens": {"input": 1, "output": 1}}
    monkeypatch.setattr(helper, "Agent", _fake_handler_class([final]))
    chat_input = ChatModel(question="q", stream=False, files=[
        _att("pic.png", mime="image/png"),
        _att("notes.txt", mime="text/plain"),
    ])
    out = _run_chat(_project(ptype="agent"), chat_input)
    # Image file was promoted to `.image` and stamped onto the final dict.
    assert out["image"] == "data:image/png;base64,QUJD"
    assert out["attachments"] == [{"name": "notes.txt", "mime_type": "text/plain", "size": 4}]


def test_chat_main_handler_exception_logs_error(monkeypatch):
    logged = []
    monkeypatch.setattr(helper, "enforce_cost_budgets", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(helper, "check_api_key_quota", lambda *a, **k: None)
    monkeypatch.setattr(helper, "log_inference",
                        lambda project, user, output, db, **kw: logged.append(output))

    class _Boom:
        def __init__(self, brain):
            pass

        async def chat(self, project, chat_input, user, db):
            raise RuntimeError("provider offline")
            yield  # pragma: no cover

    monkeypatch.setattr(helper, "Agent", _Boom)
    with pytest.raises(RuntimeError):
        _run_chat(_project(), ChatModel(question="q", stream=False))
    assert logged[0]["status"] == "error"
    assert "provider offline" in logged[0]["error"]


# ─── streaming path (no chat_id → legacy direct streaming) ─────────────

async def _consume(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return chunks


def test_chat_main_streaming_enriches_final_frame(quiet_checks, monkeypatch):
    final = {"answer": "streamed", "type": "agent", "tokens": {"input": 2, "output": 3}}
    frames = [
        "data: " + json.dumps({"text": "str"}) + "\n\n",
        "data: " + json.dumps({"text": "eamed"}) + "\n\n",
        "data: " + json.dumps(final) + "\n",
    ]
    monkeypatch.setattr(helper, "Agent", _fake_handler_class(frames))

    async def _go():
        resp = await chat_main(
            None, types.SimpleNamespace(), _project(ptype="agent"),
            ChatModel(question="q", stream=True),  # no id → non-resume path
            _user(), _FakeDB(), BackgroundTasks(),
        )
        return await _consume(resp)

    chunks = asyncio.run(_go())
    assert chunks[0] == frames[0]
    assert chunks[-1] == "event: close\n\n"
    final_frame = json.loads(chunks[-2][len("data: "):])
    assert final_frame["answer"] == "streamed"
    assert final_frame["cost"]["total"] == 0.0
    # Final output was logged exactly once.
    assert len(quiet_checks) == 1
    assert quiet_checks[0][0]["answer"] == "streamed"


def test_chat_main_streaming_dict_chunk(quiet_checks, monkeypatch):
    final = {"answer": "dict-final", "type": "agent", "tokens": {"input": 1, "output": 1}}
    monkeypatch.setattr(helper, "Agent", _fake_handler_class([final]))

    async def _go():
        resp = await chat_main(
            None, types.SimpleNamespace(), _project(ptype="agent"),
            ChatModel(question="q", stream=True),
            _user(), _FakeDB(), BackgroundTasks(),
        )
        return await _consume(resp)

    chunks = asyncio.run(_go())
    parsed = json.loads(chunks[0][len("data: "):])
    assert parsed["answer"] == "dict-final"
    assert "cost" in parsed
    assert len(quiet_checks) == 1


def test_chat_main_streaming_error_emits_error_frames(quiet_checks, monkeypatch):
    class _Boom:
        def __init__(self, brain):
            pass

        async def chat(self, project, chat_input, user, db):
            yield "data: " + json.dumps({"text": "part"}) + "\n\n"
            raise RuntimeError("mid-stream failure")

    monkeypatch.setattr(helper, "Agent", _Boom)

    async def _go():
        resp = await chat_main(
            None, types.SimpleNamespace(), _project(ptype="agent"),
            ChatModel(question="the q", stream=True),
            _user(), _FakeDB(), BackgroundTasks(),
        )
        return await _consume(resp)

    chunks = asyncio.run(_go())
    assert chunks[-1] == "event: close\n\n"
    err_final = json.loads(chunks[-2][len("data: "):])
    assert err_final["status"] == "error"
    assert "mid-stream failure" in err_final["answer"]
    assert err_final["question"] == "the q"
    # Error output logged.
    assert quiet_checks[0][0]["status"] == "error"
