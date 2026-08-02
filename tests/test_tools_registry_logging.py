"""Unit tests for restai/tools.py — userland dir resolution, tool loading /
dedup, secret redaction, log_inference edge paths and API-key token bumping.
DB tests use the real sqlite test database via open_db_wrapper."""
import json
import random
import sys
import types
from datetime import datetime, timezone

import pytest

from restai import tools as tools_mod
from restai.database import open_db_wrapper
from restai.models.databasemodels import (
    ApiKeyDatabase,
    LLMDatabase,
    OutputDatabase,
    UserDatabase,
)

suffix = str(random.randint(0, 1000000))


# ─── _userland_dir ──────────────────────────────────────────────────────

def test_userland_dir_resolves_real_subdir_to_install_root():
    path = tools_mod._userland_dir("tools")
    assert path is not None
    assert path.endswith("/userland/tools")
    install_root = path[: -len("/userland/tools")]
    # Anchored to the parent of the restai/ package, not the CWD.
    import restai
    import os
    assert install_root == os.path.dirname(os.path.dirname(os.path.abspath(restai.__file__)))
    assert install_root in sys.path


def test_userland_dir_missing_subdir_returns_none():
    assert tools_mod._userland_dir("definitely_not_a_dir_zzz") is None


# ─── load_tools ─────────────────────────────────────────────────────────

def test_load_tools_core_registry(monkeypatch):
    monkeypatch.setattr(tools_mod, "_userland_dir", lambda subdir: None)
    loaded = tools_mod.load_tools()
    names = [t.metadata.name for t in loaded]

    # Known builtins are present.
    assert "data_parser" in names
    assert "search_knowledge" in names
    assert "moderate_content" in names

    # No private helpers, no imported phantom symbols.
    assert not any(n.startswith("_") for n in names)
    assert "urlparse" not in names

    # Names are unique.
    assert len(names) == len(set(names))


def test_load_tools_userland_override_and_addition(monkeypatch, tmp_path):
    """A userland module can add a new tool and override a core one by name."""
    # Files only need to exist for pkgutil discovery; the import is served
    # from sys.modules below.
    (tmp_path / "zz_unit_fake.py").write_text("")

    mod = types.ModuleType("userland.tools.zz_unit_fake")

    def data_parser(data: str) -> str:
        """Overridden parser."""
        return "overridden"

    def zz_unit_helper(x: str) -> str:
        """A brand new userland tool."""
        return x

    data_parser.__module__ = mod.__name__
    zz_unit_helper.__module__ = mod.__name__
    mod.data_parser = data_parser
    mod.zz_unit_helper = zz_unit_helper

    monkeypatch.setattr(tools_mod, "_userland_dir", lambda subdir: str(tmp_path))
    monkeypatch.setitem(sys.modules, "userland.tools.zz_unit_fake", mod)

    loaded = tools_mod.load_tools()
    by_name = {t.metadata.name: t for t in loaded}

    assert "zz_unit_helper" in by_name
    # Core data_parser was replaced by the userland one (no duplicate).
    names = [t.metadata.name for t in loaded]
    assert names.count("data_parser") == 1
    assert "Overridden parser" in by_name["data_parser"].metadata.description


# ─── class-name dispatch tables ─────────────────────────────────────────

@pytest.mark.parametrize("class_name", [
    "Ollama", "OllamaCloud", "OllamaMultiModal", "OllamaMultiModal2",
    "OpenAI", "OpenAILike", "Grok", "Anthropic", "LiteLLM", "vLLM",
    "Gemini", "GeminiMultiModal", "AzureOpenAI", "Bedrock",
])
def test_get_llm_class_table(class_name):
    cls, defaults = tools_mod.get_llm_class(class_name)
    assert isinstance(cls, type)
    assert defaults is None or isinstance(defaults, dict)
    if class_name.startswith("Ollama"):
        assert defaults["request_timeout"] == 120.0
    if class_name == "Grok":
        assert defaults["base_url"] == "https://api.x.ai/"


def test_get_llm_class_invalid_raises():
    with pytest.raises(Exception, match="Invalid LLM class name"):
        tools_mod.get_llm_class("NotAClass")


@pytest.mark.parametrize("class_name", [
    "LangChain", "LangChain.Openai", "LangChain.HuggingFace",
    "Ollama", "OllamaEmbeddings",
])
def test_get_embedding_class_table(class_name):
    cls, defaults = tools_mod.get_embedding_class(class_name)
    assert isinstance(cls, type)
    assert defaults == {}


def test_get_embedding_class_invalid_raises():
    with pytest.raises(Exception, match="Invalid embedding class name"):
        tools_mod.get_embedding_class("NotAClass")


