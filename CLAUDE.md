# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is RESTai

AIaaS (AI as a Service) platform — create AI projects and consume them via REST API. Supports multiple project types: RAG (with optional natural language to SQL), agent (LLM chat with optional tool calling), and block (visual logic builder).

## Commands

```bash
# Backend
make dev              # Dev server with hot reload (port 9000, RESTAI_DEV=true)
make start            # Production (4 workers, port 9000)
make database         # Initialize DB schema + admin user + default models
make migrate          # Run Alembic migrations
make install          # Full setup: deps + database + frontend build

# Crons
make cron             # Install a single crontab entry that runs crons/runner.py every minute
make cron-remove      # Remove the crontab entry
restai crons          # Run the cron runner once (same thing, for ad-hoc use)

# Frontend
make frontend         # npm install + npm run build
cd frontend && npm start  # Dev server (port 3000, proxies to 9000)

# Tests
pytest tests                                    # All tests
pytest tests/test_projects.py -v                # Single file
pytest tests/test_projects.py::test_create_project  # Single test

# Code quality
make code             # black app/*.py

# WordPress plugin
cd wordpress && zip -r restai.zip restai   # Build release zip for the WP plugin
```

Package manager is `uv`. Dependencies exclude GPU group by default (`--no-group gpu`).

## Architecture

**Entry point**: `restai/main.py` — FastAPI app with lifespan that initializes `Brain`, registers routers, optionally mounts internal MCP server at `/mcp`, and mounts React SPA at `/admin/*`.

**Core orchestration**: `restai/brain.py` — `Brain` class holds LLM/embedding caches, tool registry, chat store (Redis or in-memory), and token counter. Injected via `app.state.brain`.

**Request flow**: Router endpoint → `restai/helper.py` (`chat_main`/`question_main`) → dispatches to project type handler in `restai/projects/` → logs inference via background task.

### Project types (`restai/projects/`)

All inherit from `ProjectBase` (in `base.py`) which defines `chat()` and `question()`:
- `rag.py` — Retrieval-Augmented Generation (vectorstore + embeddings + reranking + optional natural language to SQL)
- `agent.py` — Direct LLM chat. Supports multimodal image input, built-in tools, MCP servers, token-by-token streaming, fallback LLMs, history compression, ReAct fallback for tool-callless models, and output guards. Without any tools configured, behaves like a plain LLM chat (the runtime exits after one turn).
- `block.py` — Visual logic builder using Blockly. No LLM required. Interprets workspace JSON server-side via `block_interpreter.py`. Supports image passthrough to sub-projects via "Call Project" block.

### Routers (`restai/routers/`)

`/projects`, `/users`, `/teams`, `/llms`, `/embeddings`, `/tools`, `/proxy`, `/direct`, `/statistics`, `/settings`, `/auth`, `/evals` (evaluation framework), plus GPU-only `/image` and `/audio`.

Sub-routes added to `/projects/{id}/*` over time: `/widgets` (embeddable chat widget CRUD + per-widget key regeneration), `/routines` (scheduled project messages), `/tools` (agent-created custom tools), `/prompts` (version history), `/evals` (eval runs).

Path parameters on all `/projects/{projectID}/...` routes are typed `int` — callers must pass the numeric id, not the project name (a naming mismatch was the root cause of several past HTTP 422 regressions).

### Models (`restai/models/`)

- `models.py` — Pydantic schemas for API request/response. Includes input validation: `validate_safe_name` for URL-safe identifiers (regex `^[a-zA-Z0-9._:-]+$`), `Literal` types for enum fields (`privacy`, `type`, `class_name`), `max_length` on string fields, `ge`/`le` bounds on integers, and `sanitize_filename` for uploads.
- `databasemodels.py` — SQLAlchemy ORM models

Key relationships: Users ↔ Projects (many-to-many), Users ↔ Teams (members + admins), Teams → Projects/LLMs/Embeddings.

### Database

SQLite by default (`restai.db`), PostgreSQL via `POSTGRES_HOST`, MySQL via `MYSQL_HOST`. Connection pool configured via `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`. Migrations via Alembic (`alembic.ini`, `migrate.py`).

**Init flow** (`database.py`): creates tables → admin user (password from `RESTAI_DEFAULT_PASSWORD`) → default LLMs/embeddings from `restai/tools.py`.

