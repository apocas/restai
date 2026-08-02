"""Smart Search (restai/utils/search_ai.py) — LLM-response parsing, DSL
whitelist validation, RBAC scoping, and the run_search pipeline with a
faked System LLM emitting JSON."""

import asyncio
import json
import random
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.utils import search_ai

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
suffix = str(random.randint(0, 10_000_000))
state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ─── parse_llm_response ─────────────────────────────────────────────────

def test_parse_plain_json():
    assert search_ai.parse_llm_response('{"entity": "projects"}') == {"entity": "projects"}


def test_parse_fenced_json():
    text = 'Sure!\n```json\n{"entity": "users", "filters": []}\n```'
    assert search_ai.parse_llm_response(text) == {"entity": "users", "filters": []}


def test_parse_json_embedded_in_prose():
    text = 'Here you go: {"entity": "teams", "limit": 5} — hope that helps.'
    assert search_ai.parse_llm_response(text) == {"entity": "teams", "limit": 5}


def test_parse_garbage_returns_none():
    assert search_ai.parse_llm_response("no json here at all") is None
    assert search_ai.parse_llm_response("") is None
    assert search_ai.parse_llm_response("{broken: json {") is None
    # Braces found but the slice still isn't JSON.
    assert search_ai.parse_llm_response("prose {not: json} more prose") is None


# ─── validate_query ─────────────────────────────────────────────────────

def test_validate_unknown_entity_rejected():
    with pytest.raises(ValueError, match="Unknown entity"):
        search_ai.validate_query({"entity": "secrets"})


def test_validate_non_dict_rejected():
    with pytest.raises(ValueError):
        search_ai.validate_query(["not", "a", "dict"])


def test_validate_unknown_field_dropped_with_warning():
    cleaned, warnings = search_ai.validate_query({
        "entity": "projects",
        "filters": [{"field": "password", "op": "eq", "value": "x"},
                    {"field": "name", "op": "contains", "value": "a"}],
    })
    assert cleaned["filters"] == [{"field": "name", "op": "contains", "value": "a"}]
    assert any("unknown field" in w.lower() for w in warnings)


def test_validate_unsupported_op_dropped():
    cleaned, warnings = search_ai.validate_query({
        "entity": "users",
        "filters": [{"field": "username", "op": "gt", "value": "a"}],
    })
    assert cleaned["filters"] == []
    assert any("unsupported op" in w for w in warnings)


def test_validate_bool_string_coercion():
    cleaned, _ = search_ai.validate_query({
        "entity": "users",
        "filters": [{"field": "is_admin", "op": "eq", "value": "true"},
                    {"field": "is_restricted", "op": "eq", "value": "no"}],
    })
    assert cleaned["filters"][0]["value"] is True
    assert cleaned["filters"][1]["value"] is False


def test_validate_int_coercion_and_bad_int():
    cleaned, warnings = search_ai.validate_query({
        "entity": "llms",
        "filters": [{"field": "context_window", "op": "gte", "value": "4096"},
                    {"field": "context_window", "op": "lt", "value": "lots"}],
    })
    assert cleaned["filters"] == [{"field": "context_window", "op": "gte", "value": 4096}]
    assert any("non-int" in w for w in warnings)


def test_validate_enum_out_of_range_dropped():
    cleaned, warnings = search_ai.validate_query({
        "entity": "projects",
        "filters": [{"field": "type", "op": "eq", "value": "vision"}],
    })
    assert cleaned["filters"] == []
    assert any("out-of-range" in w for w in warnings)


def test_validate_limit_clamped():
    cleaned, _ = search_ai.validate_query({"entity": "teams", "limit": 5000})
    assert cleaned["limit"] == 100
    cleaned, _ = search_ai.validate_query({"entity": "teams", "limit": -3})
    assert cleaned["limit"] == 1
    cleaned, _ = search_ai.validate_query({"entity": "teams", "limit": "abc"})
    assert cleaned["limit"] == 20
    cleaned, _ = search_ai.validate_query({"entity": "teams"})
    assert cleaned["limit"] == 20


def test_validate_non_dict_filters_skipped():
    cleaned, _ = search_ai.validate_query({
        "entity": "teams", "filters": ["bogus", {"field": "name", "op": "eq", "value": 3}]})
    # non-dict skipped; str-typed field coerces value to str
    assert cleaned["filters"] == [{"field": "name", "op": "eq", "value": "3"}]


# ─── execute_query + RBAC against the real DB ───────────────────────────

def test_setup_projects(client):
    r = client.post("/teams", json={"name": f"ssrch_team_{suffix}"}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]
    for i in ("one", "two"):
        r = client.post(
            "/projects",
            json={"name": f"ssrch_{i}_{suffix}", "type": "block", "team_id": state["team_id"]},
            auth=ADMIN)
        assert r.status_code == 201, r.text
        state[i] = r.json()["project"]