# ─── image / audio generator loading ────────────────────────────────────

def _generator_env(monkeypatch, kind):
    """Fake pkgutil discovery + sys.modules so the loaders exercise their
    core-loop, userland-override and userland-append branches without
    importing any real (GPU-flavoured) worker module."""
    import pkgutil

    def make_mod(fullname):
        mod = types.ModuleType(fullname)

        def worker():
            return fullname
        worker.__module__ = fullname
        mod.worker = worker
        return mod

    core = make_mod(f"restai.{kind}.workers.coregen")
    over = make_mod(f"userland.{kind}.coregen")   # same tail → override
    newg = make_mod(f"userland.{kind}.newgen")

    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setitem(sys.modules, over.__name__, over)
    monkeypatch.setitem(sys.modules, newg.__name__, newg)

    userland_path = f"/fake/userland/{kind}"
    monkeypatch.setattr(tools_mod, "_userland_dir", lambda subdir: userland_path)

    def fake_iter_modules(path=None):
        if path == [userland_path]:
            return [(None, "coregen", False), (None, "newgen", False)]
        return [(None, "coregen", False)]

    monkeypatch.setattr(pkgutil, "iter_modules", fake_iter_modules)
    return core, over, newg


def test_load_image_generators_userland_override(monkeypatch):
    core, over, newg = _generator_env(monkeypatch, "image")
    gens = tools_mod.load_image_generators()
    mods = [g.__module__ for g in gens]
    # Core worker replaced by the userland one with the same module tail.
    assert "restai.image.workers.coregen" not in mods
    assert "userland.image.coregen" in mods
    assert "userland.image.newgen" in mods
    assert len(gens) == 2


def test_load_audio_generators_userland_override(monkeypatch):
    _generator_env(monkeypatch, "audio")
    gens = tools_mod.load_audio_generators()
    mods = [g.__module__ for g in gens]
    assert mods == ["userland.audio.coregen", "userland.audio.newgen"]


def test_load_generators_without_userland(monkeypatch):
    _generator_env(monkeypatch, "image")
    monkeypatch.setattr(tools_mod, "_userland_dir", lambda subdir: None)
    gens = tools_mod.load_image_generators()
    assert [g.__module__ for g in gens] == ["restai.image.workers.coregen"]


# ─── redaction + token counting ─────────────────────────────────────────

def test_redact_secrets_patterns():
    red = tools_mod._redact_secrets
    assert "[REDACTED]" in red("key sk-" + "a" * 24 + " done")
    assert "[REDACTED]" in red("token xoxb-" + "1" * 12)
    assert "[REDACTED]" in red("Authorization: Bearer " + "t" * 24)
    assert "[REDACTED]" in red("hash " + "f" * 40)
    assert "[REDACTED]" in red("mysql://user:hunter22@dbhost/x")
    assert red("nothing secret here") == "nothing secret here"


def test_redact_secrets_non_string_passthrough():
    assert tools_mod._redact_secrets(None) is None
    assert tools_mod._redact_secrets("") == ""
    assert tools_mod._redact_secrets(123) == 123


def test_tokens_from_string_counts():
    assert tools_mod.tokens_from_string("hello world") > 0
    assert tools_mod.tokens_from_string("") == 0


# ─── log_inference ──────────────────────────────────────────────────────

def _project(llm=None, team=None, logging=True, redact=False, pid=None):
    return types.SimpleNamespace(props=types.SimpleNamespace(
        id=pid, llm=llm, team=team,
        options=types.SimpleNamespace(
            redact_inference_logs=redact, logging=logging),
    ))


def _fetch_last_row(db, chat_id):
    return (
        db.db.query(OutputDatabase)
        .filter(OutputDatabase.chat_id == chat_id)
        .order_by(OutputDatabase.id.desc())
        .first()
    )


@pytest.fixture()
def db():
    wrapper = open_db_wrapper()
    yield wrapper
    wrapper.db.close()


@pytest.fixture()
def admin_id(db):
    row = db.db.query(UserDatabase).order_by(UserDatabase.id).first()
    assert row is not None, "test DB must have at least one user"
    return row.id


