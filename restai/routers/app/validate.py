"""HTTP endpoints for App-Builder reset + validate, plus runtime/test probes."""

from __future__ import annotations

import re

from fastapi import (
    Depends,
    HTTPException,
    Path as PathParam,
    Request,
)

from restai.auth import (
    check_not_restricted,
    get_current_username_project,
)
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import User

from ._common import (
    router,
    logger,
    _require_app_project,
    _record_ai_cost,
    _app_chat_id,
)


@router.post("/projects/{projectID}/app/reset", tags=["App Builder"])
async def route_app_reset(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Wipe everything and re-seed; used by the Reset Project button."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)
    from restai.app.storage import (
        delete_project_root, seed_hello_world,
    )
    from restai.agent2.memory import clear_session

    # Stop container before wiping; bind-mount otherwise holds public/ open.
    mgr = getattr(request.app.state.brain, "app_manager", None)
    if mgr is not None:
        try:
            mgr.remove_container(projectID)
        except Exception:
            logger.exception("reset: failed to stop container before wipe")

    delete_project_root(projectID)

    try:
        await clear_session(request.app.state.brain, _app_chat_id(projectID))
    except Exception:
        logger.exception("reset: failed to clear chat memory")

    seed_hello_world(projectID, project.props.human_name or project.props.name)

    if mgr is not None:
        try:
            await mgr.get_or_create(projectID)
        except Exception:
            logger.exception("reset: failed to start container after reseed")

    try:
        from restai.observability.audit import _log_to_db as _audit
        _audit(user.username, "APP_RESET", f"projects/{projectID}", 200)
    except Exception:
        pass

    return {"reset": True}


# Soft cap on validator payload; truncate bottom of file rather than burn tokens.
_VALIDATE_MAX_BYTES = 120 * 1024
_VALIDATE_MAX_FILES = 30


def _collect_review_files(project_id: int) -> list[dict]:
    """Read editable files (capped) for the validator."""
    from restai.app.storage import (
        get_project_root, EDITABLE_EXTENSIONS,
    )
    root = get_project_root(project_id)
    if not root.exists():
        return []
    out: list[dict] = []
    used = 0
    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(root).as_posix()
        if (
            rel.startswith("public/dist/")
            or rel.startswith("node_modules/")
            or rel.startswith(".")
            or "/." in "/" + rel
            or rel == "database.sqlite"
        ):
            continue
        if fp.suffix.lower() not in EDITABLE_EXTENSIONS:
            continue
        try:
            data = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        per_file_cap = max(2048, (_VALIDATE_MAX_BYTES - used) // max(1, _VALIDATE_MAX_FILES - len(out)))
        if len(data) > per_file_cap:
            data = data[:per_file_cap] + "\n/* [truncated for review] */"
        used += len(data)
        out.append({"path": rel, "content": data})
        if len(out) >= _VALIDATE_MAX_FILES or used >= _VALIDATE_MAX_BYTES:
            break
    return out


# Runtime-probe limits prevent hung backends + 50MB error pages from breaking validate.
_RUNTIME_PROBE_TIMEOUT = 6
_RUNTIME_PROBE_BODY_CAP = 1500
_DRY_RUN_PREVIEW_BYTES = 64 * 1024
# `FAIL <endpoint> [<method>]: <message>` per _TESTS_SYSTEM contract.
_TEST_FAIL_RE = re.compile(r"^FAIL\s+(\S+)(?:\s+(\S+))?\s*:\s*(.*)$", re.MULTILINE)


def _run_tests(request: Request, project_id: int) -> list[dict]:
    """Execute `tests/api.php` and convert FAIL lines into auto-fix-eligible issues."""
    from restai.app.storage import get_project_root
    root = get_project_root(project_id)
    test_file = root / "tests" / "api.php"
    if not test_file.is_file():
        return []
    brain = request.app.state.brain
    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        return []
    container = mgr.get_container(int(project_id))
    if container is None:
        return []
    docker_client = mgr.get_docker_client()
    if docker_client is None:
        return []

    # exec_run has no native timeout; use lower-level exec_create+exec_start in a thread abandoned after 60s.
    import threading as _threading
    import queue as _queue
    out_q: _queue.Queue = _queue.Queue(maxsize=1)

    def _exec():
        try:
            exec_id = docker_client.api.exec_create(
                container.id,
                cmd=["php", "/var/www/tests/api.php"],
                stdout=True,
                stderr=True,
                workdir="/var/www",
            )["Id"]
            output = docker_client.api.exec_start(exec_id, stream=False)
            inspect = docker_client.api.exec_inspect(exec_id)
            out_q.put((inspect.get("ExitCode"), output or b""))
        except Exception as e:
            out_q.put(("error", str(e).encode("utf-8")))

    th = _threading.Thread(target=_exec, daemon=True)
    th.start()
    try:
        exit_code, raw = out_q.get(timeout=60)
    except _queue.Empty:
        return [{
            "path": "tests/api.php",
            "severity": "high",
            "message": "Test runner timed out after 60 seconds. The test file may have a hung curl call.",
        }]

    if exit_code == "error":
        return [{
            "path": "tests/api.php",
            "severity": "low",
            "message": f"Test runner could not start: {raw.decode('utf-8', errors='replace')[:500]}",
        }]

    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    issues: list[dict] = []
    for m in _TEST_FAIL_RE.finditer(text):
        endpoint = m.group(1).strip()
        method = (m.group(2) or "").strip()
        msg = m.group(3).strip()
        # Drop FAIL lines whose endpoint isn't a project path; else filtered by immutability guard.
        if not endpoint.startswith("public/") and not endpoint.startswith("/"):
            continue
        endpoint_attr = endpoint.lstrip("/")
        prefix = f"[{method}] " if method else ""
        issues.append({
            "path": endpoint_attr,
            "severity": "high",
            "message": f"{prefix}Test failure: {msg}",
        })

    # Non-zero exit + no parsed FAIL lines → surface stderr for auto-fix loop.
    if exit_code not in (0, None) and not issues:
        snippet = text[-600:] if text else "(no output)"
        issues.append({
            "path": "tests/api.php",
            "severity": "medium",
            "message": f"Test runner exit code {exit_code}. Output tail:\n{snippet}",
        })
    return issues


def _runtime_probes(request: Request, project_id: int) -> list[dict]:
    """Hit the live preview container and surface runtime errors as issues."""
    import os as _os
    import requests as _requests
    from restai.app.storage import get_project_root

    issues: list[dict] = []
    brain = request.app.state.brain
    mgr = getattr(brain, "app_manager", None)
    if mgr is None:
        return issues
    port = mgr.get_port(project_id)
    if not port:
        return issues
    base = f"http://127.0.0.1:{port}"

    try:
        r = _requests.get(base + "/", timeout=_RUNTIME_PROBE_TIMEOUT)
        if r.status_code >= 500:
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": f"GET / returned HTTP {r.status_code}. Body: {r.text[:_RUNTIME_PROBE_BODY_CAP]}",
            })
        elif r.status_code >= 400:
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": f"GET / returned HTTP {r.status_code} — the SPA shell isn't being served. Check that public/index.html exists.",
            })
        # The new React contract uses `<div id="root">`; legacy vanilla
        # projects used `<div id="app">`. Accept either (and any quoting /
        # unquoted form) so the probe doesn't report a phantom "missing
        # mount" issue when the page is actually fine — that issue used
        # to drive the auto-fix loop to wreck working React apps by
        # renaming `#root` → `#app`.
        elif not re.search(r'\bid\s*=\s*["\']?(?:root|app)["\']?[\s/>]',
                           r.text, re.IGNORECASE):
            issues.append({
                "path": "public/index.html",
                "severity": "high",
                "message": "GET / served a page with no `id=\"root\"` (or `id=\"app\"`) mount element — the SPA can't render.",
            })
        if "<script type=\"module\" src=\"dist/app.js\"" not in r.text and "src=\"dist/app.js\"" not in r.text and "dist/app.js" not in r.text and r.status_code < 400:
            issues.append({
                "path": "public/index.html",
                "severity": "medium",
                "message": "Index page has no <script src=\"dist/app.js\"> — the TypeScript bundle won't load.",
            })
    except _requests.exceptions.RequestException as e:
        issues.append({
            "path": "/",
            "severity": "high",
            "message": f"GET / failed: {e}. The preview container is unreachable.",
        })

    # ── Probe 2: hit each public/api/*.php (skip underscore includes) ─
    root = get_project_root(project_id)
    api_dir = root / "public" / "api"
    if api_dir.is_dir():
        for php in sorted(api_dir.glob("*.php")):
            if php.name.startswith("_"):
                continue
            url = f"{base}/api/{php.name}"
            try:
                r = _requests.get(url, timeout=_RUNTIME_PROBE_TIMEOUT)
            except _requests.exceptions.RequestException as e:
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} failed: {e}",
                })
                continue
            ct = (r.headers.get("content-type") or "").lower()
            body_snip = r.text[:_RUNTIME_PROBE_BODY_CAP] if r.text else ""
            if r.status_code >= 500:
                # PHP fatal errors / parse errors land here. Body is
                # usually HTML with the actual error message — surface it
                # so the LLM can fix the right line.
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} returned HTTP {r.status_code} (likely a PHP error). Body:\n{body_snip}",
                })
                continue
            if "application/json" not in ct:
                issues.append({
                    "path": f"public/api/{php.name}",
                    "severity": "high",
                    "message": f"GET /api/{php.name} returned content-type {ct or 'none'!r} (not application/json). PHP must `header('Content-Type: application/json');`. Body:\n{body_snip}",
                })
                continue
            if 400 <= r.status_code < 500:
                # Skip 405 (GET on POST-only route is expected).
                if r.status_code != 405:
                    try:
                        body = r.json()
                        err_msg = body.get("error") if isinstance(body, dict) else None
                        if err_msg:
                            issues.append({
                                "path": f"public/api/{php.name}",
                                "severity": "medium",
                                "message": f"GET /api/{php.name} returned HTTP {r.status_code}: {err_msg}",
                            })
                    except Exception:
                        pass

    try:
        container = mgr.get_container(int(project_id))
        if container is not None:
            res = container.exec_run(
                ["sh", "-c", "test -f /tmp/esbuild.log && tail -c 6000 /tmp/esbuild.log || true"],
                demux=False,
            )
            if res.exit_code == 0 and res.output:
                log = res.output.decode("utf-8", errors="replace").strip()
                lower = log.lower()
                if log and ("✘ [error]" in lower or "[error]" in lower or "error:" in lower):
                    # esbuild appends; tail is current state.
                    snippet = log[-3000:]
                    issues.append({
                        "path": "src/",
                        "severity": "high",
                        "message": "esbuild build failed — the TypeScript bundle is broken so the page won't run. Build log tail:\n" + snippet,
                    })
    except Exception as e:
        logger.debug("validate: esbuild log read failed: %s", e)

    return issues


