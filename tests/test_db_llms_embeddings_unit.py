"""Unit tests for restai/db/llms_embeddings.py — LLM/embedding CRUD edges:
encrypted-options round-trips, masked-secret preservation on update,
get_llm_usage/reassign_llm branches, image-generator and speech-to-text CRUD.
Runs against the real sqlite test DB; every row created here is deleted."""
import json
import random
import types

import pytest

from restai.database import open_db_wrapper
from restai.models.databasemodels import ProjectDatabase
from restai.models.models import (
    EmbeddingUpdate,
    LLMModel,
    LLMUpdate,
)
from restai.utils.crypto import (
    LLM_SENSITIVE_KEYS,
    decrypt_sensitive_options,
)

suffix = str(random.randint(0, 1000000))


@pytest.fixture()
def db():
    wrapper = open_db_wrapper()
    created = []
    yield wrapper, created
    for row in created:
        try:
            merged = wrapper.db.merge(row)
            wrapper.db.delete(merged)
        except Exception:
            pass
    wrapper.db.commit()
    wrapper.db.close()


# ─── LLM create: options encrypted at rest ──────────────────────────────

def test_create_llm_encrypts_sensitive_options(db):
    db, created = db
    row = db.create_llm(
        f"enc_llm_{suffix}", "OpenAI",
        json.dumps({"api_key": "topsecret123", "model": "m1"}),
        "public", "unit", 2048, 1.5, 3.0,
    )
    created.append(row)

    stored = json.loads(row.options)
    assert stored["model"] == "m1"
    assert stored["api_key"] != "topsecret123"
    assert stored["api_key"].startswith("$ENC$")

    # Decrypt helper round-trips.
    plain = decrypt_sensitive_options(stored, LLM_SENSITIVE_KEYS)
    assert plain["api_key"] == "topsecret123"

    # And the Pydantic read model transparently decrypts.
    model = LLMModel.model_validate(row)
    assert model.options["api_key"] == "topsecret123"
    assert model.context_window == 2048
    assert model.input_cost == 1.5


def test_create_llm_bad_options_stored_verbatim(db):
    db, created = db
    row = db.create_llm(f"enc_llm_bad_{suffix}", "OpenAI", "not-json", "public", "d")
    created.append(row)
    assert row.options == "not-json"  # encryption failure logged, not raised


# ─── LLM update paths ───────────────────────────────────────────────────

def test_update_llm_scalar_fields(db):
    db, created = db
    row = db.create_llm(f"upd_llm_{suffix}", "OpenAI", "{}", "public", "old desc")
    created.append(row)

    upd = LLMUpdate(
        class_name="OpenAILike", privacy="private", description="new desc",
        input_cost=9.0, output_cost=18.0, context_window=123456,
    )
    assert db.update_llm(row, upd) is True
    fresh = db.get_llm_by_name(f"upd_llm_{suffix}")
    assert fresh.class_name == "OpenAILike"
    assert fresh.privacy == "private"
    assert fresh.description == "new desc"
    assert fresh.input_cost == 9.0
    assert fresh.output_cost == 18.0
    assert fresh.context_window == 123456


def test_update_llm_masked_secret_preserved(db):
    db, created = db
    row = db.create_llm(
        f"mask_llm_{suffix}", "OpenAI",
        json.dumps({"api_key": "real-secret", "model": "m1"}),
        "public", "d",
    )
    created.append(row)

    upd = LLMUpdate(options={"api_key": "********", "model": "m2"})
    db.update_llm(row, upd)

    stored = json.loads(db.get_llm_by_name(f"mask_llm_{suffix}").options)
    assert stored["model"] == "m2"
    plain = decrypt_sensitive_options(stored, LLM_SENSITIVE_KEYS)
    assert plain["api_key"] == "real-secret"  # mask kept the stored secret


def test_update_llm_masked_secret_without_existing_dropped(db):
    db, created = db
    row = db.create_llm(
        f"masknone_llm_{suffix}", "OpenAI", json.dumps({"model": "m1"}),
        "public", "d",
    )
    created.append(row)

    upd = LLMUpdate(options={"api_key": "********", "model": "m3"})
    db.update_llm(row, upd)
    stored = json.loads(db.get_llm_by_name(f"masknone_llm_{suffix}").options)
    assert "api_key" not in stored
    assert stored["model"] == "m3"


def test_update_llm_new_secret_encrypted(db):
    db, created = db
    row = db.create_llm(f"newsec_llm_{suffix}", "OpenAI", "{}", "public", "d")
    created.append(row)

    db.update_llm(row, LLMUpdate(options={"api_key": "fresh-secret"}))
    stored = json.loads(db.get_llm_by_name(f"newsec_llm_{suffix}").options)
    assert stored["api_key"].startswith("$ENC$")
    assert decrypt_sensitive_options(stored, LLM_SENSITIVE_KEYS)["api_key"] == "fresh-secret"


# ─── embedding create / update ──────────────────────────────────────────

