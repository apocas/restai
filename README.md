<!-- markdownlint-disable MD033 -->

<h1 align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai-logo.png?raw=true" alt="RESTai Logo" width="120"/>
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

<p align="center">
  <b>Demo:</b> <a href="https://ai.ince.pt">https://ai.ince.pt</a> &nbsp;—&nbsp; Username: <code>demo</code> &nbsp; Password: <code>demo</code>
</p>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/home.png?raw=true" width="800" alt="RESTai Dashboard"/>
</div>

---

## Quick Start

```bash
git clone https://github.com/apocas/restai && cd restai
make install
make dev  # → http://localhost:9000/admin (admin / admin)
```

**Or with Docker:**

```bash
docker compose --env-file .env up --build
```

---

## Why RESTai?

- **Multi-project AI platform** — RAG, Agents, Routers, SQL-to-NL, and Inference in one place
- **Full Web UI included** — React dashboard with analytics, not just an API
- **Any LLM** — OpenAI, Anthropic, Ollama, Gemini, Groq, LiteLLM, vLLM, Azure, and more
- **Feature complete** — Teams, RBAC, OAuth/LDAP, token tracking, Kubernetes-native
- **Extensible tools** — MCP (Model Context Protocol) for unlimited agent integrations
- **Token tracking & cost analytics** — built-in dashboard with daily usage, per-project costs, and top LLM charts

---

## Features

### Dashboard & Analytics

Track token usage, costs, and project activity from a centralized dashboard. Daily charts, top projects, and LLM distribution at a glance.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/home.png?raw=true" width="750" alt="RESTai Dashboard"/>
</div>

### Projects & Chat Playground

Create and manage AI projects. Each project has its own LLM, system prompt, tools, and configuration. Test instantly in the built-in chat playground.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/projects.png?raw=true" width="750" alt="RESTai Projects"/>
</div>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/playground.png?raw=true" width="750" alt="RESTai Playground"/>
</div>

### RAG (Retrieval-Augmented Generation)

Upload documents and query them with LLM-powered retrieval. Supports multiple vector stores, reranking (ColBERT / LLM-based), sandboxed mode to reduce hallucination, and evaluation via [deepeval](https://github.com/confident-ai/deepeval).

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rag.png?raw=true" width="750" alt="RESTai RAG"/>
</div>

### RAGSQL (Natural Language to SQL)

Connect a MySQL or PostgreSQL database — RESTai crawls the schema and translates natural language questions into SQL queries automatically.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/ragsql.jpg?raw=true" width="750" alt="RESTai RAGSQL"/>
</div>

### Agents + MCP

Zero-shot ReAct agents with built-in tools and [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server support for extensible tool access. Connect any MCP-compatible server via HTTP/SSE or stdio.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/agent1.png?raw=true" width="40%" alt="RESTai Agent"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/agent2.png?raw=true" width="40%" alt="RESTai Agent Tools"/>
</div>

### Inference (Multimodal)

Direct LLM chat and completion. Supports sending images alongside text using any vision-capable model (LLaVA, Gemini, GPT-4o, etc.).

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/inference.png?raw=true" width="750" alt="RESTai Inference"/>
</div>

### Router

Routes queries to the most suitable project automatically. Similar to a zero-shot ReAct strategy, but each route is a project scored by relevance.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/router.png?raw=true" width="750" alt="RESTai Router"/>
</div>

### Image Generation

Local and remote image generators loaded dynamically. Supports Stable Diffusion, Flux, DALL-E, RMBG2, and more.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/flux1.png?raw=true" width="45%" alt="Flux1"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/vision_sd.png?raw=true" width="22%" alt="Stable Diffusion"/>
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rmbg2.png?raw=true" width="22%" alt="RMBG2"/>
</div>

### Teams & Multi-tenancy

Each team has its own users, admins, projects, and LLM/embedding access controls. Users can belong to multiple teams.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/teams.png?raw=true" width="750" alt="RESTai Teams"/>
</div>

### Telegram Integration

Connect any project to Telegram via [BotFather](https://t.me/BotFather). Messages are processed through the project's chat pipeline and responses are sent back automatically.

### Settings & Configuration

White-label the UI, configure currency for cost tracking, set agent iteration limits, manage LLM proxy, and more.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/settings.png?raw=true" width="750" alt="RESTai Settings"/>
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
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/llms.png?raw=true" width="750" alt="RESTai LLMs"/>
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
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateless.png?raw=true" width="750" alt="RESTai Stateless Architecture"/>
</div>

### Stateful (Development)

Direct interaction with the GPU layer — ideal for small deployments.

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai_stateful.png?raw=true" width="750" alt="RESTai Stateful Architecture"/>
</div>

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RESTAI_DEFAULT_PASSWORD` | Admin user password | `admin` |
| `RESTAI_DEV` | Enable dev mode with hot reload | `false` |
| `RESTAI_GPU` | Enable GPU features (image gen) | `false` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `POSTGRES_HOST` | Use PostgreSQL instead of SQLite | — |
| `MYSQL_HOST` | Use MySQL instead of SQLite | — |
| `REDIS_HOST` / `REDIS_PORT` | Redis for persistent chat history | — |
| `CHROMADB_HOST` / `CHROMADB_PORT` | Remote ChromaDB for vector storage | — |
| `MCP_SERVER` | Enable MCP server endpoint | — |

Full configuration in [`restai/config.py`](restai/config.py).

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

```bash
make dev        # Run dev server
pytest tests    # Run tests
make code       # Format with black
```

---

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache License, Version 2.0. See [LICENSE](http://www.apache.org/licenses/LICENSE-2.0.html) for details.
