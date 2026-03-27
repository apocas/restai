# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is RestAI

AIaaS (AI as a Service) platform — create AI projects and consume them via REST API. Supports multiple project types: RAG (with optional natural language to SQL), inference, agent, and block (visual logic builder).

## Commands

```bash
# Backend
make dev              # Dev server with hot reload (port 9000, RESTAI_DEV=true)
make start            # Production (4 workers, port 9000)
make database         # Initialize DB schema + admin user + default models
make migrate          # Run Alembic migrations
make install          # Full setup: deps + database + frontend build

# Frontend
make frontend         # npm install + npm run build
cd frontend && npm start  # Dev server (port 3000, proxies to 9000)

# Tests
pytest tests                                    # All tests
pytest tests/test_projects.py -v                # Single file
pytest tests/test_projects.py::test_create_project  # Single test

# Code quality
make code             # black app/*.py
```

Package manager is `uv`. Dependencies exclude GPU group by default (`--no-group gpu`).

## Architecture

**Entry point**: `restai/main.py` — FastAPI app with lifespan that initializes `Brain`, registers routers, optionally mounts internal MCP server at `/mcp`, and mounts React SPA at `/admin/*`.

**Core orchestration**: `restai/brain.py` — `Brain` class holds LLM/embedding caches, tool registry, chat store (Redis or in-memory), and token counter. Injected via `app.state.brain`.

**Request flow**: Router endpoint → `restai/helper.py` (`chat_main`/`question_main`) → dispatches to project type handler in `restai/projects/` → logs inference via background task.

### Project types (`restai/projects/`)

All inherit from `ProjectBase` (in `base.py`) which defines `chat()` and `question()`:
- `rag.py` — Retrieval-Augmented Generation (vectorstore + embeddings + reranking + optional natural language to SQL)
- `inference.py` — Direct LLM chat/completion (supports multimodal image input)
- `agent.py` — ReAct agent with tools (built-in + MCP)
- `block.py` — Visual logic builder using Blockly. No LLM required. Interprets workspace JSON server-side via `block_interpreter.py`. Supports image passthrough to sub-projects via "Call Project" block.

### Routers (`restai/routers/`)

`/projects`, `/users`, `/teams`, `/llms`, `/embeddings`, `/tools`, `/proxy`, `/direct`, `/statistics`, `/settings`, `/auth`, `/evals` (evaluation framework), plus GPU-only `/image` and `/audio`.

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

`restai/tools.py` maps LLM class names to implementations. Valid LLM classes: Ollama, OllamaMultiModal, OllamaMultiModal2, OpenAI, OpenAILike, Grok, Groq, Anthropic, LiteLLM, vLLM, GeminiMultiModal, Gemini, AzureOpenAI. Valid embedding classes: LangChain, LangChain.Openai, LangChain.HuggingFace, OllamaEmbeddings, Ollama. All go through LlamaIndex abstractions. These sets are defined as `VALID_LLM_CLASSES` and `VALID_EMBEDDING_CLASSES` in `models.py` and enforced via Pydantic validators.

### Frontend (`frontend/`)

React 18 + MUI v5 + Redux Toolkit + Blockly (for block projects). CRA-based build. Routes in `frontend/src/app/routes.js` (lazy-loaded). Auth context in `frontend/src/app/contexts/JWTAuthContext.js`. API URL configured via `REACT_APP_RESTAI_API_URL` (defaults to `http://127.0.0.1:9000`).

Key frontend pages for block projects:
- `frontend/src/app/views/projects/IDE.jsx` — Standalone Blockly IDE page (`/project/:id/ide`)
- `frontend/src/app/views/projects/components/BlocklyEditor.jsx` — Blockly workspace React component
- `frontend/src/app/views/projects/components/blockly/blocks.js` — Custom block definitions (Get Input, Set Output, Call Project, Classifier, Log)
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

ChromaDB (default) or Redis. Configured per-project. Reranking support: ColBERT and LLM-based.

## Input Validation

Names used in URL paths (project names, usernames, team names, LLM names, embedding names) are validated with `validate_safe_name` — only `[a-zA-Z0-9._:-]` allowed. This is enforced at the Pydantic model level for create models and at the router level for LLM/embedding creation (since `LLMModel`/`EmbeddingModel` are dual-use input/output models).

Enum fields use `Literal` types: `privacy` ("public"/"private"), LLM `type` ("chat"/"completion"/"vision"/"qa"), project `type` ("rag"/"inference"/"agent"/"block"), `splitter` ("sentence"/"token").

Integer Query/Form params have `ge`/`le` bounds (pagination, chunks, limits, days).

File uploads are sanitized via `sanitize_filename` (strips path components and null bytes).

## Testing

Tests use `FastAPI.TestClient` with Basic auth: `auth=("admin", RESTAI_DEFAULT_PASSWORD)`. No conftest.py — fixtures are inline. Tests create real resources (projects, users) against a live app instance. Key test files:
- `tests/test_input_validation.py` — Name validation, enum validation, valid value acceptance
- `tests/test_security.py` — RBAC, cross-team access, empty/whitespace name rejection
- `tests/test_users.py`, `tests/test_teams.py`, `tests/test_llms.py`, `tests/test_embeddings.py` — CRUD tests
- `tests/test_mcp.py` — MCP server auth (Bearer only), access control, tool registration
- `tests/test_rate_limit.py` — Rate limiting enforcement, disable/enable, HTTP 429

Note: `tests/test_projects.py` may fail if no LLMs are configured in the test environment (pre-existing issue).

## Key env vars

`RESTAI_DEV`, `RESTAI_GPU`, `RESTAI_DEFAULT_PASSWORD`, `RESTAI_URL` (for OAuth redirects), `REDIS_HOST`/`REDIS_PORT`, `CHROMADB_HOST`/`CHROMADB_PORT`, `MCP_SERVER` (enable internal MCP server), `AGENT_MAX_ITERATIONS`, LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc). Full list in `restai/config.py`.
