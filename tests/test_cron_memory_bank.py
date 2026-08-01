"""Memory bank cron (crons/memory_bank.py) + restai/memory/bank modules.

Real sqlite rows (OutputDatabase / ProjectMemoryBankEntryDatabase) with a
faked System LLM: conversation discovery, idle gating, upsert by chat_id,
incremental summarization, compression ladder, render, and the
no-System-LLM no-op."""

import json
import random
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import crons.memory_bank as cmb
from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app
from restai.memory import bank
from restai.memory.bank.common import _now
from restai.models.databasemodels import (
    OutputDatabase,
    ProjectDatabase,
    ProjectMemoryBankEntryDatabase,
)

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)
suffix = str(random.randint(0, 10_000_000))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _db():
    from restai.database import DBWrapper
    return DBWrapper()


@pytest.fixture
def db():
    d = _db()
    yield d
    d.db.close()


def _make_agent_project(client, name, options=None):
    """Create a project via the API, then flip it to an agent with memory
    bank options (agent creation via API requires a configured LLM)."""
    r = client.post("/teams", json={"name": f"mbank_team_{name}_{suffix}"}, auth=ADMIN)
    assert r.status_code == 201, r.text
    r = client.post("/projects", json={
        "name": f"mbank_{name}_{suffix}", "type": "block", "team_id": r.json()["id"]},
        auth=ADMIN)
    assert r.status_code == 201, r.text
    pid = r.json()["project"]
    d = _db()
    try:
        proj = d.db.query(ProjectDatabase).filter(ProjectDatabase.id == pid).first()
        proj.type = "agent"
        opts = {"memory_bank_enabled": True, "memory_bank_max_tokens": 2000}
        opts.update(options or {})
        proj.options = json.dumps(opts)
        d.db.commit()
    finally:
        d.db.close()
    return pid


def _seed_output(db, project_id, chat_id, question, answer, minutes_ago):
    db.db.add(OutputDatabase(
        question=question, answer=answer, project_id=project_id,
        chat_id=chat_id, llm="fake", input_tokens=1, output_tokens=1,
        input_cost=0.0, output_cost=0.0,
        date=_now() - timedelta(minutes=minutes_ago),
    ))
    db.db.commit()


def _entries(db, project_id, granularity=None):
    q = db.db.query(ProjectMemoryBankEntryDatabase).filter(
        ProjectMemoryBankEntryDatabase.project_id == project_id)
    if granularity:
        q = q.filter(ProjectMemoryBankEntryDatabase.granularity == granularity)
    return q.all()


class FakeLLM:
    def __init__(self, reply="- user asked about topic X"):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(text=self.reply)


def _brain(fake_llm):
    if fake_llm is None:
        return SimpleNamespace(get_system_llm=lambda db: None)
    return SimpleNamespace(get_system_llm=lambda db: SimpleNamespace(llm=fake_llm))


def _run_cron(brain):
    """Run the cron's main() with Brain and platform accounting patched.

    The tick is scoped to this module's own projects: the shared test DB
    accumulates memory-bank-enabled agent projects from other modules, and
    the cron's global MAX_CHATS_PER_TICK budget would otherwise be spent on
    that backlog before reaching ours (order-dependent failures in a full
    suite run).
    """
    cron = MagicMock()
    real_list = cmb.memory_bank.list_enabled_projects

    def _ours_only(db_wrapper):
        return [p for p in real_list(db_wrapper) if str(p.name).endswith(f"_{suffix}")]

    with patch.object(cmb, "Brain", return_value=brain), \
         patch.object(cmb, "ensure_settings_table"), \
         patch.object(cmb, "CronLogger", return_value=cron), \
         patch.object(cmb.memory_bank, "list_enabled_projects", _ours_only), \
         patch("restai.limits.accounting.log_platform_usage"):
        cmb.main()
    return cron


# ─── cron tick end-to-end ───────────────────────────────────────────────

def test_no_system_llm_is_noop(client, db):
    pid = _make_agent_project(client, "nollm")
    _seed_output(db, pid, f"chat_a_{suffix}", "hi", "hello", minutes_ago=30)
    cron = _run_cron(_brain(None))
    cron.warning.assert_called_once()
    assert "No System LLM" in cron.warning.call_args.args[0]
    assert _entries(db, pid) == []


def test_idle_conversation_summarized_and_upserted(client, db):
    pid = _make_agent_project(client, "basic")
    chat = f"chat_b_{suffix}"
    _seed_output(db, pid, chat, "what is the plan?", "we ship friday", minutes_ago=40)
    _seed_output(db, pid, chat, "who owns it?", "alice does", minutes_ago=35)

    llm = FakeLLM("- shipping friday, alice owns it")
    _run_cron(_brain(llm))

    db.db.expire_all()
    rows = _entries(db, pid, "conversation")
    assert len(rows) == 1
    entry = rows[0]
    assert entry.chat_id == chat
    assert entry.summary == "- shipping friday, alice owns it"
    assert entry.source_message_count == 2
    assert entry.token_count > 0
    assert entry.last_source_at is not None
    # Full transcript went to the LLM (other backlogged projects may have
    # been summarized in the same tick, so search all prompts).
    all_prompts = "\n".join(llm.prompts)
    assert "what is the plan?" in all_prompts
    assert "alice does" in all_prompts