def test_log_inference_writes_row_with_cost(db, admin_id):
    llm_name = f"logtest_llm_{suffix}"
    db.create_llm(llm_name, "OpenAI", "{}", "public", "unit", 4096, 2.0, 4.0)
    chat_id = f"unit_chat_{suffix}_a"
    try:
        output = {
            "question": "what is up",
            "answer": "not much",
            "tokens": {"input": 1000, "output": 500},
            "id": chat_id,
            "tool_trace": [{"tool": "terminal", "latency_ms": 5, "status": "ok"}],
        }
        user = types.SimpleNamespace(id=admin_id, api_key_id=None)
        tools_mod.log_inference(
            _project(llm=llm_name), user, output, db,
            latency_ms=123, system_prompt="sys", context={"k": "v"},
        )
        row = _fetch_last_row(db, chat_id)
        assert row is not None
        assert row.question == "what is up"
        assert row.answer == "not much"
        assert row.input_tokens == 1000
        assert row.output_tokens == 500
        assert row.input_cost == pytest.approx(0.002)   # 1000 * 2.0 / 1e6
        assert row.output_cost == pytest.approx(0.002)  # 500 * 4.0 / 1e6
        assert row.latency_ms == 123
        assert row.system_prompt == "sys"
        assert json.loads(row.context) == {"k": "v"}
        assert row.status == "success"
        assert json.loads(row.tool_trace)[0]["tool"] == "terminal"
        assert row.llm == llm_name
        assert row.team_id is None
        assert row.project_id is None
    finally:
        row = _fetch_last_row(db, chat_id)
        if row:
            db.db.delete(row)
        llm = db.get_llm_by_name(llm_name)
        if llm:
            db.db.delete(llm)
        db.db.commit()


def test_log_inference_logging_disabled_strips_content(db, admin_id):
    chat_id = f"unit_chat_{suffix}_b"
    try:
        output = {
            "question": "secret question",
            "answer": "secret answer",
            "tokens": {"input": 10, "output": 5},
            "id": chat_id,
            "tool_trace": [{"tool": "x"}],
            "attachments": [{"name": "f.txt"}],
        }
        user = types.SimpleNamespace(id=admin_id, api_key_id=None)
        tools_mod.log_inference(
            _project(logging=False), user, output, db,
            system_prompt="sys", context={"c": 1},
        )
        row = _fetch_last_row(db, chat_id)
        assert row.question is None
        assert row.answer is None
        assert row.system_prompt is None
        assert row.context is None
        assert row.tool_trace is None
        assert row.attachments is None
        # Token accounting still recorded.
        assert row.input_tokens == 10
        assert row.output_tokens == 5
    finally:
        row = _fetch_last_row(db, chat_id)
        if row:
            db.db.delete(row)
            db.db.commit()


def test_log_inference_redaction_toggle(db, admin_id):
    chat_id = f"unit_chat_{suffix}_c"
    try:
        secret = "sk-" + "z" * 30
        output = {
            "question": f"my key is {secret}",
            "answer": f"got {secret} thanks",
            "tokens": {"input": 1, "output": 1},
            "id": chat_id,
        }
        user = types.SimpleNamespace(id=admin_id, api_key_id=None)
        tools_mod.log_inference(_project(redact=True), user, output, db)
        row = _fetch_last_row(db, chat_id)
        assert secret not in row.question
        assert "[REDACTED]" in row.question
        assert secret not in row.answer
    finally:
        row = _fetch_last_row(db, chat_id)
        if row:
            db.db.delete(row)
            db.db.commit()


def test_log_inference_error_truncated_and_missing_tokens(db, admin_id):
    chat_id = f"unit_chat_{suffix}_d"
    try:
        output = {
            "question": "q",
            "answer": None,
            "id": chat_id,
            "status": "error",
            "error": "E" * 9000,
        }
        user = types.SimpleNamespace(id=admin_id, api_key_id=None)
        tools_mod.log_inference(_project(), user, output, db)
        row = _fetch_last_row(db, chat_id)
        assert row.status == "error"
        assert row.input_tokens == 0 and row.output_tokens == 0
        assert len(row.error) < 9000
        assert row.error.endswith("…[truncated]")
    finally:
        row = _fetch_last_row(db, chat_id)
        if row:
            db.db.delete(row)
            db.db.commit()


# ─── record_api_key_tokens ──────────────────────────────────────────────

def _make_api_key(db, user_id):
    key = ApiKeyDatabase(
        user_id=user_id,
        key_hash=f"unit-hash-{suffix}-{random.randint(0, 10**9)}",
        encrypted_key="unit-enc",
        key_prefix="restai-u",
        description="unit test key",
        created_at=datetime.now(timezone.utc),
        tokens_used_this_month=0,
    )
    db.db.add(key)
    db.db.commit()
    db.db.refresh(key)
    return key


