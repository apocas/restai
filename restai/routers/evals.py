"""Evaluation framework router — datasets, test cases, runs, and results."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request

from restai.auth import get_current_username_project
from restai.database import get_db_wrapper, DBWrapper
from restai.models.databasemodels import (
    EvalDatasetDatabase,
    EvalTestCaseDatabase,
    EvalRunDatabase,
    EvalResultDatabase,
)
from restai.models.models import (
    EvalDatasetCreate,
    EvalDatasetUpdate,
    EvalDatasetResponse,
    EvalDatasetDetailResponse,
    EvalTestCaseCreate,
    EvalTestCaseResponse,
    EvalRunCreate,
    EvalRunResponse,
    EvalRunDetailResponse,
    EvalResultResponse,
    User,
)

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_METRICS = {"answer_relevancy", "faithfulness", "correctness"}


# ── Datasets ─────────────────────────────────────────────────────────────


@router.post("/projects/{projectID}/evals/datasets", status_code=201, tags=["Evaluations"])
async def create_dataset(
    projectID: int = Path(description="Project ID"),
    body: EvalDatasetCreate = ...,
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Create an evaluation dataset, optionally with initial test cases."""
    now = datetime.now(timezone.utc)
    dataset = EvalDatasetDatabase(
        name=body.name,
        description=body.description,
        project_id=projectID,
        created_at=now,
        updated_at=now,
    )
    db.db.add(dataset)
    db.db.flush()

    if body.test_cases:
        for tc in body.test_cases:
            db.db.add(EvalTestCaseDatabase(
                dataset_id=dataset.id,
                question=tc.question,
                expected_answer=tc.expected_answer,
                context=json.dumps(tc.context) if tc.context else None,
                created_at=now,
            ))

    db.db.commit()
    db.db.refresh(dataset)

    return EvalDatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        project_id=dataset.project_id,
        test_case_count=len(dataset.test_cases),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