def test_active_conversation_not_summarized(client, db):
    pid = _make_agent_project(client, "active")
    _seed_output(db, pid, f"chat_c_{suffix}", "still typing", "ok", minutes_ago=0)
    llm = FakeLLM()
    _run_cron(_brain(llm))
    assert _entries(db, pid) == []
    assert llm.prompts == []


def test_incremental_resummarization_updates_same_row(client, db):
    pid = _make_agent_project(client, "incr")
    chat = f"chat_d_{suffix}"
    _seed_output(db, pid, chat, "first question", "first answer", minutes_ago=60)
    _run_cron(_brain(FakeLLM("- v1 summary")))

    db.db.expire_all()
    first = _entries(db, pid, "conversation")[0]
    assert first.summary == "- v1 summary"

    # New idle turn after the summary → incremental path, same row updated.
    _seed_output(db, pid, chat, "second question", "second answer", minutes_ago=20)
    llm2 = FakeLLM("- v2 consolidated summary")
    _run_cron(_brain(llm2))

    db.db.expire_all()
    rows = _entries(db, pid, "conversation")
    assert len(rows) == 1
    assert rows[0].id == first.id
    assert rows[0].summary == "- v2 consolidated summary"
    assert rows[0].source_message_count == 2
    # Incremental prompt carries the prior summary + only the new turns.
    assert "- v1 summary" in llm2.prompts[0]
    assert "second question" in llm2.prompts[0]
    assert "first question" not in llm2.prompts[0]


def test_up_to_date_conversation_not_reprocessed(client, db):
    pid = _make_agent_project(client, "uptodate")
    chat = f"chat_e_{suffix}"
    _seed_output(db, pid, chat, "q", "a", minutes_ago=30)
    _run_cron(_brain(FakeLLM("- summarized")))
    llm2 = FakeLLM("- should never be called")
    _run_cron(_brain(llm2))
    assert llm2.prompts == []


def test_llm_failure_writes_nothing_and_does_not_crash(client, db):
    pid = _make_agent_project(client, "llmfail")
    _seed_output(db, pid, f"chat_f_{suffix}", "q", "a", minutes_ago=30)
    cron = _run_cron(_brain(FakeLLM(RuntimeError("provider down"))))
    assert _entries(db, pid) == []
    cron.error.assert_not_called()
    cron.finish.assert_called()


def test_per_tick_budget_defers_chats(client, db, monkeypatch):
    # Drain any backlog left by earlier tests (e.g. the failed-LLM chat)
    # so the capped ticks below spend their budget only on this project.
    _run_cron(_brain(FakeLLM("- drained")))
    pid = _make_agent_project(client, "budget")
    for i in range(4):
        _seed_output(db, pid, f"chat_g{i}_{suffix}", f"q{i}", f"a{i}", minutes_ago=30)
    monkeypatch.setattr(cmb, "MAX_CHATS_PER_TICK", 2)
    _run_cron(_brain(FakeLLM("- s")))
    db.db.expire_all()
    assert len(_entries(db, pid, "conversation")) == 2
    # Next tick drains the backlog.
    _run_cron(_brain(FakeLLM("- s")))
    db.db.expire_all()
    assert len(_entries(db, pid, "conversation")) == 4


# ─── scheduling unit behavior ───────────────────────────────────────────

def test_chat_absorbed_into_digest_not_requeued(client, db):
    pid = _make_agent_project(client, "absorbed")
    chat = f"chat_h_{suffix}"
    old = _now() - timedelta(days=2)
    _seed_output(db, pid, chat, "q", "a", minutes_ago=60 * 48)
    # A day digest already covers this chat's latest activity.
    db.db.add(ProjectMemoryBankEntryDatabase(
        project_id=pid, chat_id=None, granularity="day",
        period_key=old.strftime("%Y-%m-%d"), summary="- day digest",
        token_count=5, source_message_count=1,
        last_source_at=_now(), created_at=_now(), updated_at=_now()))
    db.db.commit()
    assert bank.chat_ids_needing_refresh(db, pid) == []


def test_list_enabled_projects_filters(client, db):
    enabled_pid = _make_agent_project(client, "listed")
    disabled_pid = _make_agent_project(client, "unlisted", options={"memory_bank_enabled": False})
    ids = {p.id for p in bank.list_enabled_projects(db)}
    assert enabled_pid in ids
    assert disabled_pid not in ids


