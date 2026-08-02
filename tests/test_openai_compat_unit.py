"""Unit tests for restai/utils/openai_compat.py — translate-in/out helpers,
native-passthrough routing table and the passthrough HTTP shims (with a fake
httpx client; no network)."""
import asyncio
import json
import types

from llama_index.core.base.llms.types import MessageRole

from restai.utils import openai_compat as oc


# ─── convert_messages ───────────────────────────────────────────────────

def test_convert_messages_dict_roles():
    msgs = oc.convert_messages([
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "tool", "content": "42", "tool_call_id": "call_1", "name": "calc"},
    ])
    assert [m.role for m in msgs] == [
        MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL,
    ]
    assert msgs[3].additional_kwargs["tool_call_id"] == "call_1"
    assert msgs[3].additional_kwargs["name"] == "calc"


def test_convert_messages_defaults_and_unknown_role():
    msgs = oc.convert_messages([
        {"content": "no role"},
        {"role": "director", "content": "??"},
        {"role": "user", "content": None},
    ])
    assert all(m.role == MessageRole.USER for m in msgs)
    assert msgs[2].content == ""  # None content coerced


def test_convert_messages_object_inputs_and_tool_calls():
    class TC:
        def model_dump(self):
            return {"id": "call_9", "type": "function",
                    "function": {"name": "f", "arguments": "{}"}}

    m = types.SimpleNamespace(
        role="assistant", content="calling", tool_call_id=None, name=None,
        tool_calls=[TC(), {"id": "call_10"}],
    )
    out = oc.convert_messages([m])
    calls = out[0].additional_kwargs["tool_calls"]
    assert calls[0]["id"] == "call_9"
    assert calls[1] == {"id": "call_10"}  # plain dicts pass through


# ─── build_kwargs ───────────────────────────────────────────────────────