@router.get("/projects/{projectID}/evals/datasets", tags=["Evaluations"])
async def list_datasets(
    projectID: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """List all evaluation datasets for a project."""
    datasets = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.project_id == projectID)
        .order_by(EvalDatasetDatabase.created_at.desc())
        .all()
    )
    return [
        EvalDatasetResponse(
            id=d.id,
            name=d.name,
            description=d.description,
            project_id=d.project_id,
            test_case_count=len(d.test_cases),
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in datasets
    ]


@router.get("/projects/{projectID}/evals/datasets/{datasetID}", tags=["Evaluations"])
async def get_dataset(
    projectID: int = Path(description="Project ID"),
    datasetID: int = Path(description="Dataset ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Get a dataset with all its test cases."""
    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == datasetID, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return EvalDatasetDetailResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        project_id=dataset.project_id,
        test_case_count=len(dataset.test_cases),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        test_cases=[EvalTestCaseResponse.model_validate(tc) for tc in dataset.test_cases],
    )


@router.patch("/projects/{projectID}/evals/datasets/{datasetID}", tags=["Evaluations"])
async def update_dataset(
    projectID: int = Path(description="Project ID"),
    datasetID: int = Path(description="Dataset ID"),
    body: EvalDatasetUpdate = ...,
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Update a dataset's name or description."""
    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == datasetID, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if body.name is not None:
        dataset.name = body.name
    if body.description is not None:
        dataset.description = body.description
    dataset.updated_at = datetime.now(timezone.utc)
    db.db.commit()

    return EvalDatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        project_id=dataset.project_id,
        test_case_count=len(dataset.test_cases),
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


@router.delete("/projects/{projectID}/evals/datasets/{datasetID}", tags=["Evaluations"])
async def delete_dataset(
    projectID: int = Path(description="Project ID"),
    datasetID: int = Path(description="Dataset ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a dataset and all its test cases and associated runs."""
    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == datasetID, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    db.db.delete(dataset)
    db.db.commit()
    return {"deleted": True}


# ── Test Cases ───────────────────────────────────────────────────────────


@router.post("/projects/{projectID}/evals/datasets/{datasetID}/cases", status_code=201, tags=["Evaluations"])
async def add_test_case(
    projectID: int = Path(description="Project ID"),
    datasetID: int = Path(description="Dataset ID"),
    body: EvalTestCaseCreate = ...,
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Add a test case to a dataset."""
    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == datasetID, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    tc = EvalTestCaseDatabase(
        dataset_id=datasetID,
        question=body.question,
        expected_answer=body.expected_answer,
        context=json.dumps(body.context) if body.context else None,
        created_at=datetime.now(timezone.utc),
    )
    db.db.add(tc)
    dataset.updated_at = datetime.now(timezone.utc)
    db.db.commit()
    db.db.refresh(tc)

    return EvalTestCaseResponse.model_validate(tc)


@router.delete("/projects/{projectID}/evals/datasets/{datasetID}/cases/{caseID}", tags=["Evaluations"])
async def delete_test_case(
    projectID: int = Path(description="Project ID"),
    datasetID: int = Path(description="Dataset ID"),
    caseID: int = Path(description="Test case ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Delete a test case from a dataset."""
    tc = (
        db.db.query(EvalTestCaseDatabase)
        .filter(
            EvalTestCaseDatabase.id == caseID,
            EvalTestCaseDatabase.dataset_id == datasetID,
        )
        .first()
    )
    if tc is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == datasetID, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    db.db.delete(tc)
    dataset.updated_at = datetime.now(timezone.utc)
    db.db.commit()
    return {"deleted": True}


# ── Runs ─────────────────────────────────────────────────────────────────


@router.post("/projects/{projectID}/evals/runs", status_code=201, tags=["Evaluations"])
async def start_eval_run(
    request: Request,
    projectID: int = Path(description="Project ID"),
    body: EvalRunCreate = ...,
    background_tasks: BackgroundTasks = ...,
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Start an evaluation run. Returns immediately; runs in the background."""
    # Validate metrics
    for m in body.metrics:
        if m not in VALID_METRICS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid metric '{m}'. Valid: {', '.join(sorted(VALID_METRICS))}",
            )

    # Validate dataset belongs to project
    dataset = (
        db.db.query(EvalDatasetDatabase)
        .filter(EvalDatasetDatabase.id == body.dataset_id, EvalDatasetDatabase.project_id == projectID)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if len(dataset.test_cases) == 0:
        raise HTTPException(status_code=400, detail="Dataset has no test cases")

    now = datetime.now(timezone.utc)
    run = EvalRunDatabase(
        dataset_id=body.dataset_id,
        project_id=projectID,
        prompt_version_id=body.prompt_version_id,
        status="pending",
        metrics=json.dumps(body.metrics),
        created_at=now,
    )
    db.db.add(run)
    db.db.commit()
    db.db.refresh(run)

    # Run evaluation in background
    from restai.eval import run_evaluation

    async def _run_eval():
        await run_evaluation(run.id, request.app)

    background_tasks.add_task(_run_eval)

    return EvalRunResponse.model_validate(run)


@router.get("/projects/{projectID}/evals/runs", tags=["Evaluations"])
async def list_runs(
    projectID: int = Path(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """List all evaluation runs for a project."""
    runs = (
        db.db.query(EvalRunDatabase)
        .filter(EvalRunDatabase.project_id == projectID)
        .order_by(EvalRunDatabase.created_at.desc())
        .all()
    )
    return [EvalRunResponse.model_validate(r) for r in runs]


@router.get("/projects/{projectID}/evals/runs/{runID}", tags=["Evaluations"])
async def get_run(
    projectID: int = Path(description="Project ID"),
    runID: int = Path(description="Run ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Get evaluation run details with all results."""
    run = (
        db.db.query(EvalRunDatabase)
        .filter(EvalRunDatabase.id == runID, EvalRunDatabase.project_id == projectID)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    results = [EvalResultResponse.model_validate(r) for r in run.results]

    resp = EvalRunDetailResponse.model_validate(run)
    resp.results = results
    return resp


@router.delete("/projects/{projectID}/evals/runs/{runID}", tags=["Evaluations"])
async def delete_run(
    projectID: int = Path(description="Project ID"),
    runID: int = Path(description="Run ID"),
    user: User = Depends(get_current_username_project),
    db: DBWrapper = Depends(get_db_wrapper),
):
    """Delete an evaluation run and all its results."""
    run = (
        db.db.query(EvalRunDatabase)
        .filter(EvalRunDatabase.id == runID, EvalRunDatabase.project_id == projectID)
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    db.db.delete(run)
    db.db.commit()
    return {"deleted": True}
