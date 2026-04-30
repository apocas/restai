"""LLM-driven app generation for the App Builder, two-step agent flow.

Public entry points:

- :func:`stream_plan` — chat-style planning. Takes the running message
  history (`[{role, content}, ...]`); streams the LLM's reply as
  ``("plan_chunk", text)`` deltas, then yields a single
  ``("plan_complete", {"plan": <dict|None>, "reply": "<full text>"})``.
  The plan dict is parsed from the trailing JSON block; ``None`` if the
  AI replied with a question or otherwise didn't include a parsable plan.

- :func:`stream_file_content` — generate the contents of one file given
  the approved plan + the file's (path, purpose). Yields
  ``("file_delta", text)`` deltas, then ``("file_done", final_content)``.

- :func:`fix_file_with_ai` — single-file targeted edit (kept from the
  prior version, prompt updated to the new SPA architecture so fixes
  don't reintroduce PHP-rendered HTML).

- :func:`validate_plan` — strict schema check on the plan dict (required
  fields, allowed PHP locations, file count + size caps). Used by both
  the plan endpoint (after parsing the LLM reply) and the execute
  endpoint (defense in depth — the client could have edited the plan).

All calls use the **project's own LLM** (selected at project create
time), never the platform System LLM. Cost is recorded by the endpoint
caller via the standard `log_inference` pipeline.

Architecture contract enforced by the system prompts and the validators:
- TypeScript renders ALL UI; PHP serves a JSON API only.
- PHP files MUST live under ``public/api/``; ``index.php`` outside there
  is allowed only as a thin SPA fallback router.
- HTML lives in ``public/index.html`` (SPA shell). Routing is client-side
  (hash router) so the app deploys to shared hosts without rewrite rules.
- All SQL is parameter-bound. All API responses set
  ``Content-Type: application/json`` and never emit HTML.
- No external dependencies: no Composer, no npm packages at runtime.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator, Generator, Iterable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

# Per-file cap. Matches the file CRUD endpoint so generated files can be
# edited later from the IDE.
MAX_FILE_BYTES = 256 * 1024

# Plan-level caps. The LLM is told these and the validator enforces them.
MAX_PLAN_FILES = 30
MAX_PLAN_TOTAL_BYTES = 200 * 1024  # estimated by counting purpose strings
                                   # (the plan itself is small; this is a
                                   # sanity check that the LLM isn't
                                   # generating a manifest with thousands
                                   # of files).

# Cap on a single LLM response we'll consume. The plan reply is text +
# small JSON; a single file content shouldn't exceed MAX_FILE_BYTES.
MAX_LLM_RESPONSE_BYTES = 512 * 1024

# Dynamic-context caps that bound per-LLM-call prompt size. These ride
# every per-file generation + every chat planning turn — every byte here
# is paid as inference latency on local LLMs. Tuned to keep the dynamic
# slice of any single prompt under ~25 KB (~6K tokens).
PROMPT_RELEVANT_FILES_MAX = 4         # how many sibling files to attach
PROMPT_RELEVANT_PER_FILE_BYTES = 3000  # per-file truncation cap
PROMPT_RELEVANT_TOTAL_BYTES = 12000    # combined budget across siblings
PROMPT_TARGET_FILE_BYTES = 6000        # cap on the CURRENT-file block when
                                       # the file already exists on disk
PROMPT_SNAPSHOT_PER_FILE_BYTES = 3000  # planner snapshot per shared-infra file
PROMPT_SNAPSHOT_TOTAL_BYTES = 9000     # planner snapshot combined budget

# Editable extensions for files the generator may write. Extra-tight on
# purpose: any binary asset must be added by the user manually.
GENERATION_ALLOWED_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".php", ".phtml",
    ".html", ".htm", ".css", ".scss",
    ".json", ".md", ".txt", ".svg",
    ".sql",
}


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = """You plan small self-contained web apps that run on any
cheap shared PHP host (PHP 8 + PDO SQLite, no Composer, no Node, no
other deps at deploy time). Per-file generation handles syntax/style
later — your job is structure: which files, in which phases.

ARCHITECTURE — every plan MUST conform:

1. Backend = PHP JSON API, OPTIONAL.
   - Backendless is the preferred default (calculators, games,
     localStorage apps). Omit `database`/`api`/PHP files entirely
     unless server-side persistence is genuinely required.
   - When present: all PHP under `public/api/`, JSON-only, PDO with
     prepared statements, NEVER emit HTML or `<?= ... ?>`. Shared
     `public/api/_db.php` does PDO bootstrap + idempotent
     `CREATE TABLE IF NOT EXISTS` + demo seed; other API files
     `require_once __DIR__ . '/_db.php'`. Optional `public/index.php`
     may be a 5-line SPA-fallback router only.