def _admin_user():
    return SimpleNamespace(is_admin=True)


def _db():
    from restai.database import DBWrapper
    return DBWrapper()


def test_execute_query_admin_sees_all_matches(client):
    db = _db()
    try:
        cleaned, warnings = search_ai.validate_query({
            "entity": "projects",
            "filters": [{"field": "name", "op": "contains", "value": "ssrch_"},
                        {"field": "name", "op": "contains", "value": suffix}],
        })
        assert warnings == []
        rows = search_ai.execute_query(db, _admin_user(), cleaned)
        ids = {r["id"] for r in rows}
        assert {state["one"], state["two"]} <= ids
        assert all(r["entity"] == "projects" and r["path"].startswith("/project/") for r in rows)
    finally:
        db.db.close()


def test_execute_query_rbac_limits_non_admin_to_assigned_projects(client):
    db = _db()
    try:
        user = SimpleNamespace(
            is_admin=False,
            projects=[SimpleNamespace(id=state["one"])],
            admin_teams=[],
        )
        cleaned = {"entity": "projects", "limit": 50,
                   "filters": [{"field": "name", "op": "contains", "value": suffix}]}
        rows = search_ai.execute_query(db, user, cleaned)
        ids = {r["id"] for r in rows}
        assert ids == {state["one"]}
    finally:
        db.db.close()


def test_execute_query_rbac_team_admin_sees_team_projects(client):
    db = _db()
    try:
        user = SimpleNamespace(
            is_admin=False,
            projects=[],
            admin_teams=[SimpleNamespace(id=state["team_id"], users=[], admins=[])],
        )
        cleaned = {"entity": "projects", "limit": 50,
                   "filters": [{"field": "name", "op": "contains", "value": suffix}]}
        rows = search_ai.execute_query(db, user, cleaned)
        ids = {r["id"] for r in rows}
        assert ids == {state["one"], state["two"]}
    finally:
        db.db.close()


def test_execute_query_users_rbac_self_only(client):
    db = _db()
    try:
        from restai.models.databasemodels import UserDatabase
        admin_row = db.db.query(UserDatabase).filter(UserDatabase.username == "admin").first()
        user = SimpleNamespace(is_admin=False, id=admin_row.id, admin_teams=[], teams=[])
        cleaned = {"entity": "users", "limit": 50,
                   "filters": [{"field": "username", "op": "contains", "value": "admin"}]}
        rows = search_ai.execute_query(db, user, cleaned)
        assert [r["name"] for r in rows] == ["admin"]
        assert "admin" in rows[0]["subtitle"]
    finally:
        db.db.close()


def test_execute_query_llms_rbac_no_teams_no_results(client):
    db = _db()
    try:
        user = SimpleNamespace(is_admin=False, teams=[], admin_teams=[])
        cleaned = {"entity": "llms", "filters": [], "limit": 10}
        assert search_ai.execute_query(db, user, cleaned) == []
    finally:
        db.db.close()


def test_execute_query_team_name_join_filter(client):
    db = _db()
    try:
        cleaned = {"entity": "projects", "limit": 50,
                   "filters": [{"field": "team_name", "op": "eq", "value": f"ssrch_team_{suffix}"}]}
        rows = search_ai.execute_query(db, _admin_user(), cleaned)
        assert {r["id"] for r in rows} == {state["one"], state["two"]}
    finally:
        db.db.close()


def test_execute_query_ne_and_creator_join(client):
    db = _db()
    try:
        cleaned = {"entity": "projects", "limit": 50, "filters": [
            {"field": "name", "op": "contains", "value": suffix},
            {"field": "name", "op": "ne", "value": f"ssrch_one_{suffix}"},
            {"field": "creator_username", "op": "eq", "value": "admin"},
        ]}
        rows = search_ai.execute_query(db, _admin_user(), cleaned)
        assert {r["id"] for r in rows} == {state["two"]}
    finally:
        db.db.close()


def test_execute_query_teams_rbac_and_rendering(client):
    db = _db()
    try:
        team_name = f"ssrch_team_{suffix}"
        user = SimpleNamespace(is_admin=False,
                               teams=[SimpleNamespace(id=state["team_id"])],
                               admin_teams=[])
        cleaned = {"entity": "teams", "limit": 10,
                   "filters": [{"field": "name", "op": "eq", "value": team_name}]}
        rows = search_ai.execute_query(db, user, cleaned)
        assert [r["name"] for r in rows] == [team_name]
        assert rows[0]["entity"] == "teams"
        assert rows[0]["path"] == f"/team/{state['team_id']}"

        # A user in no teams sees nothing.
        loner = SimpleNamespace(is_admin=False, teams=[], admin_teams=[])
        assert search_ai.execute_query(db, loner, cleaned) == []
    finally:
        db.db.close()


