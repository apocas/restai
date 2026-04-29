"""Filesystem helpers for app-builder projects.

Each `app` project's source tree lives at ``<apps_root>/<project_id>/`` where
``apps_root`` is either ``$RESTAI_APPS_PATH`` (typical in Docker/k8s where it
points at a persistent volume) or ``<install_root>/apps`` for local dev.

All functions that take a ``relative_path`` argument enforce a traversal guard:
the resolved absolute path must stay inside the project root or
``HTTPException(400)`` is raised. Callers must NEVER concatenate paths
themselves — always go through :func:`resolve_path`.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

import restai.config as _cfg

# Editable text files the IDE accepts. Anything else is treated as binary and
# excluded from the editor (the file may still exist on disk and be served via
# the preview proxy). Keep this list tight — extending it is much safer than
# accidentally letting users edit a real binary.
EDITABLE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".php", ".phtml",
    ".html", ".htm", ".css", ".scss",
    ".json", ".md", ".txt", ".svg",
    ".env", ".gitignore", ".htaccess",
    ".sql",
}

# Per-file size cap. Blocks pathological writes from the IDE and accidental
# binary uploads. Generated apps that need bigger assets should ship them via
# the FTP/SFTP deploy path, not the IDE.
MAX_FILE_BYTES = 256 * 1024  # 256 KB

# Directories never shown in the IDE tree (still on disk, still preview-served).
HIDDEN_DIR_NAMES = {".git", "node_modules", "vendor", "__pycache__", ".cache"}

# Per-project asyncio locks — one per project_id, lazily created. Guards file
# CRUD against the LLM regenerator stomping a concurrent IDE save.
_LOCKS: dict[int, asyncio.Lock] = {}


def get_apps_root() -> Path:
    """Return the directory under which all per-project app trees live.

    Resolved on every call so RESTAI_APPS_PATH changes between requests
    (multi-worker, settings reload) take effect immediately. Created on first
    miss — RESTai owns this directory exclusively.
    """
    raw = _cfg.RESTAI_APPS_PATH
    if raw:
        root = Path(raw)
    else:
        # PROJECT_ROOT in main.py is `Path(__file__).parent.parent`; mirror it
        # without importing main (which would pull in the FastAPI app at
        # config-resolution time).
        root = Path(__file__).resolve().parent.parent.parent / "apps"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_project_root(project_id: int) -> Path:
    """Return ``<apps_root>/<project_id>/``. Does NOT create the directory —
    callers that intend to write should use :func:`ensure_project_root`."""
    return get_apps_root() / str(int(project_id))


def ensure_project_root(project_id: int) -> Path:
    root = get_project_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_lock(project_id: int) -> asyncio.Lock:
    """Lazy, per-project asyncio lock. Use as ``async with project_lock(id):``
    around any file mutation so concurrent saves serialize."""
    pid = int(project_id)
    lock = _LOCKS.get(pid)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[pid] = lock
    return lock


def resolve_path(project_id: int, relative_path: str) -> Path:
    """Resolve ``<project_root>/<relative_path>`` and raise 400 if it would
    escape the project root.

    This is the single chokepoint for path validation in the app router —
    every endpoint that accepts a path from the request MUST call this.
    """
    if relative_path is None:
        raise HTTPException(status_code=400, detail="path is required")
    # Reject NUL bytes outright — surprises sqlite, posix, and Docker exec.
    if "\x00" in relative_path:
        raise HTTPException(status_code=400, detail="invalid path")
    # Strip leading slash to keep the join semantics intuitive (`/a/b` → `a/b`).
    cleaned = relative_path.lstrip("/").lstrip("\\")
    if not cleaned:
        raise HTTPException(status_code=400, detail="path is required")

    root = get_project_root(project_id).resolve()
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="path traversal denied")
    return candidate


def is_editable(path: Path) -> bool:
    """True if the IDE should expose ``path`` as an editable text file."""
    suffix = path.suffix.lower()
    if suffix in EDITABLE_EXTENSIONS:
        return True
    # Files with no extension are editable when they are a known config name.
    if not suffix and path.name in {"Dockerfile", "Procfile", "Makefile"}:
        return True
    return False


def compute_etag(data: bytes) -> str:
    """Stable, content-addressed ETag. SHA-256/12 — collision-resistant for
    the IDE's "did the file change underneath me?" check, short enough for
    headers."""
    return hashlib.sha256(data).hexdigest()[:12]


def list_tree(project_id: int) -> list[dict]:
    """Recursive file listing under the project root, sorted (dirs first,
    then files alphabetically). Hidden dirs (``HIDDEN_DIR_NAMES``) are
    omitted. The SQLite database file is included so the user knows it
    exists, but ``editable=False`` since it isn't text.
    """
    root = get_project_root(project_id)
    if not root.exists():
        return []

    def walk(current: Path) -> list[dict]:
        entries: list[dict] = []
        try:
            children = sorted(
                current.iterdir(),
                key=lambda p: (0 if p.is_dir() else 1, p.name.lower()),
            )
        except FileNotFoundError:
            return entries
        for child in children:
            if child.name in HIDDEN_DIR_NAMES:
                continue
            rel = child.relative_to(root).as_posix()
            if child.is_dir():
                entries.append({
                    "name": child.name,
                    "path": rel,
                    "type": "dir",
                    "children": walk(child),
                })
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = 0
                entries.append({
                    "name": child.name,
                    "path": rel,
                    "type": "file",
                    "size": size,
                    "editable": is_editable(child),
                })
        return entries

    return walk(root)


def read_file(project_id: int, relative_path: str) -> tuple[bytes, str]:
    """Return ``(content, etag)`` for ``relative_path``. 404 on missing,
    400 on traversal, 413 if larger than ``MAX_FILE_BYTES``."""
    target = resolve_path(project_id, relative_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large for editor")
    data = target.read_bytes()
    return data, compute_etag(data)


def write_file(
    project_id: int,
    relative_path: str,
    data: bytes,
    if_match: Optional[str] = None,
) -> str:
    """Write ``data`` to ``relative_path``. Returns the new ETag.

    If ``if_match`` is provided and the file already exists with a different
    ETag, raises 409 (the IDE's optimistic-concurrency story). 413 if the
    payload is larger than ``MAX_FILE_BYTES``. 400 if the extension is not in
    ``EDITABLE_EXTENSIONS`` — protects against turning the file API into an
    arbitrary binary upload.
    """
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds size cap")
    target = resolve_path(project_id, relative_path)
    if not is_editable(target):
        raise HTTPException(status_code=400, detail="extension not allowed")

    if target.exists():
        if if_match is not None:
            current_etag = compute_etag(target.read_bytes())
            if current_etag != if_match:
                raise HTTPException(
                    status_code=409,
                    detail={"reason": "etag_mismatch", "current_etag": current_etag},
                )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return compute_etag(data)


def delete_project_root(project_id: int) -> None:
    """Best-effort wipe of the project's source tree. Used on project
    deletion. Never raises — file deletion failure shouldn't block the DB
    cascade."""
    try:
        shutil.rmtree(get_project_root(project_id), ignore_errors=True)
    except Exception:
        pass


def seed_hello_world(project_id: int, project_name: str) -> None:
    """Seed a minimal SPA scaffold matching the App Builder architecture
    contract: TypeScript renders all UI, PHP serves a JSON API only, SQLite
    schema lives in PHP.

    Idempotent — never overwrites an existing file. The ``database.sqlite``
    file is created lazily by ``public/api/_db.php`` on the first request,
    matching how the deployed app must behave (so the seed exercises the
    same path as production).
    """
    root = ensure_project_root(project_id)

    safe_title = project_name.replace("</", "<\\/")  # cheap HTML safety

    files = {
        # ── SPA shell — pure HTML, no PHP, no server-rendered content ──
        "public/index.html": (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"  <title>{safe_title}</title>\n"
            "  <link rel=\"stylesheet\" href=\"styles.css\">\n"
            "</head>\n"
            "<body>\n"
            "  <div id=\"app\">Loading…</div>\n"
            "  <script type=\"module\" src=\"dist/app.js\"></script>\n"
            "</body>\n"
            "</html>\n"
        ),
        # ── Plain CSS ──────────────────────────────────────────────────
        "public/styles.css": (
            ":root { color-scheme: light dark; }\n"
            "body { font-family: system-ui, -apple-system, sans-serif; max-width: 720px;\n"
            "       margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }\n"
            "h1 { color: #1f6feb; margin-bottom: 0.25rem; }\n"
            "p.subtitle { color: #666; margin-top: 0; }\n"
            "ul.items { padding-left: 1.5rem; }\n"
            "ul.items li { margin: 0.25rem 0; }\n"
            "form { display: flex; gap: 0.5rem; margin: 1rem 0; }\n"
            "input[type=text] { flex: 1; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }\n"
            "button { padding: 0.5rem 1rem; border: 0; background: #1f6feb; color: white;\n"
            "         border-radius: 4px; cursor: pointer; }\n"
            "button:hover { background: #1855b0; }\n"
            ".error { color: #b91c1c; padding: 0.5rem; background: #fee; border-radius: 4px; }\n"
        ),
        # ── Shared PDO bootstrap + lazy schema/seed ────────────────────
        "public/api/_db.php": (
            "<?php\n"
            "// Shared PDO bootstrap. Idempotent: every API request goes\n"
            "// through here, so the DB and tables always exist.\n"
            "function db(): PDO {\n"
            "    static $pdo = null;\n"
            "    if ($pdo !== null) return $pdo;\n"
            "    $path = __DIR__ . '/../../database.sqlite';\n"
            "    $pdo = new PDO('sqlite:' . $path);\n"
            "    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);\n"
            "    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);\n"
            "    $pdo->exec(\"CREATE TABLE IF NOT EXISTS items (\n"
            "        id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            "        name TEXT NOT NULL,\n"
            "        created_at DATETIME DEFAULT CURRENT_TIMESTAMP\n"
            "    )\");\n"
            "    $count = (int)$pdo->query('SELECT COUNT(*) FROM items')->fetchColumn();\n"
            "    if ($count === 0) {\n"
            "        $stmt = $pdo->prepare('INSERT INTO items (name) VALUES (?)');\n"
            "        foreach (['Welcome to your new app', 'Edit src/app.ts to customise',\n"
            "                  'Hit Generate with AI to scaffold a real app'] as $name) {\n"
            "            $stmt->execute([$name]);\n"
            "        }\n"
            "    }\n"
            "    return $pdo;\n"
            "}\n"
        ),
        # ── Sample JSON endpoint ───────────────────────────────────────
        "public/api/items.php": (
            "<?php\n"
            "require_once __DIR__ . '/_db.php';\n"
            "header('Content-Type: application/json; charset=utf-8');\n"
            "\n"
            "$method = $_SERVER['REQUEST_METHOD'];\n"
            "try {\n"
            "    $pdo = db();\n"
            "    if ($method === 'GET') {\n"
            "        $rows = $pdo->query('SELECT id, name, created_at FROM items ORDER BY id')->fetchAll();\n"
            "        echo json_encode(['items' => $rows]);\n"
            "        exit;\n"
            "    }\n"
            "    if ($method === 'POST') {\n"
            "        $body = json_decode(file_get_contents('php://input'), true) ?? [];\n"
            "        $name = trim($body['name'] ?? '');\n"
            "        if ($name === '') {\n"
            "            http_response_code(400);\n"
            "            echo json_encode(['error' => 'name is required']);\n"
            "            exit;\n"
            "        }\n"
            "        $stmt = $pdo->prepare('INSERT INTO items (name) VALUES (?)');\n"
            "        $stmt->execute([$name]);\n"
            "        echo json_encode(['id' => (int)$pdo->lastInsertId(), 'name' => $name]);\n"
            "        exit;\n"
            "    }\n"
            "    http_response_code(405);\n"
            "    echo json_encode(['error' => 'method not allowed']);\n"
            "} catch (Throwable $e) {\n"
            "    http_response_code(500);\n"
            "    echo json_encode(['error' => $e->getMessage()]);\n"
            "}\n"
        ),
        # ── TypeScript SPA entry — fetches JSON, renders DOM ───────────
        "src/app.ts": (
            "// TypeScript SPA entry. esbuild bundles this + everything it\n"
            "// imports into public/dist/app.js. The dev container watches\n"
            "// src/ and rebuilds on every save.\n"
            "//\n"
            "// Architecture: this file (and src/views/*) renders ALL UI in\n"
            "// the browser via DOM APIs. PHP under public/api/*.php serves\n"
            "// JSON only — never HTML. Same-origin fetch, no CORS needed.\n"
            "\n"
            "interface Item {\n"
            "  id: number;\n"
            "  name: string;\n"
            "  created_at: string;\n"
            "}\n"
            "\n"
            "interface ItemsResponse {\n"
            "  items: Item[];\n"
            "}\n"
            "\n"
            "// All API URLs are RELATIVE (no leading slash). This makes the\n"
            "// app work both in the dev preview (which is iframed under\n"
            "// /projects/<id>/app/preview/) and on any FTP deploy target —\n"
            "// domain root or subdirectory, doesn't matter.\n"
            "async function fetchItems(): Promise<Item[]> {\n"
            "  const res = await fetch('api/items.php');\n"
            "  if (!res.ok) throw new Error(`HTTP ${res.status}`);\n"
            "  const body = (await res.json()) as ItemsResponse;\n"
            "  return body.items;\n"
            "}\n"
            "\n"
            "async function addItem(name: string): Promise<void> {\n"
            "  const res = await fetch('api/items.php', {\n"
            "    method: 'POST',\n"
            "    headers: { 'Content-Type': 'application/json' },\n"
            "    body: JSON.stringify({ name }),\n"
            "  });\n"
            "  if (!res.ok) {\n"
            "    const err = await res.json().catch(() => ({ error: res.statusText }));\n"
            "    throw new Error(err.error ?? `HTTP ${res.status}`);\n"
            "  }\n"
            "}\n"
            "\n"
            "function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {\n"
            "  const node = document.createElement(tag);\n"
            "  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);\n"
            "  for (const c of children) node.append(typeof c === 'string' ? document.createTextNode(c) : c);\n"
            "  return node;\n"
            "}\n"
            "\n"
            "async function render(): Promise<void> {\n"
            "  const root = document.getElementById('app')!;\n"
            "  root.innerHTML = '';\n"
            "  root.append(\n"
            f"    el('h1', {{}}, '{safe_title}'),\n"
            "    el('p', { class: 'subtitle' }, 'Generated by RESTai App Builder. Hit ',\n"
            "      el('strong', {}, 'Generate with AI'),\n"
            "      ' to scaffold a real app, or edit src/app.ts to customise this one.'),\n"
            "  );\n"
            "\n"
            "  const list = el('ul', { class: 'items' });\n"
            "  const errBox = el('div', { class: 'error', style: 'display:none' });\n"
            "\n"
            "  const refresh = async () => {\n"
            "    try {\n"
            "      list.innerHTML = '';\n"
            "      errBox.style.display = 'none';\n"
            "      const items = await fetchItems();\n"
            "      for (const it of items) list.append(el('li', {}, it.name));\n"
            "    } catch (e) {\n"
            "      errBox.style.display = 'block';\n"
            "      errBox.textContent = `Could not load items: ${(e as Error).message}`;\n"
            "    }\n"
            "  };\n"
            "\n"
            "  const input = el('input', { type: 'text', placeholder: 'Add an item…' }) as HTMLInputElement;\n"
            "  const button = el('button', { type: 'submit' }, 'Add');\n"
            "  const form = el('form', {}, input, button);\n"
            "  form.addEventListener('submit', async (ev) => {\n"
            "    ev.preventDefault();\n"
            "    const name = input.value.trim();\n"
            "    if (!name) return;\n"
            "    try {\n"
            "      await addItem(name);\n"
            "      input.value = '';\n"
            "      await refresh();\n"
            "    } catch (e) {\n"
            "      errBox.style.display = 'block';\n"
            "      errBox.textContent = (e as Error).message;\n"
            "    }\n"
            "  });\n"
            "\n"
            "  root.append(form, errBox, list);\n"
            "  await refresh();\n"
            "}\n"
            "\n"
            "document.addEventListener('DOMContentLoaded', render);\n"
        ),
        "README.md": (
            f"# {project_name}\n\n"
            "Standalone PHP + TypeScript + SQLite app generated by RESTai App Builder.\n\n"
            "## Architecture\n\n"
            "- **Frontend**: TypeScript renders all UI in the browser via DOM APIs.\n"
            "  Source in `src/`, bundled by esbuild into `public/dist/app.js`.\n"
            "- **Backend**: PHP under `public/api/` serves JSON only (never HTML).\n"
            "  Schema lives in `public/api/_db.php`, idempotent on every request.\n"
            "- **Database**: SQLite, created lazily on the first API hit at\n"
            "  `database.sqlite` in the project root.\n"
            "- **No dependencies**: no Composer, no npm at runtime. Drop the\n"
            "  contents of `public/` into any cheap shared PHP host's docroot.\n\n"
            "## File layout\n\n"
            "- `public/index.html` — SPA shell\n"
            "- `public/styles.css` — page styles\n"
            "- `public/dist/app.js` — compiled TypeScript bundle (auto-built)\n"
            "- `public/api/_db.php` — PDO bootstrap + schema/seed\n"
            "- `public/api/*.php` — JSON endpoints\n"
            "- `src/*.ts` — TypeScript sources (edit these)\n"
            "- `database.sqlite` — SQLite database (created on first request)\n\n"
            "## Deploy\n\n"
            "1. Hit **Download ZIP** in the App Builder.\n"
            "2. Upload the contents of `public/` to your host's docroot.\n"
            "3. Browse — `_db.php` will create `database.sqlite` on the first hit.\n"
        ),
    }

    for rel_path, content in files.items():
        target = root / rel_path
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
