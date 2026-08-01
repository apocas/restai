"""Eval router edge tests for restai/routers/evals.py.

Complements tests/test_evals.py (basic CRUD) with: dataset created with
inline test cases, test-case PATCH semantics (empty question 422,
expected_answer clearing, context set/clear), run creation validation
(bad metric, faithfulness on non-RAG, missing/empty dataset), the run
list/detail/delete round-trip with the evaluation runner mocked, prompt
version number mapping, and project-scoped permission failures.
"""
import random
import time

import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

ADMIN = ("admin", RESTAI_DEFAULT_PASSWORD)

suffix = str(random.randint(0, 10000000))
llm_name = f"evx_llm_{suffix}"
team_name = f"evx_team_{suffix}"
proj_name = f"evx_proj_{suffix}"
outsider = f"evx_out_{suffix}"
outsider_pass = "evx_pass_123"

state = {}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def mock_eval_runner():
    """Replace the real evaluation runner (LLM work) with a recorder.

    The router spawns a daemon thread that imports `restai.eval` and calls
    `run_evaluation`; patch it at module scope so no firing ever reaches a
    real LLM.
    """
    import restai.eval as eval_mod

    calls = []
    real = eval_mod.run_evaluation

    async def fake_run_evaluation(run_id, app_):
        calls.append(run_id)

    eval_mod.run_evaluation = fake_run_evaluation
    state["runner_calls"] = calls
    yield
    eval_mod.run_evaluation = real


