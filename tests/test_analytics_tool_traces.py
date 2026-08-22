"""Unit tests for the agent observability layer: tool-trace aggregation
(pure functions behind /analytics/tools) and log_inference persistence of the
run-outcome metadata columns added in migration 061.
"""
import json
import types

from restai.routers.projects.analytics import _percentile, aggregate_tool_traces


def _trace(rows):
    return json.dumps(rows)


# ─── percentile helper ──────────────────────────────────────────────────

def test_percentile_nearest_rank():
    assert _percentile([], 50) is None
    assert _percentile([7], 50) == 7
    # Nearest-rank via round(): the even-length midpoint rounds up (banker's
    # rounding of index 1.5 → 2 → value 3).
    assert _percentile([1, 2, 3, 4], 50) == 3
    assert _percentile([1, 2, 3, 4], 95) == 4
    assert _percentile([1, 2, 3, 4, 5], 50) == 3
    assert _percentile(list(range(1, 101)), 95) == 95


# ─── aggregate_tool_traces ──────────────────────────────────────────────

def test_aggregates_per_tool_calls_errors_latency():
    payloads = [
        _trace([
            {"tool": "search", "args": "{}", "latency_ms": 100, "status": "ok"},
            {"tool": "search", "args": "{}", "latency_ms": 300, "status": "error", "error": "x"},
            {"tool": "calculator", "args": "{}", "latency_ms": 10, "status": "ok"},
        ]),
        _trace([
            {"tool": "search", "args": "{}", "latency_ms": 200, "status": "ok"},
        ]),
    ]
    result = aggregate_tool_traces(payloads)
    assert result["runs_analyzed"] == 2
    by_name = {t["tool"]: t for t in result["tools"]}
    assert by_name["search"]["calls"] == 3
    assert by_name["search"]["errors"] == 1
    assert by_name["search"]["error_rate"] == round(1 / 3, 3)
    assert by_name["search"]["avg_ms"] == 200
    assert by_name["search"]["p50_ms"] == 200
    assert by_name["calculator"]["calls"] == 1
    # Sorted by call volume.
    assert result["tools"][0]["tool"] == "search"


def test_pseudo_rows_split_out_of_tool_stats():
    payloads = [
        _trace([
            {"tool": "llm_turn", "args": '{"turn": 1, "llm": "gpt"}', "latency_ms": 900, "status": "ok"},
            {"tool": "search", "args": "{}", "latency_ms": 50, "status": "ok"},
            {"tool": "llm_fallback", "args": '{"from": "a", "to": "b"}', "latency_ms": None, "status": "ok"},
            {"tool": "llm_turn", "args": '{"turn": 2, "llm": "backup"}', "latency_ms": 1100, "status": "ok"},
        ]),
    ]
    result = aggregate_tool_traces(payloads)
    names = [t["tool"] for t in result["tools"]]
    assert names == ["search"]
    assert result["llm_turns"]["count"] == 2
    assert result["llm_turns"]["avg_ms"] == 1000
    assert result["fallbacks"] == 1
    assert result["runs_with_fallback"] == 1


def test_malformed_payloads_skipped():
    result = aggregate_tool_traces([
        "not json {", json.dumps({"a": 1}), None,
        _trace([{"tool": "t", "latency_ms": "n/a", "status": "ok"}, "junk"]),
    ])
    assert result["runs_analyzed"] == 1
    assert result["tools"][0]["calls"] == 1
    assert result["tools"][0]["p50_ms"] is None  # non-numeric latency ignored


def test_empty_input():
    result = aggregate_tool_traces([])
    assert result == {
        "tools": [],
        "llm_turns": {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None},
        "fallbacks": 0,
        "runs_with_fallback": 0,
        "runs_analyzed": 0,
    }


# ─── log_inference persists the run-outcome columns ─────────────────────

def test_log_inference_persists_run_metadata():
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase
    from restai.tools import log_inference

    project = types.SimpleNamespace(props=types.SimpleNamespace(
        id=None, llm=None, team=None, name="obs-test",
        options=types.SimpleNamespace(redact_inference_logs=False, logging=True),
    ))
    user = types.SimpleNamespace(id=None, api_key_id=None)
    output = {
        "question": "obs-test question",
        "answer": "obs-test answer",
        "tokens": {"input": 5, "output": 2, "accuracy": "high"},
        "stop_reason": "max_time",
        "retries": 2,
        "llm_fallbacks": [{"from": "a", "to": "b"}],
        "tool_trace": [{"tool": "llm_turn", "args": "{}", "latency_ms": 42, "status": "ok"}],
    }

    db = DBWrapper()
    try:
        log_inference(project, user, output, db)
        row = (
            db.db.query(OutputDatabase)
            .filter(OutputDatabase.question == "obs-test question")
            .order_by(OutputDatabase.id.desc())
            .first()
        )
        assert row is not None
        assert row.stop_reason == "max_time"
        assert row.retries == 2
        assert row.fallbacks == 1
        assert row.token_accuracy == "high"
        assert "llm_turn" in (row.tool_trace or "")
        db.db.delete(row)
        db.db.commit()
    finally:
        db.db.close()


def test_log_inference_leaves_metadata_null_for_plain_rows():
    from restai.database import DBWrapper
    from restai.models.databasemodels import OutputDatabase
    from restai.tools import log_inference

    project = types.SimpleNamespace(props=types.SimpleNamespace(
        id=None, llm=None, team=None, name="obs-test",
        options=types.SimpleNamespace(redact_inference_logs=False, logging=True),
    ))
    user = types.SimpleNamespace(id=None, api_key_id=None)
    output = {
        "question": "obs-plain question",
        "answer": "plain",
        "tokens": {"input": 1, "output": 1},
    }

    db = DBWrapper()
    try:
        log_inference(project, user, output, db)
        row = (
            db.db.query(OutputDatabase)
            .filter(OutputDatabase.question == "obs-plain question")
            .order_by(OutputDatabase.id.desc())
            .first()
        )
        assert row is not None
        assert row.stop_reason is None
        assert row.retries is None
        assert row.fallbacks is None
        assert row.token_accuracy is None
        db.db.delete(row)
        db.db.commit()
    finally:
        db.db.close()