def test_record_api_key_tokens_bumps_counter(db, admin_id):
    from restai.limits.budget import record_api_key_tokens

    key = _make_api_key(db, admin_id)
    try:
        record_api_key_tokens(key.id, 150, db)
        db.db.refresh(key)
        assert key.tokens_used_this_month == 150
        record_api_key_tokens(key.id, 50, db)
        db.db.refresh(key)
        assert key.tokens_used_this_month == 200
    finally:
        db.db.delete(key)
        db.db.commit()


def test_record_api_key_tokens_noops(db):
    from restai.limits.budget import record_api_key_tokens

    # All of these must be silent no-ops.
    record_api_key_tokens(None, 100, db)
    record_api_key_tokens(0, 100, db)
    record_api_key_tokens(999999999, 100, db)  # missing key


def test_log_inference_bumps_api_key_quota(db, admin_id):
    chat_id = f"unit_chat_{suffix}_e"
    key = _make_api_key(db, admin_id)
    try:
        output = {
            "question": "q", "answer": "a",
            "tokens": {"input": 70, "output": 30},
            "id": chat_id,
        }
        user = types.SimpleNamespace(id=admin_id, api_key_id=key.id)
        tools_mod.log_inference(_project(), user, output, db)
        db.db.refresh(key)
        assert key.tokens_used_this_month == 100
        row = _fetch_last_row(db, chat_id)
        assert row.api_key_id == key.id
    finally:
        row = _fetch_last_row(db, chat_id)
        if row:
            db.db.delete(row)
        db.db.delete(key)
        db.db.commit()


# ─── retrieval + guard event logs ───────────────────────────────────────

FAKE_PROJECT_ID = 910000 + random.randint(0, 9999)


def test_log_retrieval_events_rows(db):
    from restai.models.databasemodels import RetrievalEventDatabase

    project = _project(pid=FAKE_PROJECT_ID)
    sources = [
        {"source": "doc.pdf", "score": 0.9, "id": "c1", "text": "chunk text"},
        {"source": "other.md", "text": ""},
        {"score": 0.5, "text": "no source key -> skipped"},
        "bare-string-source",
    ]
    try:
        tools_mod.log_retrieval_events(project, sources, db)
        rows = (
            db.db.query(RetrievalEventDatabase)
            .filter(RetrievalEventDatabase.project_id == FAKE_PROJECT_ID)
            .all()
        )
        by_source = {r.source: r for r in rows}
        assert set(by_source) == {"doc.pdf", "other.md", "bare-string-source"}
        assert by_source["doc.pdf"].score == 0.9
        assert by_source["doc.pdf"].chunk_id == "c1"
        assert by_source["doc.pdf"].chunk_text_length == len("chunk text")
        assert by_source["doc.pdf"].chunk_token_length > 0
        assert by_source["other.md"].chunk_text_length is None
        assert by_source["bare-string-source"].score is None
    finally:
        db.db.query(RetrievalEventDatabase).filter(
            RetrievalEventDatabase.project_id == FAKE_PROJECT_ID
        ).delete(synchronize_session=False)
        db.db.commit()


def test_log_guard_event_respects_logging_toggle(db, admin_id):
    from restai.models.databasemodels import GuardEventDatabase

    user = types.SimpleNamespace(id=admin_id)
    try:
        tools_mod.log_guard_event(
            _project(pid=FAKE_PROJECT_ID, logging=True), "guard-proj", user,
            "input", "block", "strict", "checked text", "DENY", db)
        tools_mod.log_guard_event(
            _project(pid=FAKE_PROJECT_ID, logging=False), "guard-proj", None,
            "output", "allow", "lenient", "hidden text", "OK", db)

        rows = (
            db.db.query(GuardEventDatabase)
            .filter(GuardEventDatabase.project_id == FAKE_PROJECT_ID)
            .order_by(GuardEventDatabase.id)
            .all()
        )
        assert len(rows) == 2
        assert rows[0].text_checked == "checked text"
        assert rows[0].user_id == admin_id
        assert rows[0].guard_project == "guard-proj"
        assert rows[1].text_checked is None  # logging off strips the text
        assert rows[1].user_id is None
        assert rows[1].guard_response == "OK"
    finally:
        db.db.query(GuardEventDatabase).filter(
            GuardEventDatabase.project_id == FAKE_PROJECT_ID
        ).delete(synchronize_session=False)
        db.db.commit()


def test_llm_row_options_are_text(db):
    """Sanity: create_llm stores options as a JSON text blob."""
    name = f"logtest_llm2_{suffix}"
    row = db.create_llm(name, "OpenAI", '{"model": "m"}', "public", "d")
    try:
        assert isinstance(row, LLMDatabase)
        assert json.loads(row.options)["model"] == "m"
    finally:
        db.db.delete(row)
        db.db.commit()