def _body(**kw):
    defaults = dict(
        temperature=None, top_p=None, frequency_penalty=None,
        presence_penalty=None, stop=None, seed=None, response_format=None,
        logprobs=None, top_logprobs=None, logit_bias=None,
        parallel_tool_calls=None, max_tokens=None, max_completion_tokens=None,
        tools=None, tool_choice=None, functions=None, function_call=None,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def test_build_kwargs_forwards_set_params_only():
    kwargs = oc.build_kwargs(_body(temperature=0.2, seed=7, stop=["\n"]))
    assert kwargs == {"temperature": 0.2, "seed": 7, "stop": ["\n"]}


def test_build_kwargs_max_completion_tokens_wins():
    assert oc.build_kwargs(_body(max_tokens=10))["max_tokens"] == 10
    assert oc.build_kwargs(
        _body(max_tokens=10, max_completion_tokens=99))["max_tokens"] == 99


def test_build_kwargs_legacy_functions_promoted_to_tools():
    kwargs = oc.build_kwargs(_body(
        functions=[{"name": "f", "parameters": {"type": "object"}}],
        function_call="auto",
    ))
    assert kwargs["tools"] == [
        {"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}
    ]
    assert kwargs["tool_choice"] == "auto"


def test_build_kwargs_tool_objects_normalized():
    fn = types.SimpleNamespace(name="lookup", description=None, parameters=None)
    tool = types.SimpleNamespace(function=fn)
    kwargs = oc.build_kwargs(_body(tools=[tool], tool_choice="required"))
    assert kwargs["tools"][0]["function"]["name"] == "lookup"
    assert kwargs["tools"][0]["function"]["description"] == ""
    assert kwargs["tools"][0]["function"]["parameters"] == {
        "type": "object", "properties": {}}
    assert kwargs["tool_choice"] == "required"


# ─── extract_finish_reason / extract_tool_calls ─────────────────────────

def test_extract_finish_reason_from_raw_dict():
    resp = types.SimpleNamespace(raw={"choices": [{"finish_reason": "length"}]})
    assert oc.extract_finish_reason(resp) == "length"


def test_extract_finish_reason_from_raw_object():
    choice = types.SimpleNamespace(finish_reason="content_filter")
    resp = types.SimpleNamespace(raw=types.SimpleNamespace(choices=[choice]))
    assert oc.extract_finish_reason(resp) == "content_filter"


def test_extract_finish_reason_tool_calls_fallback():
    msg = types.SimpleNamespace(additional_kwargs={"tool_calls": [{"id": "x"}]})
    resp = types.SimpleNamespace(raw=None, message=msg)
    assert oc.extract_finish_reason(resp) == "tool_calls"


def test_extract_finish_reason_default_stop():
    msg = types.SimpleNamespace(additional_kwargs={})
    resp = types.SimpleNamespace(raw={"choices": []}, message=msg)
    assert oc.extract_finish_reason(resp) == "stop"


def test_extract_tool_calls_none_paths():
    assert oc.extract_tool_calls(types.SimpleNamespace()) is None
    msg = types.SimpleNamespace(additional_kwargs={})
    assert oc.extract_tool_calls(types.SimpleNamespace(message=msg)) is None


def test_extract_tool_calls_dict_and_object():
    obj_fn = types.SimpleNamespace(name="obj_tool", arguments='{"a":1}')
    obj_call = types.SimpleNamespace(id="call_obj", function=obj_fn)
    msg = types.SimpleNamespace(additional_kwargs={"tool_calls": [
        {"id": "call_d", "function": {"name": "dict_tool", "arguments": "{}"}},
        {"function": {}},  # missing id/name → defaults
        obj_call,
    ]})
    out = oc.extract_tool_calls(types.SimpleNamespace(message=msg))
    assert out[0] == {
        "id": "call_d", "type": "function",
        "function": {"name": "dict_tool", "arguments": "{}"},
    }
    assert out[1]["id"].startswith("call_")
    assert out[1]["function"] == {"name": "", "arguments": "{}"}
    assert out[2]["id"] == "call_obj"
    assert out[2]["function"]["name"] == "obj_tool"


# ─── usage_from_response ────────────────────────────────────────────────

def test_usage_from_response_dict_and_object():
    resp = types.SimpleNamespace(raw={"usage": {
        "prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}})
    assert oc.usage_from_response(resp) == (12, 3, 15)

    usage = types.SimpleNamespace(prompt_tokens=5, completion_tokens=None,
                                  total_tokens=None)
    resp = types.SimpleNamespace(raw=types.SimpleNamespace(usage=usage))
    assert oc.usage_from_response(resp) == (5, 0, 5)  # total computed


def test_usage_from_response_absent():
    assert oc.usage_from_response(types.SimpleNamespace(raw=None)) is None
    assert oc.usage_from_response(types.SimpleNamespace(raw={})) is None
    resp = types.SimpleNamespace(raw={"usage": {"prompt_tokens": None,
                                                "completion_tokens": None}})
    assert oc.usage_from_response(resp) is None


# ─── native passthrough routing ─────────────────────────────────────────

def test_is_openai_native_table():
    for cls in ("OpenAI", "OpenAILike", "Grok", "vLLM", "AzureOpenAI"):
        assert oc.is_openai_native(cls) is True
    for cls in ("Anthropic", "Ollama", "Gemini", None, ""):
        assert oc.is_openai_native(cls) is False


def _llm(class_name, options):
    return types.SimpleNamespace(class_name=class_name, options=options)


def test_resolve_upstream_openai_requires_key():
    assert oc.resolve_upstream(_llm("OpenAI", {"model": "gpt-4o"})) is None


def test_resolve_upstream_openai_with_key():
    url, headers, model = oc.resolve_upstream(
        _llm("OpenAI", {"api_key": "sk-x", "model": "gpt-4o"}))
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-x"
    assert model == "gpt-4o"


def test_resolve_upstream_openailike_keyless_local():
    url, headers, model = oc.resolve_upstream(
        _llm("OpenAILike", {"api_base": "http://localhost:8000/v1/",
                            "model_name": "llama3"}),
        endpoint="embeddings",
    )
    assert url == "http://localhost:8000/v1/embeddings"
    assert "Authorization" not in headers
    assert model == "llama3"


def test_resolve_upstream_options_json_string_and_engine_fallback():
    url, headers, model = oc.resolve_upstream(
        _llm("vLLM", json.dumps({"base_url": "http://h/v1", "engine": "eng-1"})))
    assert url == "http://h/v1/chat/completions"
    assert model == "eng-1"


def test_resolve_upstream_bad_json_options():
    # Unparseable options → {} → OpenAI without key → None.
    assert oc.resolve_upstream(_llm("OpenAI", "{{{nope")) is None


def test_resolve_upstream_azure():
    llm = _llm("AzureOpenAI", {
        "azure_endpoint": "https://acct.openai.azure.com/",
        "api_key": "az-key", "engine": "dep1", "api_version": "2024-06-01",
    })
    url, headers, deployment = oc.resolve_upstream(llm)
    assert url == ("https://acct.openai.azure.com/openai/deployments/dep1/"
                   "chat/completions?api-version=2024-06-01")
    assert headers["api-key"] == "az-key"
    assert deployment == "dep1"


def test_resolve_upstream_azure_missing_pieces():
    assert oc.resolve_upstream(_llm("AzureOpenAI", {"api_key": "k"})) is None
    assert oc.resolve_upstream(
        _llm("AzureOpenAI", {"azure_endpoint": "https://x", "engine": "d"})) is None


def test_system_fingerprint_prefix():
    assert oc.system_fingerprint().startswith("restai")


# ─── passthrough_json / passthrough_sse (fake httpx client) ─────────────

class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", lines=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self._lines = lines or []

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json

    async def aread(self):
        return self.text.encode()

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeClient:
    """Stands in for httpx.AsyncClient; records the forwarded body."""
    last_body = None
    response = None

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeClient.last_body = json
        return _FakeClient.response

    def stream(self, method, url, headers=None, json=None):
        _FakeClient.last_body = json
        resp = _FakeClient.response

        class _StreamCM:
            async def __aenter__(self_inner):
                return resp

            async def __aexit__(self_inner, *a):
                return False
        return _StreamCM()


def _collect_sse(gen):
    async def run():
        return [chunk async for chunk in gen]
    return asyncio.run(run())


def test_passthrough_json_ok(monkeypatch):
    _FakeClient.response = _FakeResponse(200, json_data={"id": "cmpl-1"})
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)
    status, data = asyncio.run(
        oc.passthrough_json("http://up/v1/chat/completions", {}, {"model": "m"}))
    assert (status, data) == (200, {"id": "cmpl-1"})
    assert _FakeClient.last_body == {"model": "m"}


def test_passthrough_json_non_json_error_envelope(monkeypatch):
    _FakeClient.response = _FakeResponse(502, json_data=None, text="gateway died")
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)
    status, data = asyncio.run(oc.passthrough_json("http://up", {}, {}))
    assert status == 502
    assert data["error"]["message"] == "gateway died"
    assert data["error"]["type"] == "api_error"


def test_passthrough_sse_forces_include_usage_and_captures(monkeypatch):
    usage_frame = json.dumps({"id": "c", "choices": [],
                              "usage": {"prompt_tokens": 4, "completion_tokens": 2}})
    delta = json.dumps({"choices": [{"delta": {"content": "hi"}}]})
    _FakeClient.response = _FakeResponse(200, lines=[
        "", ": comment", "event: ping",
        f"data: {delta}",
        "data: not-json-frame",
        f"data: {usage_frame}",
        "data: [DONE]",
    ])
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)

    holder = {}
    chunks = _collect_sse(oc.passthrough_sse(
        "http://up", {}, {"model": "m", "stream": True}, holder, forward_usage=False))

    # include_usage forced upstream regardless of what the client sent.
    assert _FakeClient.last_body["stream_options"]["include_usage"] is True
    # Real usage captured for billing…
    assert holder["usage"] == {"prompt_tokens": 4, "completion_tokens": 2}
    # …but the usage-only frame is NOT forwarded when the client didn't ask;
    # non-JSON data frames pass through untouched.
    assert chunks == [
        f"data: {delta}\n\n",
        "data: not-json-frame\n\n",
        "data: [DONE]\n\n",
    ]


def test_passthrough_sse_forwards_usage_when_requested(monkeypatch):
    usage_frame = json.dumps({"choices": [], "usage": {"total_tokens": 6}})
    _FakeClient.response = _FakeResponse(200, lines=[
        f"data: {usage_frame}", "data: [DONE]"])
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)
    holder = {}
    chunks = _collect_sse(
        oc.passthrough_sse("http://up", {}, {}, holder, forward_usage=True))
    assert chunks[0] == f"data: {usage_frame}\n\n"
    assert holder["usage"] == {"total_tokens": 6}


def test_passthrough_sse_upstream_error_becomes_sse_error(monkeypatch):
    _FakeClient.response = _FakeResponse(
        401, text=json.dumps({"error": {"message": "bad key", "type": "auth"}}))
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)
    chunks = _collect_sse(oc.passthrough_sse("http://up", {}, {}, {}, True))
    assert len(chunks) == 2
    err = json.loads(chunks[0][len("data: "):])
    assert err["error"]["message"] == "bad key"
    assert chunks[1] == "data: [DONE]\n\n"


def test_passthrough_sse_upstream_error_non_json_body(monkeypatch):
    _FakeClient.response = _FakeResponse(500, text="<html>boom</html>")
    monkeypatch.setattr(oc.httpx, "AsyncClient", _FakeClient)
    chunks = _collect_sse(oc.passthrough_sse("http://up", {}, {}, {}, True))
    err = json.loads(chunks[0][len("data: "):])
    assert err["error"]["message"] == "<html>boom</html>"
    assert err["error"]["type"] == "api_error"
