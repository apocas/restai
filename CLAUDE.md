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
make test             # uv run pytest tests
pytest tests/test_projects.py -v
pytest tests/test_projects.py::test_create_project
make coverage         # pytest with coverage (term-missing + htmlcov/)
make frontend-test    # Jest via react-scripts, with coverage (frontend/src/**/*.test.js*)
cd frontend && npm test  # Jest watch mode

# Code quality
make lint             # ruff check . (zero-violation baseline — CI enforces it)
make code             # ruff check . --fix
make format           # ruff format . (opt-in; not yet applied repo-wide)

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

`/projects`, `/users`, `/teams`, `/llms`, `/embeddings`, `/tools`, `/direct`, `/statistics`, `/settings`, `/auth`, `/evals`, plus GPU-only `/image` and `/audio`.

Sub-routes on `/projects/{id}/*`: `/widgets`, `/routines`, `/tools`, `/prompts`, `/evals`.

**Path params on `/projects/{projectID}/...` are typed `int`** — pass numeric id, not project name (root cause of past 422 regressions).

### Models (`restai/models/`)

- `models.py` — Pydantic schemas. Input validation: `validate_safe_name` (regex `^[a-zA-Z0-9._:-]+$`), `Literal` enums (`privacy`, `type`, `class_name`), `max_length`, `ge`/`le` bounds, `sanitize_filename` for uploads.
- `databasemodels.py` — SQLAlchemy ORM.

Key relationships: Users ↔ Projects (m2m), Users ↔ Teams (members + admins), Teams → Projects/LLMs/Embeddings.

### Database

