"""Evaluation engine for AI projects using DeepEval metrics."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from llama_index.core.llms.llm import LLM
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from restai.models.databasemodels import (
    EvalRunDatabase,
    EvalTestCaseDatabase,
    EvalResultDatabase,
)

logger = logging.getLogger(__name__)

VALID_METRICS = {"answer_relevancy", "faithfulness", "correctness"}


class DeepEvalLLM(DeepEvalBaseLLM):
    """Adapter wrapping a LlamaIndex LLM for use with DeepEval."""

    def __init__(self, model: LLM, *args, **kwargs):
        self._llm = model
        super().__init__(*args, **kwargs)

    def load_model(self):
        return self._llm

    def generate(self, prompt: str) -> str:
        return self._llm.complete(prompt).text

    async def a_generate(self, prompt: str) -> str:
        res = await self._llm.complete(prompt)
        return res.text

    def get_model_name(self):
        return "Custom LLamaindex LLM"


def eval_rag(question, response, llm):
    """Legacy single-question RAG evaluation (kept for backward compatibility)."""
    if response is not None:
        actual_output = response.response
        retrieval_context = [node.get_content() for node in response.source_nodes]
    else:
        return None

    test_case = LLMTestCase(
        input=question, actual_output=actual_output, retrieval_context=retrieval_context
    )

    llm = DeepEvalLLM(model=llm)

    metric = AnswerRelevancyMetric(
        threshold=0.5, model=llm, include_reason=True, async_mode=False
    )
    metric.measure(test_case)

    return metric


def _build_metric(metric_name: str, eval_llm: DeepEvalLLM):
    """Create a DeepEval metric instance by name."""
    if metric_name == "answer_relevancy":
        return AnswerRelevancyMetric(
            threshold=0.5, model=eval_llm, include_reason=True, async_mode=False
        )
    elif metric_name == "faithfulness":
        return FaithfulnessMetric(
            threshold=0.5, model=eval_llm, include_reason=True, async_mode=False
        )
    elif metric_name == "correctness":
        return GEval(
            name="Correctness",
            criteria="Determine whether the actual output is factually correct and matches the expected output.",
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.5,
            model=eval_llm,
            async_mode=False,
        )
    else:
        raise ValueError(f"Unknown metric: {metric_name}")


async def _get_project_answer(project, question: str, brain, user, db):
    """Call a project's question method directly and return (answer_text, sources_list, latency_ms)."""
    from restai.models.models import QuestionModel

    q = QuestionModel(question=question, stream=False)
    start = time.perf_counter()

    # Determine the project type handler
    match project.props.type:
        case "rag":
            from restai.projects.rag import RAG
            handler = RAG(brain)
        case "inference":
            from restai.projects.inference import Inference
            handler = Inference(brain)
        case "agent":
            from restai.projects.agent import Agent
            handler = Agent(brain)
        case "block":
            from restai.projects.block import Block
            handler = Block(brain)
        case _:
            return "", [], 0

    try:
        output_generator = handler.question(project, q, user, db)
        result = None
        async for line in output_generator:
            result = line
            break

        latency_ms = int((time.perf_counter() - start) * 1000)

        if result is None:
            return "", [], latency_ms

        answer = result.get("answer", "") if isinstance(result, dict) else str(result)
        sources = []
        if isinstance(result, dict) and "sources" in result:
            for s in result["sources"]:
                if isinstance(s, dict) and "text" in s:
                    sources.append(s["text"])
                elif isinstance(s, str):
                    sources.append(s)

        return answer, sources, latency_ms
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.exception("Error getting project answer: %s", e)
        return f"Error: {e}", [], latency_ms


