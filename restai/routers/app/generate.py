"""HTTP endpoints for App-Builder AI generation (plan / dry-run / execute / fix)."""

from __future__ import annotations

from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
    Request,
)
from pydantic import BaseModel, Field

from restai.auth import (
    check_not_restricted,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User
from restai.app.storage import (
    project_lock,
    read_file,
    write_file,
)

from ._common import (
    router,
    logger,
    _require_app_project,
    _record_ai_cost,
    _sse_frame,
    _app_chat_id,
)
from .validate import _runtime_probes


# AI generation runs on the project's own LLM (not System LLM); budget+quota
# checked up-front so exhausted projects get 402 without burning LLM cycles.

class FixFilePayload(BaseModel):
    path: str = Field(description="Project-relative file path")
    instruction: str = Field(min_length=2, max_length=4000, description="What you want changed in this file")


class PlanPayload(BaseModel):
    """Body for POST /app/generate/plan."""
    message: str = Field(min_length=1, max_length=20000, description="The new user message to add to the chat thread")


class ExecutePayload(BaseModel):
    """Body for POST /app/generate/execute."""
    plan: dict = Field(description="The full approved plan dict from /generate/plan")
    overwrite: bool = Field(default=False, description="If false, skip files that already exist on disk")


_DRY_RUN_PREVIEW_BYTES = 64 * 1024


@router.post("/projects/{projectID}/app/generate/plan", tags=["App Builder"])
async def route_app_generate_plan(
    request: Request,
    payload: PlanPayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Chat-style planning, SSE-streamed."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    from fastapi.responses import StreamingResponse
    from restai.app.ai import stream_plan
    from restai.agent2.memory import get_session, save_session
    from restai.agent2.types import Message, TextBlock, user_text_message

    chat_id = _app_chat_id(projectID)
    session = await get_session(request.app.state.brain, chat_id)

    # Append the new user message and PERSIST IMMEDIATELY. If the LLM call
    # fails or the client disconnects mid-stream, we still want the
    # question on record so the user can refine without retyping.
    session.messages.append(user_text_message(payload.message))
    await save_session(request.app.state.brain, chat_id, session)

    # Soft cap: only the last 40 messages flow into the prompt to keep the
    # context window in check. The full thread stays in memory for replay.
    sliced = session.messages[-40:]
    messages = [
        {"role": m.role, "content": m.text_content() if hasattr(m, "text_content") else ""}
        for m in sliced
    ]
    last_user_msg = payload.message

    async def stream():
        # We run the LLM stream in a worker thread because LlamaIndex
        # `stream_complete` is sync. Pulling deltas off a queue keeps the
        # SSE generator async-friendly.
        import asyncio as _asyncio
        import threading as _threading
        import queue as _queue

        events: _queue.Queue = _queue.Queue()

        def producer():
            try:
                for evt_name, evt_data in stream_plan(
                    request.app.state.brain, db_wrapper, project.props.llm, messages,
                    project_id=projectID,
                ):
                    events.put((evt_name, evt_data))
            except ValueError as e:
                events.put(("error", {"message": str(e)}))
            except Exception as e:
                logger.exception("plan stream crashed")
                events.put(("error", {"message": str(e)}))
            finally:
                events.put(("__end__", None))

        thread = _threading.Thread(target=producer, daemon=True)
        thread.start()

        final_tokens = {"input": 0, "output": 0}
        final_reply = ""
        final_plan = None
        had_plan = False
        try:
            while True:
                # Yield control while waiting on the queue, and bail if
                # the client disconnected.
                try:
                    evt = await _asyncio.get_event_loop().run_in_executor(
                        None, events.get, True, 0.5,
                    )
                except _queue.Empty:
                    if await request.is_disconnected():
                        return
                    continue
                if evt is None:
                    continue
                name, data = evt
                if name == "__end__":
                    break
                if name == "plan_complete":
                    final_tokens = data.get("tokens", final_tokens)
                    final_reply = data.get("reply", "") or ""
                    final_plan = data.get("plan")
                    had_plan = final_plan is not None
                yield _sse_frame(name, data or {})
        finally:
            # Persist FULL assistant reply (incl. fenced JSON tail) as single source of truth.
            try:
                if final_reply:
                    session.messages.append(
                        Message(role="assistant", content=[TextBlock(text=final_reply)])
                    )
                    await save_session(request.app.state.brain, chat_id, session)
            except Exception:
                logger.exception("failed to persist assistant chat turn")
            try:
                _record_ai_cost(
                    request, project, user, db_wrapper,
                    question=f"plan: {last_user_msg[:200]}",
                    answer=f"plan_replied={'yes' if had_plan else 'clarify'}",
                    tokens=final_tokens, status="success",
                )
            except Exception:
                pass
            try:
                from restai.audit import _log_to_db as _audit
                _audit(
                    user.username, "APP_PLAN",
                    f"projects/{projectID}:turns={len(messages)}", 200,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/projects/{projectID}/app/generate/dry-run", tags=["App Builder"])
async def route_app_generate_dry_run(
    request: Request,
    payload: ExecutePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Diff preview without calling the LLM or writing anything."""
    _require_app_project(request, projectID, db_wrapper)

    from restai.app.ai import validate_plan
    try:
        clean_plan = validate_plan(payload.plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {e}")

    import asyncio as _asyncio
    from collections import Counter
    from restai.app.storage import get_project_root
    root = get_project_root(projectID)

    out_files = await _asyncio.get_event_loop().run_in_executor(
        None, _build_dry_run_diff, root, clean_plan,
    )
    counts = Counter(f["change_kind"] for f in out_files)
    return {"files": out_files, "counts": dict(counts)}


def _build_dry_run_diff(root, clean_plan: dict) -> list[dict]:
    """Sync helper for the dry-run endpoint (dispatched via executor)."""
    out: list[dict] = []
    root_resolved = root.resolve()
    for ph_idx, phase in enumerate(clean_plan.get("phases", []), 1):
        for file_spec in phase.get("files", []):
            path = file_spec["path"]
            target = root / path
            # Defense-in-depth vs symlink escapes (a symlink inside root could point outside).
            try:
                if not target.resolve().is_relative_to(root_resolved):
                    continue
            except OSError:
                continue
            current_content = None
            size_bytes = 0
            change_kind = "new"
            if target.is_file():
                try:
                    raw = target.read_bytes()
                    size_bytes = len(raw)
                    if size_bytes > _DRY_RUN_PREVIEW_BYTES:
                        current_content = (
                            raw[:_DRY_RUN_PREVIEW_BYTES].decode("utf-8", errors="replace")
                            + "\n/* [truncated for preview] */"
                        )
                    else:
                        current_content = raw.decode("utf-8", errors="replace")
                except OSError:
                    current_content = None
                change_kind = "overwrite"
            out.append({
                "path": path,
                "purpose": file_spec.get("purpose", ""),
                "current_content": current_content,
                "change_kind": change_kind,
                "size_bytes": size_bytes,
                "phase": phase.get("name") or f"Phase {ph_idx}",
                "phase_index": ph_idx,
            })
    return out


@router.post("/projects/{projectID}/app/generate/execute", tags=["App Builder"])
async def route_app_generate_execute(
    request: Request,
    payload: ExecutePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Build the approved plan file by file; SSE progress + per-file overwrite check."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    from fastapi.responses import StreamingResponse
    from restai.app.ai import (
        validate_plan, stream_file_content,
    )
    from restai.app.storage import (
        ensure_project_root, project_lock, write_file, get_project_root,
    )

    # Defense in depth — client could have edited the plan.
    try:
        clean_plan = validate_plan(payload.plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {e}")

    ensure_project_root(projectID)
    root = get_project_root(projectID)
    phases = clean_plan["phases"]
    overwrite = bool(payload.overwrite)

    async def stream():
        import asyncio as _asyncio
        import threading as _threading
        import queue as _queue
        from restai.app.ai import generate_contracts

        written: list[str] = []
        failed: list[dict] = []
        total_files = sum(len(ph.get("files", [])) for ph in phases)
        total_tokens = {"input": 0, "output": 0}
        global_idx = 0
        contracts_text = ""

        try:
            # Sketch-then-fill: shared contracts generated BEFORE code,
            # injected into per-file prompts for cross-file consistency.
            yield _sse_frame("contracts_start", {
                "message": "Sketching shared contracts (TS interfaces, PHP signatures, SQL schemas)…",
            })
            try:
                contracts_text, contracts_tokens = await _asyncio.get_event_loop().run_in_executor(
                    None,
                    generate_contracts,
                    request.app.state.brain, db_wrapper,
                    project.props.llm, clean_plan,
                )
                total_tokens["input"] += int(contracts_tokens.get("input", 0) or 0)
                total_tokens["output"] += int(contracts_tokens.get("output", 0) or 0)
            except Exception as e:
                logger.warning("contracts pass failed (degrading gracefully): %s", e)
                contracts_text = ""
            yield _sse_frame("contracts_done", {
                "length": len(contracts_text or ""),
                "preview": (contracts_text or "")[:500],
            })

            # Test-pack generation moved to AFTER the phase loop (was 10-30s up-front waste).
            for ph_idx, phase in enumerate(phases, 1):
                if await request.is_disconnected():
                    yield _sse_frame("error", {"message": "client disconnected"})
                    return

                ph_files = phase.get("files", [])
                yield _sse_frame("phase_start", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "description": phase.get("description") or "",
                    "index": ph_idx,
                    "total": len(phases),
                    "file_count": len(ph_files),
                })

                phase_written: list[str] = []
                phase_failed: list[dict] = []

                for f_idx, file_spec in enumerate(ph_files, 1):
                    if await request.is_disconnected():
                        yield _sse_frame("error", {"message": "client disconnected"})
                        return
                    global_idx += 1

                    path = file_spec["path"]
                    purpose = file_spec.get("purpose", "")
                    target = root / path

                    yield _sse_frame("file_start", {
                        "path": path, "purpose": purpose,
                        "index": global_idx, "total": total_files,
                        "phase": phase.get("name"),
                        "phase_index": ph_idx,
                        "phase_file_index": f_idx,
                        "phase_file_total": len(ph_files),
                    })

                    if target.exists() and not overwrite:
                        failed.append({"path": path, "error": "exists (overwrite not set)"})
                        phase_failed.append({"path": path, "error": "exists (overwrite not set)"})
                        yield _sse_frame("file_error", {
                            "path": path, "error": "exists (overwrite not set)",
                        })
                        continue

                    already_written_snapshot = list(written)

                    events: _queue.Queue = _queue.Queue()
                    final_content_holder: dict = {}
                    def producer(_spec=file_spec, _phase=phase, _already=already_written_snapshot,
                                 _pid=projectID, _contracts=contracts_text):
                        try:
                            for evt_name, evt_data in stream_file_content(
                                request.app.state.brain, db_wrapper,
                                project.props.llm, clean_plan, _spec,
                                phase=_phase, already_written=_already,
                                project_id=_pid, contracts=_contracts,
                            ):
                                events.put((evt_name, evt_data))
                        except ValueError as e:
                            events.put(("file_error", {"path": _spec["path"], "error": str(e)}))
                        except Exception as e:
                            logger.exception("file stream crashed for %s", _spec["path"])
                            events.put(("file_error", {"path": _spec["path"], "error": str(e)}))
                        finally:
                            events.put(("__end__", None))

                    thread = _threading.Thread(target=producer, daemon=True)
                    thread.start()

                    file_failed = False
                    while True:
                        try:
                            evt = await _asyncio.get_event_loop().run_in_executor(
                                None, events.get, True, 0.5,
                            )
                        except _queue.Empty:
                            if await request.is_disconnected():
                                return
                            continue
                        name, data = evt
                        if name == "__end__":
                            break
                        if name == "file_done":
                            final_content_holder.update(data)
                        elif name == "file_error":
                            failed.append({"path": path, "error": data.get("error", "")})
                            phase_failed.append({"path": path, "error": data.get("error", "")})
                            yield _sse_frame("file_error", data)
                            file_failed = True
                            continue
                        if name in ("file_delta",):
                            yield _sse_frame(name, data)

                    if file_failed or not final_content_holder:
                        continue

                    # Static arch check rejects obviously broken output before disk
                    # (PHP emitting HTML, TS importing npm, etc.).
                    from restai.app.ai import static_architecture_checks
                    arch_issues = static_architecture_checks(
                        path, final_content_holder["content"],
                    )
                    if arch_issues:
                        err_msg = "Architecture violation(s):\n- " + "\n- ".join(arch_issues)
                        failed.append({"path": path, "error": err_msg})
                        phase_failed.append({"path": path, "error": err_msg})
                        yield _sse_frame("file_error", {"path": path, "error": err_msg})
                        continue

                    t = final_content_holder.get("tokens", {})
                    total_tokens["input"] += int(t.get("input", 0) or 0)
                    total_tokens["output"] += int(t.get("output", 0) or 0)

                    # Write under per-project lock so IDE writes don't race.
                    try:
                        async with project_lock(projectID):
                            new_etag = write_file(
                                projectID, path,
                                final_content_holder["content"].encode("utf-8"),
                                if_match=None,
                            )
                        written.append(path)
                        phase_written.append(path)
                        yield _sse_frame("file_done", {
                            "path": path,
                            "etag": new_etag,
                            "size": len(final_content_holder["content"]),
                        })
                    except HTTPException as e:
                        failed.append({"path": path, "error": str(e.detail)})
                        phase_failed.append({"path": path, "error": str(e.detail)})
                        yield _sse_frame("file_error", {"path": path, "error": str(e.detail)})
                    except Exception as e:
                        failed.append({"path": path, "error": str(e)})
                        phase_failed.append({"path": path, "error": str(e)})
                        yield _sse_frame("file_error", {"path": path, "error": str(e)})

                yield _sse_frame("phase_done", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "index": ph_idx,
                    "total": len(phases),
                    "written": phase_written,
                    "failed": phase_failed,
                })

                # Per-phase runtime probes after each phase; bind-mounted files mean
                # PHP picks up changes and esbuild recompiles automatically. Best-effort.
                try:
                    phase_runtime_issues = _runtime_probes(request, projectID)
                except Exception:
                    logger.exception("phase runtime probes crashed (non-fatal)")
                    phase_runtime_issues = []
                yield _sse_frame("phase_check", {
                    "name": phase.get("name") or f"Phase {ph_idx}",
                    "index": ph_idx,
                    "issues": phase_runtime_issues,
                })

                # Per-phase inline auto-fix: ONE focused fix turn if issues
                # touch already-written files (prevents poisoning next phase's context).
                fix_targets: list[str] = []
                fix_relevant_issues: list[dict] = []
                written_set = set(written)
                for issue in phase_runtime_issues:
                    p = issue.get("path") or ""
                    if p in written_set and p not in fix_targets:
                        fix_targets.append(p)
                        fix_relevant_issues.append(issue)

                if fix_targets and not await request.is_disconnected():
                    yield _sse_frame("phase_fix_start", {
                        "phase": phase.get("name") or f"Phase {ph_idx}",
                        "index": ph_idx,
                        "targets": fix_targets,
                        "issue_count": len(fix_relevant_issues),
                    })
                    try:
                        from restai.app.ai import inline_fix_files
                        fixed_map, fix_tokens = await _asyncio.get_event_loop().run_in_executor(
                            None,
                            inline_fix_files,
                            request.app.state.brain, db_wrapper,
                            project.props.llm, clean_plan, contracts_text,
                            fix_relevant_issues, fix_targets, projectID,
                        )
                        total_tokens["input"] += int(fix_tokens.get("input", 0) or 0)
                        total_tokens["output"] += int(fix_tokens.get("output", 0) or 0)
                    except Exception:
                        logger.exception("inline fix failed for phase %s", ph_idx)
                        fixed_map = {}

                    fixed_paths: list[str] = []
                    fix_errors: list[dict] = []
                    for fp, fc in (fixed_map or {}).items():
                        from restai.app.ai import static_architecture_checks
                        arch_issues = static_architecture_checks(fp, fc)
                        if arch_issues:
                            fix_errors.append({"path": fp, "error": "Architecture violation: " + "; ".join(arch_issues)})
                            continue
                        try:
                            async with project_lock(projectID):
                                write_file(projectID, fp, fc.encode("utf-8"), if_match=None)
                            fixed_paths.append(fp)
                        except HTTPException as e:
                            fix_errors.append({"path": fp, "error": str(e.detail)})
                        except Exception as e:
                            fix_errors.append({"path": fp, "error": str(e)})

                    yield _sse_frame("phase_fix_done", {
                        "phase": phase.get("name") or f"Phase {ph_idx}",
                        "index": ph_idx,
                        "fixed": fixed_paths,
                        "errors": fix_errors,
                    })

            # Test pack: produces tests/api.php for /app/validate to feed auto-fix loop.
            yield _sse_frame("tests_start", {
                "message": "Generating end-to-end test pack (tests/api.php)…",
            })
            try:
                from restai.app.ai import generate_tests
                tests_text, tests_tokens = await _asyncio.get_event_loop().run_in_executor(
                    None,
                    generate_tests,
                    request.app.state.brain, db_wrapper,
                    project.props.llm, clean_plan, contracts_text,
                )
                total_tokens["input"] += int(tests_tokens.get("input", 0) or 0)
                total_tokens["output"] += int(tests_tokens.get("output", 0) or 0)
            except Exception as e:
                logger.warning("test gen failed (degrading gracefully): %s", e)
                tests_text = ""
            if tests_text:
                try:
                    async with project_lock(projectID):
                        write_file(
                            projectID, "tests/api.php",
                            tests_text.encode("utf-8"),
                            if_match=None,
                        )
                    yield _sse_frame("tests_generated", {
                        "path": "tests/api.php",
                        "size": len(tests_text),
                    })
                except Exception as e:
                    logger.warning("test file write failed: %s", e)

            # Restart preview; emit `preview_restarting` BEFORE await and `preview_ready`
            # AFTER, else auto-validate hits stale/half-booted container.
            mgr = getattr(request.app.state.brain, "app_manager", None)
            if mgr is not None and mgr.get_port(projectID) is not None:
                yield _sse_frame("preview_restarting", {
                    "message": "Restarting preview container so esbuild rebuilds the bundle…",
                })
                try:
                    await mgr.restart(projectID)
                    yield _sse_frame("preview_ready", {"status": "ok"})
                except Exception as e:
                    logger.exception("Preview restart failed after execute (project=%s)", projectID)
                    yield _sse_frame("preview_ready", {
                        "status": "error",
                        "error": str(e)[:200],
                    })

            yield _sse_frame("complete", {
                "written": written,
                "failed": failed,
                "tokens": total_tokens,
            })
        finally:
            try:
                _record_ai_cost(
                    request, project, user, db_wrapper,
                    question=f"execute: {clean_plan.get('summary','')[:160]}",
                    answer=f"wrote {len(written)} files, {len(failed)} failed",
                    tokens=total_tokens,
                    status="success" if not failed else "partial",
                )
            except Exception:
                pass
            try:
                from restai.audit import _log_to_db as _audit
                _audit(
                    user.username, "APP_EXECUTE",
                    f"projects/{projectID}:wrote={len(written)}:failed={len(failed)}",
                    200,
                )
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/projects/{projectID}/app/files/fix-ai", tags=["App Builder"])
async def route_app_fix_file(
    request: Request,
    payload: FixFilePayload,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Per-file targeted edit. Cheaper than full regeneration."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    current_bytes, current_etag = read_file(projectID, payload.path)
    try:
        current_text = current_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="binary file is not editable")

    from restai.app.ai import fix_file_with_ai
    try:
        new_content, tokens = fix_file_with_ai(
            request.app.state.brain, db_wrapper, project.props.llm,
            payload.path, current_text, payload.instruction,
        )
    except ValueError as e:
        _record_ai_cost(
            request, project, user, db_wrapper,
            question=f"fix {payload.path}: {payload.instruction}",
            answer="", tokens={"input": 0, "output": 0}, status="error",
        )
        raise HTTPException(status_code=400, detail=str(e))

    async with project_lock(projectID):
        new_etag = write_file(
            projectID, payload.path,
            new_content.encode("utf-8"),
            if_match=current_etag,
        )

    _record_ai_cost(
        request, project, user, db_wrapper,
        question=f"fix {payload.path}: {payload.instruction}",
        answer=new_content[:200],
        tokens=tokens, status="success",
    )

    try:
        from restai.audit import _log_to_db as _audit
        _audit(user.username, "APP_FIX_FILE", f"projects/{projectID}:{payload.path}", 200)
    except Exception:
        pass

    return {"path": payload.path, "etag": new_etag, "size": len(new_content)}
