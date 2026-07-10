import random
import pytest
from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.main import app

test_llm_name = "test_llm_" + str(random.randint(0, 1000000))
test_user = "test_llm_user_" + str(random.randint(0, 1000000))
test_llm_id = None


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_get_llms(client):
    response = client.get("/llms", auth=("admin", RESTAI_DEFAULT_PASSWORD))
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_llm(client):
    global test_llm_id
    response = client.post(
        "/llms",
        json={
            "name": test_llm_name,
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake123"},
            "privacy": "public",
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_llm_name
    test_llm_id = data["id"]


def test_create_llm_non_admin(client):
    client.post(
        "/users",
        json={
            "username": test_user,
            "password": "testpass",
            "admin": False,
            "private": False,
        },
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )

    response = client.post(
        "/llms",
        json={
            "name": "should_fail_llm",
            "class_name": "OpenAI",
            "options": {"model": "gpt-test", "api_key": "sk-fake"},
            "privacy": "public",
        },
        auth=(test_user, "testpass"),
    )
    assert response.status_code == 403

    client.delete(
        f"/users/{test_user}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )


def test_get_llm(client):
    response = client.get(
        f"/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == test_llm_name
    assert data["class_name"] == "OpenAI"
    assert data["privacy"] == "public"
    # API key should be masked
    options = data["options"]
    if isinstance(options, str):
        import json
        options = json.loads(options)
    assert options.get("api_key") == "********"


def test_update_llm(client):
    response = client.patch(
        f"/llms/{test_llm_id}",
        json={"description": "Updated test LLM"},
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200

    response = client.get(
        f"/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated test LLM"


def test_delete_llm(client):
    response = client.delete(
        f"/llms/{test_llm_id}",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 200


def test_delete_llm_not_found(client):
    response = client.delete(
        "/llms/999999",
        auth=("admin", RESTAI_DEFAULT_PASSWORD),
    )
    assert response.status_code == 404


def test_llm_usage_and_reassign_db_level():
    """get_llm_usage detects main + eval/rerank references; reassign_llm repoints
    them all and leaves unrelated option keys untouched."""
    import json as _json
    from restai.database import open_db_wrapper
    from restai.models.databasemodels import ProjectDatabase

    db = open_db_wrapper()
    suffix = str(random.randint(0, 1000000))
    old, new = "reassign_old_" + suffix, "reassign_new_" + suffix
    proj_name = "reassign_proj_" + suffix
    try:
        db.create_llm(old, "OpenAI", _json.dumps({"model": "x"}), "public", "d")
        db.create_llm(new, "OpenAI", _json.dumps({"model": "y"}), "public", "d")

        p = ProjectDatabase(
            name=proj_name, type="rag", llm=old,
            options=_json.dumps({"eval_llm": old, "rerank_llm": "someother"}),
        )
        db.db.add(p)
        db.db.commit()
        pid = p.id

        usage = db.get_llm_usage(old)
        entry = next(u for u in usage if u["id"] == pid)
        assert set(entry["fields"]) == {"llm", "eval_llm"}

        assert db.reassign_llm(old, new) == 1

        db.db.expire_all()
        refreshed = db.db.query(ProjectDatabase).filter(ProjectDatabase.id == pid).first()
        assert refreshed.llm == new
        opts = _json.loads(refreshed.options)
        assert opts["eval_llm"] == new
        assert opts["rerank_llm"] == "someother"  # unrelated key preserved
        assert not any(u["id"] == pid for u in db.get_llm_usage(old))  # nothing left
    finally:
        db.db.query(ProjectDatabase).filter(ProjectDatabase.name == proj_name).delete()
        for n in (old, new):
            row = db.get_llm_by_name(n)
            if row:
                db.delete_llm(row)
        db.db.commit()
        db.db.close()


def test_guard_references_are_ids_and_survive_rename():
    """Guard references store the project id; renaming the guard project doesn't
    break dependents (the id is stable), and deleting it nulls the references."""
    import json as _json
    from restai.database import open_db_wrapper
    from restai.models.databasemodels import ProjectDatabase

    db = open_db_wrapper()
    suffix = str(random.randint(0, 1000000))
    guard_name = "guardproj_" + suffix
    guard_renamed = "guardproj_renamed_" + suffix
    dep_in = "dep_in_" + suffix
    dep_out = "dep_out_" + suffix
    try:
        for n in (guard_name, dep_in, dep_out):
            db.db.add(ProjectDatabase(name=n, type="agent", options="{}"))
        db.db.commit()
        guard_id = db.get_project_by_name(guard_name).id

        # Dependents reference the guard by ID (input via column, output via option).
        db.db.query(ProjectDatabase).filter(ProjectDatabase.name == dep_in).update({"guard": str(guard_id)})
        p_out = db.db.query(ProjectDatabase).filter(ProjectDatabase.name == dep_out).first()
        p_out.options = _json.dumps({"guard_output": str(guard_id)})
        db.db.commit()

        # Renaming the guard project leaves the id-based references intact.
        db.db.query(ProjectDatabase).filter(ProjectDatabase.id == guard_id).update({"name": guard_renamed})
        db.db.commit()
        db.db.expire_all()
        assert db.db.query(ProjectDatabase).filter(ProjectDatabase.name == dep_in).first().guard == str(guard_id)

        # Deleting the guard project nulls the dangling references.
        assert db.clear_guard_references(guard_id) == 2
        db.db.commit()
        db.db.expire_all()
        assert db.db.query(ProjectDatabase).filter(ProjectDatabase.name == dep_in).first().guard is None
        refreshed_out = db.db.query(ProjectDatabase).filter(ProjectDatabase.name == dep_out).first()
        assert _json.loads(refreshed_out.options)["guard_output"] is None
    finally:
        for n in (guard_name, guard_renamed, dep_in, dep_out):
            db.db.query(ProjectDatabase).filter(ProjectDatabase.name == n).delete()
        db.db.commit()
        db.db.close()


def test_delete_llm_reassign_endpoint(client):
    """The DELETE endpoint refuses to orphan projects: 409 without reassign_to,
    400 for an unknown target, and repoints dependents when given a valid one."""
    import json as _json
    from restai.database import open_db_wrapper
    from restai.models.databasemodels import ProjectDatabase

    suffix = str(random.randint(0, 1000000))
    old, new = "ep_old_" + suffix, "ep_new_" + suffix
    proj_name = "ep_proj_" + suffix

    r1 = client.post("/llms", json={"name": old, "class_name": "OpenAI",
                                    "options": {"model": "x"}, "privacy": "public"},
                     auth=("admin", RESTAI_DEFAULT_PASSWORD))
    old_id = r1.json()["id"]
    client.post("/llms", json={"name": new, "class_name": "OpenAI",
                               "options": {"model": "y"}, "privacy": "public"},
                auth=("admin", RESTAI_DEFAULT_PASSWORD))

    db = open_db_wrapper()
    p = ProjectDatabase(name=proj_name, type="rag", llm=old, options="{}")
    db.db.add(p)
    db.db.commit()
    pid = p.id
    db.db.close()

    try:
        u = client.get(f"/llms/{old_id}/usage", auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert u.status_code == 200 and u.json()["count"] == 1

        # No replacement → blocked.
        assert client.delete(f"/llms/{old_id}",
                             auth=("admin", RESTAI_DEFAULT_PASSWORD)).status_code == 409
        # Unknown replacement → 400.
        assert client.delete(f"/llms/{old_id}?reassign_to=nope_{suffix}",
                             auth=("admin", RESTAI_DEFAULT_PASSWORD)).status_code == 400
        # Valid replacement → deleted + project repointed.
        d = client.delete(f"/llms/{old_id}?reassign_to={new}",
                          auth=("admin", RESTAI_DEFAULT_PASSWORD))
        assert d.status_code == 200 and d.json()["reassigned"] == 1

        db2 = open_db_wrapper()
        assert db2.db.query(ProjectDatabase).filter(ProjectDatabase.id == pid).first().llm == new
        db2.db.close()
    finally:
        dbc = open_db_wrapper()
        dbc.db.query(ProjectDatabase).filter(ProjectDatabase.name == proj_name).delete()
        dbc.db.commit()
        for n in (old, new):
            row = dbc.get_llm_by_name(n)
            if row:
                dbc.delete_llm(row)
        dbc.db.commit()
        dbc.db.close()