2. Frontend = React 18 + MUI v5, bundled by esbuild into a single
   `public/dist/app.js`. Required files for any non-trivial app:
   - `public/index.html`: SPA shell with `<div id="root">` +
     `<script type="module" src="dist/app.js">`. Pure HTML, no PHP.
   - `public/styles.css`: body reset ONLY (margin: 0; box-sizing). MUI
     handles component styling.
   - `src/main.tsx`: React entry, `createRoot` + `<ThemeProvider>` +
     `<CssBaseline />` + `<App />`.
   - `src/App.tsx`: top-level layout (`<AppBar>` + `<Container>`) plus
     a tiny `useHashRouter` hook that switches between view components.
   - `src/theme.ts`: `createTheme({ palette, typography, shape })` —
     pick a colour scheme that matches the app's domain (florist →
     pinks/greens, finance → navy/teal, etc.). Don't ship default blue.
   - `src/api.ts` (only if there's a backend): typed `fetch()` wrappers.
   - `src/views/<Name>.tsx`: one default-export React component per page.

3. Database = SQLite (only when needed). Schema in `_db.php`, foreign
   keys explicit. Omit the `database` array entirely for backendless.

INVARIANTS the planner MUST respect:
- **Allowed npm imports** — STRICT ALLOWLIST: `react`, `react-dom`,
  `react-dom/client`, `@mui/material/*`, `@mui/icons-material/*`,
  `@mui/system`, `@emotion/react`, `@emotion/styled`. No router libs,
  no axios, no lodash, no date-fns — write inline equivalents.
- **All fetch URLs RELATIVE**: `fetch('api/items.php')` NOT
  `fetch('/api/items.php')` (the dev preview iframes the app under
  `/projects/<id>/app/preview/`; a leading slash escapes the mount).
- Function components + hooks only — NO `class` components.

PHASED EXECUTION — split work into ordered phases (1-5 files each, 2-6
phases typical, hard caps 8 files/phase and 10 phases). Each phase has
one responsibility (don't mix backend + frontend). Earlier phases lay
foundations later ones depend on. Per-file generation runs as a
separate focused LLM call per file.

Typical phases:
  1 "Foundation" — index.html, styles.css, main.tsx, App.tsx, theme.ts
  2 "Database"   — public/api/_db.php (only if backend)
  3 "Backend"    — public/api/<name>.php × N (only if backend)
  4 "API client" — src/api.ts (only if backend)
  5 "Views"      — src/views/<Name>.tsx × N

TWO MODES:

MODE A — INITIAL SCAFFOLD (new app, no prior Approve & Build):
- Emit the FULL phased plan, 3-15 files across 2-6 phases.
- Always include the 5 Foundation files. Add backend phases only if
  persistence is needed.

MODE B — INCREMENTAL CHANGE (refinement, fix, or auto-fix prompt) —
DEFAULT for any chat turn after the first build:
- Emit ONE phase containing ONLY files that change or need to be
  created. Don't relist correct files. Typically 1-5 files.
- Missing-file errors mean CREATE the missing file (not remove the
  importer). PHP 500s mean fix the file's syntax/logic. Resist
  regenerating everything when the user asks for a small fix.

OUTPUT FORMAT — your reply has TWO parts:

Part 1 (free text): A short conversational reply to the user. Acknowledge
their request, explain what you're proposing, mention any tradeoffs.
2-6 sentences max.

Part 2 (REQUIRED almost always): a single fenced ```json``` code block
with the structured plan. You MUST include this block whenever you have
ANY plan to propose. The most common reason a build fails is a reply
that has Part 1 but forgets Part 2 — DO NOT do this.

Skip Part 2 ONLY when you genuinely need clarification before you can
plan. In that case Part 1 must end with an explicit question mark, and
you must ask ONE specific question (e.g. "Should the cart persist across
sessions, or just for the current page?"). If you find yourself
describing what you'd build, you've already decided — emit Part 2.

Part 2 shape — exactly this, no comments inside the JSON:

```json
{
  "summary": "1-2 sentence description of the change (or app, for initial)",
  "database": [
    {"table": "items", "columns": [{"name": "id", "type": "INTEGER PRIMARY KEY"}, {"name": "name", "type": "TEXT NOT NULL"}]}
  ],
  "api": [
    {"path": "public/api/items.php", "methods": ["GET", "POST"], "purpose": "List + create items"}
  ],
  "frontend": [
    {"view": "Home", "purpose": "Item grid"}
  ],
  "phases": [
    {
      "name": "Foundation",
      "description": "SPA shell, theme, entry point + top-level App component.",
      "files": [
        {"path": "public/index.html", "purpose": "SPA shell with #root mount + dist/app.js script tag"},
        {"path": "public/styles.css", "purpose": "Body reset only; MUI handles component styling"},
        {"path": "src/theme.ts", "purpose": "createTheme({ palette, typography, shape }) — pick a colour scheme that matches the app's vibe"},
        {"path": "src/main.tsx", "purpose": "ReactDOM.createRoot + ThemeProvider + CssBaseline + render <App />"},
        {"path": "src/App.tsx", "purpose": "Top-level layout with AppBar + Container + tiny hash-router that switches the active view"}
      ]
    },
    {
      "name": "Database & schema",
      "description": "PDO bootstrap with idempotent CREATE TABLE and demo seed.",
      "files": [
        {"path": "public/api/_db.php", "purpose": "db() function, CREATE TABLE IF NOT EXISTS items, seed 3 demo rows"}
      ]
    },
    {
      "name": "Backend API",
      "description": "JSON endpoints. Each file requires _db.php and emits Content-Type: application/json.",
      "files": [
        {"path": "public/api/items.php", "purpose": "GET list of items as JSON; POST {name} inserts and returns the new row"}
      ]
    },
    {
      "name": "Frontend integration",
      "description": "Typed fetch wrappers + Home view that fetches items and renders an MUI list with an add-form Card.",
      "files": [
        {"path": "src/api.ts", "purpose": "fetchItems(), addItem(name) — typed wrappers around api/items.php (RELATIVE URLs)"},
        {"path": "src/views/Home.tsx", "purpose": "Default-export React component using <Container>, <Card>, <List>, <TextField>, <Button>; useEffect to fetch on mount"}
      ]
    }
  ]
}
```

TEST FILES ARE AUTHORITATIVE.
The build can include LLM-generated tests at `tests/api.php` (or
similar). When a test fails it means the APPLICATION is wrong, not the
test. Never include `tests/...` paths in your plan's `files` array;
never modify or delete test files.

RULES for the plan:
- `phases` is REQUIRED and must be a non-empty array.
- Each phase has `name` (short title), `description` (1 sentence on what
  the phase delivers), and `files` (1-8 entries).
- Every PHP path MUST start with `public/api/` (the only exception is a
  bare `public/index.php` SPA-fallback router).
- Every file path MUST have one of these extensions:
  .ts .tsx .js .php .html .css .json .md .txt .svg .sql
- For initial scaffolds: include `public/index.html`, `public/styles.css`,
  `src/app.ts` (typically in the first phase). Add backend phases only if
  persistence is needed.
- For incremental changes: ONE phase named "Fix" (or similar) with only
  the files that need to change/be created.
- The database/api/frontend arrays may be empty when the app doesn't use
  them, OR may carry full context for the current build. phases[].files
  is what triggers writes."""


_FILE_SYSTEM_TEMPLATE = """You are generating one file in a small
self-contained PHP+TypeScript+SQLite web app, which is being built
PHASE BY PHASE. The full architectural plan the user has approved is
below. Generate ONLY the file specified — no prose, no markdown, no
code fences, no explanation.

ARCHITECTURE CONTRACT (applies to every file you write — the plan above
was designed to fit it, do NOT deviate):

- Backend: PHP under `public/api/`, JSON-only, parameter-bound SQL,
  schema in `public/api/_db.php`.
- Frontend: React 18 + MUI v5 SPA. Entry `src/main.tsx` →
  `<ThemeProvider theme={{theme}}><CssBaseline /><App /></ThemeProvider>`.
  `src/App.tsx` is the top-level layout (AppBar + Container) plus a tiny
  hash-router that switches between view components in `src/views/*.tsx`.
  Typed fetch wrappers in `src/api.ts`. Theme in `src/theme.ts`.
- npm imports — STRICT ALLOWLIST: `react`, `react-dom`, `react-dom/client`,
  `@mui/material/...`, `@mui/icons-material/...`, `@mui/system`,
  `@emotion/react`, `@emotion/styled`. No router libs, no axios, no lodash.
- HTML: ONLY in `public/index.html` (SPA shell, has `<div id="root">` +
  dist/app.js script tag). Optional `public/index.php` as a 5-line
  SPA-fallback router. NO inline JSX in HTML.
- Styling: MUI `sx` prop and theme tokens. `public/styles.css` holds
  ONLY a body reset (margin: 0; min-height: 100vh; background colour).
  All component styling lives inside React.
- SQLite: PDO, file at the project root, schema bootstrapped on first
  request by `public/api/_db.php`. All fetch URLs RELATIVE
  (`fetch('api/items.php')` not `'/api/items.php'`).

THE FULL PLAN (all phases):
{plan_json}

CURRENT PHASE: {phase_name}
PHASE PURPOSE: {phase_description}
{already_written_block}
NOW GENERATE THIS FILE:
- path: {file_path}
- purpose: {file_purpose}

ROLE-SPECIFIC GUIDANCE:
{role_guidance}

The file you're generating is part of this phase. Make it consistent
with files already written in earlier phases (paths above), and ensure
it works alongside the other files in the current phase + the files
that later phases will produce (per the plan).

Output ONLY the raw file contents. No prose. No fences. No commentary."""


_FIX_FILE_SYSTEM = """You are editing one file in a small self-contained
PHP+TypeScript+SQLite web app. Output the COMPLETE new contents of the
file — no diffs, no markdown, no fences, no explanation. Preserve the
file's existing style; only change what the user asked for. If the
instruction is impossible or unsafe, return the file unchanged.

ARCHITECTURE CONTRACT — your edit must keep the file consistent with:
- Backend = PHP under `public/api/` only, JSON-only, parameter-bound SQL.
- Frontend = TypeScript renders all UI via DOM APIs.
- HTML lives only in `public/index.html` (SPA shell). PHP NEVER renders HTML.
- SQLite via PDO, schema bootstrapped in `public/api/_db.php`.

NEVER add PHP that emits HTML. NEVER add Composer dependencies. NEVER add
npm runtime dependencies. NEVER call `restai_*` helpers — the deployed app
is fully standalone.

Output: ONLY the new file contents. No code fences."""


def _role_guidance_for(path: str) -> str:
    """Return a short, file-type-specific guidance block that gets
    interpolated into _FILE_SYSTEM_TEMPLATE. Keep it tight — generic
    rules already live in the contract."""
    p = path.lower()
    if p == "public/index.html":
        return (
            "- Plain HTML5. <head> includes `<meta charset>`, viewport, "
            "title, and `<link rel=\"stylesheet\" href=\"styles.css\">`.\n"
            "- <body> contains exactly one `<div id=\"root\"></div>` and "
            "ends with `<script type=\"module\" src=\"dist/app.js\"></script>`.\n"
            "- NO inline JS, NO PHP, NO server-rendered content."
        )
    if p == "public/styles.css":
        return (
            "- Body reset ONLY. MUI handles component styling — do NOT "
            "duplicate it here. Typical content:\n"
            "    `body { margin: 0; min-height: 100vh; background: #fafafa; }`\n"
            "    `*, *::before, *::after { box-sizing: border-box; }`\n"
            "- No font imports (MUI's Roboto fallback is fine), no preprocessor."
        )
    if p == "public/index.php":
        return (
            "- This file exists ONLY as a thin SPA fallback router. Max 8 lines.\n"
            "- If `$_SERVER['REQUEST_URI']` starts with `/api/`, return false "
            "(let PHP serve the real api file).\n"
            "- If the requested path maps to an existing static file, return false.\n"
            "- Otherwise `readfile(__DIR__ . '/index.html')` and exit. Set "
            "`Content-Type: text/html`."
        )
    if p == "public/api/_db.php":
        return (
            "- Open `new PDO('sqlite:' . __DIR__ . '/../../database.sqlite')`.\n"
            "- `setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION)` and "
            "`PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC`.\n"
            "- Run `CREATE TABLE IF NOT EXISTS` for every table in the plan.\n"
            "- Seed 2-5 demo rows per table if the table is empty (use "
            "`SELECT COUNT(*)` to check).\n"
            "- Expose a `db()` function returning the PDO instance OR set a "
            "`$db` global. Pick one and stick with it.\n"
            "- Wrap everything in a `function bootstrap_db()` called on first "
            "require so other files can `require_once` cheaply."
        )
    if p.startswith("public/api/"):
        return (
            "- `require_once __DIR__ . '/_db.php';` first.\n"
            "- `header('Content-Type: application/json; charset=utf-8');`\n"
            "- Read JSON body via `json_decode(file_get_contents('php://input'), true) ?? []`.\n"
            "- Dispatch on `$_SERVER['REQUEST_METHOD']`.\n"
            "- ALL SQL via `$db->prepare(...)->execute([...])`.\n"
            "- On error: `http_response_code(400|500)` + `echo json_encode(['error' => '...'])` + `exit;`.\n"
            "- On success: `echo json_encode($payload);` (numeric keys preserved as JSON arrays).\n"
            "- NEVER `echo` anything that isn't JSON."
        )
    if p == "src/main.tsx":
        return (
            "- Entry point. Imports React, `createRoot` from 'react-dom/client', "
            "ThemeProvider + CssBaseline from '@mui/material', `theme` from './theme', "
            "and `App` from './App'.\n"
            "- `const root = document.getElementById('root'); "
            "if (!root) throw new Error('#root not found');`\n"
            "- `createRoot(root).render(<React.StrictMode><ThemeProvider theme={theme}>"
            "<CssBaseline /><App /></ThemeProvider></React.StrictMode>);`\n"
            "- Keep it tiny — all logic lives in App.tsx and the views."
        )
    if p == "src/App.tsx":
        return (
            "- Top-level component (default export). Holds the route state via a "
            "tiny inline `useHashRouter` hook (≈8 lines: `useState` of "
            "`location.hash.slice(1) || 'home'` + `useEffect` adding "
            "`hashchange` listener).\n"
            "- Wrap content in `<Box sx={{ minHeight: '100vh' }}>`. Render "
            "`<AppBar position=\"static\"><Toolbar><Typography variant=\"h6\">"
            "{appName}</Typography>...nav links via <Button color=\"inherit\" "
            "href=\"#shop\">Shop</Button></Toolbar></AppBar>`.\n"
            "- Then `<Container maxWidth=\"lg\" sx={{ py: 4 }}>{viewElement}</Container>`.\n"
            "- Switch on the route to import + render the matching view component "
            "from `./views/<Name>`.\n"
            "- Use named imports from `@mui/material` (Tree-shaken by esbuild)."
        )
    if p == "src/theme.ts":
        return (
            "- `import { createTheme } from '@mui/material/styles';`\n"
            "- Export a `theme` constant with at minimum: `palette: { mode, primary, "
            "secondary, background }`, `typography: { fontFamily, h1, h4, body1 }`, "
            "`shape: { borderRadius }`, `components: { MuiButton: { defaultProps: "
            "{ disableElevation: true } } }` (or similar) for opinionated defaults.\n"
            "- Pick colours that MATCH THE APP'S DOMAIN (e.g. florist → soft pinks/"
            "greens; finance → navy/teal; calculator → cool greys). Don't ship the "
            "default blue."
        )
    if p == "src/api.ts":
        return (
            "- Export typed fetch wrappers for each `api/*.php` endpoint listed in the plan.\n"
            "- Define interfaces for request/response shapes.\n"
            "- Generic helper: `async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T>` "
            "that throws if `!res.ok` (include the JSON `error` field in the message).\n"
            "- All requests `Content-Type: application/json`.\n"
            "- All paths RELATIVE — write `'api/products.php'` NOT `'/api/products.php'`. "
            "The dev preview iframes the app under `/projects/<id>/app/preview/`; a "
            "leading slash escapes the mount and 404s."
        )
    if p.startswith("src/views/"):
        return (
            "- DEFAULT export — a React function component. e.g. "
            "`export default function Home() { ... }`.\n"
            "- Use MUI primitives: `<Container>`, `<Box>`, `<Stack>`, `<Grid>`, "
            "`<Card>`/`<CardContent>`, `<Typography>`, `<Button>`, `<TextField>`, "
            "`<List>`/`<ListItem>`, `<CircularProgress>`, `<Alert>`. Icons from "
            "`@mui/icons-material` (named imports).\n"
            "- Data fetching: `const [data, setData] = useState<T|null>(null); "
            "const [loading, setLoading] = useState(true); const [error, setError] "
            "= useState<string|null>(null); useEffect(() => { fetchX().then(setData)"
            ".catch(e => setError(e.message)).finally(() => setLoading(false)); }, []);`.\n"
            "- Render `loading ? <CircularProgress /> : error ? <Alert severity=\"error\">"
            "{error}</Alert> : <ActualContent />`.\n"
            "- Forms: controlled `<TextField>` with `useState`, validate inline, "
            "submit via `onSubmit` of an enclosing `<Box component=\"form\">`.\n"
            "- Import wrappers from `../api`. NEVER reach into `document.*` directly."
        )
    if p.startswith("src/"):
        return (
            "- TypeScript module. Default to named exports unless it's a React "
            "component (those are default exports).\n"
            "- Allowlist for npm imports: react, react-dom, @mui/material/*, "
            "@mui/icons-material/*, @emotion/react, @emotion/styled."
        )
    if p == "README.md":
        return (
            "- Short README: app overview, file layout, how to deploy "
            "(unzip, drop in docroot, browse).\n"
            "- 30-80 lines max."
        )
    return "- Follow the architecture contract above. Be concise and complete."


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


# Curated allowlist of npm imports the runtime image bakes into
# /opt/restai-app-deps/node_modules. Subpath imports (e.g.
# `@mui/material/Button`, `react-dom/client`) match by prefix.
_ALLOWED_NPM_IMPORTS = (
    "react",
    "react-dom",
    "@mui/material",
    "@mui/icons-material",
    "@mui/system",
    "@emotion/react",
    "@emotion/styled",
)


def _is_allowed_npm_import(spec: str) -> bool:
    if spec.startswith(".") or spec.startswith("/"):
        return True
    for pkg in _ALLOWED_NPM_IMPORTS:
        if spec == pkg or spec.startswith(pkg + "/"):
            return True
    return False


def _js_string_and_comment_ranges(text: str) -> list[tuple[int, int]]:
    """Return ``[(start, end), ...]`` byte ranges covering every JS/TS
    string literal, template literal, line comment, and block comment.
    Used by the static-architecture check to discriminate between a real
    ``require('x')`` call and a docs page that contains an EXAMPLE of
    `require('x')` inside a string / JSX text / comment.

    Crude state machine — handles single/double quotes, backticks,
    backslash escapes, ``//`` line comments, and ``/* */`` block comments.
    Doesn't fully understand JSX text (which isn't quote-delimited), so
    callers should also anchor patterns to JS-operator prefixes.
    """
    ranges: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Line comment.
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j < 0:
                j = n
            ranges.append((i, j))
            i = j
            continue
        # Block comment.
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                ranges.append((i, n))
                break
            ranges.append((i, j + 2))
            i = j + 2
            continue
        # String / template literal.
        if ch in ("'", '"', "`"):
            quote = ch
            j = i + 1
            while j < n:
                cj = text[j]
                if cj == "\\" and j + 1 < n:
                    j += 2
                    continue
                if cj == quote:
                    break
                j += 1
            ranges.append((i, j + 1))
            i = j + 1
            continue
        i += 1
    return ranges


def _pos_in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    """True when ``pos`` falls inside any of the half-open ranges."""
    for start, end in ranges:
        if start <= pos < end:
            return True
    return False


# Matches an opening JSX/HTML tag like `<pre>`, `<code>`, `<Box>`, `<Box sx={...}>`.
_JSX_OPEN_TAG_RE = re.compile(r'<[a-zA-Z][^<>]*>')


def _is_inside_jsx_text(text: str, pos: int) -> bool:
    """Cheap heuristic: a require/import keyword at ``pos`` is inside
    JSX text content if there's an opening JSX tag on the same line
    before it. Doesn't catch every case (e.g. multi-line JSX text), but
    handles the common `<pre>const x = require('dockerode')</pre>`
    documentation pattern that was producing false positives."""
    line_start = text.rfind("\n", 0, pos) + 1
    pre = text[line_start:pos]
    return bool(_JSX_OPEN_TAG_RE.search(pre))


def static_architecture_checks(path: str, content: str) -> list[str]:
    """Cheap pre-write checks that catch architecture violations BEFORE
    the file lands on disk. Returns a list of human-readable problems
    (empty list = file is fine).

    These are pattern-based, not full parsing — the goal is to reject
    obvious architecture-rule violations the LLM produces despite the
    system prompt. The execute endpoint surfaces each entry as a
    file_error, which the auto-fix loop will then pick up with the exact
    issue text.
    """
    issues: list[str] = []
    p = (path or "").replace("\\", "/").lstrip("/")
    ext = ""
    if "." in p:
        ext = p[p.rfind("."):].lower()

    # PHP files: must be JSON-only. No HTML interpolation.
    if ext in (".php", ".phtml"):
        # `<?= ... ?>` is HTML interpolation — banned everywhere except
        # the optional public/index.php SPA-fallback router (which still
        # shouldn't really need it, but we don't reject the router).
        if "<?=" in content and p != "public/index.php":
            issues.append(
                "Contains `<?= ... ?>` HTML interpolation. PHP files must emit "
                "JSON only via `header('Content-Type: application/json'); "
                "echo json_encode(...);` — never inline HTML."
            )
        # `?>` followed by HTML markup outside the SPA-fallback router
        # is the same problem in long form.
        if (
            p != "public/index.php"
            and "?>" in content
            and any(tag in content.lower() for tag in ("<html", "<body", "<div", "<table", "<ul"))
        ):
            issues.append(
                "Closes the PHP tag and emits HTML markup. API files must stay "
                "inside `<?php` and only echo JSON."
            )
        # Composer is forbidden — generated apps have zero npm/composer deps.
        if "require 'vendor/autoload.php'" in content or 'require "vendor/autoload.php"' in content:
            issues.append(
                "Requires Composer's vendor/autoload.php — Composer is forbidden "
                "in this app builder; use only stdlib PHP + PDO."
            )

    # TypeScript / JavaScript files: only relative imports + the curated
    # allowlist of npm packages baked into the runtime image
    # (/opt/restai-app-deps/node_modules). Anything else is rejected so the
    # generated bundle can't pull in arbitrary deps that won't resolve at
    # build time and bloat the deployed JS.
    #
    # Scan a copy of the source with string + template-literal content
    # stripped, otherwise a docs page that contains an EXAMPLE of an npm
    # import inside a code-sample string ("const Docker = require('dockerode')")
    # would trip the check.
    if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
        # Find string-literal + comment ranges so we can skip "code shown
        # as documentation" — e.g. a docs page that shows
        # `const docker = require('dockerode')` inside a string or JSX
        # text shouldn't trip the npm-allowlist check.
        skip_ranges = _js_string_and_comment_ranges(content)

        for m in re.finditer(r'^\s*(import)\s+(?:[^"\']*?\s+from\s+)?["\']([^"\']+)["\']',
                             content, re.MULTILINE):
            kw_pos = m.start(1)
            if _pos_in_ranges(kw_pos, skip_ranges):
                continue
            if _is_inside_jsx_text(content, kw_pos):
                continue
            spec = m.group(2)
            if not _is_allowed_npm_import(spec):
                issues.append(
                    f"Imports `{spec}` — not in the allowlist. The bundle ships "
                    "only React 18, MUI v5 (@mui/material, @mui/icons-material), "
                    "and Emotion (@emotion/react, @emotion/styled). Use relative "
                    "imports for project files."
                )
        # `require(...)` — also skip when the keyword sits inside JSX
        # text like `<code>const docker = require('dockerode')</code>`
        # which isn't quote-delimited but is still documentation, not a
        # real JS call.
        for m in re.finditer(
            r'(?:^|[\s=,;:\[\{(!&|?])(require)\(\s*["\']([^"\']+)["\']\s*\)',
            content,
            re.MULTILINE,
        ):
            kw_pos = m.start(1)
            if _pos_in_ranges(kw_pos, skip_ranges):
                continue
            if _is_inside_jsx_text(content, kw_pos):
                continue
            spec = m.group(2)
            if not _is_allowed_npm_import(spec):
                issues.append(
                    f"Calls `require('{spec}')` — not in the allowlist. Same rules "
                    "as `import`: React + MUI + Emotion + relative paths only."
                )

    # HTML files: must be pure HTML — no PHP, no server-rendered content.
    if ext in (".html", ".htm"):
        if "<?php" in content or "<?=" in content:
            issues.append(
                "Contains `<?php` or `<?=` tags. HTML files must be pure HTML "
                "(SPA shell). PHP belongs only under public/api/."
            )
        # If this is the SPA shell, sanity-check it has the mount + script.
        if p == "public/index.html":
            # `createRoot()` works on any element type; HTML5 also allows
            # unquoted attribute values. Match `id="root"`, `id='root'`,
            # or bare `id=root` on any element, case-insensitive.
            if not re.search(r'\bid\s*=\s*["\']?root["\']?[\s/>]', content, re.IGNORECASE):
                issues.append(
                    "Missing `id=\"root\"` mount point. React's createRoot() "
                    "needs an element with id=\"root\" (typically a `<div>`)."
                )
            if "dist/app.js" not in content:
                issues.append(
                    "Missing `<script ... src=\"dist/app.js\">`. The bundled "
                    "React + MUI app won't load without it."
                )

    return issues


def validate_file_path(path: str) -> str:
    """Reject traversal, disallowed extensions, reserved dirs. Returns the
    normalised path. Raises ``ValueError`` on rejection."""
    if not path or not isinstance(path, str):
        raise ValueError("missing path")
    p = path.replace("\\", "/").lstrip("/")
    if not p or p.startswith(".."):
        raise ValueError(f"invalid path: {path!r}")
    if any(seg == ".." for seg in p.split("/")):
        raise ValueError(f"path traversal in {path!r}")
    if p.startswith("dist/") or "/dist/" in p or p.startswith("public/dist/"):
        raise ValueError(f"writes to dist/ are reserved for esbuild: {path!r}")
    if p.startswith("node_modules/"):
        raise ValueError(f"writes to node_modules/ are not allowed: {path!r}")
    if p == "database.sqlite":
        raise ValueError("database.sqlite is created by PHP at runtime")
    dot = p.rfind(".")
    if dot < 0:
        raise ValueError(f"path needs an extension: {path!r}")
    ext = p[dot:].lower()
    if ext not in GENERATION_ALLOWED_EXTENSIONS:
        raise ValueError(f"extension {ext} not allowed (path: {path!r})")
    # ── Architecture contract: PHP location ──────────────────────────
    if ext in (".php", ".phtml"):
        # Allowed: anything under public/api/, OR exactly public/index.php
        # (SPA fallback router), OR anything under tests/ (the test
        # runner uses CLI PHP to hit the API endpoints from inside the
        # container; tests are immutable during auto-fix — see the
        # test-immutability guard in the plan endpoint).
        if not (
            p.startswith("public/api/")
            or p == "public/index.php"
            or p.startswith("tests/")
        ):
            raise ValueError(
                f"PHP files must live under public/api/, tests/, or be the "
                f"public/index.php SPA router. Got: {path!r}"
            )
    return p


MAX_PLAN_PHASES = 10
MAX_FILES_PER_PHASE = 8


def validate_plan(plan: Any) -> dict:
    """Strict plan-schema validation. Returns the cleaned plan with phases
    normalised (every phase has ``name``, ``description``, ``files``).

    Accepts two input shapes:
    1. NEW (preferred): ``{phases: [{name, description?, files: [...]}, ...]}``
    2. LEGACY: ``{files: [...]}`` — wrapped into a single "Build" phase
       so older callers / older LLM outputs still work.

    Raises ``ValueError`` on first failure."""
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("plan.summary is required (non-empty string)")

    # Database/api/frontend are advisory but if present must be lists.
    for key in ("database", "api", "frontend"):
        v = plan.get(key)
        if v is not None and not isinstance(v, list):
            raise ValueError(f"plan.{key} must be an array")

    # Resolve phases — accept new shape or back-compat wrap of flat files.
    raw_phases = plan.get("phases")
    if raw_phases is None and isinstance(plan.get("files"), list):
        raw_phases = [{
            "name": "Build",
            "description": "All files for this build.",
            "files": plan["files"],
        }]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise ValueError("plan.phases must be a non-empty array")
    if len(raw_phases) > MAX_PLAN_PHASES:
        raise ValueError(f"plan.phases exceeds the {MAX_PLAN_PHASES}-phase cap")

    seen_paths: set[str] = set()
    total_purpose_bytes = 0
    total_files = 0
    cleaned_phases: list[dict] = []

    for ph_idx, phase in enumerate(raw_phases):
        if not isinstance(phase, dict):
            raise ValueError(f"plan.phases[{ph_idx}] must be an object")
        ph_name = phase.get("name")
        if not isinstance(ph_name, str) or not ph_name.strip():
            raise ValueError(f"plan.phases[{ph_idx}].name is required (non-empty string)")
        ph_desc = phase.get("description", "") or ""
        if not isinstance(ph_desc, str):
            raise ValueError(f"plan.phases[{ph_idx}].description must be a string")
        if len(ph_desc) > 500:
            raise ValueError(f"plan.phases[{ph_idx}].description too long (>500 chars)")

        ph_files = phase.get("files")
        if not isinstance(ph_files, list) or not ph_files:
            raise ValueError(f"plan.phases[{ph_idx}].files must be a non-empty array")
        if len(ph_files) > MAX_FILES_PER_PHASE:
            raise ValueError(
                f"plan.phases[{ph_idx}].files exceeds the {MAX_FILES_PER_PHASE}-file-per-phase cap"
            )

        cleaned_files: list[dict] = []
        for f_idx, entry in enumerate(ph_files):
            if not isinstance(entry, dict):
                raise ValueError(f"plan.phases[{ph_idx}].files[{f_idx}] must be an object")
            try:
                p = validate_file_path(entry.get("path", ""))
            except ValueError as e:
                raise ValueError(str(e))
            if p in seen_paths:
                raise ValueError(f"duplicate file across plan phases: {p!r}")
            seen_paths.add(p)
            purpose = entry.get("purpose", "")
            if not isinstance(purpose, str):
                raise ValueError(f"plan.phases[{ph_idx}].files[{p!r}].purpose must be a string")
            if len(purpose) > 500:
                raise ValueError(f"plan.phases[{ph_idx}].files[{p!r}].purpose too long (>500 chars)")
            total_purpose_bytes += len(purpose.encode("utf-8", errors="ignore"))
            cleaned_files.append({"path": p, "purpose": purpose})

        total_files += len(cleaned_files)
        cleaned_phases.append({
            "name": ph_name.strip(),
            "description": ph_desc.strip(),
            "files": cleaned_files,
        })

    if total_files == 0:
        raise ValueError("plan must contain at least one file across all phases")
    if total_files > MAX_PLAN_FILES:
        raise ValueError(f"plan total files ({total_files}) exceeds {MAX_PLAN_FILES}")
    if total_purpose_bytes > MAX_PLAN_TOTAL_BYTES:
        raise ValueError("plan total purpose text exceeds size cap")

    cleaned = dict(plan)  # shallow copy
    cleaned["summary"] = summary.strip()
    cleaned["phases"] = cleaned_phases
    # Drop the legacy top-level files array if present, so downstream
    # consumers always see the canonical phased shape.
    cleaned.pop("files", None)
    return cleaned


# ---------------------------------------------------------------------------
# JSON-tail extraction from the LLM's plan reply
# ---------------------------------------------------------------------------


# Markdown fence with any (optional) language tag.
_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)\s*```", re.DOTALL)


def extract_plan_from_reply(reply: str) -> Optional[dict]:
    """Pull a plan dict out of an LLM reply.

    Strategy:
    1. Look for the LAST fenced ```json``` block (or any fenced block) and
       try to parse it. We take the last one because the LLM may include
       inline JSON examples earlier in the reply.
    2. If that fails, find the outermost balanced object that contains a
       ``"summary"`` key and try to parse it.

    Returns None if no parsable plan was found (the AI may have asked a
    clarifying question instead of producing a plan)."""
    if not reply:
        return None

    candidates: list[str] = []
    for m in _FENCE_RE.finditer(reply):
        candidates.append(m.group(1).strip())
    candidates.reverse()  # LAST fence first

    # Also try the bare-text outermost-braces fallback.
    start, end = reply.find("{"), reply.rfind("}")
    if start >= 0 and end > start:
        candidates.append(reply[start : end + 1])

    for c in candidates:
        try:
            parsed = json.loads(c)
        except json.JSONDecodeError:
            continue
        # Accept the new phased shape (`phases`) AND the legacy flat shape
        # (`files`). Without `phases` here the chat-hydrate path returns
        # null for new-format plans and the plan card vanishes from the UI
        # after every page load.
        if isinstance(parsed, dict) and "summary" in parsed and (
            "phases" in parsed or "files" in parsed
        ):
            return parsed
    return None


# ---------------------------------------------------------------------------
# LLM streaming helpers
# ---------------------------------------------------------------------------


def _resolve_llm(brain: Any, db: Any, project_llm_name: Optional[str]):
    if not project_llm_name:
        raise ValueError("Project has no LLM configured. Edit the project to pick one.")
    llm = brain.get_llm(project_llm_name, db)
    if llm is None:
        raise ValueError(f"LLM '{project_llm_name}' is not available")
    return llm


def _stream_complete(llm, prompt: str) -> Iterable[str]:
    """Iterate the LLM's deltas as plain text chunks.

    We use ``stream_complete`` (sync iterator) because every LlamaIndex LLM
    backend implements it and it's what `restai/projects/rag.py:236` uses.
    Each ``token_response`` has ``.delta`` (the new text chunk).
    """
    try:
        stream = llm.llm.stream_complete(prompt)
    except Exception as e:
        logger.exception("LLM stream_complete failed")
        raise ValueError(f"LLM call failed: {e}")
    total = 0
    for token_response in stream:
        delta = getattr(token_response, "delta", None)
        if delta is None:
            # Older LlamaIndex returns deltas via .text accumulation; we
            # diff against the running total instead.
            new_text = getattr(token_response, "text", "") or ""
            if not new_text:
                continue
            delta = new_text[total:]
        if not delta:
            continue
        total += len(delta)
        if total > MAX_LLM_RESPONSE_BYTES:
            raise ValueError(
                f"LLM response exceeds {MAX_LLM_RESPONSE_BYTES // 1024} KB cap"
            )
        yield delta


# ---------------------------------------------------------------------------
# Public streaming entry points
# ---------------------------------------------------------------------------


def _format_messages_for_complete(messages: list[dict]) -> str:
    """Flatten a chat-style message list into a single prompt suitable
    for ``llm.llm.complete`` / ``stream_complete``.

    We use ``stream_complete`` rather than ``stream_chat`` because every
    LlamaIndex LLM (including local Ollama, OpenAI-compatible, Anthropic,
    etc.) implements it; ``stream_chat`` is patchier across providers.
    The system prompt is injected by the caller and prepended here.
    """
    parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "").strip().lower()
        content = m.get("content") or ""
        if role == "system":
            parts.append(f"# System\n{content}")
        elif role == "assistant":
            parts.append(f"# Assistant (previous reply)\n{content}")
        else:
            parts.append(f"# User\n{content}")
    parts.append("# Assistant (your reply now)\n")
    return "\n\n".join(parts)


def stream_plan(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    messages: list[dict],
    *,
    project_id: Optional[int] = None,
) -> Generator[tuple[str, dict], None, None]:
    """Stream the LLM's planning reply.

    When ``project_id`` is provided, an EXISTING PROJECT SNAPSHOT block
    (file index + full content of shared-infra files) is appended to the
    system prompt so refinement turns plan against real on-disk state
    instead of guessing.

    Yields ``("plan_chunk", {"text": delta})`` for each LLM delta, then a
    single ``("plan_complete", {"plan": dict|None, "reply": str, "tokens":
    {"input": int, "output": int}})``.
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    llm = _resolve_llm(brain, db, project_llm_name)

    system_text = _PLAN_SYSTEM
    if project_id is not None:
        snapshot = _build_project_snapshot(project_id)
        if snapshot:
            system_text = _PLAN_SYSTEM + "\n\n" + snapshot

    full_messages = [{"role": "system", "content": system_text}] + list(messages)
    prompt = _format_messages_for_complete(full_messages)

    accumulated: list[str] = []
    for delta in _stream_complete(llm, prompt):
        accumulated.append(delta)
        yield ("plan_chunk", {"text": delta})

    reply = "".join(accumulated)
    plan = extract_plan_from_reply(reply)
    if plan is not None:
        try:
            plan = validate_plan(plan)
        except ValueError as e:
            logger.info("plan rejected by validator: %s", e)
            # Surface the rejection as part of the completion event so the
            # UI can show the reply but disable the Approve button.
            plan = None
            reply = reply + (
                f"\n\n_(server: the plan you provided was rejected — {e}. "
                "Please revise.)_"
            )

    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, reply)
    yield (
        "plan_complete",
        {
            "plan": plan,
            "reply": reply,
            "tokens": {"input": in_tokens, "output": out_tokens},
        },
    )


def _pick_relevant_files(
    target_path: str,
    candidates: list[str],
    max_files: int = 6,
) -> list[str]:
    """Choose which already-written files to attach to the prompt as
    full content. Heuristics, in priority order:

    1. ALWAYS include shared infra files: `src/App.tsx`, `src/theme.ts`,
       `src/api.ts`, `public/api/_db.php`, `public/index.html`. View
       components import from App / theme / api; PHP API files
       require_once _db.php; references to index.html are common.
    2. Include files in the same directory as the target.
    3. Fill remaining slots with most-recent (end of list) candidates.

    Returns at most `max_files` paths."""
    chosen: list[str] = []
    seen = set()

    def _add(p: str):
        if p in seen or p == target_path or p not in candidates:
            return
        seen.add(p)
        chosen.append(p)

    # 1) Shared infra
    for shared in ("src/App.tsx", "src/theme.ts", "src/api.ts", "public/api/_db.php", "public/index.html"):
        if len(chosen) >= max_files:
            break
        _add(shared)

    # 2) Same directory
    target_dir = target_path.rsplit("/", 1)[0] if "/" in target_path else ""
    if target_dir:
        for c in candidates:
            if len(chosen) >= max_files:
                break
            c_dir = c.rsplit("/", 1)[0] if "/" in c else ""
            if c_dir == target_dir:
                _add(c)

    # 3) Most-recent (most useful for incremental)
    for c in reversed(candidates):
        if len(chosen) >= max_files:
            break
        _add(c)

    return chosen


# Files we always want the planner to see in full when refining an
# existing build. Keeping these visible stops the LLM from hallucinating
# new style.css / new index.html and from blowing away the design system.
_PLANNER_SHARED_INFRA = (
    "public/index.html",
    "public/styles.css",
    "src/main.tsx",
    "src/App.tsx",
    "src/theme.ts",
    "src/api.ts",
    "public/api/_db.php",
)


def _build_project_snapshot(project_id: int) -> str:
    """For follow-up planning: the file index + full content of the
    shared-infra files actually present on disk. Returns "" when the
    project is empty (initial build — no snapshot needed)."""
    from restai.app.storage import get_project_root, EDITABLE_EXTENSIONS
    root = get_project_root(project_id)
    if not root.exists():
        return ""
    paths: list[str] = []
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
        paths.append(rel)
    if not paths:
        return ""
    parts = [
        "EXISTING PROJECT SNAPSHOT — these files are CURRENTLY ON DISK. "
        "Plan against them, not against an imaginary blank slate. For "
        "follow-up changes, pick the SMALLEST set of files needed and "
        "preserve everything else.\n",
        "All files:\n" + "\n".join(f"- {p}" for p in paths) + "\n",
    ]
    shared_present = [p for p in _PLANNER_SHARED_INFRA if p in paths]
    if shared_present:
        contents = _read_file_contents_for_prompt(
            project_id, shared_present,
            per_file_cap=PROMPT_SNAPSHOT_PER_FILE_BYTES,
            total_cap=PROMPT_SNAPSHOT_TOTAL_BYTES,
        )
        if contents:
            parts.append(
                "\nFull content of shared-infra files (CSS, SPA shell, entry "
                "points, DB bootstrap) so you can reference real selectors / "
                "function names / table columns instead of guessing:"
            )
            for p, content in contents.items():
                parts.append(f"\n--- {p} ---\n{content}\n--- end {p} ---")
    return "\n".join(parts) + "\n"


def _read_file_contents_for_prompt(
    project_id: int,
    paths: list[str],
    per_file_cap: int = 6000,
    total_cap: int = 24000,
) -> dict[str, str]:
    """Read the actual on-disk content of `paths` for the prompt. Caps:
    per-file truncation + total budget so we don't blow the context
    window on a project with very long files."""
    from restai.app.storage import get_project_root
    root = get_project_root(project_id)
    if not root.exists():
        return {}
    out: dict[str, str] = {}
    used = 0
    for p in paths:
        target = root / p
        if not target.is_file():
            continue
        try:
            data = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(data) > per_file_cap:
            data = data[:per_file_cap] + "\n/* [truncated for prompt budget] */"
        if used + len(data) > total_cap:
            break
        out[p] = data
        used += len(data)
    return out


_CONTRACTS_SYSTEM = """You are sketching the SHARED CONTRACTS for a small
PHP+TypeScript+SQLite web app, BEFORE any implementation is written.

Your output is a single Markdown document with three short sections —
no implementation, just the signatures every file in the build will
target. The implementation step relies on these to keep imports,
function names, response shapes, and table columns consistent across
files.

Output format — exactly this Markdown structure, no fences, no extra
prose:

## TypeScript interfaces

```ts
interface Product {
  id: number;
  name: string;
  price_cents: number;
}

interface CartItem {
  product_id: number;
  qty: number;
}
```

(Include EVERY data shape the frontend touches. One `interface` per
shape. Use `number` / `string` / `boolean` / arrays / nested types.
NEVER `any`.)

## TypeScript API client signatures

```ts
async function fetchProducts(): Promise<Product[]>
async function addToCart(productId: number, qty: number): Promise<{ ok: true }>
async function fetchCart(): Promise<CartItem[]>
```

(One async function per `/api/*.php` endpoint that the frontend will
call. These become exports from `src/api.ts`.)

## PHP API endpoint contracts

```
GET /api/products.php
  → 200 application/json
  → { "products": Product[] }
  → 500 application/json
  → { "error": string }

POST /api/cart.php
  body: { "product_id": number, "qty": number }
  → 200 application/json
  → { "ok": true }
  → 400 application/json
  → { "error": string }
```

(One block per HTTP method per endpoint. Body shape, success response,
error response. Match the TypeScript signatures above.)

## SQL schema

```sql
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cart_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL DEFAULT 1
);
```

(EXACT `CREATE TABLE` statements that `public/api/_db.php` will run.
Skip this section entirely if the plan has no database / api files.)

RULES:
- Output ONLY the Markdown document. No prose before or after.
- Every TypeScript interface field name must match the SQL column name
  (snake_case throughout, both layers).
- Every TS API client function must have a matching PHP endpoint contract
  with the SAME response shape.
- Skip sections that don't apply (e.g. backendless apps skip everything
  except TypeScript interfaces).

Keep it compact — under 80 lines total."""


def generate_contracts(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    plan: dict,
) -> tuple[str, dict]:
    """Sketch the shared contracts for a build (interfaces, function
    signatures, SQL schemas) BEFORE any code is generated. The output
    is a Markdown string that gets passed into every per-file LLM call,
    so cross-file references (function names, response shapes, column
    names) stay consistent.

    Returns ``(contracts_markdown, {"input": int, "output": int})``.
    Returns ``("", {...})`` if the plan is too small to need contracts
    (a single-file fix-up doesn't benefit from this pass)."""
    files = []
    for ph in plan.get("phases") or []:
        files.extend(ph.get("files") or [])
    # Skip contracts for tiny incremental plans — overhead isn't worth it.
    if len(files) < 3:
        return "", {"input": 0, "output": 0}

    llm = _resolve_llm(brain, db, project_llm_name)
    plan_json = json.dumps(plan, indent=2)
    prompt = (
        _CONTRACTS_SYSTEM
        + "\n\nTHE PLAN you're sketching contracts for:\n"
        + plan_json
        + "\n\nNow output the Markdown contracts document."
    )
    try:
        result = llm.llm.complete(prompt)
    except Exception as e:
        logger.exception("generate_contracts: LLM call failed")
        # Don't block the build on contracts failure — return empty so
        # the rest of the pipeline runs without them.
        return "", {"input": 0, "output": 0}
    text = (result.text if hasattr(result, "text") else str(result)) or ""
    # Strip leading/trailing whitespace + an outer markdown fence if the
    # LLM wrapped the whole document despite being told not to.
    text = text.strip()
    fence = _FENCE_RE.search(text)
    # Only strip the fence if the ENTIRE response is one fence (rare; the
    # contracts output has multiple internal ``` blocks, which is correct).
    if fence and fence.start() == 0 and fence.end() == len(text):
        text = fence.group(1).strip()
    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, text)
    return text, {"input": in_tokens, "output": out_tokens}