_VALIDATE_SYSTEM = """You are a code reviewer for a tiny React + MUI +
PHP + SQLite web app. The runtime is bundled by esbuild into one JS
file; the deploy needs only PHP + the bundle. You may be shown:

1. RUNTIME EVIDENCE — concrete failures observed by actually hitting the
   live preview (HTTP status codes, PHP error messages, esbuild build
   log). These are FACTS, not guesses. If present, every runtime
   failure must map to an entry in your `issues` array.

2. The full project source. Look ONLY for things that would actually
   break the deployed app:
   - Dangling refs to files/functions/exports that genuinely don't exist
     in the file list.
   - An HTML form / fetch call pointing at an `api/<x>.php` that has no
     matching file.
   - PHP that emits HTML or uses string-concat SQL.
   - SPA shell missing `<div id="root">` or `<script src="dist/app.js">`.

NPM IMPORT ALLOWLIST — these are LEGITIMATE, do NOT flag them:
  react, react-dom, react-dom/client, @mui/material/*,
  @mui/icons-material/*, @mui/system, @emotion/react, @emotion/styled.
Flag ONLY `import x from "<other-package>"` (e.g. axios, react-router,
lodash). Relative imports (./ or ../) are always fine.

INNOCENT UNTIL PROVEN GUILTY — bias hard against false positives:
- If you can't point at a SPECIFIC line that breaks the deployed app,
  say `ok: true`. Stylistic preferences, "could be more idiomatic",
  "should add error handling", "could split into smaller components",
  unused imports, missing TypeScript types — NONE of these are issues.
- The user's last build was working. A false-positive issue triggers an
  auto-fix loop that often WRECKS the working app to address phantom
  problems. When in doubt, return `ok: true`.

OUTPUT FORMAT — exactly this JSON, no prose, no fences:

{
  "ok": true,
  "summary": "Looks good — wired up correctly.",
  "issues": []
}

OR

{
  "ok": false,
  "summary": "1-sentence overview of the problems",
  "issues": [
    {"path": "src/app.ts", "severity": "high", "message": "Imports './views/Cart' but the plan/files list doesn't include src/views/Cart.ts."},
    {"path": "public/api/items.php", "severity": "medium", "message": "$id is interpolated into the SQL on line 14 — should be parameter-bound."}
  ]
}

`severity` is one of `low`, `medium`, `high`. Output ONLY the JSON object."""


