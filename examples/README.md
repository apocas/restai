# RESTai examples

Runnable, copy-pasteable examples for consuming a RESTai instance over its REST API.

Everything here talks to a **live RESTai server**. Point the examples at your own
instance (`http://localhost:9000` by default) or at the public demo.

```
examples/
├── curl_cookbook.sh            # The whole lifecycle as annotated curl commands
├── python/
│   ├── restai_client.py        # Small dependency-light client (requests) reused below
│   ├── rag_quickstart.py       # Create a RAG project, ingest, ask, search, clean up
│   ├── agent_chat_streaming.py # Agent project + multi-turn streaming chat (SSE)
│   ├── direct_openai_sdk.py    # Use the official `openai` SDK against /v1 (no project)
│   ├── describe_video/         # Vision: describe an mp4/YouTube video frame-by-frame
│   └── image_categorization/   # Vision + zero-shot classifier
├── php/                        # Minimal PHP client (Modem + Project) and a demo
└── widget/                     # Drop-in HTML chat widget (one <script> tag)
```

## Prerequisites

1. **A running RESTai server.** See the top-level [README](../README.md) — `make dev`
   (source) or `docker run -p 9000:9000 apocas/restai:latest`. Defaults to
   `http://localhost:9000`, admin / admin.

2. **At least one LLM configured** (and an embeddings model for RAG examples).
   RESTai ships with **no models pre-seeded** — add them in the admin UI under
   **Settings → LLMs / Embeddings** (`/admin`), or via `POST /llms`. The examples
   auto-discover whatever you've configured, so you don't hard-code model names.

3. **A team that the project can belong to.** Projects are owned by a team, and the
   team must be granted access to the LLM/embeddings the project uses. The Python and
   curl examples create (or reuse) a team called `examples` and grant it the models
   they pick — you don't have to set this up by hand.

## Configuration (environment variables)

Every example reads the same env vars, so you set them once:

| Variable             | Default                 | Purpose                                                        |
| -------------------- | ----------------------- | -------------------------------------------------------------- |
| `RESTAI_URL`         | `http://localhost:9000` | Base URL of your RESTai server                                 |
| `RESTAI_API_KEY`     | _(unset)_               | Bearer API key. **Preferred.** When set, used instead of Basic |
| `RESTAI_USER`        | `admin`                 | Basic-auth username (used only when `RESTAI_API_KEY` is unset) |
| `RESTAI_PASSWORD`    | `admin`                 | Basic-auth password                                            |
| `RESTAI_LLM`         | _(auto-discovered)_     | Force a specific LLM name instead of auto-picking              |
| `RESTAI_VISION_LLM`  | _(auto-discovered)_     | LLM name to use for the vision examples (must accept images)   |
| `RESTAI_EMBEDDINGS`  | _(auto-discovered)_     | Force a specific embeddings model name                         |

### Getting an API key

Basic auth (`admin` / `admin`) works out of the box for local dev, but for anything
real, mint a scoped key:

```bash
curl -s -X POST http://localhost:9000/users/admin/apikeys \
  -u admin:admin -H 'Content-Type: application/json' \
  -d '{"description": "examples", "read_only": false}'
# → {"api_key": "sk-...", ...}   (shown only once)

export RESTAI_API_KEY="sk-..."
```

You can scope a key to specific projects and make it read-only — see
`POST /users/{username}/apikeys` in the [Swagger docs](https://restai.cloud/swagger/).

## Running

```bash
# Python (Python 3.9+)
cd python
pip install -r requirements.txt
python rag_quickstart.py

# curl walkthrough
./curl_cookbook.sh

# PHP
php php/main.php
```

The full, always-current API reference is the Swagger UI on your own instance at
`http://localhost:9000/docs` (or the hosted copy at <https://restai.cloud/swagger/>).