_TESTS_SYSTEM = """You are generating ONE PHP test file (`tests/api.php`)
that asserts each `/api/*.php` endpoint of a small self-contained app
behaves per its contracts. The test file runs INSIDE the dev container
via `php tests/api.php`, hits each endpoint over HTTP at
`http://127.0.0.1:8080/api/<name>.php`, and prints PASS/FAIL lines for
every assertion.

The test file you produce is AUTHORITATIVE during auto-fix — if a test
fails the app code gets repaired, NOT the test. So the assertions must
be SOUND: only check things the contracts promise (response status,
content-type, JSON keys with correct types, error shape on failure
input). DO NOT assert specific values that depend on seed data the LLM
can't predict.

OUTPUT FORMAT — strict, line-oriented stdout:

```
PASS public/api/products.php GET → 200, application/json, has key 'products'
FAIL public/api/cart.php POST: expected status 200, got 500: <body snippet>
PASS public/api/cart.php DELETE → 200
```

Each line is one assertion. The test runner parses these:
- `PASS <endpoint>: ...` → ignored (no issue surfaced)
- `FAIL <endpoint>: <message>` → issue with `path: <endpoint>`,
  severity `high`, message `<message>` fed to the auto-fix loop

Endpoint MUST be the full project-relative PHP path (e.g.
`public/api/cart.php`) — the runner attributes failures by path.

IMPLEMENTATION RULES for the PHP test file:
- Pure stdlib PHP. ext-curl + ext-json only. NO Composer.
- Define a small `assert_*` helper set: `assert_status($got, $want, $endpoint, $method)`,
  `assert_json($body, $endpoint, $method)`, `assert_has_key($obj, $key, $endpoint, $method)`,
  `assert_type($value, $type, $endpoint, $method, $key)`.
- Each helper prints `PASS <endpoint> <METHOD> → ...` on success or
  `FAIL <endpoint> <METHOD>: <message>` on failure, then continues
  (no `exit` on first failure — we want all assertions in one run).
- Use a 5-second curl timeout per request (`CURLOPT_TIMEOUT = 5`).
- For POST/PUT, build a realistic minimal payload from the contract.
  e.g. for `POST /api/cart.php` with body `{product_id, qty}`, send
  `{"product_id": 1, "qty": 1}` (use 1 as a safe default for foreign
  keys since the seed in `_db.php` should have at least one row).
- The script's exit code: 0 if all PASS, 1 if any FAIL.

WHAT TO TEST per endpoint:
- GET endpoints: status 200, content-type contains "application/json",
  body is valid JSON, top-level shape matches contract.
- POST endpoints with required body: send a valid payload, assert 200 +
  expected response shape; ALSO send invalid (missing field) and assert
  400 + JSON `{error: string}`.
- DELETE endpoints: assert 200 (or 405 if not implemented).

Output ONLY the PHP file contents. Begin with `<?php`. No markdown
fences, no commentary."""