### Auth (`restai/auth.py`)

Three methods checked in order: JWT cookie (`restai_token`), Bearer API key, Basic auth. OAuth (Google, Microsoft, GitHub, OIDC) configured via env vars in `restai/config.py`. Key dependency functions: `get_current_username`, `get_current_username_admin`, `get_current_username_project`.

### LLM integration

`restai/tools.py` maps LLM class names to implementations. Valid LLM classes: Ollama, OllamaMultiModal, OllamaMultiModal2, OpenAI, OpenAILike, Grok, Anthropic, LiteLLM, vLLM, GeminiMultiModal, Gemini, AzureOpenAI. Valid embedding classes: LangChain, LangChain.Openai, LangChain.HuggingFace, OllamaEmbeddings, Ollama. All go through LlamaIndex abstractions. These sets are defined as `VALID_LLM_CLASSES` and `VALID_EMBEDDING_CLASSES` in `models.py` and enforced via Pydantic validators.

### Frontend (`frontend/`)

React 18 + MUI v5 + Redux Toolkit + Blockly (for block projects). CRA-based build. Routes in `frontend/src/app/routes.js` (lazy-loaded). Auth context in `frontend/src/app/contexts/JWTAuthContext.js`. API URL configured via `REACT_APP_RESTAI_API_URL` (defaults to `http://127.0.0.1:9000`).

