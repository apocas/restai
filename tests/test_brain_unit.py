"""Unit tests for restai/brain.py — LLM/embedding caches, system-LLM read-through,
image cache (Redis + in-process fallback), chat-store reinit, tool/generator
listing and post-processing helpers. Pure fakes; no network or real LLMs."""
import json
import time
import types

import pytest

import restai.config as config
from restai.brain import Brain


def bare_brain() -> Brain:
    """A Brain without running __init__ (skips tokenizer / tool loading)."""
    b = object.__new__(Brain)
    b.embeddings_cache = {}
    b._classifier_cache = {}
    b._ner_cache = {}
    b._agent2_sessions = {}
    b.tools = None
    b.generators = []
    b.audio_generators = []
    return b


# ─── construction ───────────────────────────────────────────────────────

def test_lightweight_brain_defers_tools_and_has_empty_generators():
    b = Brain(lightweight=True)
    assert b.tools is None
    assert b.generators == []
    assert b.audio_generators == []
    assert b._agent2_sessions == {}
    assert not hasattr(b, "chat_store")


def test_full_brain_loads_tools_and_chat_store(monkeypatch):
    import restai.tools as tools_mod

    monkeypatch.setattr(tools_mod, "load_tools", lambda: [])
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = Brain()
    assert b.tools == []
    assert b.generators == []  # GPU off → never populated
    assert hasattr(b, "chat_store")