async def run_evaluation(run_id: int, app):
    """Execute an evaluation run in the background.

    Args:
        run_id: ID of the EvalRunDatabase record to execute.
        app: FastAPI app instance (for accessing brain via app.state.brain).
    """
    from restai.database import get_db_wrapper
    from restai.models.models import User

    db = get_db_wrapper()
    try:
        run = db.db.query(EvalRunDatabase).filter(EvalRunDatabase.id == run_id).first()
        if run is None:
            logger.error("Eval run %d not found", run_id)
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.db.commit()

        metrics_list = json.loads(run.metrics) if isinstance(run.metrics, str) else run.metrics
        test_cases = (
            db.db.query(EvalTestCaseDatabase)
            .filter(EvalTestCaseDatabase.dataset_id == run.dataset_id)
            .all()
        )

        if not test_cases:
            run.status = "completed"
            run.summary = json.dumps({})
            run.completed_at = datetime.now(timezone.utc)
            db.db.commit()
            return

        brain = app.state.brain
        project = brain.find_project(run.project_id, db)
        if project is None:
            run.status = "failed"
            run.error = "Project not found or could not be loaded"
            run.completed_at = datetime.now(timezone.utc)
            db.db.commit()
            return

        # Apply prompt version if specified, or record active version
        if run.prompt_version_id:
            pv = db.get_prompt_version(run.prompt_version_id)
            if pv and pv.project_id == run.project_id:
                project.props.system = pv.system_prompt
        else:
            active_pv = db.get_active_prompt_version(run.project_id)
            if active_pv:
                run.prompt_version_id = active_pv.id
                db.db.commit()

        # Get eval LLM — use the project's own LLM
        eval_llm = None
        if project.props.llm:
            llm_model = brain.get_llm(project.props.llm, db)
            if llm_model:
                eval_llm = DeepEvalLLM(model=llm_model.llm)

        # Create a synthetic user for the eval (use the project creator)
        user_db = db.get_user_by_id(project.props.creator) if project.props.creator else None
        if user_db is None:
            # Fallback to admin
            user_db = db.get_user_by_username("admin")
        user = User.model_validate(user_db)

        score_totals = {}
        score_counts = {}

        for tc in test_cases:
            try:
                answer, sources, latency_ms = await _get_project_answer(
                    project, tc.question, brain, user, db
                )

                context = None
                if tc.context:
                    try:
                        context = json.loads(tc.context) if isinstance(tc.context, str) else tc.context
                    except (json.JSONDecodeError, TypeError):
                        context = None

                retrieval_context = sources if sources else (context or [])

                for metric_name in metrics_list:
                    try:
                        if metric_name == "faithfulness" and not retrieval_context:
                            # Skip faithfulness if no context available
                            continue
                        if metric_name == "correctness" and not tc.expected_answer:
                            # Skip correctness if no expected answer
                            continue

                        test = LLMTestCase(
                            input=tc.question,
                            actual_output=answer,
                            expected_output=tc.expected_answer,
                            retrieval_context=retrieval_context if retrieval_context else None,
                        )

                        if eval_llm:
                            metric = _build_metric(metric_name, eval_llm)
                            metric.measure(test)
                            score = metric.score
                            reason = metric.reason if hasattr(metric, 'reason') else None
                        else:
                            score = 0.0
                            reason = "No LLM available for evaluation"

                        passed = score >= 0.5 if score is not None else False

                        result = EvalResultDatabase(
                            run_id=run.id,
                            test_case_id=tc.id,
                            actual_answer=answer,
                            retrieval_context=json.dumps(retrieval_context) if retrieval_context else None,
                            metric_name=metric_name,
                            score=score,
                            reason=reason,
                            passed=passed,
                            latency_ms=latency_ms,
                        )
                        db.db.add(result)

                        if score is not None:
                            score_totals[metric_name] = score_totals.get(metric_name, 0) + score
                            score_counts[metric_name] = score_counts.get(metric_name, 0) + 1

                    except Exception as e:
                        logger.exception("Error evaluating metric '%s' for test case %d: %s", metric_name, tc.id, e)
                        result = EvalResultDatabase(
                            run_id=run.id,
                            test_case_id=tc.id,
                            actual_answer=answer,
                            metric_name=metric_name,
                            score=0.0,
                            reason=f"Evaluation error: {e}",
                            passed=False,
                            latency_ms=latency_ms,
                        )
                        db.db.add(result)

                db.db.commit()

            except Exception as e:
                logger.exception("Error processing test case %d: %s", tc.id, e)
                continue

        summary = {
            k: round(score_totals[k] / score_counts[k], 4)
            for k in score_totals
            if score_counts.get(k, 0) > 0
        }

        run.status = "completed"
        run.summary = json.dumps(summary)
        run.completed_at = datetime.now(timezone.utc)
        db.db.commit()

    except Exception as e:
        logger.exception("Eval run %d failed: %s", run_id, e)
        try:
            run = db.db.query(EvalRunDatabase).filter(EvalRunDatabase.id == run_id).first()
            if run:
                run.status = "failed"
                run.error = str(e)
                run.completed_at = datetime.now(timezone.utc)
                db.db.commit()
        except Exception:
            pass
    finally:
        db.db.close()