# ─── compression ladder ─────────────────────────────────────────────────

def _seed_entry(db, pid, granularity, summary, token_count, days_ago, chat_id=None,
                period_key=None):
    at = _now() - timedelta(days=days_ago)
    row = ProjectMemoryBankEntryDatabase(
        project_id=pid, chat_id=chat_id, granularity=granularity,
        period_key=period_key or at.strftime("%Y-%m-%d"), summary=summary,
        token_count=token_count, source_message_count=1,
        last_source_at=at, created_at=at, updated_at=at)
    db.db.add(row)
    db.db.commit()
    return row


def test_compress_within_headroom_is_noop(client, db):
    pid = _make_agent_project(client, "headroom")
    _seed_entry(db, pid, "conversation", "- old", 110, days_ago=3, chat_id="x")
    llm = FakeLLM("- digest")
    with patch("restai.limits.accounting.log_platform_usage"):
        bank.compress_entries(_brain(llm), db, pid, max_tokens=100)
    # 110 <= 100 * 1.25 → nothing compressed, no LLM call.
    assert llm.prompts == []
    assert len(_entries(db, pid, "conversation")) == 1


def test_compress_rolls_conversations_into_day_digest(client, db):
    pid = _make_agent_project(client, "rollup")
    a = _seed_entry(db, pid, "conversation", "- convo one", 100, days_ago=3, chat_id="c1")
    _seed_entry(db, pid, "conversation", "- convo two", 100, days_ago=3, chat_id="c2")
    day_key = a.last_source_at.strftime("%Y-%m-%d")
    llm = FakeLLM("- merged digest")
    with patch("restai.limits.accounting.log_platform_usage"):
        bank.compress_entries(_brain(llm), db, pid, max_tokens=50)

    db.db.expire_all()
    assert _entries(db, pid, "conversation") == []
    days = _entries(db, pid, "day")
    assert len(days) == 1
    assert days[0].summary == "- merged digest"
    assert days[0].period_key == day_key
    assert days[0].source_message_count == 2
    # Both source summaries were sent to the digest LLM.
    assert "- convo one" in llm.prompts[0] and "- convo two" in llm.prompts[0]


def test_compress_recent_conversations_not_rolled(client, db):
    pid = _make_agent_project(client, "recent")
    _seed_entry(db, pid, "conversation", "- fresh", 200, days_ago=0, chat_id="c1")
    llm = FakeLLM("- digest")
    with patch("restai.limits.accounting.log_platform_usage"):
        bank.compress_entries(_brain(llm), db, pid, max_tokens=50)
    # Under 1 day old → conversation→day rollup skips it; over budget with
    # nothing to roll up → falls through to drop-oldest and deletes it.
    db.db.expire_all()
    assert _entries(db, pid) == []


def test_compress_drops_oldest_when_llm_unavailable(client, db):
    pid = _make_agent_project(client, "droponly")
    _seed_entry(db, pid, "month", "- ancient", 100, days_ago=90, period_key="2026-04")
    newest = _seed_entry(db, pid, "month", "- newer", 100, days_ago=40, period_key="2026-06")
    with patch("restai.limits.accounting.log_platform_usage"):
        bank.compress_entries(_brain(None), db, pid, max_tokens=110)
    db.db.expire_all()
    rows = _entries(db, pid)
    assert len(rows) == 1
    assert rows[0].id == newest.id  # oldest dropped first


# ─── render ─────────────────────────────────────────────────────────────

def test_render_empty_bank_is_empty_string(client, db):
    pid = _make_agent_project(client, "renderempty")
    assert bank.render_for_prompt(db, pid, 1000) == ""


def test_render_includes_entries_grouped_by_granularity(client, db):
    pid = _make_agent_project(client, "render")
    _seed_entry(db, pid, "conversation", "- convo summary", 10, days_ago=0, chat_id="chatxyz1")
    _seed_entry(db, pid, "week", "- week digest", 10, days_ago=10, period_key="2026-W29")
    out = bank.render_for_prompt(db, pid, 100000)
    assert out.startswith("[Project Memory Bank")
    assert "## Recent conversations" in out
    assert "- convo summary" in out
    assert "## By week" in out
    assert "(2026-W29) - week digest" in out


def test_render_respects_token_budget(client, db):
    pid = _make_agent_project(client, "renderbudget")
    for i in range(5):
        _seed_entry(db, pid, "conversation", f"- summary number {i} " + "x" * 200,
                    10, days_ago=0, chat_id=f"c{i}")
    small = bank.render_for_prompt(db, pid, 60)
    large = bank.render_for_prompt(db, pid, 100000)
    assert len(small) < len(large)
    # At least the preamble survives.
    assert small.startswith("[Project Memory Bank")