def test_setup(client):
    r = client.post(
        "/llms",
        json={
            "name": llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["llm_id"] = r.json()["id"]

    r = client.post("/teams", json={"name": team_name, "llms": [llm_name]}, auth=ADMIN)
    assert r.status_code == 201, r.text
    state["team_id"] = r.json()["id"]

    r = client.post(
        "/projects",
        json={"name": proj_name, "llm": llm_name, "type": "agent", "team_id": state["team_id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["proj_id"] = r.json()["project"]

    r = client.post(
        "/users",
        json={"username": outsider, "password": outsider_pass, "admin": False, "private": False},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------ datasets


def test_create_dataset_with_inline_cases(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/datasets",
        json={
            "name": f"evx_ds_{suffix}",
            "description": "inline cases",
            "test_cases": [
                {"question": "What is 2+2?", "expected_answer": "4"},
                {"question": "Capital of France?", "expected_answer": "Paris", "context": ["France facts"]},
            ],
        },
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["test_case_count"] == 2
    state["ds_id"] = data["id"]


def test_get_dataset_detail_includes_cases(client):
    r = client.get(f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}", auth=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert len(data["test_cases"]) == 2
    questions = {tc["question"] for tc in data["test_cases"]}
    assert questions == {"What is 2+2?", "Capital of France?"}
    state["case_ids"] = [tc["id"] for tc in data["test_cases"]]


def test_dataset_scoped_to_project_404(client):
    # Right dataset id, wrong project id -> 404.
    r = client.get(f"/projects/99999999/evals/datasets/{state['ds_id']}", auth=ADMIN)
    assert r.status_code == 404


def test_update_case_question(client):
    cid = state["case_ids"][0]
    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/{cid}",
        json={"question": "What is 3+3?"},
        auth=ADMIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["question"] == "What is 3+3?"
    assert r.json()["expected_answer"] == "4"  # untouched


def test_update_case_empty_question_rejected(client):
    cid = state["case_ids"][0]
    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/{cid}",
        json={"question": "   "},
        auth=ADMIN,
    )
    assert r.status_code == 422


def test_update_case_clear_expected_answer(client):
    cid = state["case_ids"][0]
    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/{cid}",
        json={"expected_answer": ""},
        auth=ADMIN,
    )
    assert r.status_code == 200
    assert r.json()["expected_answer"] is None


def test_update_case_set_and_clear_context(client):
    cid = state["case_ids"][0]
    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/{cid}",
        json={"context": ["ctx one", "ctx two"]},
        auth=ADMIN,
    )
    assert r.status_code == 200

    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/{cid}",
        json={"context": []},
        auth=ADMIN,
    )
    assert r.status_code == 200


def test_update_case_unknown_ids(client):
    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/99999999",
        json={"question": "x"},
        auth=ADMIN,
    )
    assert r.status_code == 404

    r = client.patch(
        f"/projects/{state['proj_id']}/evals/datasets/99999999/cases/1",
        json={"question": "x"},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_delete_case_unknown(client):
    r = client.delete(
        f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}/cases/99999999",
        auth=ADMIN,
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ runs


def test_start_run_invalid_metric(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": state["ds_id"], "metrics": ["vibes"]},
        auth=ADMIN,
    )
    assert r.status_code == 422
    assert "Invalid metric" in r.json()["detail"]


def test_start_run_faithfulness_non_rag(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": state["ds_id"], "metrics": ["faithfulness"]},
        auth=ADMIN,
    )
    assert r.status_code == 422
    assert "RAG" in r.json()["detail"]


def test_start_run_unknown_dataset(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": 99999999, "metrics": ["correctness"]},
        auth=ADMIN,
    )
    assert r.status_code == 404


def test_start_run_empty_dataset(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/datasets",
        json={"name": f"evx_empty_{suffix}"},
        auth=ADMIN,
    )
    assert r.status_code == 201
    empty_id = r.json()["id"]

    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": empty_id, "metrics": ["correctness"]},
        auth=ADMIN,
    )
    assert r.status_code == 400
    assert "no test cases" in r.json()["detail"]

    r = client.delete(f"/projects/{state['proj_id']}/evals/datasets/{empty_id}", auth=ADMIN)
    assert r.status_code == 200


def test_start_run_happy_path_mocked_runner(client):
    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": state["ds_id"], "metrics": ["correctness", "answer_relevancy"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "pending"
    state["run_id"] = data["id"]

    # The runner thread fires the mocked coroutine; give it a moment.
    for _ in range(50):
        if state["runner_calls"]:
            break
        time.sleep(0.05)
    assert state["run_id"] in state["runner_calls"]


def test_run_with_prompt_version_mapping(client):
    # Editing the system prompt auto-creates a prompt version.
    r = client.patch(
        f"/projects/{state['proj_id']}",
        json={"system": f"versioned prompt {suffix}"},
        auth=ADMIN,
    )
    assert r.status_code == 200

    r = client.get(f"/projects/{state['proj_id']}/prompts", auth=ADMIN)
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) >= 1
    pv = versions[0]

    r = client.post(
        f"/projects/{state['proj_id']}/evals/runs",
        json={"dataset_id": state["ds_id"], "metrics": ["correctness"], "prompt_version_id": pv["id"]},
        auth=ADMIN,
    )
    assert r.status_code == 201, r.text
    state["run2_id"] = r.json()["id"]

    # List maps the global prompt-version PK to the per-project version number.
    r = client.get(f"/projects/{state['proj_id']}/evals/runs", auth=ADMIN)
    assert r.status_code == 200
    runs = {run["id"]: run for run in r.json()}
    assert state["run_id"] in runs and state["run2_id"] in runs
    assert runs[state["run2_id"]]["prompt_version"] == pv["version"]
    assert runs[state["run_id"]]["prompt_version"] is None

    # Detail carries it too.
    r = client.get(f"/projects/{state['proj_id']}/evals/runs/{state['run2_id']}", auth=ADMIN)
    assert r.status_code == 200
    detail = r.json()
    assert detail["prompt_version"] == pv["version"]
    assert detail["results"] == []  # mocked runner produced no results


def test_get_run_unknown(client):
    r = client.get(f"/projects/{state['proj_id']}/evals/runs/99999999", auth=ADMIN)
    assert r.status_code == 404


def test_delete_run(client):
    r = client.delete(f"/projects/{state['proj_id']}/evals/runs/{state['run2_id']}", auth=ADMIN)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = client.get(f"/projects/{state['proj_id']}/evals/runs/{state['run2_id']}", auth=ADMIN)
    assert r.status_code == 404


def test_delete_run_unknown(client):
    r = client.delete(f"/projects/{state['proj_id']}/evals/runs/99999999", auth=ADMIN)
    assert r.status_code == 404


# ------------------------------------------------------------------ permissions


def test_outsider_gets_404_everywhere(client):
    auth = (outsider, outsider_pass)
    pid, ds = state["proj_id"], state["ds_id"]
    assert client.get(f"/projects/{pid}/evals/datasets", auth=auth).status_code == 404
    assert client.post(
        f"/projects/{pid}/evals/datasets", json={"name": "x"}, auth=auth
    ).status_code == 404
    assert client.get(f"/projects/{pid}/evals/datasets/{ds}", auth=auth).status_code == 404
    assert client.get(f"/projects/{pid}/evals/runs", auth=auth).status_code == 404
    assert client.post(
        f"/projects/{pid}/evals/runs",
        json={"dataset_id": ds, "metrics": ["correctness"]},
        auth=auth,
    ).status_code == 404


def test_cleanup(client):
    client.delete(f"/projects/{state['proj_id']}/evals/runs/{state['run_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['proj_id']}/evals/datasets/{state['ds_id']}", auth=ADMIN)
    client.delete(f"/projects/{state['proj_id']}", auth=ADMIN)
    client.delete(f"/teams/{state['team_id']}", auth=ADMIN)
    client.delete(f"/users/{outsider}", auth=ADMIN)
    client.delete(f"/llms/{state['llm_id']}", auth=ADMIN)