def test_execute_query_llms_comparison_ops_and_team_scope(client):
    from restai.models.databasemodels import LLMDatabase
    db = _db()
    try:
        small = LLMDatabase(name=f"ssrch_llm_small_{suffix}", class_name="Ollama",
                            options="{}", privacy="private", description="",
                            context_window=1024)
        big = LLMDatabase(name=f"ssrch_llm_big_{suffix}", class_name="Ollama",
                          options="{}", privacy="private", description="",
                          context_window=32768)
        db.db.add_all([small, big])
        db.db.commit()

        cleaned = {"entity": "llms", "limit": 10, "filters": [
            {"field": "name", "op": "contains", "value": "ssrch_llm"},
            {"field": "name", "op": "contains", "value": suffix},
            {"field": "context_window", "op": "gt", "value": 2048},
        ]}
        rows = search_ai.execute_query(db, _admin_user(), cleaned)
        assert [r["id"] for r in rows] == [big.id]
        assert "ctx 32768" in rows[0]["subtitle"]

        # Non-admin scoped to LLMs granted via their teams.
        member = SimpleNamespace(is_admin=False,
                                 teams=[SimpleNamespace(llms=[small])],
                                 admin_teams=[])
        cleaned["filters"] = [{"field": "name", "op": "contains", "value": suffix}]
        rows = search_ai.execute_query(db, member, cleaned)
        assert [r["id"] for r in rows] == [small.id]
    finally:
        db.db.close()


def test_execute_query_users_rbac_team_admin_sees_members(client):
    db = _db()
    try:
        from restai.models.databasemodels import UserDatabase
        admin_row = db.db.query(UserDatabase).filter(UserDatabase.username == "admin").first()
        team = SimpleNamespace(users=[SimpleNamespace(id=admin_row.id)], admins=[])
        viewer = SimpleNamespace(is_admin=False, id=-1, admin_teams=[team], teams=[])
        cleaned = {"entity": "users", "limit": 10,
                   "filters": [{"field": "username", "op": "eq", "value": "admin"}]}
        rows = search_ai.execute_query(db, viewer, cleaned)
        assert [r["name"] for r in rows] == ["admin"]
    finally:
        db.db.close()


# ─── run_search pipeline with a faked System LLM ────────────────────────

def _brain_emitting(text):
    calls = []

    def complete(prompt):
        calls.append(prompt)
        return SimpleNamespace(text=text)
    llm = SimpleNamespace(llm=SimpleNamespace(complete=complete))
    return SimpleNamespace(get_system_llm=lambda db: llm), calls


def test_run_search_end_to_end(client):
    db = _db()
    try:
        spec = json.dumps({
            "entity": "projects",
            "filters": [{"field": "name", "op": "contains", "value": suffix}],
            "limit": 10,
            "note": "best effort",
        })
        brain, calls = _brain_emitting(spec)
        # Platform accounting is best-effort — a crash there must not break search.
        with patch("restai.limits.accounting.log_platform_usage",
                   side_effect=RuntimeError("accounting down")):
            out = asyncio.run(search_ai.run_search(brain, db, _admin_user(), "my projects"))
        assert {r["id"] for r in out["results"]} >= {state["one"], state["two"]}
        assert out["note"] == "best effort"
        assert out["warnings"] == []
        assert out["query"]["limit"] == 10
        # The user's query text made it into the translation prompt.
        assert "my projects" in calls[0]
    finally:
        db.db.close()


def test_run_search_no_system_llm():
    brain = SimpleNamespace(get_system_llm=lambda db: None)
    with pytest.raises(ValueError, match="No system LLM"):
        asyncio.run(search_ai.run_search(brain, None, _admin_user(), "q"))


def test_run_search_llm_crash_wrapped():
    def complete(prompt):
        raise RuntimeError("provider down")
    llm = SimpleNamespace(llm=SimpleNamespace(complete=complete))
    brain = SimpleNamespace(get_system_llm=lambda db: llm)
    with pytest.raises(ValueError, match="System LLM call failed"):
        asyncio.run(search_ai.run_search(brain, None, _admin_user(), "q"))


def test_run_search_invalid_json_from_llm(client):
    db = _db()
    try:
        brain, _ = _brain_emitting("I can't answer that in JSON, sorry.")
        with patch("restai.limits.accounting.log_platform_usage"):
            with pytest.raises(ValueError, match="invalid JSON"):
                asyncio.run(search_ai.run_search(brain, db, _admin_user(), "q"))
    finally:
        db.db.close()