def test_embedding_crud_round_trip(db):
    db, created = db
    row = db.create_embedding(
        f"unit_emb_{suffix}", "Ollama", json.dumps({"model_name": "e1"}),
        "private", "emb desc", 384,
    )
    created.append(row)
    assert db.get_embedding_by_name(f"unit_emb_{suffix}").id == row.id
    assert db.get_embedding_by_id(row.id).name == f"unit_emb_{suffix}"

    upd = EmbeddingUpdate(
        class_name="LangChain.Openai", privacy="public", description="new",
        dimension=1536, options={"model_name": "e2"},
    )
    assert db.update_embedding(row, upd) is True
    fresh = db.get_embedding_by_name(f"unit_emb_{suffix}")
    assert fresh.class_name == "LangChain.Openai"
    assert fresh.privacy == "public"
    assert fresh.description == "new"
    assert fresh.dimension == 1536
    assert json.loads(fresh.options)["model_name"] == "e2"


def test_update_embedding_masked_secret_preserved(db):
    db, created = db
    row = db.create_embedding(
        f"unit_emb_mask_{suffix}", "Ollama",
        json.dumps({"api_key": "emb-secret", "model_name": "e1"}),
        "public", None, 128,
    )
    created.append(row)

    upd = EmbeddingUpdate(options={"api_key": "********", "model_name": "e9"})
    db.update_embedding(row, upd)
    stored = json.loads(db.get_embedding_by_name(f"unit_emb_mask_{suffix}").options)
    assert stored["api_key"] == "emb-secret"  # embeddings store plaintext; mask preserved
    assert stored["model_name"] == "e9"


def test_update_llm_unparseable_options_stored_verbatim(db):
    db, created = db
    row = db.create_llm(f"badopt_llm_{suffix}", "OpenAI", "{}", "public", "d")
    created.append(row)
    db.update_llm(row, LLMUpdate(options="def-not-json"))
    assert db.get_llm_by_name(f"badopt_llm_{suffix}").options == "def-not-json"


def test_get_lists_and_by_id(db):
    db, created = db
    llm = db.create_llm(f"list_llm_{suffix}", "OpenAI", "{}", "public", "d")
    emb = db.create_embedding(f"list_emb_{suffix}", "Ollama", "{}", "public", "d", 4)
    created.extend([llm, emb])
    assert any(r.id == llm.id for r in db.get_llms())
    assert any(r.id == emb.id for r in db.get_embeddings())
    assert db.get_llm_by_id(llm.id).name == llm.name
    assert db.get_llm_by_id(-1) is None


def test_delete_llm_and_embedding(db):
    db, _ = db
    llm = db.create_llm(f"del_llm_{suffix}", "OpenAI", "{}", "public", "d")
    emb = db.create_embedding(f"del_emb_{suffix}", "Ollama", "{}", "public", "d", 8)
    assert db.delete_llm(llm) is True
    assert db.delete_embedding(emb) is True
    assert db.get_llm_by_name(f"del_llm_{suffix}") is None
    assert db.get_embedding_by_name(f"del_emb_{suffix}") is None


# ─── get_llm_usage / reassign_llm ───────────────────────────────────────

@pytest.fixture()
def usage_projects(db):
    db_w, created = db
    old = f"usage_old_{suffix}"
    p_main = ProjectDatabase(
        name=f"usage_p_main_{suffix}", type="agent", llm=old, options="{}")
    p_opts = ProjectDatabase(
        name=f"usage_p_opts_{suffix}", type="rag", llm="something-else",
        options=json.dumps({"eval_llm": old, "rerank_llm": old, "k": 3}))
    p_both = ProjectDatabase(
        name=f"usage_p_both_{suffix}", type="rag", llm=old,
        options=json.dumps({"rerank_llm": old, "guard_output": "7"}))
    p_none = ProjectDatabase(
        name=f"usage_p_none_{suffix}", type="agent", llm="unrelated",
        options="not json at all")
    db_w.db.add_all([p_main, p_opts, p_both, p_none])
    db_w.db.commit()
    created.extend([p_main, p_opts, p_both, p_none])
    return db_w, old, p_main, p_opts, p_both, p_none


def test_get_llm_usage_branches(usage_projects):
    db, old, p_main, p_opts, p_both, p_none = usage_projects
    usage = {u["name"]: u for u in db.get_llm_usage(old)}
    assert usage[p_main.name]["fields"] == ["llm"]
    assert usage[p_opts.name]["fields"] == ["eval_llm", "rerank_llm"]
    assert usage[p_both.name]["fields"] == ["llm", "rerank_llm"]
    assert p_none.name not in usage
    assert usage[p_main.name]["id"] == p_main.id