def generate_tests(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    plan: dict,
    contracts: str,
) -> tuple[str, dict]:
    """Generate ONE PHP test file (`tests/api.php`) from the plan +
    contracts. Returns ``(test_file_content, {"input", "output"})``.

    Returns ``("", {...})`` and skips the LLM call when:
    - no `public/api/*.php` files in the plan (backendless app — nothing to test)
    - contracts pass produced empty output (plan was too small to bother)
    """
    if not contracts:
        return "", {"input": 0, "output": 0}

    # Inspect the plan: any /api/ files?
    api_files: list[str] = []
    for ph in plan.get("phases") or []:
        for f in ph.get("files") or []:
            p = (f.get("path") or "").replace("\\", "/").lstrip("/")
            if p.startswith("public/api/") and not p.split("/")[-1].startswith("_"):
                api_files.append(p)
    if not api_files:
        return "", {"input": 0, "output": 0}

    llm = _resolve_llm(brain, db, project_llm_name)

    # Pull only the "PHP API endpoint contracts" section from the contracts
    # markdown — we don't need to send TS interfaces or SQL to the test
    # generator. Saves tokens.
    api_contracts_section = contracts
    m = re.search(
        r"##\s*PHP API endpoint contracts.*?(?=\n##\s|\Z)",
        contracts,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        api_contracts_section = m.group(0)

    prompt = (
        _TESTS_SYSTEM
        + "\n\nAPI ENDPOINTS THE PLAN DEFINES:\n"
        + "\n".join(f"  - {p}" for p in api_files)
        + "\n\nCONTRACTS (PHP API section):\n"
        + api_contracts_section.strip()
        + "\n\nNOW EMIT THE PHP TEST FILE. Begin with `<?php`."
    )
    try:
        result = llm.llm.complete(prompt)
    except Exception:
        logger.exception("generate_tests: LLM call failed")
        return "", {"input": 0, "output": 0}
    text = (result.text if hasattr(result, "text") else str(result)) or ""
    text = text.strip()

    fence = _FENCE_RE.search(text)
    if fence and fence.start() == 0 and fence.end() == len(text):
        text = fence.group(1).strip()

    # Sanity: must start with `<?php` and contain at least one curl call.
    if not text.startswith("<?php"):
        # Try to find the <?php line and trim leading prose.
        idx = text.find("<?php")
        if idx >= 0:
            text = text[idx:]
        else:
            return "", {"input": _estimate_tokens(brain, prompt), "output": _estimate_tokens(brain, text)}
    if "curl_init" not in text:
        # The LLM produced something but it isn't a runnable curl-based
        # test pack. Skip rather than ship junk.
        return "", {"input": _estimate_tokens(brain, prompt), "output": _estimate_tokens(brain, text)}
    if len(text.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
        return "", {"input": _estimate_tokens(brain, prompt), "output": _estimate_tokens(brain, text)}

    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, text)
    return text, {"input": in_tokens, "output": out_tokens}


_INLINE_FIX_SYSTEM = """You are fixing files mid-build, between two
phases of a phased app generation pass. Runtime probes detected issues
in files that have ALREADY been written; the next phase depends on
these being correct, so you need to repair them NOW before generation
continues.

You will be shown:
- The full plan (all phases).
- The shared contracts (TS interfaces, PHP signatures, SQL).
- The current on-disk content of each file you must fix.
- The list of issues — concrete failures observed by hitting the live
  preview, NOT guesses.

OUTPUT FORMAT — strict JSON, no prose, no markdown fences:

{
  "files": [
    {"path": "public/api/_db.php", "content": "<?php\\n... full new content ..."},
    {"path": "src/api.ts", "content": "// ... full new content ..."}
  ]
}

RULES:
- Only emit files from the `target_paths` list — do NOT add new files,
  do NOT modify files outside that list. Adding new files is the next
  phase's job.
- Each entry is the COMPLETE new contents of the file (no diffs, no
  patches). The content replaces the on-disk file wholesale.
- Address every issue listed. The runtime evidence is authoritative;
  the LLM's previous output is what's broken, not the test or the probe.
- Stay consistent with the contracts above and with files already
  written that you AREN'T touching (their paths are listed for context).
- Architecture rules still apply (PHP under public/api/ only, JSON-only
  endpoints, no PHP in HTML, no npm imports in TS, etc.)."""


def inline_fix_files(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    plan: dict,
    contracts: str,
    issues: list[dict],
    target_paths: list[str],
    project_id: int,
) -> tuple[dict[str, str], dict]:
    """Mid-build fix turn — repair files between phases.

    Returns ``(file_contents_by_path, {"input": int, "output": int})``.
    On parse / LLM failure returns ``({}, {...})`` so the build can
    continue degraded rather than abort.

    `target_paths` constrains what the LLM is allowed to rewrite (only
    files written by THIS phase or earlier). Any file in the response
    outside the target list is dropped.
    """
    if not target_paths or not issues:
        return {}, {"input": 0, "output": 0}
    llm = _resolve_llm(brain, db, project_llm_name)

    # Read current content of every target file so the LLM sees what it's
    # actually fixing instead of guessing.
    current = _read_file_contents_for_prompt(
        project_id, target_paths,
        per_file_cap=PROMPT_RELEVANT_PER_FILE_BYTES,
        total_cap=PROMPT_RELEVANT_TOTAL_BYTES,
    )

    parts: list[str] = [_INLINE_FIX_SYSTEM, ""]
    if contracts:
        parts.append("SHARED CONTRACTS:\n")
        parts.append(contracts.strip())
        parts.append("")
    parts.append("THE FULL PLAN:\n" + json.dumps(plan, indent=2) + "\n")
    parts.append("ISSUES TO FIX (runtime evidence — facts, not guesses):")
    for i, issue in enumerate(issues, 1):
        parts.append(
            f"  [{i}] severity={issue.get('severity','?')} path={issue.get('path','?')}\n"
            f"      {issue.get('message','')}"
        )
    parts.append("")
    parts.append("FILES YOU MAY REWRITE (only these — adding new files is the next phase's job):")
    for tp in target_paths:
        parts.append(f"  - {tp}")
    parts.append("")
    parts.append("CURRENT CONTENT OF EACH TARGET FILE:")
    for tp in target_paths:
        body = current.get(tp, "(file is empty or could not be read)")
        parts.append(f"\n--- {tp} ---\n{body}\n--- end {tp} ---")
    parts.append("\nNOW EMIT THE STRICT JSON.")

    prompt = "\n".join(parts)
    try:
        result = llm.llm.complete(prompt)
    except Exception:
        logger.exception("inline_fix_files: LLM call failed")
        return {}, {"input": 0, "output": 0}
    text = (result.text if hasattr(result, "text") else str(result)) or ""
    text = text.strip()
    fence = _FENCE_RE.search(text)
    if fence and fence.group(1):
        text = fence.group(1).strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Tolerate prose around the JSON: take outermost braces.
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                parsed = json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                parsed = None
    files = (parsed or {}).get("files") if isinstance(parsed, dict) else None
    if not isinstance(files, list):
        return {}, {"input": _estimate_tokens(brain, prompt), "output": _estimate_tokens(brain, text)}

    target_set = set(target_paths)
    out: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path")
        c = entry.get("content")
        if not isinstance(p, str) or not isinstance(c, str):
            continue
        try:
            normalized = validate_file_path(p)
        except ValueError:
            continue
        if normalized not in target_set:
            # LLM tried to add/modify a file outside the target list — drop.
            continue
        if len(c.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
            continue
        out[normalized] = c

    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, text)
    return out, {"input": in_tokens, "output": out_tokens}


def stream_file_content(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    plan: dict,
    file_spec: dict,
    *,
    phase: Optional[dict] = None,
    already_written: Optional[list[str]] = None,
    project_id: Optional[int] = None,
    contracts: Optional[str] = None,
) -> Generator[tuple[str, dict], None, None]:
    """Generate one file's contents from the approved plan.

    `phase` is the current phase dict; when provided, the LLM gets
    phase-scoped context.
    `already_written` is the list of file paths written by previous
    phases / earlier files in this phase, so the LLM can reference them
    by exact path instead of guessing.
    `project_id`, when provided, lets the function read the ACTUAL
    content of relevant already-written files from disk and inject them
    into the prompt — the LLM sees real code instead of just paths.
    `contracts` is the optional sketch-then-fill output (TS interface
    signatures, PHP function signatures, SQL CREATE TABLE) so every file
    targets the same contracts.

    Yields ``("file_delta", {"path", "text"})`` for each LLM delta, then
    ``("file_done", {"path", "content", "tokens"})`` with the final full
    text. The caller writes to disk + emits to SSE."""
    llm = _resolve_llm(brain, db, project_llm_name)
    path = validate_file_path(file_spec["path"])
    purpose = file_spec.get("purpose", "")
    role_guidance = _role_guidance_for(path)
    plan_json = json.dumps(plan, indent=2)
    phase_name = (phase or {}).get("name") or "Build"
    phase_desc = (phase or {}).get("description") or ""

    # If the target file already exists on disk, prepend its CURRENT
    # content with an explicit MODIFY instruction. Without this, the LLM
    # treats every per-file generation as a from-scratch rewrite — which
    # on a follow-up turn is how `styles.css` ends up gutted to a 10-line
    # bare stub when the user asked to tweak one button.
    current_target_block = ""
    if project_id is not None:
        from restai.app.storage import get_project_root
        target_disk = get_project_root(project_id) / path
        if target_disk.is_file():
            try:
                existing = target_disk.read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing = None
            if existing:
                if len(existing) > PROMPT_TARGET_FILE_BYTES:
                    existing = existing[:PROMPT_TARGET_FILE_BYTES] + "\n/* [truncated for prompt budget] */"
                current_target_block = (
                    "\nTHIS FILE ALREADY EXISTS — its current content is shown below.\n"
                    "MODIFY it to satisfy the purpose above. PRESERVE every existing "
                    "selector / class / function / import / comment / structure that "
                    "isn't directly contradicted by the purpose. DO NOT rewrite from "
                    "scratch. Output the COMPLETE new file (the writer replaces the "
                    "file wholesale), but keep all unchanged sections intact byte-for-byte.\n"
                    f"\n--- CURRENT {path} ---\n{existing}\n--- end CURRENT {path} ---\n"
                )

    # Build the already-written block. If project_id is provided, ALSO
    # inject the actual content of the most-relevant existing files —
    # the LLM reads its own previous output instead of guessing.
    if already_written:
        relevant_files: dict[str, str] = {}
        if project_id is not None:
            picked = _pick_relevant_files(path, already_written, max_files=PROMPT_RELEVANT_FILES_MAX)
            if picked:
                relevant_files = _read_file_contents_for_prompt(
                    project_id, picked,
                    per_file_cap=PROMPT_RELEVANT_PER_FILE_BYTES,
                    total_cap=PROMPT_RELEVANT_TOTAL_BYTES,
                )
        if relevant_files:
            blocks = [
                "FILES ALREADY WRITTEN IN EARLIER STEPS — full content of the most relevant ones is shown below; rely on these (paths, function signatures, table schemas) instead of guessing:\n"
            ]
            blocks.append("All written paths:\n" + "\n".join(f"- {p}" for p in already_written) + "\n")
            for p, content in relevant_files.items():
                blocks.append(f"\n--- {p} ---\n{content}\n--- end {p} ---\n")
            already_written_block = "".join(blocks)
        else:
            already_written_block = (
                "FILES ALREADY WRITTEN IN EARLIER STEPS (you can rely on these existing):\n"
                + "\n".join(f"- {p}" for p in already_written)
                + "\n"
            )
    else:
        already_written_block = (
            "FILES ALREADY WRITTEN IN EARLIER STEPS: (none — this is the first file in the build)\n"
        )

    # Optional contracts block (sketch-then-fill output) — see
    # `generate_contracts` for the producer.
    if contracts:
        already_written_block = (
            "SHARED CONTRACTS (TS interfaces / PHP signatures / SQL schemas — every "
            "file in this build MUST conform to these exact names and shapes):\n\n"
            + contracts.strip()
            + "\n\n"
            + already_written_block
        )
    system = _FILE_SYSTEM_TEMPLATE.format(
        plan_json=plan_json,
        phase_name=phase_name,
        phase_description=phase_desc,
        already_written_block=already_written_block + current_target_block,
        file_path=path,
        file_purpose=purpose,
        role_guidance=role_guidance,
    )
    prompt = system  # single-turn; system + user are merged
    accumulated: list[str] = []
    for delta in _stream_complete(llm, prompt):
        accumulated.append(delta)
        yield ("file_delta", {"path": path, "text": delta})

    raw = "".join(accumulated).strip()
    # Strip code fences if the LLM wrapped (despite being told not to).
    fence = _FENCE_RE.search(raw)
    if fence and len(fence.group(1)) > 0:
        raw = fence.group(1).strip()
    if not raw:
        raise ValueError("LLM returned empty content")
    if len(raw.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
        raise ValueError("generated file exceeds size cap")

    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, raw)
    yield (
        "file_done",
        {
            "path": path,
            "content": raw,
            "tokens": {"input": in_tokens, "output": out_tokens},
        },
    )


def fix_file_with_ai(
    brain: Any,
    db: Any,
    project_llm_name: Optional[str],
    path: str,
    current_content: str,
    instruction: str,
) -> tuple[str, dict]:
    """Single-file targeted edit. Returns ``(new_content, {input, output})``.

    Same SPA-architecture system prompt as the plan/execute flow so fixes
    don't drift back to PHP-rendered HTML. Synchronous (non-streaming) —
    the per-file fix UX is a quick edit, not a long-running flow.
    """
    llm = _resolve_llm(brain, db, project_llm_name)
    validate_file_path(path)
    if len(current_content.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
        raise ValueError("File is too large for AI editing")

    prompt = (
        f"{_FIX_FILE_SYSTEM}\n\n"
        f"File path: {path}\n\n"
        "Current contents:\n"
        "```\n"
        f"{current_content}\n"
        "```\n\n"
        f"User instruction:\n{instruction.strip()}\n\n"
        "Output the new full file contents now."
    )
    try:
        result = llm.llm.complete(prompt)
    except Exception as e:
        logger.exception("LLM complete failed during fix-file")
        raise ValueError(f"LLM call failed: {e}")
    text = (result.text if hasattr(result, "text") else str(result)) or ""
    new_content = text.strip()
    fence = _FENCE_RE.search(new_content)
    if fence and len(fence.group(1)) > 0:
        new_content = fence.group(1).strip()
    if not new_content:
        raise ValueError("LLM returned an empty file")
    if len(new_content.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
        raise ValueError("Edited file would exceed size cap")
    in_tokens = _estimate_tokens(brain, prompt)
    out_tokens = _estimate_tokens(brain, text)
    return new_content, {"input": in_tokens, "output": out_tokens}


def _estimate_tokens(brain: Any, text: str) -> int:
    """Best-effort token count using Brain's tokenizer. Returns 0 on
    failure rather than blowing up the cost-logging path."""
    if not text:
        return 0
    try:
        return len(brain.tokenizer(text))
    except Exception:
        return 0
