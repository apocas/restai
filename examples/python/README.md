# Python examples

```bash
pip install -r requirements.txt

# Optional — point at your server / use a scoped key (defaults: localhost:9000, admin/admin)
export RESTAI_URL="http://localhost:9000"
export RESTAI_API_KEY="sk-..."
```

| Example                     | What it shows                                                       | Needs                          |
| --------------------------- | ------------------------------------------------------------------- | ------------------------------ |
| `rag_quickstart.py`         | Full RAG lifecycle: team → project → ingest → ask (w/ sources) → search → cleanup | 1 LLM + 1 embeddings |
| `agent_chat_streaming.py`   | Agent project, multi-turn **streaming** chat over SSE               | 1 LLM                          |
| `direct_openai_sdk.py`      | The official `openai` SDK against RESTai's `/v1` (no project needed) | 1 LLM (+ embeddings, optional) |
| `describe_video/`           | Vision — describe a video frame-by-frame, then summarize            | 1 vision LLM                   |
| `image_categorization/`     | Vision + zero-shot classifier                                       | 1 vision LLM                   |

`restai_client.py` is a ~250-line `requests` wrapper the first three import. The two
vision folders use raw `requests` on purpose, so each is a self-contained reference
for the multimodal flow.

> RESTai seeds **no** models. Configure at least one LLM (and an embeddings model for
> RAG) under `/admin` first — the examples auto-discover whatever you've added. Force a
> specific one with `RESTAI_LLM` / `RESTAI_VISION_LLM` / `RESTAI_EMBEDDINGS`.