def test_reassign_llm_repoints_and_preserves_other_keys(usage_projects):
    db, old, p_main, p_opts, p_both, p_none = usage_projects
    new = f"usage_new_{suffix}"
    changed = db.reassign_llm(old, new)
    assert changed == 3

    db.db.refresh(p_main)
    db.db.refresh(p_opts)
    db.db.refresh(p_both)
    db.db.refresh(p_none)

    assert p_main.llm == new
    opts = json.loads(p_opts.options)
    assert opts["eval_llm"] == new
    assert opts["rerank_llm"] == new
    assert opts["k"] == 3  # untouched sibling key preserved

    both_opts = json.loads(p_both.options)
    assert p_both.llm == new
    assert both_opts["rerank_llm"] == new
    assert both_opts["guard_output"] == "7"

    assert p_none.llm == "unrelated"

    # Old name no longer referenced; second reassign is a no-op.
    assert db.get_llm_usage(old) == []
    assert db.reassign_llm(old, new) == 0


# ─── image generators ───────────────────────────────────────────────────

def test_image_generator_crud_and_mask(db):
    db, created = db
    gen = db.create_image_generator(
        f"unit_gen_{suffix}", "openai",
        {"api_key": "gen-secret", "model": "gpt-image-1"},
        privacy="public", description="d", enabled=True,
    )
    created.append(gen)
    stored = json.loads(gen.options)
    assert stored["api_key"].startswith("$ENC$")
    assert db.get_image_generator_by_name(f"unit_gen_{suffix}").id == gen.id
    assert db.get_image_generator_by_id(gen.id).name == f"unit_gen_{suffix}"
    assert any(g.id == gen.id for g in db.get_image_generators())

    upd = types.SimpleNamespace(
        class_name=None, privacy=None, description=None, enabled=False,
        options=json.dumps({"api_key": "********", "model": "gpt-image-2"}),
    )
    assert db.edit_image_generator(gen, upd) is True
    fresh = db.get_image_generator_by_id(gen.id)
    assert fresh.enabled is False
    opts = json.loads(fresh.options)
    assert opts["model"] == "gpt-image-2"
    assert decrypt_sensitive_options(opts, LLM_SENSITIVE_KEYS)["api_key"] == "gen-secret"


def test_image_generator_edit_scalar_fields_and_mask_drop(db):
    db, created = db
    gen = db.create_image_generator(f"unit_gen4_{suffix}", "openai", {"model": "m"})
    created.append(gen)
    upd = types.SimpleNamespace(
        class_name="google", privacy="private", description="new desc",
        enabled=None,
        options=json.dumps({"api_key": "********", "model": "m2"}),
    )
    assert db.edit_image_generator(gen, upd) is True
    fresh = db.get_image_generator_by_id(gen.id)
    assert fresh.class_name == "google"
    assert fresh.privacy == "private"
    assert fresh.description == "new desc"
    opts = json.loads(fresh.options)
    assert "api_key" not in opts  # mask with no stored secret → dropped
    assert opts["model"] == "m2"


def test_image_generator_edit_noop_returns_false(db):
    db, created = db
    gen = db.create_image_generator(f"unit_gen2_{suffix}", "openai", {}, enabled=True)
    created.append(gen)
    upd = types.SimpleNamespace(
        class_name=None, privacy=None, description=None, enabled=None, options=None)
    assert db.edit_image_generator(gen, upd) is False


def test_image_generator_delete(db):
    db, _ = db
    gen = db.create_image_generator(f"unit_gen3_{suffix}", "openai", {})
    assert db.delete_image_generator(gen) is True
    assert db.get_image_generator_by_name(f"unit_gen3_{suffix}") is None


# ─── speech-to-text ─────────────────────────────────────────────────────

def test_speech_to_text_crud_and_mask(db):
    db, created = db
    stt = db.create_speech_to_text(
        f"unit_stt_{suffix}", "openai", {"api_key": "stt-secret", "model": "whisper-1"},
    )
    created.append(stt)
    assert json.loads(stt.options)["api_key"].startswith("$ENC$")
    assert db.get_speech_to_text_by_name(f"unit_stt_{suffix}").id == stt.id
    assert db.get_speech_to_text_by_id(stt.id).name == f"unit_stt_{suffix}"
    assert any(m.id == stt.id for m in db.get_speech_to_text())

    upd = types.SimpleNamespace(
        class_name="deepgram", privacy="private", description="upd", enabled=False,
        options=json.dumps({"api_key": "********", "model": "nova"}),
    )
    assert db.edit_speech_to_text(stt, upd) is True
    fresh = db.get_speech_to_text_by_id(stt.id)
    assert fresh.class_name == "deepgram"
    assert fresh.privacy == "private"
    assert fresh.enabled is False
    opts = json.loads(fresh.options)
    assert opts["model"] == "nova"
    assert decrypt_sensitive_options(opts, LLM_SENSITIVE_KEYS)["api_key"] == "stt-secret"


def test_speech_to_text_delete(db):
    db, _ = db
    stt = db.create_speech_to_text(f"unit_stt2_{suffix}", "openai", {})
    assert db.delete_speech_to_text(stt) is True
    assert db.get_speech_to_text_by_name(f"unit_stt2_{suffix}") is None
