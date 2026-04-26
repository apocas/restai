# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is RESTai

AIaaS platform — create AI projects and consume them via REST API. Project types: RAG (with optional NL→SQL), agent (LLM chat with optional tool calling / MCP), and block (visual logic builder).

## Commands

```bash
# Backend
make dev              # Dev server with hot reload (port 9000, RESTAI_DEV=true)
make start            # Production (4 workers, port 9000)
make database         # Init DB schema + admin user + default models
make migrate          # Run Alembic migrations
make install          # Full setup: deps + database + frontend build

# Crons
make cron             # Install crontab entry that runs crons/runner.py every minute
make cron-remove
restai crons          # Run the cron runner once (ad-hoc)

# Frontend
make frontend         # npm install + npm run build
cd frontend && npm start  # Dev server (port 3000, proxies to 9000)

# Tests
pytest tests
pytest tests/test_projects.py -v
pytest tests/test_projects.py::test_create_project

# Code quality
make code             # black app/*.py

# WordPress plugin
cd wordpress && zip -r restai.zip restai
```

Package manager is `uv`. Default install excludes GPU group (`--no-group gpu`).

## Architecture

**Entry point**: `restai/main.py` — FastAPI app with lifespan that initializes `Brain`, registers routers, optionally mounts internal MCP server at `/mcp`, mounts React SPA at `/admin/*`.

**Core orchestration**: `restai/brain.py` — `Brain` holds LLM/embedding caches, tool registry, chat store (Redis or in-memory), token counter. Injected via `app.state.brain`.

**Request flow**: Router → `restai/helper.py` (`chat_main`/`question_main`) → project type handler in `restai/projects/` → background task logs inference.

### Project types (`restai/projects/`)

All inherit from `ProjectBase` (`base.py`) which defines `chat()` / `question()`:
- `rag.py` — vectorstore + embeddings + reranking + optional NL→SQL
- `agent.py` — Direct LLM chat. Multimodal images, builtin tools, MCP, streaming, fallback LLMs, history compression, ReAct fallback for tool-callless models, output guards. Without tools: behaves like plain LLM chat (one turn).
- `block.py` — Visual builder using Blockly. No LLM. Workspace JSON interpreted by `block_interpreter.py`. Supports image passthrough via "Call Project".

### Routers (`restai/routers/`)

`/projects`, `/users`, `/teams`, `/llms`, `/embeddings`, `/tools`, `/proxy`, `/direct`, `/statistics`, `/settings`, `/auth`, `/evals`, plus GPU-only `/image` and `/audio`.

Sub-routes on `/projects/{id}/*`: `/widgets`, `/routines`, `/tools`, `/prompts`, `/evals`.

**Path params on `/projects/{projectID}/...` are typed `int`** — pass numeric id, not project name (root cause of past 422 regressions).

### Models (`restai/models/`)

- `models.py` — Pydantic schemas. Input validation: `validate_safe_name` (regex `^[a-zA-Z0-9._:-]+$`), `Literal` enums (`privacy`, `type`, `class_name`), `max_length`, `ge`/`le` bounds, `sanitize_filename` for uploads.
- `databasemodels.py` — SQLAlchemy ORM.

Key relationships: Users ↔ Projects (m2m), Users ↔ Teams (members + admins), Teams → Projects/LLMs/Embeddings.

### Database

SQLite default (`restai.db`); Postgres via `POSTGRES_HOST`; MySQL via `MYSQL_HOST`. Pool: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`. Migrations via Alembic.

**Init flow** (`database.py`): tables → admin user (`RESTAI_DEFAULT_PASSWORD`) → default LLMs/embeddings from `restai/tools.py`.

**Migration portability — REQUIRED.** Every migration MUST run cleanly on SQLite, MySQL, and PostgreSQL. SQLite is permissive enough that backend-specific bugs only surface in prod on MySQL/Postgres, leaving the schema permanently inconsistent. Hard rules:
- **No `server_default` on `sa.Text()`/TEXT/BLOB.** MySQL pre-8.0.13 rejects them. Default in app code on insert, or leave nullable. `server_default='0'` on integers is fine everywhere.
- **Backtick-quote MySQL reserved words in raw SQL.** Common landmines: `key`, `order`, `group`, `rank`, `limit`, `read`. Prefer parameter-bound `op.execute(sa.text(...))`.
- **Never wrap `op.create_table` (or any structural op) in a broad try/except that swallows errors.** That pattern caused migrations 035/036/038/039 to silently advance `alembic_version` on MySQL, leaving tables missing at version 046. For idempotency, gate with `sa.inspect(op.get_bind()).has_table('foo')` — see `migrations/versions/047_heal_silent_migration_failures.py`.
- **Avoid SQLite-only DDL.** SQLite rejects `DROP COLUMN`/`ALTER COLUMN` on older versions; use `op.batch_alter_table` so SQLite gets a copy-rebuild while MySQL/Postgres get the native ALTER.
- **Test on at least two backends before merging.** SQLite alone is not evidence of portability.

### Auth (`restai/auth.py`)

Three methods checked in order: JWT cookie (`restai_token`), Bearer API key, Basic. OAuth (Google/Microsoft/GitHub/OIDC) via env vars in `restai/config.py`. Key dependencies: `get_current_username`, `get_current_username_admin`, `get_current_username_project`.

### LLM integration

`restai/tools.py` maps LLM class names to implementations. `VALID_LLM_CLASSES`/`VALID_EMBEDDING_CLASSES` defined in `models.py`, enforced via Pydantic. All LLMs go through LlamaIndex abstractions.

### Frontend (`frontend/`)

React 18 + MUI v5 + Redux Toolkit + Blockly. CRA build. Routes in `frontend/src/app/routes.js` (lazy-loaded). Auth context in `frontend/src/app/contexts/JWTAuthContext.js`. API URL via `REACT_APP_RESTAI_API_URL` (default `http://127.0.0.1:9000`).