Key frontend pages for block projects:
- `frontend/src/app/views/projects/IDE.jsx` — Standalone Blockly IDE page (`/project/:id/ide`)
- `frontend/src/app/views/projects/components/BlocklyEditor.jsx` — Blockly workspace React component
- `frontend/src/app/views/projects/components/blockly/blocks.js` — Custom block definitions (Get Input, Set Output, Call Project, Classifier, Log). All other toolbox entries are Blockly 12 built-ins (full Logic / Control / Math / Text / Lists / Variables / Procedures matching MIT App Inventor's general-purpose set — no platform-specific blocks).

Server-side execution for block projects lives in `restai/projects/block_interpreter.py`. Dispatch is via two dicts built in `__init__` (`_stmt_handlers`, `_value_handlers`) keyed by the block's `type` string. Flow control (break / continue / procedure early-return) uses internal sentinel exceptions `_BlockBreak`, `_BlockContinue`, `_BlockReturn` that propagate out to the enclosing loop / procedure handler. Procedures live in `self.procedures` (registered at `execute()` start so definitions can appear after calls in the workspace), with a `_scope_stack` of param frames layered over globals — `variables_set` / `variables_get` check the top frame first and fall through to `self.variables`, giving parameter isolation without polluting globals.
- `frontend/src/app/views/projects/components/blockly/toolbox.js` — Toolbox category configuration

### MCP Server (`restai/mcp.py`)

Optional internal MCP server that exposes user projects as MCP tools. Built with FastMCP, served over SSE at `/mcp/sse`. Disabled by default — enable via `MCP_SERVER=true` env var or the admin settings page (requires restart).

Two tools: `list_projects` (returns accessible projects as JSON) and `query_project` (sends a question to a project, returns the answer). Authentication via Bearer API key on every request. Users can only access their assigned projects; admins access all. Settings follow the GPU toggle pattern (`config.py` → `settings.py` → `main.py` conditional mount).

### Evaluation Framework (`restai/eval.py`, `restai/routers/evals.py`)

Built-in evaluation system for measuring AI project quality. Users create test datasets (question + optional expected answer), run evaluations with selectable metrics, and track scores over time. Endpoints under `/projects/{id}/evals/...`.

Three metrics via DeepEval: `answer_relevancy` (all project types), `faithfulness` (RAG — checks answers are grounded in retrieved context), `correctness` (compares against expected answer). Eval runs execute in the background via `BackgroundTasks`, calling each project's `question()` method directly (skips logging/budget).

Database tables: `eval_datasets`, `eval_test_cases`, `eval_runs`, `eval_results` (one row per metric per test case). Frontend at `/project/:id/evals` with dataset management, run execution, results table, and score trend chart.

### Prompt Versioning (`prompt_versions` table)

Every system prompt change is automatically versioned. When `edit_project` in `database.py` detects a prompt change, it creates a `PromptVersionDatabase` record with version number, text, user, and timestamp.

Endpoints: `GET /projects/{id}/prompts` (list versions), `GET /projects/{id}/prompts/{versionId}` (get version), `POST /projects/{id}/prompts/{versionId}/activate` (restore old version). Eval runs link to prompt versions via `prompt_version_id` on `EvalRunDatabase` for A/B comparison.

Frontend: collapsible "Version History" panel in the project edit page, version chips on eval runs.

### Rate Limiting (`restai/budget.py`)

Per-project request rate limiting. Configured via `rate_limit` field in `ProjectOptions` (requests per minute, `None` = unlimited). Enforced by `check_rate_limit()` in `budget.py`, called alongside `check_budget()` in `helper.py` before every inference. Returns HTTP 429 when exceeded. Counts recent requests from `OutputDatabase` (indexed by `project_id` and `date`).

### Latency Tracking

Every inference logs `latency_ms` in `OutputDatabase`. Timing starts at the router endpoint (`chat_query`/`question_query_endpoint`) and is passed through `helper.py` to `log_inference`. The `/projects/{id}/tokens/daily` endpoint includes `avg_latency_ms` per day. Frontend shows a latency chart and average latency stat card in `ProjectTokens.jsx`.

### Vector stores (`restai/vectordb/`)

ChromaDB (default) or Redis. Configured per-project. Reranking support: ColBERT and LLM-based. ChromaDB uses `_client_cache` dict to reuse `PersistentClient` per path, avoiding SQLite lock contention with multiple workers.

### Home Dashboard (`frontend/src/app/views/dashboard/`)

Full-width layout with: 6 stat cards (Projects, Users, Teams, Tokens, Cost, Avg Latency) with gradient icon circles → Activity section (daily tokens area chart + Activity Pulse card with Nightingale rose chart, 30-day micro heatmap, insight pills) → Distribution row (project types donut, LLM usage donut, top LLMs bar) → two side-by-side tables (Top Projects, Latest Projects). Charts use Recharts gradient fills and ECharts for donuts/rose.

### Project Invitations (`project_invitations` table)

Users can invite other users to their projects. The invited user must belong to the same team as the project. Follows the same pattern as team invitations.

Endpoints: `POST /projects/{id}/invitations` (send invite, requires project membership, blocked for restricted users), `GET /invitations` (returns both team and project invitations with `type` field), `GET /invitations/count` (combined count), `POST /invitations/projects/{id}/accept`, `POST /invitations/projects/{id}/decline`.

Frontend: "Invite User" card in the Security tab of project details. Invitations page (`/invitations`) shows both team and project invitations in separate sections.

### SSO Auto-Created User Settings

Two global settings in the Authentication section of platform settings:
- `sso_auto_restricted` (default: `true`) — auto-created SSO/LDAP users are in restricted (read-only) mode
- `sso_auto_team_id` (default: empty) — auto-created users are automatically added to the specified team

Applied in `restai/oauth.py` (SSO) and `restai/routers/users.py` (LDAP) during user creation. Config attrs: `config.SSO_AUTO_RESTRICTED`, `config.SSO_AUTO_TEAM_ID`.

### Restricted Users (`is_restricted` field on `UserDatabase`)

Per-user read-only mode. Restricted users can view assigned projects and use playgrounds but cannot create/edit projects, manage users/teams, or send project invitations. Enforced via `check_not_restricted(user)` in `restai/auth.py`, called in 14+ project endpoints plus the project invitation endpoint.

### Embeddable Chat Widget (`restai/widget/chat.js`)

Self-contained vanilla JS widget with Shadow DOM, served at `/widget/chat.js`. Supports streaming (opt-in via `data-stream="true"`) and non-streaming modes. Reads config from `data-*` attributes. Markdown-lite rendering, typing indicator, conversation memory via chat_id. Widget builder in the project details Widget tab auto-generates a project-scoped API key.

### Knowledge Base Sync (`restai/sync.py`, `crons/sync.py`)

Sync from 5 external sources: URL, S3, Confluence, SharePoint, Google Drive. Each source has its own `sync_interval` and `last_sync` timestamp to prevent duplicate syncs across workers. Standalone cron script (`crons/sync.py`) replaces daemon threads; uses `Brain(lightweight=True)` to skip tool loading.

### Cron Runner (`crons/runner.py`)

Single entry point that dynamically discovers and runs all cron modules in the `crons/` directory. Each module must define a `main()` function. Modules with `DAEMON = True` (e.g. `slack.py`) are skipped. One crontab entry runs everything: `* * * * * cd /path/to/restai && uv run python crons/runner.py`. New cron scripts are auto-discovered — just add a `.py` file with a `main()` function to `crons/`.

The runner launches every cron **in parallel** as isolated subprocesses (so a slow/hung job can't block the others) with a per-job 10-minute timeout, and takes a per-job `flock` on `.cron-<name>.lock` files under the repo root — if the previous invocation is still running, the next one skips that job and leaves the others alone. DB-backed logging via `CronLogger` in each module; logs visible at `/admin/cron-logs` (filterable by job + status, with a "Run Now" button that shells out to the runner in a FastAPI `BackgroundTask`).

Slack is now a cron-friendly poller (`crons/slack.py`, uses `slack_sdk.WebClient` + `conversations.history`). The old Socket Mode daemon was removed — no more `slack_bot.py`, no `slack_app_token` field.

Telegram is also cron-driven (`crons/telegram.py`, long-poll-then-exit each minute). The legacy `TelegramPoller` daemon in `restai/telegram.py` is dead code (no callers). Each project's bot also responds to `/chatid` (or `/myid`) by replying with the current chat's id — gives admins a one-shot way to fill in `telegram_default_chat_id` (the destination used by the `send_telegram` builtin tool, since Telegram bots can't initiate conversations).

### Project Routines

`ProjectRoutineDatabase` (`restai/models/databasemodels.py:445`) — scheduled messages that auto-fire on a project via the normal chat/question pipeline. Fields: `name`, `message`, `schedule_minutes`, `enabled`, `last_run`, `last_result`.

Endpoints: `GET/POST/PATCH/DELETE /projects/{id}/routines[/{routineId}]`, plus `POST /projects/{id}/routines/{routineId}/fire` for manual trigger. Execution in `crons/routines.py` — `asyncio.wait_for` each routine with a 300s per-routine timeout so a hung MCP call can't stall the whole job; the runner's outer 600s timeout is a second safety net. The `for routine in routines` loop `continue`s on every exception so one broken routine never blocks the rest.

Frontend: **Routines** tab on the project page, CRUD + a "fire via API" card showing the curl command.

### Memory Bank (project-wide conversation context)

Agent-only opt-in feature. When `ProjectOptions.memory_bank_enabled=true`, every conversation in the project contributes a short LLM-generated summary to a shared memory bank (`ProjectMemoryBankEntryDatabase` / table `project_memory_bank_entries`). The rendered bank gets prepended to the system prompt of every chat in that project, giving the agent context across users and sessions.

- **Source of truth**: `OutputDatabase` rows. Authoritative across workers, survives Redis TTLs, bound to `project_id`. Redis-backed agent2 sessions are *not* used (not enumerable per project).
- **Summaries via System LLM** — same setting Smart Search / Prompt AI use. When no System LLM is configured the cron is a no-op (logs a single warning).
- **Cron**: `crons/memory_bank.py` — runs every minute via the standard runner. Skips conversations idle <10 min (`CONVERSATION_IDLE_MINUTES`). Per-conversation summaries upserted by `chat_id`. Then runs the compression ladder.
- **Compression ladder** in `restai/memory_bank.py:compress_entries`: rolls up `conversation` rows older than 1 day into `day` digests; `day` rows older than 7 days into `week`; `week` older than 30 days into `month`. If still over budget after `month`, deletes oldest entries until within `memory_bank_max_tokens`. The headroom multiplier (`COMPRESSION_HEADROOM`, 1.25) avoids burning System LLM tokens on tiny overshoots.
- **Injection** at `agent.py:_augment_system_prompt_with_memory_bank` — prepends the rendered block to the system prompt before `_build_runtime`. Failures degrade silently (the bank just isn't injected this turn).
- **Survives project edit form saves**: the form does not surface every key in `ProjectOptions`, so the memory bank state lives inside the options blob just like other knobs. The toggle + max-tokens fields are persisted explicitly via the form, so no `PRESERVED_KEYS` carry-over needed (unlike Mobile, which is set out-of-band).
- **Privacy**: every project member sees summaries derived from every other member's conversations. The project edit form surfaces a warning Alert when the toggle is on.

### Cron Logs

`CronLogDatabase` — one row per runner invocation per job. Fields: `job`, `status` (success/error/warning), `message`, `details` (traceback), `items_processed`, `duration_ms`, `date`. Written by the `CronLogger` helper (`restai/cron_log.py`) — each cron instantiates it at the top of `main()`, calls `info()`/`warning()`/`error()`, and `finish()` at the end. `__del__` is a safety net: if `finish()` was never called (process killed), the destructor writes an error row.

Admin page: `/admin/cron-logs` — filter by job/status, expand any row for the full message and traceback, **Run Now** button to kick the runner on-demand (spawns `crons/runner.py` as a subprocess so event loops / DB sessions stay clean), **Purge** button to wipe the table.

### File Attachments in Chat/Question

`QuestionModel` and `ChatModel` both accept an optional `files: list[FileAttachment]` (max 10) where each attachment is `{name, content (base64), mime_type?}`. When a message with files hits an agent project, `_upload_files_and_augment_prompt` (`restai/projects/agent.py`) decodes the bytes, calls `DockerManager.put_files(chat_id, [...])` to drop them into the container's `/home/user/uploads/` via `put_archive` on a tar stream, then appends a manifest to the user prompt (`[Files attached by the user (available in /home/user/uploads/...)]`) so the LLM naturally picks up the terminal-tool workflow. Container persists across messages in the same chat, so follow-up messages keep access to previously uploaded files.

Docker is required — with the sandbox disabled, the helper appends a note telling the LLM the files couldn't be delivered instead of failing the request. Questions (stateless) use an ephemeral `chat_id` so the sandbox still gets spun up for the duration of that one call.

Frontend: paperclip button in `ChatPanel.jsx` next to the existing image-upload cloud icon (agent-projects only). 20 MB per file, 10 files per message, base64-encoded in the same JSON body as the question.

### Agent-Created Tools & Docker Sandbox

Agents can create their own Python tools at runtime via the built-in `create_tool` tool (`restai/llms/tools/create_tool.py`). Tools are stored in `ProjectToolDatabase` (scoped to one project), test-executed in Docker before save, and auto-loaded by `_build_runtime` in `restai/projects/agent.py` on every subsequent chat. Each custom tool has an `enabled` toggle for per-tool kill-switch.

Docker lifecycle: `restai/docker_manager.py` — per-chat containers reused across tool calls within the same conversation, idle cleanup by `crons/docker_cleanup.py` (removes containers older than `docker_timeout` seconds). Script execution uses base64-piped `python3 -c`; file uploads use `base64 -d | tar xf -` via `exec_run` because `put_archive` is blocked on read-only rootfs containers.

Sandbox config: 1 GiB tmpfs on `/tmp` and `/home/user` (plenty of room for `pip install pandas` + uploaded CSVs), 512 MiB RAM, 0.5 CPU, auto-remove on stop. Admin settings: `docker_enabled`, `docker_url`, `docker_image`, `docker_network`, `docker_read_only`.

- **`docker_read_only`** (default `true`) — rootfs read-only; blocks writes to `site-packages` so the LLM *cannot* `pip install`. Turn **off** only when you need pip; the container still dies on idle cleanup so mutations are ephemeral either way.
- **`docker_network`** (default `none`) — network isolation; set to `bridge` to give the LLM outbound access (needed for pip to reach PyPI, also needed by any tool that hits external APIs).

Changing either setting from the admin UI calls `brain.init_docker_manager()` which shuts down the old manager + its cached containers and rebuilds with the new config. Existing containers are stopped via `docker_cleanup.py` cron, so the next chat message always lands in a fresh container matching current settings.

**Image recommendation:** Debian-slim (`python:3.12-slim`) is the default. Avoid Alpine images — they use musl libc which is incompatible with manylinux wheels, so packages like pandas/numpy have to compile from source, which is slow and can blow through the tmpfs budget.

Read-only Tools view on the project main page (`ProjectInfoTools`); editable Agent-Created Tools section in project edit (`ProjectEditTools`).

### Agentic Browser

Per-chat Playwright/Chromium container driven from a tiny in-container HTTP server. Admin-gated (Settings → Agentic Browser), then exposed to agents via nine `browser_*` builtin tools: `browser_goto`, `browser_content`, `browser_click`, `browser_fill`, `browser_select`, `browser_screenshot`, `browser_wait`, `browser_download`, `browser_eval`.

- **Container lifecycle** — `restai/browser/manager.py:BrowserManager` mirrors `DockerManager`: per-chat-id labels, orphan lookup by label, idle cleanup via `crons/browser_cleanup.py`. Image defaults to `mcr.microsoft.com/playwright/python:v1.48.0-jammy` (Chromium + Playwright preinstalled). Container port `7000` is published on `127.0.0.1:<random>` and `BrowserManager.get_or_create(chat_id)` reads the host port via `container.attrs["NetworkSettings"]["Ports"]`.
- **Micro-server** — `restai/browser/micro_server.py` runs *inside* the container (copied in via `put_archive` on create). Pure stdlib (`http.server` + `playwright.sync_api`) — zero extra pip installs. One module-level `BrowserContext` persists cookies/localStorage across tool calls within a chat.
- **Storage state persistence** — after login flows, `BrowserManager.save_storage_state(project_id, domain, state)` writes cookies to Redis (or an in-process fallback) keyed by `(project_id, domain)` with a 30-day TTL. Next chat on the same project can `load_storage_state` and skip the login dance.
- **Domain allowlist** — `ProjectOptions.browser_allowed_domains` (comma-separated, supports `*.example.com` suffix globs). `browser_goto` refuses anything not on the list; empty list = unrestricted (admin choice, risky).
- **Secrets vault** — `project_secrets` table (migration 040, encrypted-at-rest via the same Fernet helpers used for LLM `LLM_SENSITIVE_KEYS`). Admin CRUD via `/projects/{id}/secrets` + new **Secrets** tab on the project edit page (`ProjectEditSecrets.jsx`). `browser_fill(selector, secret_ref="portal_pw")` resolves the plaintext server-side (`DBWrapper.resolve_project_secret`) and types it directly — the value never enters the LLM's context, the inference log, or the audit log.
- **`browser_eval` opt-in** — disabled by default via `ProjectOptions.browser_allow_eval`. Admin must flip it on per project because a prompt-injected page could use JS eval to exfiltrate cookies / hit authed APIs.
- **Screenshots** reuse the existing Brain image cache — `browser_screenshot` returns `![](/image/cache/<id>.png)` markdown that `_drive_runtime` guarantees lands in the final answer (same mechanism as `draw_image`).

### System LLM & AI Assistants

Global "System LLM" setting (Admin → Settings → **System LLM**). Used as the backing model for platform-level AI helpers that aren't project-scoped. When unset, the assistants are hidden from the UI.

- **Smart Search** (`restai/utils/search_ai.py`, `SmartSearch.jsx`) — natural-language search across projects/users/teams/llms/embeddings. Whitelist-based entity/field schema, LLM emits a JSON query spec, server validates + runs RBAC-scoped SQLAlchemy queries, returns normalized `{entity, id, name, subtitle, path}` rows.
- **System Prompt Generator** (`restai/utils/prompt_ai.py`) — per-project "Generate with AI" button next to the system prompt textarea.
- **Blockly Workspace Generator** (`restai/utils/blockly_ai.py`) — block-project IDE has a "generate from description" prompt; emits Blockly workspace JSON from a `BLOCK_REFERENCE` schema.

`Brain.get_system_llm()` reads the `system_llm` setting directly from the DB on every call so multi-worker deployments see config changes immediately (no env-var cache).

### WordPress Plugin (`wordpress/restai/`)

Full WP plugin that wraps RESTai. Each capability maps to a dedicated RESTai project (auto-provisioned on first connect); a widget key is lazily created on the support bot project and stashed in `restai_widget_credentials` so the chat script authenticates instead of staying in preview mode.

- Settings page: URL + Bearer API key + team dropdown + image-generator picker; "Auto-provision starter projects" button.
- Gutenberg sidebar: Generate body, excerpt, SEO meta, featured image, translations. Also a server-rendered content-generator block + `[restai_generate]` shortcode with transient caching.
- Analytics admin page: mirrors `/statistics/summary` + `/statistics/daily-tokens`; button to **Push all to Support Bot** (force-full knowledge sync).
- All `/projects/{id}/...` calls use the integer project id stored in `restai_project_map` (the plugin's task → project-id map). `sync_system_prompt` PATCHes after creation because `ProjectModelCreate` doesn't accept `system`.

Plugin bootstrap in `includes/class-restai.php`, shared Icon helper (`Icon::svg()` / `Icon::data_url()`) in `includes/class-restai-icon.php`, WP REST namespace `restai/v1` in `includes/class-restai-rest.php`. Tested through WordPress 6.9, PHP 7.4+, GPL-2.0+, wp.org-ready (`readme.txt` + i18n + sanitize/escape everywhere).

Local dev stack: `wordpress/docker-compose.yml` spins up WP 6.6 + MariaDB with the plugin bind-mounted at `/var/www/html/wp-content/plugins/restai`.

### Mobile pairing (Android client under `android/`)

Project-scoped mobile companion apps pair via a QR code generated from the project's **Mobile** tab. The protocol is platform-neutral — the QR payload is plain JSON that any mobile client can consume. An Android client ships in `android/`; future iOS would land in a sibling `ios/`.

**Pairing protocol** — `ProjectEditMobile.jsx` calls `POST /projects/{id}/mobile/enable` which mints a **read-only, project-scoped API key** and returns a one-time plaintext plus a JSON QR payload:

```json
{ "host": "https://restai.example.com", "project_id": 42, "project_name": "…", "api_key": "…" }
```

- Endpoints (`restai/routers/projects.py`, Mobile section at the bottom): `GET/POST /projects/{id}/mobile{/enable,/disable,/regenerate}`.
- The minted `ApiKeyDatabase` row id is stashed in `ProjectOptions.mobile_api_key_id` so the app can (a) pair more phones with the same key while the QR stays visible and (b) **regenerate** invalidates all paired phones in one click.
- Disabling the toggle **deletes** the API key (cascade 401 on paired phones).
- The plaintext is surfaced on **every** status read while the integration is enabled (decrypted from `ApiKeyDatabase.encrypted_key` via `decrypt_api_key`) so the QR stays visible across page reloads for pairing new phones. **Regenerate key** invalidates every paired phone at once by rotating the row; **Disable** drops it entirely.

**Android client** — Kotlin + Jetpack Compose app. One activity, two screens: `QrScreen` (CameraX + ML Kit barcode scanner) and `ChatScreen` (Compose + OkHttp SSE reader against `/projects/{id}/chat` with `stream=true`). Credentials live in `EncryptedSharedPreferences` (AES-256-GCM). On every 401 the app clears the stored key and drops the user back on the QR screen. Build: open `android/` in Android Studio or `cd android && ./gradlew assembleDebug`. APK lands in `android/app/build/outputs/apk/debug/`.

### Onboarding Checklist (`frontend/src/app/views/dashboard/shared/OnboardingChecklist.jsx`)

Home-dashboard card shown to admins on fresh installs, gated by three auto-detected steps: add an LLM, attach the LLM to a team, create a project. Auto-hides when all three are done; dismissible via `localStorage["restai_onboarding_dismissed"]`. QA override: append `?onboarding=force` to the URL to render it even when dismissed or fully complete.

### Security Hardening

Accumulated fixes worth remembering:

- **Security headers** (`cors_middleware` in `restai/main.py`) — `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY` + CSP on admin paths. Widget paths exempt from `X-Frame-Options` + CSP so embeds still work.
- **Settings secrets encrypted at rest** — `SETTINGS_ENCRYPTED_KEYS` (`restai/utils/crypto.py`) covers `proxy_key`, `redis_password`, all `sso_*_client_secret`. `DBWrapper.upsert_setting` encrypts on write, `get_setting/get_settings/get_setting_value` decrypt on read. Rows are `expunge`d before mutation so plaintext can't be committed back.
- **Per-project `redact_inference_logs` option** (`ProjectOptions`) — when enabled, `log_inference` strips OpenAI/Slack/Bearer tokens, long alphanumeric strings, and `user:pass@host` patterns from question/answer/system_prompt/context before persisting. Default off.
- **Impersonation audit trail** — `/auth/impersonate/{username}` and `/auth/exit-impersonation` write `IMPERSONATE_START` / `IMPERSONATE_END` audit entries via `audit._log_to_db`.
- **LDAP cookie** — sets `httponly=True`, `samesite="strict"` (was missing httponly).
- **Salted API-key / recovery-code hashing** — `hash_api_key` / `hash_recovery_code` (`restai/utils/crypto.py`) now use PBKDF2-SHA256 + random 16-byte salt with `$pbkdf2$` prefix. `verify_*` accepts both new PBKDF2 hashes and legacy SHA256 for migration.
- **Widget restricted-user block** — `get_widget_from_request` (`restai/auth.py`) rejects with 403 if the widget creator is restricted-and-not-admin.
- **Frontend 401 handling** (`frontend/src/app/utils/api.js`) — on any 401 outside `/login`, sets `sessionStorage["session_expired"] = "1"` and redirects to `/admin/login`; the login page surfaces "Your session has expired. Please log in again." via `useEffect`.

### Custom Team Branding

`TeamBranding` model with `primary_color`, `secondary_color`, `logo_url`, `app_name`, `welcome_message`. Stored as JSON in `TeamDatabase.branding` column. Users with multiple teams can select preferred branding via `UserOptions.preferred_team_id`.

### Two-Factor Authentication (TOTP)

TOTP 2FA with `pyotp`, Fernet-encrypted secrets stored in `UserDatabase.totp_secret`, SHA256-hashed recovery codes. JWT-based temp tokens for TOTP verification (5-min expiry, `purpose: "totp_verify"`). Platform-wide enforcement via `enforce_2fa` setting. Login page integrates TOTP step with recovery code toggle.

## Input Validation

Names used in URL paths (project names, usernames, team names, LLM names, embedding names) are validated with `validate_safe_name` — only `[a-zA-Z0-9._:-]` allowed. This is enforced at the Pydantic model level for create models and at the router level for LLM/embedding creation (since `LLMModel`/`EmbeddingModel` are dual-use input/output models).

Enum fields use `Literal` types: `privacy` ("public"/"private"), project `type` ("rag"/"agent"/"block"), `splitter` ("sentence"/"token").

Integer Query/Form params have `ge`/`le` bounds (pagination, chunks, limits, days).

File uploads are sanitized via `sanitize_filename` (strips path components and null bytes).

## Testing

Tests use `FastAPI.TestClient` with Basic auth: `auth=("admin", RESTAI_DEFAULT_PASSWORD)`. Fixtures are inline in `conftest.py` (sets `sys.setrecursionlimit(20000)` and pre-builds Pydantic model schemas). Tests create real resources (projects, users) against a live app instance. Key test files:
- `tests/test_input_validation.py` — Name validation, enum validation, valid value acceptance
- `tests/test_security.py` — RBAC, cross-team access, empty/whitespace name rejection
- `tests/test_users.py`, `tests/test_teams.py`, `tests/test_llms.py`, `tests/test_embeddings.py` — CRUD tests
- `tests/test_mcp.py` — MCP server auth (Bearer only), access control, tool registration
- `tests/test_rate_limit.py` — Rate limiting enforcement, disable/enable, HTTP 429
- `tests/test_settings.py` — Settings CRUD, SSO auto-restricted/team defaults, config sync
- `tests/test_restricted.py` — Restricted user permissions enforcement
- `tests/test_totp.py` — TOTP 2FA setup, verify, recovery codes
- `tests/test_project_invitations.py` — Project invites: send, accept, decline, team validation, duplicate prevention
- `tests/test_comments.py` — Project comment CRUD

Note: `tests/test_projects.py` may fail if no LLMs are configured in the test environment (pre-existing issue).

## Key env vars

`RESTAI_DEV`, `RESTAI_GPU`, `RESTAI_DEFAULT_PASSWORD`, `RESTAI_URL` (for OAuth redirects), `REDIS_HOST`/`REDIS_PORT`, `CHROMADB_HOST`/`CHROMADB_PORT`, `MCP_SERVER` (enable internal MCP server), LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc). Full list in `restai/config.py`.

Runtime-tunable settings (proxy, SSO, Docker, MCP, system LLM, knowledge retention, 2FA enforcement, etc.) live in the `settings` DB table and are read directly via `db.get_setting_value()` on every access — **don't rely on env-var caches in `config.*` for anything user-configurable**, they only hold the initial seed values. This is what lets multi-worker deployments pick up settings changes without a restart.