def test_docker_and_browser_manager_properties(monkeypatch):
    import restai.docker as docker_mod
    from restai.browser import runtime as browser_mod

    b = bare_brain()
    monkeypatch.setattr(docker_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(browser_mod, "is_enabled", lambda: False)
    assert b.docker_manager is None
    assert b.browser_manager is None

    monkeypatch.setattr(docker_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(browser_mod, "is_enabled", lambda: True)
    assert b.docker_manager is docker_mod
    assert b.browser_manager is browser_mod


def test_mime_ext_maps_are_inverse():
    for mime, ext in Brain._MIME_TO_EXT.items():
        assert Brain._EXT_TO_MIME[ext] in Brain._MIME_TO_EXT


# ─── image cache: in-process fallback ───────────────────────────────────

def test_image_cache_local_round_trip(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()

    name = b.cache_image(b"pixels", "image/jpeg")
    assert name.endswith(".jpg")
    assert len(name.split(".")[0]) == 32  # unguessable hex id

    data, mime = b.get_cached_image(name)
    assert data == b"pixels"
    assert mime == "image/jpeg"


def test_image_cache_unknown_mime_defaults_png(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    assert b.cache_image(b"x", "application/weird").endswith(".png")
    assert b.cache_image(b"x", None).endswith(".png")


def test_image_cache_miss_returns_none(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    assert b.get_cached_image("deadbeef.png") is None


def test_image_cache_traversal_guards(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    assert b.get_cached_image("") is None
    assert b.get_cached_image("a/b.png") is None
    assert b.get_cached_image("a\\b.png") is None
    assert b.get_cached_image(".hidden") is None


def test_image_cache_ttl_expiry(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    name = b.cache_image(b"old", "image/png")
    store = b._image_cache_local()
    data, mime, _exp = store[name]
    store[name] = (data, mime, time.time() - 1)  # force past-TTL
    assert b.get_cached_image(name) is None
    assert name not in store  # expired entry purged on read


def test_image_cache_lazy_sweep_on_write(monkeypatch):
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    store = b._image_cache_local()
    store["stale.png"] = (b"z", "image/png", time.time() - 10)
    b.cache_image(b"fresh")
    assert "stale.png" not in store


# ─── image cache: Redis-backed ──────────────────────────────────────────

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.set_calls = []
        self.closed = False
        self.fail_set = False
        self.fail_get = False

    def set(self, key, value, ex=None):
        if self.fail_set:
            raise RuntimeError("redis down")
        self.set_calls.append((key, ex))
        self.store[key] = value

    def get(self, key):
        if self.fail_get:
            raise RuntimeError("redis down")
        return self.store.get(key)

    def close(self):
        self.closed = True


def _patch_redis(monkeypatch, url="redis://fake:6379"):
    import redis as redis_mod
    clients = []

    def from_url(_url):
        c = FakeRedis()
        c.url = _url
        clients.append(c)
        return c

    monkeypatch.setattr(config, "build_redis_url", lambda: url)
    monkeypatch.setattr(redis_mod.Redis, "from_url", staticmethod(from_url))
    return clients


def test_image_cache_redis_round_trip_and_ttl(monkeypatch):
    clients = _patch_redis(monkeypatch)
    b = bare_brain()
    name = b.cache_image(b"redis-bytes", "image/webp")
    assert name.endswith(".webp")
    client = clients[0]
    key, ex = client.set_calls[0]
    assert key == Brain._IMAGE_CACHE_KEY_PREFIX + name
    assert ex == Brain._IMAGE_CACHE_TTL_SECONDS

    data, mime = b.get_cached_image(name)
    assert data == b"redis-bytes"
    assert mime == "image/webp"


def test_image_cache_redis_client_is_cached_until_url_changes(monkeypatch):
    clients = _patch_redis(monkeypatch)
    b = bare_brain()
    b.cache_image(b"a")
    b.cache_image(b"b")
    assert len(clients) == 1  # reused

    monkeypatch.setattr(config, "build_redis_url", lambda: "redis://other:6379")
    b.cache_image(b"c")
    assert len(clients) == 2
    assert clients[1].url == "redis://other:6379"


def test_image_cache_redis_dropped_when_url_cleared(monkeypatch):
    clients = _patch_redis(monkeypatch)
    b = bare_brain()
    b.cache_image(b"a")
    old = clients[0]
    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    assert b._image_cache_redis() is None
    assert old.closed is True
    assert b._image_cache_redis_client is None


def test_image_cache_redis_build_failure_falls_back(monkeypatch):
    import redis as redis_mod

    monkeypatch.setattr(config, "build_redis_url", lambda: "redis://fake:6379")

    def boom(_url):
        raise RuntimeError("cannot build")
    monkeypatch.setattr(redis_mod.Redis, "from_url", staticmethod(boom))

    b = bare_brain()
    name = b.cache_image(b"fallback")
    # Landed in the in-process store despite the configured URL.
    assert name in b._image_cache_local()


def test_image_cache_redis_write_failure_falls_back(monkeypatch):
    clients = _patch_redis(monkeypatch)
    b = bare_brain()
    b.cache_image(b"warm-up")  # builds the client
    clients[0].fail_set = True
    name = b.cache_image(b"payload")
    assert name in b._image_cache_local()
    data, _ = b.get_cached_image(name)  # redis get returns None -> local hit
    assert data == b"payload"


def test_image_cache_redis_read_failure_checks_local(monkeypatch):
    clients = _patch_redis(monkeypatch)
    b = bare_brain()
    name = b.cache_image(b"only-redis")
    clients[0].fail_get = True
    assert b.get_cached_image(name) is None  # not in local either


# ─── chat store / agent2 redis reinit ───────────────────────────────────

def test_reinit_chat_store_simple_without_redis(monkeypatch):
    from llama_index.core.storage.chat_store import SimpleChatStore

    monkeypatch.setattr(config, "build_redis_url", lambda: None)
    b = bare_brain()
    b.reinit_chat_store()
    assert isinstance(b.chat_store, SimpleChatStore)
    assert b._agent2_redis is None
    assert b._agent2_redis_url is None


def test_reinit_chat_store_redis_when_configured(monkeypatch):
    import restai.brain as brain_mod

    class FakeStore:
        def __init__(self, redis_url):
            self.redis_url = redis_url

    monkeypatch.setattr(config, "build_redis_url", lambda: "redis://h:6379")
    monkeypatch.setattr(brain_mod, "RedisChatStore", FakeStore)
    b = bare_brain()
    b.reinit_chat_store()
    assert isinstance(b.chat_store, FakeStore)
    assert b.chat_store.redis_url == "redis://h:6379"


def test_reinit_agent2_redis_clears_cached_client():
    b = bare_brain()

    class Client:
        def aclose(self):
            return None
    b._agent2_redis = Client()
    b._agent2_redis_url = "redis://x"
    b.reinit_agent2_redis()
    assert b._agent2_redis is None
    assert b._agent2_redis_url is None


def test_reinit_agent2_redis_swallows_close_errors():
    b = bare_brain()

    class Bad:
        @property
        def aclose(self):
            raise RuntimeError("boom")

        close = aclose
    b._agent2_redis = Bad()
    b.reinit_agent2_redis()  # must not raise
    assert b._agent2_redis is None


def test_reinit_agent2_redis_safe_when_never_built():
    b = bare_brain()
    b.reinit_agent2_redis()
    assert b._agent2_redis is None


def test_reinit_agent2_redis_schedules_aclose_on_running_loop():
    import asyncio

    b = bare_brain()
    closed = []

    class AsyncClient:
        async def aclose(self):
            closed.append(1)

    async def main():
        b._agent2_redis = AsyncClient()
        b._agent2_redis_url = "redis://x"
        b.reinit_agent2_redis()
        await asyncio.sleep(0)  # let the fire-and-forget task run

    asyncio.run(main())
    assert closed == [1]
    assert b._agent2_redis is None


# ─── LLM load / cache-free get ──────────────────────────────────────────

def _llm_row(name="fake-llm", class_name="OpenAI", options='{"model": "m1"}'):
    return types.SimpleNamespace(
        id=1, name=name, class_name=class_name, options=options,
        privacy="public", description="d", input_cost=1.0, output_cost=2.0,
        context_window=4096, teams=[],
    )


class FakeInnerLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.system_prompt = "preset"


def test_load_llm_builds_from_class_and_merges_defaults(monkeypatch):
    import restai.tools as tools_mod

    monkeypatch.setattr(
        tools_mod, "get_llm_class",
        lambda cn: (FakeInnerLLM, {"request_timeout": 99, "model": "default"}),
    )
    db = types.SimpleNamespace(get_llm_by_name=lambda name: _llm_row())
    llm = Brain.load_llm("fake-llm", db)
    assert llm is not None
    assert llm.model_name == "fake-llm"
    # options override defaults; non-conflicting defaults survive.
    assert llm.llm.kwargs == {"request_timeout": 99, "model": "m1"}
    assert llm.props.input_cost == 1.0


def test_load_llm_unknown_returns_none():
    db = types.SimpleNamespace(get_llm_by_name=lambda name: None)
    assert Brain.load_llm("nope", db) is None


def test_get_llm_resets_system_prompt(monkeypatch):
    import restai.tools as tools_mod

    monkeypatch.setattr(tools_mod, "get_llm_class", lambda cn: (FakeInnerLLM, {}))
    db = types.SimpleNamespace(get_llm_by_name=lambda name: _llm_row())
    b = bare_brain()
    llm = b.get_llm("fake-llm", db)
    assert llm.llm.system_prompt is None


def test_get_llm_unknown_returns_none():
    b = bare_brain()
    db = types.SimpleNamespace(get_llm_by_name=lambda name: None)
    assert b.get_llm("nope", db) is None


# ─── system LLM DB read-through ─────────────────────────────────────────

def test_get_system_llm_unset_or_blank_returns_none():
    b = bare_brain()
    db = types.SimpleNamespace(get_setting=lambda key: None)
    assert b.get_system_llm(db) is None

    db = types.SimpleNamespace(get_setting=lambda key: types.SimpleNamespace(value="   "))
    assert b.get_system_llm(db) is None

    db = types.SimpleNamespace(get_setting=lambda key: types.SimpleNamespace(value=None))
    assert b.get_system_llm(db) is None


def test_get_system_llm_reads_setting_every_call():
    b = bare_brain()
    calls = []
    b.get_llm = lambda name, db: calls.append(name) or "the-llm"
    values = iter(["llm-a", "llm-b"])
    db = types.SimpleNamespace(
        get_setting=lambda key: types.SimpleNamespace(value=next(values))
    )
    assert b.get_system_llm(db) == "the-llm"
    assert b.get_system_llm(db) == "the-llm"
    assert calls == ["llm-a", "llm-b"]  # no caching between calls


# ─── embedding cache ────────────────────────────────────────────────────

class FakeEmbeddingImpl:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _embedding_row(name="fake-emb"):
    return types.SimpleNamespace(
        id=1, name=name, class_name="Ollama", options='{"model_name": "e1"}',
        privacy="public", description=None, dimension=384, teams=[],
    )


def test_get_embedding_builds_and_caches(monkeypatch):
    import restai.tools as tools_mod

    monkeypatch.setattr(
        tools_mod, "get_embedding_class",
        lambda cn: (FakeEmbeddingImpl, {"base_url": "http://x"}),
    )
    b = bare_brain()
    db = types.SimpleNamespace(get_embedding_by_name=lambda name: _embedding_row())
    first = b.get_embedding("fake-emb", db)
    assert first is not None
    assert first.embedding.kwargs == {"model_name": "e1", "base_url": "http://x"}
    assert b.embeddings_cache["fake-emb"] is first

    # Second call is served from the cache even if the DB row vanished.
    db_gone = types.SimpleNamespace(get_embedding_by_name=lambda name: None)
    assert b.get_embedding("fake-emb", db_gone) is first


def test_get_embedding_unknown_returns_none():
    b = bare_brain()
    db = types.SimpleNamespace(get_embedding_by_name=lambda name: None)
    assert b.get_embedding("missing", db) is None


# ─── tools / generators listing ─────────────────────────────────────────

def _fn_tool(name):
    from llama_index.core.tools import FunctionTool

    def fn(x: str) -> str:
        """Do the thing."""
        return x
    fn.__name__ = name
    return FunctionTool.from_defaults(fn=fn, name=name, description="t")


def test_get_tools_lazy_loads_once(monkeypatch):
    import restai.tools as tools_mod

    loads = []
    fake = [_fn_tool("alpha"), _fn_tool("beta")]
    monkeypatch.setattr(tools_mod, "load_tools", lambda: loads.append(1) or fake)
    b = bare_brain()
    assert b.get_tools() == fake
    assert b.get_tools() == fake
    assert len(loads) == 1


def test_get_tools_filters_by_name(monkeypatch):
    import restai.tools as tools_mod
    import restai.docker as docker_mod

    fake = [_fn_tool("alpha"), _fn_tool("terminal"), _fn_tool("beta")]
    monkeypatch.setattr(tools_mod, "load_tools", lambda: fake)
    monkeypatch.setattr(docker_mod, "is_enabled", lambda: False)
    b = bare_brain()
    picked = b.get_tools(["alpha", "terminal"])
    assert [t.metadata.name for t in picked] == ["alpha", "terminal"]
    # terminal is registered even without Docker (warns, still present).


def test_get_tools_unknown_names_yield_empty(monkeypatch):
    import restai.tools as tools_mod

    monkeypatch.setattr(tools_mod, "load_tools", lambda: [_fn_tool("alpha")])
    b = bare_brain()
    assert b.get_tools(["nope"]) == []


def _worker(module_tail):
    def worker():
        return "img"
    worker.__module__ = f"restai.image.workers.{module_tail}"
    return worker


def test_get_generators_filtering():
    b = bare_brain()
    dalle, sdxl = _worker("dalle"), _worker("sdxl")
    b.generators = [dalle, sdxl]
    assert b.get_generators() == [dalle, sdxl]
    assert b.get_generators(["sdxl"]) == [sdxl]
    assert b.get_generators(["missing"]) == []


def test_get_audio_generators_filtering():
    b = bare_brain()
    whisper = _worker("whisper")
    b.audio_generators = [whisper]
    assert b.get_audio_generators() == [whisper]
    assert b.get_audio_generators(["whisper"]) == [whisper]
    assert b.get_audio_generators(["other"]) == []


def test_classify_rejects_invalid_model():
    from restai.models.models import ClassifierModel

    b = bare_brain()
    m = ClassifierModel(sequence="hello", labels=["a"], model="not/a-real-model")
    with pytest.raises(ValueError, match="Invalid classifier"):
        b.classify(m)


# ─── post-processing: reasoning + counting ──────────────────────────────

def test_post_processing_reasoning_no_think_passthrough():
    b = bare_brain()
    out = {"answer": "plain answer"}
    assert b.post_processing_reasoning(out) == {"answer": "plain answer"}


def test_post_processing_reasoning_extracts_think_blocks():
    b = bare_brain()
    out = {"answer": "<think>step one</think>final <think>step two</think>answer"}
    result = b.post_processing_reasoning(out)
    assert result["answer"] == "final answer"
    assert result["reasoning"]["output"] == "step one\n\nstep two"
    steps = result["reasoning"]["steps"]
    assert [s["output"] for s in steps] == ["step one", "step two"]
    assert steps[0]["actions"][0]["action"] == "reasoning"


def test_post_processing_reasoning_prepends_to_existing():
    b = bare_brain()
    out = {
        "answer": "<think>thought</think>done",
        "reasoning": {"output": "tool ran", "steps": [{"output": "tool ran"}]},
    }
    result = b.post_processing_reasoning(out)
    assert result["reasoning"]["output"] == "thought\n\ntool ran"
    assert result["reasoning"]["steps"][0]["output"] == "thought"
    assert result["reasoning"]["steps"][1]["output"] == "tool ran"


def test_post_processing_reasoning_empty_think_ignored():
    b = bare_brain()
    out = {"answer": "<think>   </think>real"}
    result = b.post_processing_reasoning(out)
    assert "reasoning" not in result
    assert result["answer"] == "<think>   </think>real"


def test_post_processing_counting_matches_event():
    b = bare_brain()
    ev_other = types.SimpleNamespace(
        prompt="unrelated", prompt_token_count=1, completion_token_count=1)
    ev = types.SimpleNamespace(
        prompt="system stuff…my question", prompt_token_count=42,
        completion_token_count=7)
    b.token_counter = types.SimpleNamespace(llm_token_counts=[ev_other, ev])
    out = {"question": "my question", "answer": "the answer"}
    b.post_processing_counting(out)
    assert out["tokens"] == {"input": 42, "output": 7, "accuracy": "medium"}
    assert b.token_counter.llm_token_counts == []  # consumed


def test_post_processing_counting_fallback_estimates():
    b = bare_brain()
    b.token_counter = types.SimpleNamespace(llm_token_counts=[])
    out = {"question": "what is love", "answer": "baby don't hurt me"}
    b.post_processing_counting(out)
    assert out["tokens"]["accuracy"] == "low"
    assert out["tokens"]["input"] > 0
    assert out["tokens"]["output"] > 0


# ─── find_project ───────────────────────────────────────────────────────

def test_find_project_missing_returns_none():
    b = bare_brain()
    db = types.SimpleNamespace(get_project_by_id=lambda pid: None)
    assert b.find_project(12345, db) is None


def test_find_project_rag_vector_failure_degrades(monkeypatch):
    """A broken vector-store setup must not raise — project loads, vector None."""
    from restai.vectordb import tools as vector_tools

    def boom(project):
        raise RuntimeError("no vector backend")
    monkeypatch.setattr(vector_tools, "find_vector_db", boom)

    row = types.SimpleNamespace(
        id=777, name="unit_rag_proj_x", embeddings="none-emb", type="rag",
        llm="l", system=None, censorship=None, vectorstore="chroma",
        guard=None, human_name=None, human_description=None, creator=None,
        public=False, default_prompt=None, options="{}", team_id=None,
        users=[], team=None, creator_user=None,
    )
    db = types.SimpleNamespace(get_project_by_id=lambda pid: row)
    b = bare_brain()
    project = b.find_project(777, db)
    assert project is not None
    assert project.vector is None
    assert project.props.name == "unit_rag_proj_x"


def test_agent2_session_store_is_plain_dict():
    b = bare_brain()
    b._agent2_sessions["chat1"] = [{"role": "user", "content": "hi"}]
    assert b._agent2_sessions["chat1"][0]["content"] == "hi"
    assert json.dumps(b._agent2_sessions)  # serializable shape
