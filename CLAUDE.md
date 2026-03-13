# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is RestAI

AIaaS (AI as a Service) platform — create AI projects and consume them via REST API. Supports multiple project types: RAG, inference, agent, vision, router, and RAG-SQL.

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

**Entry point**: `restai/main.py` — FastAPI app with lifespan that initializes `Brain`, registers routers, optionally mounts MCP server and React SPA at `/admin/*`.

**Core orchestration**: `restai/brain.py` — `Brain` class holds LLM/embedding caches, tool registry, chat store (Redis or in-memory), and token counter. Injected via `app.state.brain`.

**Request flow**: Router endpoint → `restai/helper.py` (`chat_main`/`question_main`) → dispatches to project type handler in `restai/projects/` → logs inference via background task.

### Project types (`restai/projects/`)

All inherit from `ProjectBase` (in `base.py`) which defines `chat()` and `question()`:
- `rag.py` — Retrieval-Augmented Generation (vectorstore + embeddings + reranking)
- `inference.py` — Direct LLM chat/completion
- `agent.py` — ReAct agent with tools (built-in + MCP)
- `vision.py` — Multi-modal image-to-text
- `router.py` — Routes queries to other projects via classifier
- `ragsql.py` — Natural language to SQL

### Routers (`restai/routers/`)

`/projects`, `/users`, `/teams`, `/llms`, `/embeddings`, `/tools`, `/proxy`, `/statistics`, `/auth`, plus GPU-only `/image` and `/audio`.

### Models (`restai/models/`)

- `models.py` — Pydantic schemas for API request/response
- `databasemodels.py` — SQLAlchemy ORM models

Key relationships: Users ↔ Projects (many-to-many), Users ↔ Teams (members + admins), Teams → Projects/LLMs/Embeddings.

### Database

SQLite by default (`restai.db`), PostgreSQL via `POSTGRES_HOST`, MySQL via `MYSQL_HOST`. Connection pool configured via `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`. Migrations via Alembic (`alembic.ini`, `migrate.py`).

**Init flow** (`database.py`): creates tables → admin user (password from `RESTAI_DEFAULT_PASSWORD`) → default LLMs/embeddings from `restai/tools.py`.

### Auth (`restai/auth.py`)

Three methods checked in order: JWT cookie (`restai_token`), Bearer API key, Basic auth. OAuth (Google, Microsoft, GitHub, OIDC) configured via env vars in `restai/config.py`. Key dependency functions: `get_current_username`, `get_current_username_admin`, `get_current_username_project`.

### LLM integration

`restai/tools.py` maps LLM class names to implementations: Ollama, OpenAI, Anthropic, Groq, LiteLLM, vLLM, Gemini, Azure OpenAI, etc. All go through LlamaIndex abstractions.

### Frontend (`frontend/`)

React 18 + MUI v5 + Redux Toolkit. CRA-based build. Routes in `frontend/src/app/routes.js` (lazy-loaded). Auth context in `frontend/src/app/contexts/JWTAuthContext.js`. API URL configured via `REACT_APP_RESTAI_API_URL` (defaults to `http://127.0.0.1:9000`).

### Vector stores (`restai/vectordb/`)

ChromaDB (default) or Redis. Configured per-project. Reranking support: ColBERT and LLM-based.

## Testing

Tests use `FastAPI.TestClient` with Basic auth: `auth=("admin", RESTAI_DEFAULT_PASSWORD)`. No conftest.py — fixtures are inline. Tests create real resources (projects, users) against a live app instance.

## Key env vars

`RESTAI_DEV`, `RESTAI_GPU`, `RESTAI_DEFAULT_PASSWORD`, `RESTAI_URL` (for OAuth redirects), `REDIS_HOST`/`REDIS_PORT`, `CHROMADB_HOST`/`CHROMADB_PORT`, `MCP_SERVER`, `AGENT_MAX_ITERATIONS`, LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc). Full list in `restai/config.py`.
