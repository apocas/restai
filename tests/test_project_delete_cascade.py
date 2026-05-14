"""Regression for the May 14 production bug where deleting a project
threw `IntegrityError 1451` because most child FKs to projects.id
lacked ON DELETE CASCADE. Migration 050 fixes the schema on
MySQL/Postgres; `database.py:delete_project` adds an
application-side fallback for SQLite (and any deployment running
pre-050).

This test runs against the SQLite test DB and just exercises the
fallback path — but the assertion (delete returns 200, prompt_version
row is gone) is the same shape MySQL would have failed."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from restai.config import RESTAI_DEFAULT_PASSWORD
from restai.database import open_db_wrapper
from restai.main import app
from restai.models.databasemodels import (
    PromptVersionDatabase,
    ProjectCommentDatabase,
)


def test_project_delete_cascades_to_children():
    auth = ("admin", RESTAI_DEFAULT_PASSWORD)
    suffix = uuid.uuid4().hex[:6]
    team_name = f"delcascade_team_{suffix}"
    project_name = f"delcascade_proj_{suffix}"

    with TestClient(app) as c:
        # Set up team + project
        r = c.post("/teams", json={"name": team_name}, auth=auth)
        assert r.status_code == 201, r.text
        team_id = r.json()["id"]
        r = c.post(
            "/projects",
            json={"name": project_name, "type": "block", "team_id": team_id},
            auth=auth,
        )
        assert r.status_code == 201, r.text
        project_id = r.json()["project"]

        # Manually plant a prompt_version row + a project_comment so the
        # fallback path actually has something to clean up. We bypass
        # the API for these because the API normally creates them as a
        # side effect that we don't want to trigger here.
        db = open_db_wrapper()
        try:
            from datetime import datetime, timezone
            db.db.add(PromptVersionDatabase(
                project_id=project_id,
                version=1,
                system_prompt="seeded",
                created_at=datetime.now(timezone.utc),
                is_active=True,
            ))
            db.db.add(ProjectCommentDatabase(
                project_id=project_id,
                user_id=1,  # admin
                content="seeded",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            db.db.commit()
            # Sanity: rows exist
            assert db.db.query(PromptVersionDatabase).filter_by(project_id=project_id).count() >= 1
        finally:
            db.db.close()

        # The actual test: project delete must succeed even though
        # child rows reference it.
        r = c.delete(f"/projects/{project_id}", auth=auth)
        assert r.status_code in (200, 204), r.text

        # Verify cascade: child rows are gone
        db = open_db_wrapper()
        try:
            assert db.db.query(PromptVersionDatabase).filter_by(project_id=project_id).count() == 0
            assert db.db.query(ProjectCommentDatabase).filter_by(project_id=project_id).count() == 0
        finally:
            db.db.close()

        # Cleanup
        c.delete(f"/teams/{team_id}", auth=auth)