Block project pages:
- `frontend/src/app/views/projects/IDE.jsx` — Standalone Blockly IDE (`/project/:id/ide`)
- `frontend/src/app/views/projects/components/BlocklyEditor.jsx` — workspace component
- `frontend/src/app/views/projects/components/blockly/blocks.js` — custom blocks (Get Input, Set Output, Call Project, Classifier, Log). Other entries are Blockly 12 builtins (matching MIT App Inventor's general-purpose set).
- `frontend/src/app/views/projects/components/blockly/toolbox.js` — toolbox config

Server-side execution in `restai/projects/block_interpreter.py`. Dispatch via `_stmt_handlers`/`_value_handlers` dicts keyed by block `type`. Flow control (break/continue/early-return) uses sentinel exceptions `_BlockBreak`/`_BlockContinue`/`_BlockReturn` propagated to the enclosing handler. Procedures registered at `execute()` start (so definitions can appear after calls), with a `_scope_stack` of param frames over globals — `variables_set`/`variables_get` check the top frame first then fall through to `self.variables` (parameter isolation without polluting globals).

### MCP Server (`restai/mcp.py`)

Optional internal MCP server exposing user projects as MCP tools. FastMCP over SSE at `/mcp/sse`. Off by default — enable via `MCP_SERVER=true` or admin settings (requires restart). Tools: `list_projects`, `query_project`. Bearer API key per request; users see only their assigned projects, admins see all.

### Evaluation Framework (`restai/eval.py`, `restai/routers/evals.py`)

Datasets (question + optional expected answer), runs with selectable metrics, score tracking. Endpoints under `/projects/{id}/evals/...`. Metrics via DeepEval: `answer_relevancy`, `faithfulness` (RAG), `correctness`. Runs execute in `BackgroundTasks`, calling `question()` directly (skips logging/budget).

Tables: `eval_datasets`, `eval_test_cases`, `eval_runs`, `eval_results` (one row per metric per test case). Frontend at `/project/:id/evals`.

### Prompt Versioning (`prompt_versions` table)

Every system prompt change is auto-versioned. `edit_project` in `database.py` creates a `PromptVersionDatabase` row on prompt changes.

Endpoints: `GET /projects/{id}/prompts`, `GET /projects/{id}/prompts/{versionId}`, `POST /projects/{id}/prompts/{versionId}/activate`. Eval runs link via `prompt_version_id` on `EvalRunDatabase`. Frontend: collapsible Version History panel + version chips on eval runs.

### Rate Limiting (`restai/budget.py`)

Per-project request rate limit via `ProjectOptions.rate_limit` (req/min, `None` = unlimited). `check_rate_limit()` runs alongside `check_budget()` before every inference. HTTP 429 when exceeded. Counts from `OutputDatabase` (indexed by `project_id`/`date`).

### Latency Tracking

Every inference logs `latency_ms` in `OutputDatabase`. Timing starts at the router endpoint, passed through `helper.py` to `log_inference`. `/projects/{id}/tokens/daily` includes `avg_latency_ms`. Frontend chart + stat card in `ProjectTokens.jsx`.

### Vector stores (`restai/vectordb/`)

ChromaDB (default) or Redis. Per-project. ColBERT and LLM-based reranking. ChromaDB `_client_cache` reuses `PersistentClient` per path to avoid SQLite lock contention with multiple workers.

### Home Dashboard (`frontend/src/app/views/dashboard/`)

Full-width: 6 stat cards (Projects, Users, Teams, Tokens, Cost, Avg Latency) → Activity (daily tokens area chart + Activity Pulse with Nightingale rose, 30-day micro heatmap, insight pills) → Distribution (project types/LLM donuts, top LLMs bar) → side-by-side tables (Top Projects, Latest Projects). Recharts for area; ECharts for donuts/rose.

### Project Invitations (`project_invitations` table)

Invite users into projects (must share a team with the project). Same pattern as team invitations.

Endpoints: `POST /projects/{id}/invitations` (member-only, restricted-blocked), `GET /invitations` (team + project, with `type` field), `GET /invitations/count`, `POST /invitations/projects/{id}/accept`, `POST /invitations/projects/{id}/decline`. Frontend: Invite User card in Security tab; `/invitations` page splits the two kinds.

### SSO Auto-Created User Settings

Two global Auth settings:
- `sso_auto_restricted` (default `true`) — auto-created SSO/LDAP users in restricted (read-only) mode
- `sso_auto_team_id` (default empty) — auto-add to team

Applied in `restai/oauth.py` (SSO) and `restai/routers/users.py` (LDAP). Config attrs: `config.SSO_AUTO_RESTRICTED`, `config.SSO_AUTO_TEAM_ID`.

### Restricted Users (`is_restricted` on `UserDatabase`)

Per-user read-only mode. Can view assigned projects + use playgrounds; cannot create/edit projects, manage users/teams, or send project invitations. Enforced via `check_not_restricted(user)` in `restai/auth.py` (called in 14+ project endpoints + invitations endpoint).

### Embeddable Chat Widget (`restai/widget/chat.js`)

Self-contained vanilla JS with Shadow DOM, served at `/widget/chat.js`. Streaming opt-in via `data-stream="true"`. Config from `data-*` attrs. Markdown-lite, typing indicator, conversation memory via chat_id. Project edit Widget tab auto-generates a project-scoped API key.

### Knowledge Base Sync (`restai/sync.py`, `crons/sync.py`)

Sources: URL, S3, Confluence, SharePoint, Google Drive. Each has its own `sync_interval` and `last_sync` to prevent duplicate syncs across workers. Standalone cron uses `Brain(lightweight=True)` to skip tool loading.

### Cron Runner (`crons/runner.py`)

Single entry point — dynamically discovers + runs all `crons/*.py` modules with a `main()`. Modules with `DAEMON = True` (e.g. `slack.py`) are skipped. One crontab entry: `* * * * * cd /path/to/restai && uv run python crons/runner.py`. Drop a `.py` file with `main()` into `crons/` to add a job.

Each cron runs in parallel as an isolated subprocess (slow/hung jobs can't block others) with a 10-min per-job timeout, and takes a per-job `flock` on `.cron-<name>.lock` — if the previous invocation is still running, the next skips that job and leaves the rest alone. DB-backed logging via `CronLogger`; logs at `/admin/cron-logs` (filterable, with "Run Now" button shelling out to runner via `BackgroundTask`).

Slack is now a cron poller (`crons/slack.py`, `slack_sdk.WebClient` + `conversations.history`). Old Socket Mode daemon removed — no `slack_bot.py`, no `slack_app_token`.

Telegram cron-driven (`crons/telegram.py`, long-poll-then-exit). Legacy `TelegramPoller` daemon in `restai/telegram.py` is dead code. Each project's bot also responds to `/chatid` (or `/myid`) — gives admins a one-shot way to fill `telegram_default_chat_id` (used by `send_telegram` builtin tool, since bots can't initiate conversations).

### WhatsApp Business Integration

Per-project WhatsApp Cloud API. **Webhook-driven** — Meta POSTs to `${RESTAI_URL}/webhooks/whatsapp` (`restai/routers/whatsapp_webhook.py`). One shared URL; routing via `entry[0].changes[0].value.metadata.phone_number_id` matched against project's `whatsapp_phone_number_id`.

- **Per-project options**: `whatsapp_phone_number_id`, `whatsapp_access_token`/`whatsapp_app_secret`/`whatsapp_verify_token` (encrypted), `whatsapp_default_to`, `whatsapp_allowed_phone_numbers` (E.164 CSV allowlist).
- **Signature verification** (`restai/whatsapp.py:verify_signature`): HMAC-SHA256 of raw bytes keyed on `whatsapp_app_secret`, constant-time vs `X-Hub-Signature-256`. Must be computed on raw bytes BEFORE JSON parse — whitespace/key-order differences break the digest. Bad sig → 401 + warning log.
- **Webhook ack timing**: always 200 within request — heavy work to `BackgroundTasks`. Meta retries on non-2xx or >10s.
- **Builtin** `send_whatsapp` mirrors `send_telegram`. Constrained by Meta's 24h customer-service window — outside requires pre-approved templates (out of scope).
- **Public URL required**: local dev needs a tunnel. Allowlist strongly recommended in prod.
- **Out of scope (v2)**: inbound media, templates for cold outbound, status callbacks, group chats.

### Project Routines

`ProjectRoutineDatabase` — scheduled messages auto-fired via the normal chat/question pipeline. Fields: `name`, `message`, `schedule_minutes`, `enabled`, `last_run`, `last_result`.

Endpoints: `GET/POST/PATCH/DELETE /projects/{id}/routines[/{routineId}]`, `POST /projects/{id}/routines/{routineId}/fire`. Execution in `crons/routines.py` — `asyncio.wait_for` per routine with 300s timeout (so a hung MCP call can't stall the job); the runner's outer 600s is a second safety net. The loop `continue`s on every exception so one broken routine never blocks the rest. Frontend: Routines tab + curl card for the fire endpoint.

### Memory Bank (project-wide conversation context)

Agent-only opt-in via `ProjectOptions.memory_bank_enabled`. Every conversation contributes an LLM summary to a shared bank (`ProjectMemoryBankEntryDatabase` / `project_memory_bank_entries`); rendered bank prepends to system prompt of every chat — context across users and sessions.

- **Source**: `OutputDatabase` rows. Authoritative across workers, survives Redis TTLs. Redis agent2 sessions NOT used (not enumerable per project).
- **Summaries via System LLM**. Without one, cron is no-op.
- **Cron** `crons/memory_bank.py` — every minute. Skips conversations idle <10 min. Per-conversation summaries upserted by `chat_id`, then runs compression ladder.
- **Compression ladder** in `restai/memory_bank.py:compress_entries`: `conversation` >1 day → `day`; `day` >7 days → `week`; `week` >30 days → `month`. If still over budget, deletes oldest until within `memory_bank_max_tokens`. `COMPRESSION_HEADROOM` (1.25) avoids burning System LLM tokens on tiny overshoots.
- **Injection** at `agent.py:_augment_system_prompt_with_memory_bank` — prepends before `_build_runtime`. Failures degrade silently.
- **Privacy**: every project member sees summaries from every other member. Form shows a warning Alert when on.

### Cron Logs

`CronLogDatabase` — one row per runner invocation per job. Fields: `job`, `status` (success/error/warning), `message`, `details` (traceback), `items_processed`, `duration_ms`, `date`. Written by `CronLogger` (`restai/cron_log.py`) — instantiated at top of `main()`, calls `info()`/`warning()`/`error()`, `finish()` at end. `__del__` is a safety net if `finish()` was never called.

Admin: `/admin/cron-logs` — filter by job/status, expand row for full message + traceback, **Run Now** kicks the runner on-demand (subprocess so event loops/DB stay clean), **Purge** wipes the table.

### File Attachments in Chat/Question

`QuestionModel` and `ChatModel` accept optional `files: list[FileAttachment]` (max 10), each `{name, content (base64), mime_type?}`. For agent projects, `_upload_files_and_augment_prompt` (`restai/projects/agent.py`) decodes bytes, calls `DockerManager.put_files(chat_id, [...])` to drop into `/home/user/uploads/` via `put_archive` on a tar stream, then appends a manifest to the user prompt so the LLM picks up the terminal-tool workflow. Container persists across same-chat messages.

Docker required — sandbox-disabled appends a note instead of failing. Questions (stateless) use ephemeral `chat_id` so the sandbox spins for the one call.

Frontend: paperclip button in `ChatPanel.jsx` (agent-only). 20 MB/file, 10 files/message, base64 in same JSON body.

### Agent-Created Tools & Docker Sandbox

Agents create Python tools at runtime via builtin `create_tool` (`restai/llms/tools/create_tool.py`). Stored in `ProjectToolDatabase` (project-scoped), test-executed in Docker before save, auto-loaded by `_build_runtime` on every chat. Each has `enabled` toggle.

Docker lifecycle: `restai/docker_manager.py` — per-chat containers reused across tool calls; idle cleanup by `crons/docker_cleanup.py` (older than `docker_timeout` seconds). Script execution uses base64-piped `python3 -c`; uploads use `base64 -d | tar xf -` via `exec_run` because `put_archive` is blocked on read-only rootfs.

Sandbox: 1 GiB tmpfs on `/tmp` and `/home/user`, 512 MiB RAM, 0.5 CPU, auto-remove on stop. Settings: `docker_enabled`, `docker_url`, `docker_image`, `docker_network`, `docker_read_only`.
- **`docker_read_only`** (default `true`) — rootfs read-only; blocks pip. Off only when you need pip; ephemeral either way.
- **`docker_network`** (default `none`) — network isolation; `bridge` for outbound (pip, external APIs).

Changing either calls `brain.init_docker_manager()` (shuts down old + cached containers, rebuilds). Existing containers stopped via `docker_cleanup.py` cron so the next chat lands in a fresh container matching settings.

**Image recommendation:** Debian-slim (`python:3.12-slim`) is default. Avoid Alpine — musl libc breaks manylinux wheels (pandas/numpy compile from source, slow + tmpfs-busting).

Read-only Tools view on project main page (`ProjectInfoTools`); editable Agent-Created Tools section in project edit (`ProjectEditTools`).

### Agentic Browser

Per-chat Playwright/Chromium container driven from an in-container HTTP server. Admin-gated. Nine `browser_*` builtins: `goto`, `content`, `click`, `fill`, `select`, `screenshot`, `wait`, `download`, `eval`.

- **Lifecycle** — `restai/browser/manager.py:BrowserManager` mirrors `DockerManager`: per-chat-id labels, orphan lookup, idle cleanup via `crons/browser_cleanup.py`. Default image `mcr.microsoft.com/playwright/python:v1.48.0-jammy`. Port 7000 published on `127.0.0.1:<random>`; host port read via `container.attrs["NetworkSettings"]["Ports"]`.
- **Micro-server** — `restai/browser/micro_server.py` runs in the container (copied via `put_archive`). Pure stdlib + `playwright.sync_api`. Module-level `BrowserContext` persists cookies/localStorage across calls within a chat.
- **Storage state** — `BrowserManager.save_storage_state(project_id, domain, state)` writes cookies to Redis (or in-process fallback) keyed by `(project_id, domain)`, 30-day TTL. Next chat can `load_storage_state` and skip login.
- **Domain allowlist** — `ProjectOptions.browser_allowed_domains` (CSV, `*.example.com` suffix). `browser_goto` refuses non-listed; empty = unrestricted (risky).
- **Secrets vault** — `project_secrets` table (migration 040, Fernet-encrypted). CRUD via `/projects/{id}/secrets` + Secrets tab. `browser_fill(selector, secret_ref="portal_pw")` resolves plaintext server-side (`DBWrapper.resolve_project_secret`) — value never enters LLM context, inference log, or audit log.
- **`browser_eval` opt-in** — `ProjectOptions.browser_allow_eval` default off (prompt-injected page could exfil cookies).
- **Screenshots** reuse Brain image cache — returns `![](/image/cache/<id>.png)` that `_drive_runtime` guarantees lands in the final answer.

### System LLM & AI Assistants

Global "System LLM" (Admin → Settings → System LLM) backs platform-level AI helpers. When unset, assistants are hidden.

- **Smart Search** (`restai/utils/search_ai.py`, `SmartSearch.jsx`) — NL search across projects/users/teams/llms/embeddings. Whitelist-based schema, LLM emits JSON spec, server validates + runs RBAC-scoped SQLAlchemy queries.
- **System Prompt Generator** (`restai/utils/prompt_ai.py`) — per-project "Generate with AI" button.
- **Blockly Workspace Generator** (`restai/utils/blockly_ai.py`) — block IDE generates from prompt; emits workspace JSON from `BLOCK_REFERENCE` schema.

`Brain.get_system_llm()` reads `system_llm` setting from DB on every call (multi-worker config changes immediate).

### WordPress Plugin (`wordpress/restai/`)

Full WP plugin. Each capability maps to a dedicated RESTai project (auto-provisioned on first connect); a widget key is lazily minted on the support bot project and stashed in `restai_widget_credentials`.

- Settings page: URL + Bearer key + team + image-generator picker; "Auto-provision starter projects" button.
- Gutenberg sidebar: body / excerpt / SEO meta / featured image / translations. Server-rendered content-generator block + `[restai_generate]` shortcode with transient caching.
- Analytics page mirrors `/statistics/summary` + `/statistics/daily-tokens`; "Push all to Support Bot" force-syncs knowledge.
- All `/projects/{id}/...` calls use integer id from `restai_project_map`. `sync_system_prompt` PATCHes after creation (`ProjectModelCreate` doesn't accept `system`).

Bootstrap in `includes/class-restai.php`, Icon helper in `includes/class-restai-icon.php`, WP REST namespace `restai/v1` in `includes/class-restai-rest.php`. WP 6.9, PHP 7.4+, GPL-2.0+. Local dev via `wordpress/docker-compose.yml` (WP 6.6 + MariaDB, plugin bind-mounted).

### Mobile pairing (Android client under `android/`)

Project-scoped companion apps pair via QR from the project's **Mobile** tab. Platform-neutral plain-JSON payload. Android in `android/`; future iOS in sibling `ios/`.

**Pairing** — `POST /projects/{id}/mobile/enable` mints a read-only project-scoped API key, returns plaintext + JSON QR: `{host, project_id, project_name, api_key}`.

- Endpoints (`restai/routers/projects.py`, Mobile section): `GET/POST /projects/{id}/mobile{/enable,/disable,/regenerate}`.
- Minted `ApiKeyDatabase` row id stashed in `ProjectOptions.mobile_api_key_id`; **regenerate** invalidates all paired phones at once. Disabling deletes the key (cascade 401).
- Plaintext surfaced on every status read while enabled (decrypted from `ApiKeyDatabase.encrypted_key` via `decrypt_api_key`) so QR stays visible across reloads.

**Android** — Kotlin + Compose. `QrScreen` (CameraX + ML Kit) + `ChatScreen` (OkHttp SSE against `/projects/{id}/chat?stream=true`). Credentials in `EncryptedSharedPreferences`. 401 clears key and drops back to QR. Build: `cd android && ./gradlew assembleDebug`.

### Onboarding Checklist (`frontend/src/app/views/dashboard/shared/OnboardingChecklist.jsx`)

Home-dashboard card for admins on fresh installs, gated by three auto-detected steps: add an LLM, attach to a team, create a project. Auto-hides when done; dismissible via `localStorage["restai_onboarding_dismissed"]`. QA override: `?onboarding=force`.

### Security Hardening

Accumulated fixes worth remembering:

- **Security headers** (`cors_middleware` in `restai/main.py`) — `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY` + CSP on admin paths. Widget paths exempt from frame-options + CSP so embeds work.
- **Settings secrets encrypted at rest** — `SETTINGS_ENCRYPTED_KEYS` (`utils/crypto.py`) covers `proxy_key`, `redis_password`, all `sso_*_client_secret`. `DBWrapper.upsert_setting` encrypts on write; getters decrypt on read. Rows are `expunge`d before mutation so plaintext can't commit back.
- **Per-project `redact_inference_logs` option** — strips OpenAI/Slack/Bearer tokens, long alphanumerics, `user:pass@host` patterns from question/answer/system_prompt/context before persisting. Default off.
- **Impersonation audit trail** — `/auth/impersonate/{username}` and `/auth/exit-impersonation` write `IMPERSONATE_START`/`IMPERSONATE_END` via `audit._log_to_db`.
- **LDAP cookie** — `httponly=True`, `samesite="strict"` (httponly was missing).
- **Salted API-key / recovery-code hashing** — `hash_api_key` / `hash_recovery_code` use PBKDF2-SHA256 + random 16-byte salt with `$pbkdf2$` prefix. `verify_*` accepts both new and legacy SHA256 for migration.
- **Widget restricted-user block** — `get_widget_from_request` rejects 403 if widget creator is restricted-and-not-admin.
- **Frontend 401 handling** — sets `sessionStorage["session_expired"]="1"` and redirects to `/admin/login`; login page shows "Your session has expired".
- **SSRF guard on `crawler_classic` + 10s timeout** — resolves hostname through `restai.helper._is_private_ip` and refuses loopback / RFC1918 / link-local (closes AWS IMDS exfil). Same guard applied to `restai/sync.py:_sync_url`.
- **Userland tool loader pinned to install root** — `tools.py:load_tools` reads from `<install_root>/tools` (not cwd-relative `./tools`). Skips cleanly when missing. Closes a code-exec surface from unexpected CWDs.
- **Per-key audit trail on settings** — `patch_settings` writes `audit._log_to_db(actor, "SETTING", "settings/<key>:<status>", 200)` per changed key. Secret keys get `:secret_changed` (values NEVER recorded); non-secret keys include 32-char fingerprint.
- **Password-age tracking** — `users.password_updated_at` stamped on every `create_user`/`update_user` (migration 041). `password_max_age_days` (default 0 = disabled) drives a soft warning in `/auth/login` response (`password_warning`). Never blocks. Legacy NULL rows never warn.
- **Per-API-key monthly quotas** — `api_keys.token_quota_monthly` (NULL = unlimited), `tokens_used_this_month`, `quota_reset_at` (migration 042). `restai/budget.py:check_api_key_quota` raises 429 when hit; rolls over lazily on first check after `quota_reset_at` (1st-of-next-month UTC). `record_api_key_tokens` in `log_inference` bumps. Admin: `PATCH /users/{u}/apikeys/{id}`.
- **API errors carry field-level metadata** — `ApiError` exposes `fieldErrors` (field → message), parsed from 422 `detail` via `_extractFieldErrors`. Forms mark TextField with `error` + `helperText`. `ProjectEdit.jsx` plumbs via `fieldErrors` + `clearFieldError` props; `memory_bank_max_tokens` is the wired demo. `options.<name>` accepted so nested locs (`["body","options","k"]`) light up the right field.
- **Contextual chat error messages** — `ChatPanel.jsx:formatChatError(status, detail)` maps 402 → "budget exhausted", 429 → "rate limit" (quota-specific when detail mentions quota), 413 → "too large", 503/502 → "overloaded". Used by both streaming (`onopen` captures status, hands to `onerror`) and non-streaming (`catch (e)` consumes `e.status`+`e.detail`). 401/402/413/429 also toast.
- **JWT secret strength check** — startup WARNs when `RESTAI_AUTH_SECRET` is empty/<32 chars/known-weak. Result lands on `fs_app.state.auth_secret_weak`, surfaced to UI via `auth_secret_weak` in `/setup`. `_ensure_env_secret` writes a 64-byte urlsafe default on first boot — this catches legacy installs and copy-pasted dev envs.
- **Client-side validation on project-edit numerics** — `projectOptionValidators.js` exports `clientValidators` (rate_limit/k/score/memory_bank_max_tokens/cache_threshold) + `makeErrorFor(fieldErrors, state)`. ProjectEdit tabs consume so typos light up inline without 422 round-trip. Server `ApiError.fieldErrors` still wins on save.

### Project Template Library

Separate from project-to-project clone. Publishes a project's state (system prompt + options + Blockly workspace) as a **template** with three-tier visibility: **private** (creator), **team** (`team_id` members), **public** (any logged-in user).

- **Table**: `project_templates` (`ProjectTemplateDatabase`, migration 043). Fields: `name`, `description`, `project_type`, `suggested_llm`, `suggested_embeddings`, `system_prompt`, `options_json`, `blockly_workspace`, `visibility`, `creator_id`, `team_id`, `created_at`, `use_count`.
- **Router**: `restai/routers/templates.py`. Endpoints: `POST /projects/{id}/publish-template`, `GET /templates` (visibility-filtered), `GET /templates/{id}`, `PATCH/DELETE /templates/{id}` (owner-only), `POST /templates/{id}/instantiate`.
- **Instantiation**: caller picks target `team_id` + `llm` + `embeddings` (LLM access is team-scoped, so `suggested_llm` may not be available). New project via `DBWrapper.create_project` + options/system-prompt replay; `use_count` incremented.
- **Frontend**: `Library.jsx` adds a "Community Templates" section with **Use Template** dialog. `ProjectInfo.jsx` adds a **Save as template** icon next to **Clone**.
- **Visibility vs. clone**: clone copies a live project (eval datasets, prompt versions, etc.). Templates are a lightweight config snapshot.

### Inline Content Moderation Tool

Agent-callable builtin: `moderate_content(text, policy="default")` (`restai/llms/tools/moderate_content.py`). Different from `guard_output` (which runs a guard project on the final response) — this is mid-flow so the agent can retry/rephrase/abort.

- **Detection** — regex-based, no deps: credit card / email / phone / US SSN / IPv4 / API-key shapes (`sk-...`, `xox[baprs]-...`, `AKIA...`, `gh[pousr]_...`). Plus short prompt-injection check ("ignore previous instructions", "system prompt", "you are now").
- **Per-project options** — `moderation_blocklist` (CSV of literal substring terms, case-insensitive) + `moderation_redact_pii` (default `true`). When on, flagged spans replaced with `[REDACTED:<type>]` in the `SANITIZED:` block.
- **Return** — `"OK: no issues found"` or `"FLAGGED: <reasons>\nSANITIZED: <text>"`. String, not JSON.
- **Degrades gracefully** — works without project context. DB hiccups never raise into the agent.

### Bulk File Ingest Queue

RAG-only — uploads decoupled from request/response so a 500-page PDF doesn't time out the admin.

- **Table**: `bulk_ingest_jobs` (migration 044). Fields: project_id, filename, mime_type, size_bytes, file_path, method/splitter/chunks, status (`queued`/`processing`/`done`/`error`), error_message, documents_count, chunks_count, timestamps.
- **Staging dir**: `$TMPDIR/restai_bulk_ingest/`. Each upload is a tempfile prefixed with project id. Cleaned up on completion or delete.
- **Router** (`restai/routers/bulk_ingest.py`): `POST /projects/{id}/ingest-bulk` (multipart, 202 + queued ids), `GET /projects/{id}/ingest-bulk`, `DELETE /projects/{id}/ingest-bulk/{jobID}`.
- **Cron** (`crons/bulk_ingest.py`): claims one queued row at a time (`status=queued` → `processing` in single txn), dispatches via auto_ingest → markitdown → docling → classic fallback chain, finalizes with a fresh DB session. Tempfile deleted regardless.
- **UI**: `ProjectEditKnowledge.jsx` adds Bulk File Ingest section atop Knowledge tab with multi-file uploader and status table polling 5s.
- **Scope**: queued jobs with missing staged file auto-error on next tick. Agent / block projects reject with 400.

### Routine Execution Log

Per-fire history table (`routine_execution_log`, migration 045) alongside `ProjectRoutineDatabase`. Legacy `last_result` is a single string — can't show flaky-routine patterns. New table keeps `status` (ok/error), `result` (truncated answer or error), `duration_ms`, `manual` (true for admin-triggered, false for cron), `created_at`. Cascade-deletes with parent.

- **Cron**: writes one row per fire. Best-effort — log row failures never break the tick.
- **Manual fires**: also write a row with `manual=true`.
- **History endpoint**: `GET /projects/{id}/routines/{routineID}/history?limit=50` (newest first).
- **UI**: `ProjectEditRoutines.jsx` adds a History icon button → dialog with per-fire table.

### Agent Tool-Call Trace

Per-tool-call timeline captured during `agent._drive_runtime` and persisted to `OutputDatabase.tool_trace` (migration 046). JSON list of `{tool, args, latency_ms, status, error?}`. Latency between LLM `assistant` event (containing `ToolUseBlock`) and matching `tool_result` event. Status best-effort: tools following `"ERROR: ..."` / `"OK: ..."` convention auto-classify; rest default to `ok`.

- **Persistence**: `tools.py:log_inference` writes `tool_trace` if present, gated by `logging` toggle.
- **UI**: `ProjectLogs.jsx` renders Tool Trace panel under each expanded log row — one row per call with tool chip, truncated args, error block, latency. Error rows get a subtle red wash.
- **Empty trace**: agents that didn't use tools (or non-agent projects) leave `tool_trace=NULL` — panel omitted.

### Per-Project Analytics Drill-Down

`GET /projects/{id}/analytics/conversations` returns summary + daily + hourly + top_users, plus:
- `status_breakdown` — `[{status, count}]` grouped by `OutputDatabase.status` (success/error/budget/quota/rate_limit/etc.)
- `latency_buckets` — fixed histogram (`0-100ms`, `100-500ms`, `500ms-2s`, `2-10s`, `10s+`)
- `llm_breakdown` — per-LLM `{llm, messages, tokens, cost}` (useful for projects that rotated models or use a fallback chain)

Frontend `ProjectAnalytics.jsx` renders the three as a Grid row at the bottom (outcome mini-table + latency bar chart + LLM table).

### Project Event Webhooks

Per-project outbound HTTP webhooks for events SMBs typically wire into Zapier/n8n/CRMs. Shape: HTTPS POST with JSON body, `X-RESTai-Event` header, optional `X-RESTai-Signature: sha256=<hex>` (HMAC-SHA256 of raw body keyed on per-project secret).

- **Per-project options**: `webhook_url`, `webhook_secret` (encrypted via `PROJECT_SENSITIVE_KEYS`), `webhook_events` (CSV mask; empty = all).
- **Supported events** (`restai/webhooks.py:SUPPORTED_EVENTS`): `budget_exceeded`, `sync_completed`, `eval_completed`, `routine_failed`, `test`.
- **Hook points**: `restai/budget.py:check_budget` fires before raising 402; `crons/sync.py` after each per-source sync; `crons/routines.py` when a routine raises; `restai/eval.py` after a run completes. Every emit wrapped in `try/except` so a webhook failure can NEVER crash inference/cron/eval.
- **SSRF guard** — same `restai/helper.py:_is_private_ip` check applied to webhook URLs. Loopback/RFC1918/link-local refused.
- **Fire-and-forget** — POSTs run in daemon thread with 10s timeout. Non-2xx logged but never raised.
- **Admin Test endpoint** — `POST /projects/{id}/webhooks/test` (`restai/routers/webhooks.py`) fires synthetic `test` event. "Send Test Event" button in Integrations tab.

### Email + SMS notification tools

Two more outbound-notification builtins next to `send_telegram` / `send_whatsapp`:

- **`send_email`** (`restai/llms/tools/send_email.py`) — stdlib `smtplib`. Project options: `smtp_host`, `smtp_port` (default 587 STARTTLS, 465 → implicit TLS), `smtp_user`, `smtp_password` (encrypted), `smtp_from`, `email_default_to`. Falls through to plaintext if relay doesn't advertise STARTTLS.
- **`send_sms`** (`restai/llms/tools/send_sms.py`) — Twilio REST API, basic-auth with sid+token. Project options: `twilio_account_sid`, `twilio_auth_token` (encrypted), `twilio_from_number`, `sms_default_to`. Splits at 1600-char Twilio body limit.

Both pull from encrypted options blob and surface relay/provider error verbatim on failure (no exceptions leak).

### Custom Team Branding

`TeamBranding` model: `primary_color`, `secondary_color`, `logo_url`, `app_name`, `welcome_message`. Stored as JSON in `TeamDatabase.branding`. Multi-team users select preferred via `UserOptions.preferred_team_id`.

### Two-Factor Authentication (TOTP)

TOTP via `pyotp`, Fernet-encrypted secrets in `UserDatabase.totp_secret`, SHA256-hashed recovery codes. JWT temp tokens for verify (5-min, `purpose: "totp_verify"`). Platform-wide enforcement via `enforce_2fa` setting. Login page integrates TOTP step + recovery code toggle.

## Input Validation

Names in URL paths (project, username, team, LLM, embedding) validated with `validate_safe_name` — only `[a-zA-Z0-9._:-]`. Enforced at Pydantic level for create models and at router level for LLM/embedding creation (since `LLMModel`/`EmbeddingModel` are dual-use input/output).

Enum fields use `Literal`: `privacy` ("public"/"private"), `type` ("rag"/"agent"/"block"), `splitter` ("sentence"/"token").

Integer Query/Form params have `ge`/`le` bounds. File uploads sanitized via `sanitize_filename` (strips path + null bytes).

## Testing

`FastAPI.TestClient` with Basic auth: `auth=("admin", RESTAI_DEFAULT_PASSWORD)`. Inline fixtures in `conftest.py` (`sys.setrecursionlimit(20000)`, pre-builds Pydantic schemas). Tests create real resources against a live app instance. Key files:
- `tests/test_input_validation.py` — name/enum/valid-value
- `tests/test_security.py` — RBAC, cross-team, empty/whitespace name rejection
- `tests/test_users.py`, `tests/test_teams.py`, `tests/test_llms.py`, `tests/test_embeddings.py` — CRUD
- `tests/test_mcp.py` — MCP auth (Bearer), access control, tool registration
- `tests/test_rate_limit.py` — rate limit enforcement, disable/enable, 429
- `tests/test_settings.py` — settings CRUD, SSO defaults, config sync
- `tests/test_restricted.py` — restricted permissions
- `tests/test_totp.py` — TOTP setup, verify, recovery codes
- `tests/test_project_invitations.py` — send/accept/decline, team validation, dup prevention
- `tests/test_comments.py` — project comments

`tests/test_projects.py` may fail if no LLMs configured (pre-existing).

## Key env vars

`RESTAI_DEV`, `RESTAI_GPU`, `RESTAI_DEFAULT_PASSWORD`, `RESTAI_URL` (OAuth redirects), `REDIS_HOST`/`REDIS_PORT`, `CHROMADB_HOST`/`CHROMADB_PORT`, `MCP_SERVER`, LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc). Full list in `restai/config.py`.

Runtime-tunable settings (proxy, SSO, Docker, MCP, system LLM, knowledge retention, 2FA, branding, GUI-managed everything) live in the `settings` DB table. Consumers read via `restai.config.<NAME>` — `restai/config.py` defines a module-level `__getattr__` that resolves any GUI-managed key by querying the DB on every access (`_GUI_SETTING_ATTRS` is the authoritative `config_name -> (db_key, type, default)` map).

**There is no in-process mirror anymore.** Earlier versions kept `_CONFIG_ATTR_MAP` and re-`setattr`'d each updated value back onto `restai.config` after every PATCH /settings; that mutation only landed in the worker that handled the request, so multi-worker uvicorn deployments saw stale values everywhere else (`POST /settings/docker/test` failing intermittently was the canary). DB-direct read-through is the only correct pattern.

**Env-var support dropped for GUI-managed keys.** Bootstrap-only env vars (POSTGRES_HOST, RESTAI_FERNET_KEY, RESTAI_AUTH_SECRET, RESTAI_DEV, etc.) still live as module-level constants because they're needed before the DB is reachable; everything else goes in the Settings page. Existing deployments already have old env values seeded in the DB.

**Bare-name lookup gotcha inside `config.py`:** module `__getattr__` only fires for `module.X`-style access from elsewhere. Inside `restai/config.py`, a bare `REDIS_HOST` is looked up in module globals (no descriptor) and raises `NameError`. When a function in `config.py` needs a GUI setting, do `import restai.config as _cfg` and use `_cfg.REDIS_HOST`. See `build_redis_url()` and `load_oauth_providers()`.