@router.post("/projects/{projectID}/app/validate", tags=["App Builder"])
async def route_app_validate(
    request: Request,
    projectID: int = PathParam(description="Project ID"),
    user: User = Depends(get_current_username_project),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """Have the project's LLM review the generated app; returns structured report."""
    check_not_restricted(user)
    project = _require_app_project(request, projectID, db_wrapper)

    from restai.limits.budget import check_budget, check_rate_limit, check_api_key_quota
    check_budget(project, db_wrapper)
    check_rate_limit(project, db_wrapper)
    check_api_key_quota(user, db_wrapper)

    files = _collect_review_files(projectID)
    if not files:
        return {"ok": False, "summary": "No source files to review.", "issues": []}

    # Runtime probes BEFORE LLM: surface facts + feed them as evidence to the review.
    runtime_issues: list[dict] = []
    try:
        runtime_issues = _runtime_probes(request, projectID)
    except Exception:
        logger.exception("validate: runtime probes crashed")

    # Run LLM-generated test pack (best-effort) and merge into runtime evidence.
    try:
        # Let esbuild finish so test pack hits stable backend.
        import asyncio as _asyncio_v
        await _asyncio_v.sleep(1.5)
        test_issues = await _asyncio_v.get_event_loop().run_in_executor(
            None, _run_tests, request, projectID,
        )
        if test_issues:
            runtime_issues.extend(test_issues)
    except Exception:
        logger.exception("validate: test runner crashed")

    # FAST PATH: probes clean → skip LLM static review (known false-positive source).
    if not runtime_issues:
        return {
            "ok": True,
            "summary": "Runtime probes + test runner clean — app is observably working.",
            "issues": [],
        }

    parts: list[str] = []
    if runtime_issues:
        parts.append(
            "RUNTIME EVIDENCE (concrete failures observed by hitting the live preview):\n"
        )
        for i, issue in enumerate(runtime_issues, 1):
            parts.append(
                f"\n[{i}] {issue.get('severity','?').upper()} @ {issue.get('path','?')}\n"
                f"    {issue.get('message','')}\n"
            )
        parts.append(
            "\nThe failures above are facts, not guesses. Your fix plan must address them.\n\n"
        )
    parts.append("Project files:\n")
    for f in files:
        parts.append(f"\n=== {f['path']} ===\n{f['content']}\n")
    user_prompt = "".join(parts)
    full_prompt = _VALIDATE_SYSTEM + "\n\n" + user_prompt

    from restai.app.ai import _resolve_llm, _FENCE_RE
    import json as _json_pkg
    try:
        llm = _resolve_llm(request.app.state.brain, db_wrapper, project.props.llm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = llm.llm.complete(full_prompt)
    except Exception as e:
        # Degrade gracefully: return runtime evidence even when the LLM is unreachable.
        logger.exception("validate: LLM call failed; returning runtime evidence only")
        clean_issues = []
        seen: set[tuple[str, str]] = set()
        for it in runtime_issues:
            path = str(it.get("path", "") or "")[:200]
            message = str(it.get("message", "") or "")[:1000]
            if (path, message) in seen:
                continue
            seen.add((path, message))
            clean_issues.append({
                "path": path,
                "severity": str(it.get("severity", "high") or "high").lower(),
                "message": message,
            })
        return {
            "ok": False,
            "summary": (
                f"AI reviewer unreachable ({type(e).__name__}). "
                f"{len(clean_issues)} runtime issue(s) reported below — "
                "auto-fix will still target these."
            ),
            "issues": clean_issues,
            "ai_error": str(e)[:500],
        }

    raw = (result.text if hasattr(result, "text") else str(result)) or ""
    raw = raw.strip()
    fence = _FENCE_RE.search(raw)
    if fence and fence.group(1):
        raw = fence.group(1).strip()

    parsed: dict = {"ok": False, "summary": "Validator returned unparseable output.", "issues": []}
    try:
        # Tolerate prose around the JSON; take outermost braces.
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            cand = _json_pkg.loads(raw[start : end + 1])
            if isinstance(cand, dict):
                parsed = cand
    except Exception:
        pass

    parsed.setdefault("ok", False)
    parsed.setdefault("summary", "")
    issues = parsed.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    clean_issues = []
    for it in issues[:50]:
        if not isinstance(it, dict):
            continue
        clean_issues.append({
            "path": str(it.get("path", "") or "")[:200],
            "severity": str(it.get("severity", "medium") or "medium").lower(),
            "message": str(it.get("message", "") or "")[:1000],
        })

    # Merge runtime evidence into final issues, dedup on (path, message).
    seen = {(it["path"], it["message"]) for it in clean_issues}
    runtime_count = 0
    for it in runtime_issues:
        key = (str(it.get("path", "") or "")[:200], str(it.get("message", "") or "")[:1000])
        if key in seen:
            continue
        seen.add(key)
        clean_issues.insert(0, {
            "path": key[0],
            "severity": str(it.get("severity", "high") or "high").lower(),
            "message": key[1],
        })
        runtime_count += 1

    # Runtime failures override LLM verdict.
    if runtime_count > 0:
        parsed["ok"] = False
        if not parsed.get("summary"):
            parsed["summary"] = (
                f"{runtime_count} runtime failure(s) observed when hitting the live preview."
            )

    parsed["issues"] = clean_issues

    try:
        in_tokens = len(request.app.state.brain.tokenizer(full_prompt)) if hasattr(request.app.state.brain, "tokenizer") else 0
        out_tokens = len(request.app.state.brain.tokenizer(raw)) if hasattr(request.app.state.brain, "tokenizer") else 0
        _record_ai_cost(
            request, project, user, db_wrapper,
            question=f"validate: {len(files)} files",
            answer=parsed.get("summary", "")[:200],
            tokens={"input": in_tokens, "output": out_tokens},
            status="success",
        )
    except Exception:
        pass

    try:
        from restai.observability.audit import _log_to_db as _audit
        _audit(
            user.username, "APP_VALIDATE",
            f"projects/{projectID}:ok={parsed.get('ok')}:issues={len(clean_issues)}", 200,
        )
    except Exception:
        pass

    return parsed
