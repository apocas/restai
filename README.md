<!-- markdownlint-disable MD033 -->

<h1 align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai-logo.png" alt="RESTai Logo" width="120"/>
  <br/>RESTai
</h1>

<p align="center">
  <strong>AIaaS (AI as a Service) — Create AI projects and consume them via a simple REST API.</strong>
</p>

<p align="center">
  <a href="https://github.com/apocas/restai/actions/workflows/tests.yml"><img src="https://github.com/apocas/restai/actions/workflows/tests.yml/badge.svg" alt="Tests"/></a>
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/>
  <a href="https://github.com/apocas/restai/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green.svg" alt="License"/></a>
  <img src="https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/kubernetes-ready-326CE5?logo=kubernetes&logoColor=white" alt="Kubernetes"/>
</p>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/templates.png" width="800" alt="RESTai Dashboard"/>
</div>

---

## Quick Start

### Install from PyPI

```bash
pip install restai-core
restai init      # Create database + admin user
restai migrate   # Run migrations
restai serve     # → http://localhost:9000/admin (admin / admin)
```

Use an env file for configuration:

```bash
restai serve -e .env -p 8080 -w 4
```

Available on [PyPI](https://pypi.org/project/restai-core/) — includes the pre-built React frontend, no Node.js required.

### Run from source (development)

```bash
git clone https://github.com/apocas/restai && cd restai
make install
make dev  # → http://localhost:9000/admin (admin / admin)
```

### Docker

```bash
docker compose --env-file .env up --build
```

## Updating

**PyPI:**
```bash
pip install --upgrade restai-core
restai migrate -e .env
```

**From source:**
```bash
make update
```

Fetches the latest release tag from GitHub, installs dependencies, runs database migrations, and rebuilds the frontend. Auto-detects GPU for GPU-specific deps.

---

## Why RESTai?

- **Multi-project AI platform** — RAG (with optional SQL-to-NL and auto-sync from URLs/S3), Agents, Block (visual logic), and Inference in one place
- **Full Web UI included** — React dashboard with analytics, not just an API
- **Any LLM** — OpenAI, Anthropic, Ollama, Gemini, Groq, LiteLLM, vLLM, Azure, and more
- **Feature complete** — Teams, RBAC, OAuth/LDAP, TOTP 2FA, token tracking, per-project rate limiting, white-label branding, Kubernetes-native
- **Extensible tools** — MCP (Model Context Protocol) for unlimited agent integrations
- **Token tracking, cost & latency analytics** — built-in dashboard with daily usage, per-project costs, latency monitoring, and top LLM charts

---

## Features

### Dashboard & Analytics

Track token usage, costs, latency, and project activity from a centralized dashboard. Daily charts for tokens, costs, and response latency per project — identify performance regressions at a glance.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/home.png" width="750" alt="RESTai Dashboard"/>
</div>

### Projects & Chat Playground

Create and manage AI projects. Each project has its own LLM, system prompt, tools, and configuration. Test instantly in the built-in chat playground.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/projects.png" width="750" alt="RESTai Projects"/>
</div>

### RAG (Retrieval-Augmented Generation)

Upload documents and query them with LLM-powered retrieval. Supports multiple vector stores, reranking (ColBERT / LLM-based), sandboxed mode to reduce hallucination, and evaluation via [deepeval](https://github.com/confident-ai/deepeval). Optionally connect a MySQL or PostgreSQL database to translate natural language questions into SQL queries automatically.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rag.png" width="750" alt="RESTai RAG"/>
</div>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/analytics.png" width="750" alt="RESTai RAG Analytics"/>
</div>

### Agents + MCP

Zero-shot ReAct agents with built-in tools and [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server support for extensible tool access. Connect any MCP-compatible server via HTTP/SSE or stdio.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/agent.png" width="750" alt="RESTai Agent"/>
</div>

### Inference (Multimodal)

Direct LLM chat and completion. Supports sending images alongside text using any vision-capable model (LLaVA, Gemini, GPT-4o, etc.).

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/playground.png" width="750" alt="RESTai Inference"/>
</div>

### Block (Visual Logic Builder)

Build processing logic visually using a Blockly-based IDE — no LLM required. Drag-and-drop blocks to define how input is transformed into output. Use the "Call Project" block to invoke other RESTai projects, enabling composition of AI pipelines without writing code.

**Supported blocks:** text operations, math, logic, variables, loops, and custom RESTai blocks (Get Input, Set Output, Call Project, Log).

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/block.png" width="750" alt="RESTai Block IDE"/>
</div>

### MCP Server

RESTai includes an optional built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that exposes your projects as tools consumable by any MCP client — Claude Desktop, Cursor, or custom agents. Each user authenticates with a Bearer API key and can only access their assigned projects.

Enable via `MCP_SERVER=true` environment variable or the admin settings page (requires restart). Clients connect to `http://your-host:9000/mcp/sse`.

**Available tools:**
- `list_projects` — Discover which AI projects you have access to
- `query_project` — Send a question (with optional image) to any accessible project

### Evaluation Framework

Built-in evaluation system to measure and track AI project quality over time. Create test datasets with question/expected-answer pairs, run evaluations with multiple metrics, and visualize score trends.

**Metrics** (powered by [DeepEval](https://github.com/confident-ai/deepeval)):
- **Answer Relevancy** — Is the answer relevant to the question?
- **Faithfulness** — Is the answer grounded in the retrieved context? (RAG projects)
- **Correctness** — Does the answer match the expected output?

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/eval.png" width="750" alt="RESTai Evaluation"/>
</div>

### Prompt Versioning

Every system prompt change is automatically versioned. Browse the full history, compare versions, and restore any previous prompt with one click. Eval runs are linked to prompt versions, enabling A/B comparison — see exactly how a prompt change affected quality scores.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/prompts.png" width="750" alt="RESTai Prompt Versioning"/>
</div>

### Image Generation

Local and remote image generators loaded dynamically. Supports Stable Diffusion, Flux, DALL-E, RMBG2, and more.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/image.png" width="45%" alt="Flux1"/>
</div>

### GPU Auto-Detection & Management

RESTai automatically detects NVIDIA GPUs at startup and displays detailed hardware information in the admin settings — model name, VRAM, temperature, utilization, power draw, driver and CUDA versions. GPU support is auto-enabled when hardware is detected, or can be toggled manually.

`make install` also detects GPUs automatically and installs GPU dependencies when available.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/gpus.png" width="750" alt="RESTai GPU Detection"/>
</div>

### Direct Access (OpenAI-Compatible)

Use LLMs, image generators, and audio transcription directly via OpenAI-compatible API endpoints — no project required. Team-level permissions control which models each user can access, and all usage counts toward team budgets.

**Supported endpoints:**
- `POST /v1/chat/completions` — Chat with any LLM (streaming supported)
- `POST /v1/images/generations` — Generate images via DALL-E, Flux, Stable Diffusion, etc.
- `POST /v1/audio/transcriptions` — Transcribe audio files

Works with any OpenAI-compatible SDK:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:9000/v1", api_key="YOUR_API_KEY")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/directaccess.png" width="750" alt="RESTai Direct Access"/>
</div>

### Teams & Multi-tenancy

Each team has its own users, admins, projects, and LLM/embedding access controls — including image and audio generator permissions. Users can belong to multiple teams, each with optional custom branding.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/teams.png" width="750" alt="RESTai Teams"/>
</div>

### Custom Branding (White-Labeling)

Each team can customize the platform appearance for its members — ideal for white-labeling or multi-tenant deployments where different teams need distinct identities.

**Configurable per team:**
- **App Name** — Override the platform name in the sidebar and header
- **Logo** — Custom logo via URL or data URI (replaces the default logo)
- **Primary & Secondary Colors** — Full MUI theme color override with live color picker
- **Welcome Message** — Custom landing text for team members

**Multi-team users:** When a user belongs to multiple branded teams, a team switcher appears in the sidebar letting them choose which branding to apply. The preference is persisted in user settings.

**API:** `GET /teams/{id}/branding` returns team branding without authentication (useful for custom login pages). Update branding via `PATCH /teams/{id}` with a `branding` object.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/branding.png" width="750" alt="RESTai Branding"/>
</div>

### Two-Factor Authentication (TOTP)

Secure local user accounts with TOTP-based two-factor authentication, compatible with Google Authenticator, Authy, and other authenticator apps.

- **User self-service** — Enable/disable 2FA from the user profile page with QR code setup and one-time recovery codes
- **Admin enforcement** — Platform admins can enforce 2FA for all local users via the settings page (users cannot disable when enforced)
- **Recovery codes** — 8 single-use codes generated during setup for account recovery if the authenticator is lost
- **Local auth only** — 2FA applies to username/password login; SSO and API key authentication are unaffected
- **Encrypted secrets** — TOTP secrets are encrypted at rest using Fernet; recovery codes are stored as SHA-256 hashes

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/branding.png" width="750" alt="RESTai Branding"/>
</div>

### Guardrails

Protect your AI projects with input and output guards. Guards are regular RestAI projects — define safety rules via system prompts, and they'll evaluate every request and response automatically.

- **Input Guard** — Checks user questions before inference
- **Output Guard** — Checks LLM responses after inference
- **Block or Warn mode** — Hard-block unsafe content or flag it while passing through
- **Analytics dashboard** — Track block rates, view blocked requests, and monitor guard effectiveness over time

### Response Cache

Enable per-project response caching to speed up repeated or similar questions. Uses ChromaDB vector similarity to match incoming questions against cached answers — if a question is similar enough (above the configurable threshold), the cached answer is returned instantly without calling the LLM.

Works across all project types. Cache is automatically invalidated when the knowledge base changes (document ingestion or deletion). Configurable similarity threshold (default 0.85). Clear cache anytime via the project details page or API.

### Audit Log

Every mutation (create, update, delete) across the platform is automatically logged — who did what, when, and which resource was affected. Admins can review the full audit trail from the admin dashboard.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/audit.png" width="750" alt="RESTai Audit Log"/>
</div>

### Rate Limiting

Set per-project request limits to prevent abuse and control costs. Configure the maximum number of requests per minute in the project edit page. Returns HTTP 429 when the limit is exceeded.

### Knowledge Base Sync

Automatically keep your RAG knowledge base up-to-date by syncing from external sources on a schedule. Configure per project — each project manages its own sources and sync interval.

**Supported sources:**
- **Web URLs** — Periodically re-scrape web pages and update the knowledge base
- **Amazon S3** — Sync documents from S3 buckets with optional prefix filtering (supports all file types: PDF, DOCX, CSV, etc.)
- **Confluence** — Sync all pages from a Confluence Cloud space (HTML stripped to plain text, paginated)
- **SharePoint / Microsoft 365** — Sync files from a SharePoint Online document library via Microsoft Graph API (OAuth2 client credentials, optional folder filter)
- **Google Drive** — Sync files from a Drive folder via service account (supports native Google Docs/Sheets/Slides export + binary files)

**Features:**
- Configurable sync intervals (15 minutes to 24 hours)
- Multiple sources per project with independent settings (splitter, chunk size)
- Manual "Sync Now" trigger via UI or API (`POST /projects/{id}/sync/trigger`)
- Last sync timestamp tracking
- All credentials masked in API responses (S3 keys, Confluence tokens, SharePoint secrets, Drive service account JSON)

### Telegram & Slack Integration

Connect any project to **Telegram** or **Slack** — messages are processed through the project's chat pipeline and responses are sent back automatically. No public URL required.

- **Telegram** — Paste your [BotFather](https://t.me/BotFather) token in the project settings
- **Slack** — Create a Slack app at [api.slack.com](https://api.slack.com), enable Socket Mode, and paste the Bot Token (xoxb-...) and App Token (xapp-...) in the project settings

### Settings & Configuration

White-label the UI, configure currency for cost tracking, set agent iteration limits, manage LLM proxy, and more.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/settings.png" width="750" alt="RESTai Settings"/>
</div>

---

## Supported LLMs

Any LLM provider supported by LlamaIndex. Each model has a configurable context window with automatic chat memory management — older messages are summarized rather than dropped.

| Provider | Class | Type |
|----------|-------|------|
| [Ollama](https://ollama.com/) | `Ollama` / `OllamaMultiModal` | chat / vision |
| [OpenAI](https://platform.openai.com/) | `OpenAI` | chat |
| [Anthropic](https://www.anthropic.com/) | `Anthropic` | chat |
| [Google Gemini](https://ai.google.dev/) | `Gemini` / `GeminiMultiModal` | chat / vision |
| [Groq](https://groq.com/) | `Groq` | chat |
| [Grok (xAI)](https://x.ai/) | `Grok` | chat |
| [LiteLLM](https://litellm.ai/) | `LiteLLM` | chat |
| [vLLM](https://vllm.ai/) | `vLLM` | chat |
| [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) | `AzureOpenAI` | chat |
| OpenAI-Compatible | `OpenAILike` | chat |

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/llms.png" width="750" alt="RESTai LLMs"/>
</div>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/ollama.png" width="750" alt="RESTai Ollama"/>
</div>

---

## Tech Stack

**Backend:** [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://www.sqlalchemy.org/) · [LlamaIndex](https://www.llamaindex.ai/) · [Alembic](https://alembic.sqlalchemy.org/)
**Frontend:** [React 18](https://react.dev/) · [MUI v5](https://mui.com/) · [Redux Toolkit](https://redux-toolkit.js.org/)
**Vector Stores:** [ChromaDB](https://www.trychroma.com/) · [PGVector](https://github.com/pgvector/pgvector) · [Weaviate](https://weaviate.io/) · [Pinecone](https://www.pinecone.io/)
**Databases:** SQLite (default) · PostgreSQL · MySQL
**Package Manager:** [uv](https://github.com/astral-sh/uv)

---

## API

All endpoints are documented via [Swagger](https://apocas.github.io/restai/swagger/) and [API reference](https://apocas.github.io/restai/api.html).

**Create a project:**

```bash
curl -X POST http://localhost:9000/projects \
  -u admin:admin \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my-rag",
    "type": "rag",
    "llm": "gpt-4o",
    "embeddings": "text-embedding-3-small",
    "vectorstore": "chroma"
  }'
```

**Chat with a project:**

```bash
curl -X POST http://localhost:9000/projects/my-rag/chat \
  -u admin:admin \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is RESTai?"}'
```

---

## Installation

RESTai uses [uv](https://github.com/astral-sh/uv) for dependency management. Python 3.11+ required.

### Local

```bash
make install    # Install deps, initialize DB, build frontend
make dev        # Development server with hot reload (port 9000)
make start      # Production server (4 workers, port 9000)
```

Default credentials: `admin` / `admin` (configurable via `RESTAI_DEFAULT_PASSWORD`).

### Docker

```bash
# Edit .env with your configuration, then:
docker compose --env-file .env up --build
```

Optional profiles for additional services:

```bash
docker compose --env-file .env --profile redis up --build      # + Redis
docker compose --env-file .env --profile postgres up --build   # + PostgreSQL
docker compose --env-file .env --profile mysql up --build      # + MySQL
```

### Kubernetes (Helm)

A Helm chart is provided in `chart/restai/`.

```bash
helm install restai chart/restai/ \
  --set config.database.postgres.host=my-postgres \
  --set secrets.postgresPassword=mypassword
```

For production with multiple replicas, set fixed secrets for JWT and encryption:

```bash
helm install restai chart/restai/ \
  --set config.database.postgres.host=postgres \
  --set secrets.postgresPassword=mypassword \
  --set secrets.authSecret=$(openssl rand -base64 48) \
  --set secrets.ssoSecretKey=$(openssl rand -base64 48) \
  --set secrets.fernetKey=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
```

See `chart/restai/` for full Helm values and configuration options.

---

## Architecture

### Stateless (Production)

No state stored in the RESTai service — ideal for horizontal scaling.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateless.png" width="750" alt="RESTai Stateless Architecture"/>
</div>

### Stateful (Development)

Direct interaction with the GPU layer — ideal for small deployments.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateful.png" width="750" alt="RESTai Stateful Architecture"/>
</div>

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RESTAI_DEFAULT_PASSWORD` | Admin user password | `admin` |
| `RESTAI_DEV` | Enable dev mode with hot reload | `false` |
| `RESTAI_GPU` | Enable GPU features (image gen) | auto-detected |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `POSTGRES_HOST` | Use PostgreSQL instead of SQLite | — |
| `MYSQL_HOST` | Use MySQL instead of SQLite | — |
| `REDIS_HOST` / `REDIS_PORT` | Redis for persistent chat history | — |
| `CHROMADB_HOST` / `CHROMADB_PORT` | Remote ChromaDB for vector storage | — |
| `MCP_SERVER` | Enable built-in MCP server at `/mcp/sse` | `false` |

Full configuration in [`restai/config.py`](restai/config.py).

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

```bash
make dev        # Run dev server
pytest tests    # Run tests
make code       # Format with black
```

> **Note:** This project started as 100% human-written code. Nowadays, only a small percentage of the codebase is human-developed — the majority is AI-generated.

---

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache License, Version 2.0. See [LICENSE](http://www.apache.org/licenses/LICENSE-2.0.html) for details.