SQLite default (`restai.db`); Postgres via `POSTGRES_HOST`; MySQL via `MYSQL_HOST`. Pool: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`. Migrations via Alembic.

**Init flow** (`database.py`): tables → admin user (`RESTAI_DEFAULT_PASSWORD`) → default team (admin added as member + admin). No LLMs/embeddings are seeded — add them via `/admin` or `POST /llms`.

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

**Deleting an LLM reassigns dependents.** `GET /llms/{id}/usage` lists projects that reference the LLM — as their main `llm` column or via the `eval_llm`/`rerank_llm` option overrides (`db.get_llm_usage`; the `guard` column is a guard *project* id, not an LLM, so it's excluded). `DELETE /llms/{id}` refuses with 409 if any project still references it; the caller must pass `?reassign_to=<name>` and `db.reassign_llm` repoints every reference (main + overrides, preserving other option keys) before the row is deleted — so no project is ever left pointing at a missing model. Frontend `llms/List.jsx` checks usage on the delete click and, when non-zero, opens a reassign dialog (replacement `<Select>` + affected-project list) instead of the plain confirm.

**Guard references are by project ID.** `ProjectDatabase.guard` (input guard) and the `guard_output` key in `ProjectOptions` (output guard) store the guard **project's id** — stable across renames (migration `060` converted legacy name values → ids; `guard` stays a `String` column holding the id, `guard_output` stays the id in the options JSON — data-only, no cross-backend column-type/FK churn on the heavily-referenced `projects` table). `Guard.__init__` resolves numeric refs via `get_project_by_id`, with a name-lookup fallback for any legacy value. On guard-project **delete**, `db.delete_project` calls `db.clear_guard_references(id)` to null dependents' `guard`/`guard_output` (app-side stand-in for an FK `SET NULL`, since `guard_output` lives in JSON). Display: the project GET response carries read-only `guard_name`/`guard_output_name` (resolved in `core.py:_attach_guard_names`) so the info tabs show the name; the edit picker (`ProjectEditSecurity.jsx`) stores the id and labels by name. The `log_guard_event` audit row still records the readable guard-project name.

### OpenAI-Compatible Direct Access (`restai/routers/direct.py`, `restai/utils/openai_compat.py`)

`/v1/*` endpoints let external OpenAI SDKs/tools drive any platform LLM. Bearer API key or JWT cookie auth (`get_current_username`); `check_not_restricted` + `check_api_key_quota` (per-key monthly token quota → OpenAI-style 429) + team/budget resolution (`integrations/direct_access.py`) run before inference; usage logged to `OutputDatabase` (project_id NULL) and billed from the LLM's per-1M rates + counted against the key quota.

- **Endpoints**: `POST /v1/chat/completions`, `POST /v1/completions` (legacy), `POST /v1/embeddings` (+ `dimensions`/`encoding_format:base64`/`user`), `GET /v1/models` + `GET /v1/models/{id}`, `POST /v1/moderations`, plus `/v1/images/generations` (`image.py`) and `/v1/audio/transcriptions` (`audio.py`). Non-OpenAI helper: `GET /direct/models` — lists LLMs, embeddings, and generators. Generators come from the **DB config** (`image.dispatch.list_available_generators` / `audio.dispatch.list_available_stt_models`), NOT `brain.get_generators()` (which is only the loaded *local-worker* FunctionTools). Remote generators (OpenAI/Google/Deepgram/AssemblyAI and OpenAI-compatible imports) dispatch through `restai/{image,audio}/providers/*` and need **no GPU**, so they're listed and served on GPU-less deployments; only `class_name == "local"` workers require GPU (`Brain.get_generators`, which returns `[]` when GPU is off — see `brain.py` where `self.generators`/`self.audio_generators` default to `[]` and are only populated when `RESTAI_GPU`).
- **Two execution paths** (`openai_compat.py`): **native passthrough** when the LLM class is OpenAI-wire-compatible (`OpenAI`/`OpenAILike`/`Grok`/`vLLM`/`AzureOpenAI` — `is_openai_native`) forwards the request body to the provider's upstream endpoint (`resolve_upstream` reads base_url+api_key+model from the LLM options) and streams raw SSE back — full fidelity (real usage, logprobs, streaming tool-call deltas, `n`, `logit_bias`, response_format json_schema). For streaming it forces `stream_options.include_usage` upstream to capture usage for billing. Every other provider uses the **translated fallback** (`convert_messages`/`build_kwargs` → `llm.chat`/`stream_chat` → translate out), improved with real `response.raw.usage`, a leading `role` stream chunk, and per-tool-call `index`.
- **Error envelope**: `restai/middleware.py` reshapes errors on `/v1/*` paths only into OpenAI's `{"error":{message,type,param,code}}` (e.g. 404→`model_not_found`, 402→`insufficient_quota`, 429→`rate_limit_exceeded`); non-`/v1/` paths keep `{detail}`.
- `/v1/moderations` is regex-backed (`llms/tools/moderate_content.py`) — best-effort PII/injection/blocklist, NOT OpenAI's ML taxonomy (standard categories always False; RESTai adds `pii`/`prompt_injection`/`blocklist` extra keys). Out of scope: `/v1/audio/speech` (TTS), `/v1/responses`.

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

### Token Accounting Coverage (`restai/tools.py:log_inference`, `restai/integrations/direct_access.py:log_direct_usage`, `restai/limits/accounting.py`)

Two funnels write `OutputDatabase` rows + bump API-key quota + charge the team wallet: `log_inference` (project chat via `helper.chat_main`) and `log_direct_usage` (`/v1/*` direct). Everything through `chat_main` (RAG, all agent loops, block, widget/mobile, Slack/Telegram/WhatsApp/routines) and the direct endpoints is fully accounted. Additionally accounted (were off the books):
- **Guard checks** — `Guard.verify` returns token counts; `base.py:_account_guard` logs a row against the **guard project** (its own team/LLM) for each input/output guard, so a guarded turn produces multiple rows.
- **Nested project inference** — `search_knowledge` tool (`log_inference(proj, user, result, db)` — the RAG result already carries `tokens`) and the KG-query endpoint (`routers/projects/kg.py`).
- **System-LLM platform helpers** — memory-bank cron (`memory/bank/common.py`), Smart Search, system-prompt + Blockly generators call `accounting.log_platform_usage`, which writes an **attribution-only** row (`team_id`/`api_key_id`/`project_id` NULL → visible in `/statistics` but bills no team). `question` is `(platform:<feature>)`.
- **`accounting.count_usage(response, prompt, answer)`** prefers real provider usage (`openai_compat.usage_from_response`) then tiktoken.
Agent loops that estimate (agent2 restai / llamaindex / openai_agents) fold `tool_trace` (tool round-trip context) into the estimate so multi-step turns aren't undercounted. **The agent2 restai loop now prefers real provider usage** (see "Agent Resilience" — accuracy "high" when every turn reported usage, partial usage floors the estimate at "medium"); its tiktoken fallback additionally folds the **system prompt** (incl. memory-bank injection) and the **full accumulated transcript** (`session.messages`, minus the final answer) into the input estimate — a long multi-turn agent chat on a no-usage provider (e.g. Ollama) otherwise reported only the latest question's tokens. All monotonic (`max` against the old question+trace estimate — only ever adds). **Still off the books by design**: evals (skip logging), image/audio cost (non-token). `check_budget` in `budget.py` is a dead shim (no callers).

### Per-Response Cost (`accounting.attach_cost`)

Every chat response that reports `tokens: {input, output}` also reports `cost: {input, output, total}` (USD) — same math as `log_inference` (`tokens * llm.{input,output}_cost / 1e6`). Attached at the `helper.py` API boundary — the one place all project types + emit paths converge — so it flows through non-streaming (`chat_main` before `return line`), non-resume streaming (`stream_with_logging`), and the resume drain (`_drain_generator_into_session`). `_enrich_final_frame` re-serializes the final `data: {json}\n` SSE frame (RAG/agent stream a pre-serialized string) to inject cost; text-delta frames pass through untouched. `attach_cost` is idempotent (skips if `cost` present), best-effort (pricing lookup failure leaves the response untouched), and yields zero cost for LLM-less block projects. `/v1/*` responses keep OpenAI's `usage` shape (no `cost`) for spec compatibility. Frontend: cost chip in `MessageBubble.jsx` + `PlaygroundLanes.jsx` (tooltip breaks out input/output); `ChatReplayDialog.jsx` rebuilds `cost` from stored `input_cost`/`output_cost` columns. Formatter: `formatCost` in `app/utils/utils.js` (sub-cent aware).

### Latency Tracking

Every inference logs `latency_ms` in `OutputDatabase`. Timing starts at the router endpoint, passed through `helper.py` to `log_inference`. `/projects/{id}/tokens/daily` includes `avg_latency_ms`. Frontend chart + stat card in `ProjectTokens.jsx`.

### Vector stores (`restai/vectordb/`)

ChromaDB (default) or Redis. Per-project. LLM-based reranking. ChromaDB `_client_cache` reuses `PersistentClient` per path to avoid SQLite lock contention with multiple workers.

**Backend health, verified live (see `tests/test_reembed_live.py`, `tests/test_pgvector.py`):**
- **pgvector — `table_name` is NOT the table.** `PGVectorStore` prefixes `data_` itself (`get_data_model`: `tablename = "data_%s" % index_name`), so passing `table_name="data_p{id}"` creates **`data_data_p{id}`**. Every raw-SQL method used to target `data_p{id}` and therefore raised `UndefinedTable` — and `delete()`, being `DROP TABLE IF EXISTS`, silently dropped nothing, so removing a project leaked its whole vector table. Only the llama-index-mediated paths (ingest, retrieval) ever worked, which is why it went unnoticed. `PGVectorDB.physical_table` is the real name; `table_name` is only for the llama-index handoff. The double prefix is kept deliberately — it is the on-disk name in existing deployments. Raw queries go through `_conn()`, which disposes the engine in a `finally` (they previously leaked a pool on every raised query).
- **Weaviate needs `llama-index-vector-stores-weaviate>=1.6.2`.** Earlier releases hard-import `_ContextManagerWrapper`, which `weaviate-client>=4.20` removed; the old `>=0.6` range resolved to 1.6.0 and made the backend fail to import at all (any Weaviate project → 500). Upstream metadata does not catch it — every version declares the same permissive `weaviate-client<5`.
- **Pinecone is the one backend with no local test path** (needs a cloud index). Its `list_all_nodes` is written to the same contract but has never been executed.

`find_vector_db(project)` (`vectordb/tools.py`) maps `project.props.vectorstore` → backend class; a **None/empty** vectorstore (e.g. a RAG project created via the API, where the field is optional) defaults to ChromaDB — same as the frontend create wizard. `find_file_loader` also lives in `vectordb/tools.py` (NOT the legacy `modules/loaders.py`, which only holds the `LOADERS` dict) — import it from there in ingest/sync paths.

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
- **Compression ladder** in `restai/memory/bank/compress.py:compress_entries`: `conversation` >1 day → `day`; `day` >7 days → `week`; `week` >30 days → `month`. If still over budget, deletes oldest until within `memory_bank_max_tokens`. `COMPRESSION_HEADROOM` (1.25) avoids burning System LLM tokens on tiny overshoots. The bank module (`restai/memory/bank/`) is split into `common`/`summarize`/`compress`/`render`/`scheduling`; `restai/memory/search.py` is the per-project memory-search index. Import as `from restai.memory import bank, search`.
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

Sandbox: `docker_memory_mb` RAM (default 512) with a tmpfs of the same size on `/tmp` and `/home/user`, 0.5 CPU, auto-remove on stop. tmpfs pages are charged to the memory cgroup, so the two are deliberately one setting — the old fixed 1 GiB tmpfs under a 512 MiB limit was unreachable and failed as an OOM kill rather than an error. Settings: `docker_enabled`, `docker_url`, `docker_image`, `docker_network`, `docker_read_only`, `docker_memory_mb`.
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

### Mobile pairing (PWA at `/mobile`)

Project-scoped companion app pairs via QR from the project's **Mobile** tab. The native Android client was replaced by a **PWA** (top-level `mobile/`, a separate CRA app served at the URL path `/mobile` — see "Mobile PWA" below). Plain-JSON pairing payload, unchanged.

**Pairing** — `POST /projects/{id}/mobile/enable` mints a read-only project-scoped API key, returns plaintext + JSON QR: `{host, project_id, project_name, api_key}` (`host` from `config.RESTAI_URL`, else request origin).

- Endpoints (`restai/routers/projects/mobile.py`, Mobile section): `GET/POST /projects/{id}/mobile{/enable,/disable,/regenerate}`.
- Minted `ApiKeyDatabase` row id stashed in `ProjectOptions.mobile_api_key_id`; **regenerate** invalidates all paired phones at once. Disabling deletes the key (cascade 401).
- Plaintext surfaced on every status read while enabled (decrypted from `ApiKeyDatabase.encrypted_key` via `decrypt_api_key`) so QR stays visible across reloads.

### Mobile PWA (`mobile/`, served at `/mobile`)

Separate CRA app (NOT part of `frontend/`), built to `mobile/build`, served by the backend exactly like the admin SPA: static mount `/mobile/static` + a `/mobile/{path}` catch-all with index fallback (`restai/app_setup.py` `MOBILE_BUILD_DIR` / `register_static_mounts` / `register_spa`). `make mobile` builds it (also run by `make install`/`make update`; `make clean` wipes `mobile/build`). Real PWA: hand-written `public/service-worker.js` (scope `/mobile/`), `manifest.json`, icons.

- **Pairing** (`mobile/src/Pair.jsx`): `html5-qrcode` camera scan + manual paste fallback; validates via `GET {host}/auth/whoami` (Bearer) before saving creds to `localStorage` (plaintext — NOT encrypted-at-rest like the old Android EncryptedSharedPreferences).
- **Chat** (`mobile/src/Chat.jsx` + `api.js`): `POST {host}/projects/{id}/chat` via `@microsoft/fetch-event-source`, Bearer key, body `{question, stream, id?, image?, files?}`. SSE: `{text}` deltas → `{answer,id}` final → `event: close`; ignores `tool_call_*`/`plan` frames; strips `<think>…</think>`. Markdown via react-markdown (GFM + sanitized raw HTML); inline images on the paired host fetched with the Bearer header → object URL. Conversation memory via `id`; ephemeral history; 401/403 → clear creds → back to pairing.
- **Same-origin constraint**: `/projects/.../chat` and `/auth/whoami` have NO CORS headers (only `/widget/` does — `restai/middleware.py`), so the PWA must be served from the same origin as the QR `host` (the normal single-instance deployment). Keep `RESTAI_URL` matching the public origin.

### Onboarding Checklist (`frontend/src/app/views/dashboard/shared/OnboardingChecklist.jsx`)

Home-dashboard card for admins on fresh installs, gated by three auto-detected steps: add an LLM, attach to a team, create a project. Auto-hides when done; dismissible via `localStorage["restai_onboarding_dismissed"]`. QA override: `?onboarding=force`.

### Security Hardening

Accumulated fixes worth remembering:

- **Security headers** (`cors_middleware` in `restai/main.py`) — `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY` + CSP on admin paths. Widget paths exempt from frame-options + CSP so embeds work.
- **Settings secrets encrypted at rest** — `SETTINGS_ENCRYPTED_KEYS` (`utils/crypto.py`) covers `redis_password`, all `sso_*_client_secret`. `DBWrapper.upsert_setting` encrypts on write; getters decrypt on read. Rows are `expunge`d before mutation so plaintext can't commit back.
- **Per-project `redact_inference_logs` option** — strips OpenAI/Slack/Bearer tokens, long alphanumerics, `user:pass@host` patterns from question/answer/system_prompt/context before persisting. Default off.
- **Impersonation audit trail** — `/auth/impersonate/{username}` and `/auth/exit-impersonation` write `IMPERSONATE_START`/`IMPERSONATE_END` via `audit._log_to_db`.
- **LDAP cookie** — `httponly=True`, `samesite="strict"` (httponly was missing).
- **Salted API-key / recovery-code hashing** — `hash_api_key` / `hash_recovery_code` use PBKDF2-SHA256 + random 16-byte salt with `$pbkdf2$` prefix. `verify_*` accepts both new and legacy SHA256 for migration.
- **Widget restricted-user block** — `get_widget_from_request` rejects 403 if widget creator is restricted-and-not-admin.
- **Frontend 401 handling** — sets `sessionStorage["session_expired"]="1"` and redirects to `/admin/login`; login page shows "Your session has expired".
- **SSRF guard on `crawler_classic` + 10s timeout** — resolves hostname through `restai.helper._is_private_ip` and refuses loopback / RFC1918 / link-local (closes AWS IMDS exfil). Same guard applied to `restai/sync.py:_sync_url`.
- **Userland extension loaders pinned to install root** — userland auto-import folders live under `<install_root>/userland/`: `tools/` (agent builtins), `image/` (image generators), `audio/` (speech). `tools.py` resolves each via the shared `_userland_dir(subdir)` helper — anchored to the install root (never cwd-relative), skips cleanly when missing, prepends install root to `sys.path`, imports as `userland.<kind>.<mod>`. Closes a code-exec surface from unexpected CWDs. `.gitignore` keeps the folders (`.gitkeep`/`__init__.py`) but ignores dropped modules.
- **Per-key audit trail on settings** — `patch_settings` writes `audit._log_to_db(actor, "SETTING", "settings/<key>:<status>", 200)` per changed key. Secret keys get `:secret_changed` (values NEVER recorded); non-secret keys include 32-char fingerprint.
- **Password-age tracking** — `users.password_updated_at` stamped on every `create_user`/`update_user` (migration 041). `password_max_age_days` (default 0 = disabled) drives a soft warning in `/auth/login` response (`password_warning`). Never blocks. Legacy NULL rows never warn.
- **Per-API-key monthly quotas** — `api_keys.token_quota_monthly` (NULL = unlimited), `tokens_used_this_month`, `quota_reset_at` (migration 042). `restai/budget.py:check_api_key_quota` raises 429 when hit; rolls over lazily on first check after `quota_reset_at` (1st-of-next-month UTC). `record_api_key_tokens` in `log_inference` bumps. Admin: `PATCH /users/{u}/apikeys/{id}`.
- **API errors carry field-level metadata** — `ApiError` exposes `fieldErrors` (field → message), parsed from 422 `detail` via `_extractFieldErrors`. Forms mark TextField with `error` + `helperText`. `ProjectEdit.jsx` plumbs via `fieldErrors` + `clearFieldError` props; `memory_bank_max_tokens` is the wired demo. `options.<name>` accepted so nested locs (`["body","options","k"]`) light up the right field.
- **Contextual chat error messages** — `ChatPanel.jsx:formatChatError(status, detail)` maps 402 → "budget exhausted", 429 → "rate limit" (quota-specific when detail mentions quota), 413 → "too large", 503/502 → "overloaded". Used by both streaming (`onopen` captures status, hands to `onerror`) and non-streaming (`catch (e)` consumes `e.status`+`e.detail`). 401/402/413/429 also toast.
- **JWT secret strength check** — startup WARNs when `RESTAI_AUTH_SECRET` is empty/<32 chars/known-weak. Result lands on `fs_app.state.auth_secret_weak`, surfaced to UI via `auth_secret_weak` in `/setup`. `_ensure_env_secret` writes a 64-byte urlsafe default on first boot — this catches legacy installs and copy-pasted dev envs.
- **Client-side validation on project-edit numerics** — `projectOptionValidators.js` exports `clientValidators` (rate_limit/k/score/memory_bank_max_tokens) + `makeErrorFor(fieldErrors, state)`. ProjectEdit tabs consume so typos light up inline without 422 round-trip. Server `ApiError.fieldErrors` still wins on save.

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

### Upload Ceiling (`max_upload_size_mb`)

One admin-configurable per-file ceiling across **every** upload surface, enforced *before* the body is read. Previously `MAX_UPLOAD_SIZE` was an env-var module constant that governed RAG ingest only, appeared in **zero** deployment files (so it was frozen at 100 MB for every Docker/Helm install), and every path did `contents = await file.read()` *before* the 413 — meaning raising the number converted a clean rejection into an OOM.

- **The setting** — GUI-managed like `max_audio_upload_size`: `settings.py` (`SETTINGS_DEFAULTS` + `_INT_KEYS` + response), `config._GUI_SETTING_ATTRS["MAX_UPLOAD_SIZE_MB"]`, `SettingsResponse`/`SettingsUpdate`, `Settings.jsx` Limits card, 9 locales. Read via `config.max_upload_bytes()`. **No in-process mirror** — DB read-through per access, so a second uvicorn worker sees a change immediately. (Inside `config.py` itself use `import restai.config as _cfg`; a bare name skips module `__getattr__`.) Surfaced on `/info` so clients pre-validate instead of hard-coding a number.
- **`BodySizeLimitMiddleware`** (`restai/middleware.py`) — pure ASGI, not `BaseHTTPMiddleware` (which runs the app in a task group and re-raises receive-side errors out of `call_next`, so a clean 413 can't be emitted, and which would wrap every SSE stream in a task group). Two layers: a `Content-Length` fast path, plus a wrapped `receive` that counts bytes — `Content-Length` is absent under `Transfer-Encoding: chunked`, so the header check alone is bypassable. Upload paths get `max_upload_bytes() + 2 MB` multipart slack (boundaries + sibling form fields exceed the file itself); everything else gets `_JSON_BODY_LIMIT_BYTES` (32 MB). Raising `HTTPException` from middleware would surface as a 500 (the app's handlers live in the inner `ExceptionMiddleware`), so it sends the response itself, guarding on `response_started`. `/v1/*` keeps the OpenAI envelope with `type="invalid_request_error"` — `api_error` reads as retryable and clients would re-upload.
- **Streaming everywhere** — `core.py` ingest and `bulk_ingest.py` check `UploadFile.size` (Starlette populates it while parsing, spooling parts >1 MB to disk) then `copyfileobj`; `integrations/sync.py` SharePoint + both GDrive fetches use `stream=True` + `_stream_to_tempfile` instead of `resp.content` (S3's `download_fileobj` was already correct).
- **Chat attachments** — `helper.enforce_attachment_limits(chat_input)` runs at the `chat_main` boundary (so chat, question, public projects and mobile are all covered — `files` is in `_PUBLIC_SAFE_CHAT_FIELDS`, i.e. reachable unauthenticated) and caps both `files[].content` and the `.image` slot, which carries no length bound of its own. A URL in `.image` is skipped — `resolve_image` fetches those behind the SSRF guard. `_b64_decoded_size` computes real bytes from the base64 length; `_attachment_meta.size` used to report the base64 length, overstating every attachment by 4/3.
- **DB safety** — `tools.py` caps the `image` column at `_IMAGE_COLUMN_LIMIT` (drops an oversized base64 image rather than aborting the billing INSERT) and routes `log_tool_trace` through `_cap_text_column`.
- **Sandbox transfer** — `docker.py:put_files` spools the tar to a `SpooledTemporaryFile` instead of `buf.getvalue()` and tries `container.put_archive` first, falling back to the proven 64 KB `exec_run` chunk loop. The tmpfs mounts are declared as `mounts=[Mount(type="tmpfs")]`, not the `tmpfs=` kwarg: `tmpfs=` maps to `HostConfig.Tmpfs`, which never registers as a MountPoint, so Docker treats those paths as read-only rootfs and refuses `put_archive`. tmpfs pages are charged to the memory cgroup, so their size tracks the new `docker_memory_mb` setting — a 1 GB tmpfs under a 512m limit fails as an OOM kill, not an error. The Docker client also gets `timeout=max(60, DOCKER_TIMEOUT)` (SDK default 60s is far too short for a large `put_archive`), and the timeout is part of `_client_cache_key()` so changing it rebuilds the client.
- **Frontend** — `api.upload()` (`utils/api.js`) is XHR-based because `fetch` cannot report upload progress; it shares `_buildApiError` with `request` so ApiError/fieldErrors/401-redirect behave identically. Progress bars in `ProjectEditKnowledge.jsx` + `RAGUpload.jsx`; client-side caps from `/info` there, in `ChatPanel.jsx` (was a hard-coded 20) and in the mobile PWA (`mobile/src/Chat.jsx`, which capped nothing). A proxy-level 413 has no JSON envelope, so `_buildApiError` special-cases it with a message naming `client_max_body_size`.
- **Deployment** — `chart/restai/values.yaml` sets `nginx.ingress.kubernetes.io/proxy-body-size` (ingress-nginx defaults to **1 MB**, which rejected every Helm install's uploads regardless of app config) plus read/send timeouts, and adds `uploadStaging` (shared PVC) + `tmpVolume` (per-pod emptyDir for Starlette's spool, so it doesn't land on the node's unsized overlay). README documents the proxy directives and the worker/slow-loris tradeoff.
- **Tests** — `tests/test_upload_limits.py` (path→limit resolution, middleware enforcement + OpenAI envelope, setting round-trip through `/settings`→`/info`→`config`, attachment + image caps, exact base64 sizing), plus the bulk-ingest 413/rollback/507/chunks-bounds cases in `tests/test_bulk_ingest.py`, and `api.upload` coverage in `frontend/src/app/utils/api.test.js`. `test_bulk_ingest.py`'s fixture now creates its own team WITH the LLM+embedding attached — picking `teams[0]` and `llms[0]` independently gave a pair with no access relationship, so all 5 tests had been silently skipping on a 403.

### Bulk File Ingest Queue

RAG-only — uploads decoupled from request/response so a 500-page PDF doesn't time out the admin.

- **Table**: `bulk_ingest_jobs` (migration 044). Fields: project_id, filename, mime_type, size_bytes, file_path, method/splitter/chunks, status (`queued`/`processing`/`done`/`error`), error_message, documents_count, chunks_count, timestamps.
- **Staging dir**: `config.UPLOAD_STAGING_PATH` (env, bootstrap default `./data/bulk_ingest/`), NOT `$TMPDIR`. The API and cron run in separate containers under both docker-compose and Helm and share only the data volume, so a `/tmp` path was written by one and invisible to the other — **bulk ingest never worked in either default deployment**. compose sets it on the shared `/app/data` volume; Helm needs `uploadStaging.enabled=true` (a shared RWX PVC — an emptyDir is per-pod and would reintroduce the same bug).
- **Router** (`restai/routers/bulk_ingest.py`): `POST /projects/{id}/ingest-bulk` (multipart, 202 + queued ids), `GET /projects/{id}/ingest-bulk`, `DELETE /projects/{id}/ingest-bulk/{jobID}`. Every part's `UploadFile.size` is validated **before anything is staged** — the old per-file check ran mid-loop, after earlier files were already written to disk AND committed as rows, so a rejected batch left debris (regression test: `test_enqueue_rejects_oversized_file`). Staging streams via `shutil.copyfileobj` (never `.read()`), `size_bytes` is stat'd off the written file, and `_require_free_space` refuses with **507** rather than filling the volume (keeps `_DISK_HEADROOM_BYTES` = 512 MB free).
- **Cron** (`crons/bulk_ingest.py`): claims one queued row at a time (`status=queued` → `processing` in single txn), dispatches via auto_ingest → markitdown → docling → classic fallback chain, finalizes with a fresh DB session. Tempfile deleted regardless. Once per tick it also runs `_reclaim_stalled_jobs` (rows stuck at `processing` past `STALE_PROCESSING_SECONDS` → requeued if the file survives, else errored) and `_purge_orphan_staged_files` (staged files with no live row). Both piggy-back on the drain loop's own session — opening extra `open_db_wrapper()`s consumed the tests' mocked session sequence and burned prod connections.
- **Docling in the queue was dead.** `load_documents(manager, ...)` calls `manager.dict()` and `auto_ingest` skips docling when `manager is None`; the cron passed None to both, so `method=docling` raised AttributeError on every job and `method=auto` silently ingested at lower fidelity than the synchronous endpoint. `_get_manager()` starts one lazily (a tick with no docling work doesn't pay for a spawned Manager).
- **Timeouts move together**: `crons/runner.py:JOB_TIMEOUT_OVERRIDES` gives bulk_ingest 3600s (vs the 600s default), and the Helm chart's `cron.activeDeadlineSeconds` must stay ≥ that or k8s kills the pod mid-ingest and leaves the row stuck.
- **UI**: `ProjectEditKnowledge.jsx` adds Bulk File Ingest section atop Knowledge tab with multi-file uploader (real progress bar via `api.upload`, client-side cap from `/info`) and status table polling 5s.
- **Scope**: queued jobs with missing staged file auto-error on next tick. Agent / block projects reject with 400. `size_bytes` is `BigInteger` (migration 062) — `Integer` capped at 2 GB, and SQLite's dynamic typing would have hidden that until prod hit MySQL/Postgres.

### Knowledge-Base Re-Embedding (`restai/reembed.py`, migration 063)

Changing a RAG project's `embeddings` used to write the new name and leave the vector store full of OLD-model vectors — an opaque 500 on a dimension change, silently meaningless similarity scores otherwise, and unrecoverable either way because **every ingest path deletes its source bytes** (`core.py:ingest_file` unlinks its tempfile in a `finally`; `crons/bulk_ingest.py` and `integrations/sync.py` likewise). The chunk text in the vector store is the only durable copy — `StorageContext.from_defaults()` is called without `persist_dir` everywhere, so there is no side docstore — so the fix re-embeds **existing chunks**, never re-ingests files.

- **Trigger**: changing `embeddings` on a RAG project with a non-empty store auto-enqueues a job (`core.py:route_edit_project`, where `reset_memory_index` already fired). `POST /projects/{id}/reembed?to_embeddings=` is the explicit path — also the repair route for projects already broken by the old behaviour, where re-picking the same model in the UI would register no change.
- **Phases** (`reembed.run_job`, tracked in `reembed_jobs.phase`): `snapshotting` → verify → `resetting` → `rebuilding`. **The verify step is the whole safety argument**: the snapshot's line count must equal `vector.info()` exactly, or the job aborts having destroyed nothing. `WeaviateDB`/`PineconeDB` return partial results on read errors and their `info()` returns **0** from its except branch, so "empty" and "unreachable" are indistinguishable; Pinecone's `list()` is serverless-only.
- **Resume is phase-aware and load-bearing.** `_POST_DESTRUCTIVE_PHASES = (resetting, rebuilding)` — a job resuming in either must NOT re-snapshot (it would capture the emptied/half-rebuilt store and overwrite the only backup). `_write_snapshot` refuses to overwrite an existing file as a second guard. `crons/reembed.py:_reclaim_stalled_jobs` requeues into the recorded phase rather than back to `queued`.
- **Snapshot** is JSONL under `UPLOAD_STAGING_PATH/reembed/`, deleted only on `done`. `purge_orphan_snapshots` keys on `status != "done"`, NOT on open statuses — a failed job's snapshot is the surviving copy.
- **Metadata fidelity**: reads go through the new **abstract** `VectorBase.list_all_nodes(limit, offset)` (full metadata + real pagination), not `list_all_chunks`, which projects out everything but `source` and would drop yake `keywords`. Rebuild strips `_`-prefixed / `doc_id` / `ref_doc_id` keys and inserts via batched `index.insert_nodes`.
- **Guards while a job is open** (`reembed.raise_if_migrating`, 503): all 9 knowledge endpoints, `POST /ingest-bulk`, **`POST /sync/trigger`** (phrased differently from the others — easy to miss, and it spawns a writer thread), and `crons/sync.py`. Chat is guarded in **`helper.chat_main`** beside `enforce_cost_budgets` — the one boundary every entry path crosses, and before any SSE stream opens so a real 503 is possible. NL→SQL-only projects are exempt.
- **Provenance**: `projects.embeddings_indexed` records which model the vectors were actually built with, stamped beside all 9 `project.vector.save()` calls. NULL = never stamped (pre-upgrade) and must read as *unknown*, not stale.
- **Cost**: `embeddings.input_cost` (USD/1M tokens, default 0.0 so existing installs migrate free) drives `accounting.log_embedding_usage`, charged **per batch** so a dead job bills only what it spent and a resumed one doesn't double-charge. Never abort a running migration on budget — a partial store is the failure mode this exists to prevent.
- **Per-backend**: Chroma/pgvector/Weaviate handle a dimension change via `reset()`. **Pinecone cannot** — all projects share one fixed-dimension index; `check_compatibility` returns `compatible: false`.
- **Deployment gotcha**: `EMBEDDINGS_PATH` defaulted to `./embeddings/` *inside each container*, so the API and cron had private Chroma stores in both shipped deployments (breaking cron-side knowledge work generally, not just this). docker-compose now puts it on the shared `/app/data` volume; the Helm chart documents the RWX requirement. A misconfigured deployment fails **safe** here — the verify step reads 0 and refuses.

Tests: `tests/test_cron_reembed.py` (phase machine + every abort path, fakes only), `tests/test_reembed.py` (HTTP surface, guards, compatibility rules).

### Routine Execution Log

Per-fire history table (`routine_execution_log`, migration 045) alongside `ProjectRoutineDatabase`. Legacy `last_result` is a single string — can't show flaky-routine patterns. New table keeps `status` (ok/error), `result` (truncated answer or error), `duration_ms`, `manual` (true for admin-triggered, false for cron), `created_at`. Cascade-deletes with parent.

- **Cron**: writes one row per fire. Best-effort — log row failures never break the tick.
- **Manual fires**: also write a row with `manual=true`.
- **History endpoint**: `GET /projects/{id}/routines/{routineID}/history?limit=50` (newest first).
- **UI**: `ProjectEditRoutines.jsx` adds a History icon button → dialog with per-fire table.

### Agent Resilience (agent2 `restai` loop)

The default agent loop survives provider trouble instead of dying mid-run. Policy lives in `restai/agent2/resilience.py`; the ladder is applied per turn in `Agent2Runtime` (`restai/agent2/agent.py`):

1. **Transient retries** — 429/5xx/timeout/connection errors (classified SDK-agnostically by status attrs, class names, and message shape; context-length/auth errors vetoed) retry on the same provider with capped exponential backoff + jitter (`retry_attempts=2`, `retry_base_delay=1.0` constructor knobs). Streaming retries only before the first delta reaches the client.
2. **native→ReAct swap** — unchanged (auto mode, turn 1) but now only for NON-transient errors; a down provider fails ReAct identically, so transient failures go straight to step 3.
3. **Fallback LLM chain** — `ProjectOptions.fallback_llm` (CSV of LLM names, resolved in `agent.py:_resolve_fallback_chain`, unknown/unsupported names skipped with a warning). Session messages are provider-neutral, so the run continues on the next provider with full conversation context; the requested mode is restored for the new provider. Switches are recorded in `runtime.fallback_trail`, surfaced live as an `{"llm_fallback": {from,to}}` SSE frame (unknown to old clients — ignored), appended to `tool_trace` as synthetic `llm_fallback` rows, and exposed on the response as `llm_used`/`llm_fallbacks` (only when a switch happened). `log_inference` attributes the row + cost to `output["llm_used"]` when present.

Tool execution hardening (also `Agent2Runtime`):
- **Sync tools run in worker threads** (`AdaptedTool.call` → `asyncio.to_thread`; sandbox tools thread `docker_manager.run_script`) — parallel tool batches actually parallelize and one slow tool no longer freezes every chat on the worker.
- **Per-call timeout** — `ProjectOptions.tool_timeout` (default 300s, 0=off) via `asyncio.wait_for`; timeouts return an `ERROR: … timed out` tool result the model can react to.
- **Arg validation + coercion** — `tool_adapter.coerce_and_validate_args` runs before execution: fixes "5"→5, "true"→True, JSON-string arrays/objects (big win for ReAct-mode small models); missing/uncoercible params return a crisp error with a compact schema description instead of a deep TypeError. Lenient by design (anyOf/$ref/unknown keys pass through).
- **Loop guard** — the 3rd+ identical `(tool, args)` call in a run still executes (stateful tools may legitimately repeat) but gets a `[loop guard: …]` note appended nudging the model to change approach.
- Unknown-tool errors list the available tool names.

**Real token usage**: providers attach `Message.usage` (`{"input","output"}`, normalized by `providers.normalize_usage`) from OpenAI `response.usage` (streaming via `stream_options include_usage`, with a one-shot retry without it for gateways that reject the param), Anthropic `usage`, and Bedrock converse `usage`. The runtime sums per-call usage across turns (`usage_input`/`usage_output`; `usage_complete` when every turn reported). `Agent._count_tokens` prefers complete real usage (accuracy "high" — per-call input sums match provider billing for multi-turn loops), floors the tiktoken estimate with partial usage ("medium"), else keeps the transcript-aware estimate ("low"). `Message.usage` is per-run transient — never serialized into persisted sessions.

Failed runs are labeled: a provider-error final (`stop_reason == "error"`, i.e. retries + chain exhausted) sets `output["status"]="error"` + `output["error"]` in `_drive_runtime`, so the log row and the analytics status_breakdown record a failure instead of a "success" whose answer reads "Provider error: …"; planned mode aborts remaining steps on it. Compression-summarizer calls report their usage back through `compress_session(usage_sink=…)` → `runtime._absorb_side_usage` (added to run totals without touching turn counters, so `usage_complete` stays turn-based).

Unit tests: `tests/test_agent2_resilience.py` (fake providers, no SDKs/network).

### Agent Loop Feature Parity (external loops)

The four SDK loops (`claude` / `llamaindex` / `smolagents` / `openai_agents`) carry the same hardening as the restai loop, via shared helpers in `restai/projects/agent_shared.py`:

- **`ToolRunPolicy`** — one instance per request, used by EVERY tool wrapper in all four loops (builtins, project sandbox tools, MCP-adapted tools): sync tools run in worker threads (they used to block the event loop inline in the claude/openai_agents wrappers), `tool_timeout` enforced (`run_async` via `asyncio.wait_for`, `run_sync` via an abandoned-on-expiry executor thread for smolagents' sync world), identical-call loop-guard note on the 3rd+ repeat, model-visible output cap (`truncate_tool_output` — previously only trace previews were capped, the model got the full dump), and exceptions/timeouts normalized to `ERROR: …` strings.
- **`drive_with_fallbacks`** — whole-run fallback chain (`options.fallback_llm`, same option as restai). Each loop's `chat()` builds a `_drive` factory taking `(llm_override, run_state)`; on failure the driver retries on the next LLM **only while nothing streamed and `run_state["tools_executed"] == 0`** — an SDK run can't resume mid-flight, so a retry is allowed only before any side effect. Loop-incompatible names skip naturally (the loop's resolver 400s, the driver advances). Emits the same `{"llm_fallback"}` SSE frame, merges `llm_fallback` rows into the result's tool_trace, and sets `llm_used`/`llm_fallbacks` on the output so `log_inference`/`attach_cost` attribute correctly. Terminal failures yield `("error", {...})` (chat() sets `status`/`error` — same labeling as restai).
- **Usage accuracy labels everywhere**: claude (SDK ResultMessage usage → "high"), smolagents (per-step `token_usage` → "high"), openai_agents (`result.context_wrapper.usage` aggregated across turns → "high"), llamaindex (transcript-aware estimate via `estimate_input_tokens`, floored by final-response usage from `usage_from_raw_response` → "medium", else "low"). Estimate fallbacks all use `agent_shared.estimate_input_tokens` (question + system prompt incl. rendered history/memory + tool_trace).
- **llamaindex iteration cap**: `max_iterations` passed to `agent.run()`; the workflow's `WorkflowRuntimeError("Max iterations …")` is caught and converted to the standard max-turns "say continue" notice (`stop_reason="max_turns"`) instead of failing the run.
- Gotcha: an async-built llama-index `FunctionTool.fn` is the SYNC bridge (returns a value, not an awaitable) which runs the coroutine on a FRESH event loop. MCP sessions are bound to the request's loop, so the bridge breaks MCP tool calls. Every loop wrapper therefore uses `real_fn`/`async_fn` (the original callable) and keeps async tools on the request loop: llamaindex/claude/openai_agents await it directly; smolagents (sync world, agent runs in an executor thread) dispatches via `asyncio.run_coroutine_threadsafe(coro, main_loop)` — safe because the main loop sits idle in `run_in_executor` while the agent thread blocks.
- Second MCP gotcha: MCP tool fns take `**kwargs` and forward them VERBATIM to the server — the loops' context injection (`_brain`/`_chat_id`/`_project_id`, keyed off has-var-kwargs) would ship an unserializable Brain to the server and fail every call. MCP-adapted tools are wrapped with `inject_context=False` (openai_agents/smolagents); llamaindex's `_wrap_adapted_with_policy` never injects.

**Wall-clock cap (`ProjectOptions.max_execution_time`, 0 = unlimited, all loops).** Per-RUN limit alongside the per-CALL `tool_timeout` and the per-run turn cap `max_iterations`. Enforced at safe points only — never mid-stream: the restai runtime checks at turn boundaries (`Agent2Runtime._deadline`, set at construction so an auto-plan request's steps share ONE budget; a tripped step sets `output["stopped_max_time"]` and `_chat_planned_stream` skips the remaining steps + synthesis; the intra-turn resilience ladder also respects it — no retries, backoff sleeps, or provider-chain switches once the deadline passed). The SDK loops check **before pulling the next event** (an in-hand event — a whole turn's text, an executed tool's output, the terminal usage record — is never discarded), gated on run completion so a run that finished just past the cap isn't mislabeled (llamaindex: `handler.done()`; openai_agents: `result.is_complete`; claude: ResultMessage seen; smolagents: `final_answer` set — trailing usage events still drain). **A trip must actually STOP execution**: llamaindex `await handler.cancel_run()` (bounded; breaking out of `stream_events()` alone leaves the workflow running LLM turns + side-effecting tools in the background — same cancel on the repetition break), openai_agents `result.cancel()`, claude best-effort `client.interrupt()` before the context-exit disconnect, smolagents explicitly `close()`s the unexhausted sync generator in a worker thread (GC-closing it on the event loop can block on smolagents' parallel-tool executor exit — forever with `tool_timeout=0`). `drive_with_fallbacks` shares one deadline across fallback attempts and starts no new attempt past it. All loops emit `stop_reason="max_time"` (propagated to the response by every `chat()`) + the shared `max_time_notice` ("reply continue" — the persisted session/history resumes where it stopped). There is deliberately no env var for this — it's per-project, GUI-managed like `max_iterations`. **Options save path gotcha**: the Tools card saves through `ProjectInfoTools.handleSave`'s explicit key merge — a new agent option added to `ProjectEditTools` MUST also be added there or edits are silently dropped (regression tests in `ProjectInfoTools.test.jsx`).

Tests: `tests/test_agent_loops_parity.py` (policy, fallback driver, estimator, wall-clock helpers, per-loop wrapper integration — imports the real SDKs, no network).

### Agent Tool-Call Trace

Per-tool-call timeline captured during `agent._drive_runtime` and persisted to `OutputDatabase.tool_trace` (migration 046). JSON list of `{tool, args, latency_ms, status, error?}`. Latency between LLM `assistant` event (containing `ToolUseBlock`) and matching `tool_result` event. Status: the runtime's `ToolResultBlock.is_error` flag is authoritative (covers unknown tools, invalid args, timeouts, raised exceptions), with a case-insensitive `error` prefix check as fallback for builtins returning soft error strings.

- **Synthetic timeline rows**: `llm_turn` (one per LLM turn — wall time incl. retries/backoff + the serving model, from the assistant event's `turn_latency_ms`/`llm` data) and `llm_fallback` (mid-run model switches). Together with the tool rows the trace reads as a full run timeline.
- **Persistence**: `tools.py:log_inference` writes `tool_trace` if present, gated by `logging` toggle.
- **UI**: `ProjectLogs.jsx` renders Tool Trace panel under each expanded log row — one row per call with tool chip, truncated args, error block, latency. Error rows get a subtle red wash.
- **Empty trace**: non-agent projects (and external-loop runs without tool calls) leave `tool_trace=NULL` — panel omitted. restai-loop runs always carry at least their `llm_turn` rows.

### Agent Run Observability (migration 061)

Four nullable `OutputDatabase` columns persisted by `log_inference` for every row (NULL on non-agent rows/history): **`stop_reason`** (`max_turns`/`max_time`/`error`; NULL = completed normally), **`retries`** (`Agent2Runtime.retry_count`, transient provider retries incl. streaming — recorded via `Agent._record_fallbacks`), **`fallbacks`** (`len(output["llm_fallbacks"])`), **`token_accuracy`** (`tokens.accuracy` — high/medium/low provenance). All five loops propagate `stop_reason` onto the output; external loops' counts come from the same output keys.

- **`GET /projects/{id}/analytics/tools`** (`analytics.py`) — per-tool stats for the month window aggregated from persisted traces via the pure `aggregate_tool_traces` helper (unit-tested in `tests/test_analytics_tool_traces.py`): calls, errors, error_rate, avg/p50/p95 latency, plus `llm_turns` latency rollup, fallback totals, `runs_analyzed`, and a `truncated` flag (newest-first cap `_TOOL_ANALYTICS_MAX_ROWS=2000`). Pseudo-rows (`llm_turn`/`llm_fallback`) are split out of tool stats.
- **`/analytics/conversations` additions**: `stop_reason_breakdown` (how agent runs ended — distinct from `status_breakdown`, which is the request outcome) and `reliability` (`retries`/`fallbacks`/`runs_with_fallback` sums + `token_accuracy` counts).
- **Frontend**: `ProjectAnalytics.jsx` second drill-down row (Agent Run Endings + reliability, LLM Turn Latency, Tool Performance table — hidden when no agent data); `ProjectLogs.jsx` RUN OUTCOME chips (stop reason / retries / fallbacks / token accuracy) on expanded rows; the logs endpoint returns raw ORM rows so new columns flow to clients automatically.

### Conversation Inspector & Live Run Telemetry

- **`GET /projects/{id}/logs/conversation/{chat_id}/details`** (`analytics.py:build_conversation_details`, pure over row objects) — everything about one conversation: per-turn tokens/cost/latency/outcome metadata + parsed tool_trace, plus rollups (totals, latency avg/p95, models, per-tool stats via `aggregate_tool_traces`). 404 on unknown chat. Companion to the replay endpoint (transcript only). Tests: `tests/test_conversation_details.py` (creates LLM/team/project via API, inserts OutputDatabase rows directly).
- **`ConversationDetailsDialog.jsx`** — opened by the QueryStats button NEXT TO the Replay button in `ProjectLogs.jsx`: stat tiles, per-turn latency + stacked input/output token mini-bar charts (last 30 turns), turns table with per-turn `TraceTimelineBar` mini-timelines + outcome chips + click-to-expand Q/A/error/tool-calls, and a per-conversation tool usage table.
- **`RunTelemetry.jsx`** — live playground telemetry strip in `ChatPanel.jsx` (above the input): run clock, tool-call Gantt rows building in realtime from the SSE frames (500ms tick while streaming), error/fallback counters, ~output-token estimate; freezes at the final state until the next question (snapshot taken in `onclose` via refs — closures see stale state). Pure derivations live in `app/utils/runTelemetry.js` (`buildLiveTimeline`/`traceToSegments`/`estimateTokens`/`formatMs` — unit-tested; components importing react-markdown can't be, so keep logic there).
- **Chart colors** are the dataviz reference palette, validated per mode with the skill validator: blue `#2a78d6`/`#3987e5` = LLM/input, aqua `#1baf7a`/`#199e70` = tools (orange FAILED CVD separation against error-red in dark mode — don't "fix" it back), orange = output tokens, `#d03b3b` = errors (always with a text label/tooltip, never color alone).

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

`FastAPI.TestClient` with Basic auth: `auth=("admin", RESTAI_DEFAULT_PASSWORD)`. Inline fixtures in `conftest.py` (`sys.setrecursionlimit(20000)`, pre-builds Pydantic schemas). For speed, `conftest.py` runs the app lifespan ONCE per process (every module's `with TestClient(app)` after the first is a no-op enter — don't add per-module startup assumptions), disables telemetry, and cheapens bcrypt/PBKDF2 for test-created credentials. Tests create real resources against a live app instance. Key files:
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

**Linting**: ruff, configured in `pyproject.toml` (`[tool.ruff]`). Default E/F rules with pragmatic ignores (`E402` late imports, `E712` SQLAlchemy `== True`, `E731`, `E741`); `migrations/` and `examples/` excluded. The repo is at zero violations and CI runs `ruff check .` before tests — keep it clean. Some `__init__.py` re-exports carry `# noqa: F401` because tests/monkeypatching reach them via the package namespace; module-level "unused" imports may be compat re-exports (e.g. `restai.database.verify_password`) — check importers before deleting.

**Coverage**: pytest-cov (`[tool.coverage.run]` sources: `restai`, `crons`, `modules`). `make coverage` for local HTML report; CI prints the term report.

**Frontend tests**: Jest via `react-scripts test` (CRA built-in) + Testing Library; setup in `frontend/src/setupTests.js`, coverage scope in the `jest` key of `frontend/package.json` (`src/app/**`, locales excluded). `make frontend-test` / `npm run test:ci` runs headless with coverage; CI runs it before the frontend build. Tests colocate with source (`*.test.js`/`*.test.jsx`). Pure-logic modules (utils, validators, `chatErrors.js`) are the pattern to follow — components importing `react-markdown` (ESM-only) break under CRA's Jest transform, so extract logic out of such components rather than rendering them (that's why `formatChatError` lives in `chatErrors.js`, not ChatPanel).

## Key env vars

`RESTAI_DEV`, `RESTAI_DEFAULT_PASSWORD`, `RESTAI_URL` (OAuth redirects), `MCP_SERVER`, `HF_TOKEN` (HuggingFace gated models). Full list in `restai/config.py`. **No LLM provider API keys** — those live per-LLM in `/admin/llms` and are encrypted at rest; same for image-generator and audio-generator credentials.

GPU toggle, Redis (chat memory), and the vector backends (ChromaDB / PGVector / Weaviate / Pinecone) are GUI-managed in `/admin/settings` — env-var bootstrap was dropped, see the `_GUI_SETTING_ATTRS` block in `restai/config.py`. GPU is auto-detected on first boot (`gpu_enabled` default `None` ⇒ `detect_gpu()` fallback in `__getattr__`).

Runtime-tunable settings (SSO, Docker, MCP, system LLM, knowledge retention, 2FA, branding, GUI-managed everything) live in the `settings` DB table. Consumers read via `restai.config.<NAME>` — `restai/config.py` defines a module-level `__getattr__` that resolves any GUI-managed key by querying the DB on every access (`_GUI_SETTING_ATTRS` is the authoritative `config_name -> (db_key, type, default)` map).

**There is no in-process mirror anymore.** Earlier versions kept `_CONFIG_ATTR_MAP` and re-`setattr`'d each updated value back onto `restai.config` after every PATCH /settings; that mutation only landed in the worker that handled the request, so multi-worker uvicorn deployments saw stale values everywhere else (`POST /settings/docker/test` failing intermittently was the canary). DB-direct read-through is the only correct pattern.

**Env-var support dropped for GUI-managed keys.** Bootstrap-only env vars (POSTGRES_HOST, RESTAI_FERNET_KEY, RESTAI_AUTH_SECRET, RESTAI_DEV, etc.) still live as module-level constants because they're needed before the DB is reachable; everything else goes in the Settings page. Existing deployments already have old env values seeded in the DB.

**Bare-name lookup gotcha inside `config.py`:** module `__getattr__` only fires for `module.X`-style access from elsewhere. Inside `restai/config.py`, a bare `REDIS_HOST` is looked up in module globals (no descriptor) and raises `NameError`. When a function in `config.py` needs a GUI setting, do `import restai.config as _cfg` and use `_cfg.REDIS_HOST`. See `build_redis_url()` and `load_oauth_providers()`.
