"""Use the official OpenAI SDK against RESTai's OpenAI-compatible /v1 endpoints.

RESTai exposes "direct access" — call any configured LLM/embeddings model straight,
without creating a project. Team permissions still apply and usage counts toward team
budgets. Because the surface is OpenAI-compatible, any OpenAI SDK works: just point
`base_url` at `<your-restai>/v1`.

    POST /v1/chat/completions   (streaming supported)
    POST /v1/embeddings
    GET  /v1/models             (lists the LLM names you can use)
    POST /v1/images/generations      (if an image generator is configured)
    POST /v1/audio/transcriptions    (if an STT model is configured)

The `model` you pass is the **name** of the model as configured in RESTai (in
/admin → LLMs), not an OpenAI model id.

Auth: the OpenAI SDK sends a Bearer token, so this example needs a real
RESTAI_API_KEY (HTTP Basic / admin:admin won't work through the SDK). Mint one:

    curl -X POST $RESTAI_URL/users/admin/apikeys -u admin:admin \\
         -H 'Content-Type: application/json' -d '{"description":"examples"}'
    export RESTAI_API_KEY="sk-..."

    pip install openai
    python direct_openai_sdk.py
"""

import os

import requests
from openai import OpenAI

BASE = os.getenv("RESTAI_URL", "http://localhost:9000").rstrip("/")
API_KEY = os.getenv("RESTAI_API_KEY")
if not API_KEY:
    raise SystemExit(
        "Set RESTAI_API_KEY — the OpenAI SDK authenticates with a Bearer token "
        "(Basic auth isn't usable through the SDK). See the module docstring for "
        "the one-liner to mint a key."
    )


def main() -> None:
    client = OpenAI(base_url=f"{BASE}/v1", api_key=API_KEY)
    print(f"→ Direct access at {BASE}/v1")

    # Discover LLM names this server exposes (GET /v1/models).
    models = [m.id for m in client.models.list().data]
    if not models:
        raise SystemExit("No LLMs available to this key. Configure one in /admin first.")
    model = os.getenv("RESTAI_LLM") or models[0]
    print(f"→ LLMs: {models}")
    print(f"→ using '{model}'\n")

    # 1. Plain chat completion.
    print("── chat.completions ────────────────────────────────")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are terse."},
            {"role": "user", "content": "Say hello to RESTai in one short sentence."},
        ],
    )
    print(resp.choices[0].message.content)

    # 2. Streaming chat completion (standard OpenAI SSE — the SDK handles it).
    print("\n── chat.completions (stream) ───────────────────────")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Count from 1 to 5, space-separated."}],
        stream=True,
    )
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()

    # 3. Embeddings — needs an embeddings model. /v1/models lists only LLMs, so we
    #    discover one via GET /embeddings (or set RESTAI_EMBEDDINGS).
    print("\n── embeddings ──────────────────────────────────────")
    emb_model = os.getenv("RESTAI_EMBEDDINGS")
    if not emb_model:
        embs = requests.get(f"{BASE}/embeddings",
                            headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30).json()
        emb_model = embs[0]["name"] if embs else None
    if emb_model:
        out = client.embeddings.create(model=emb_model, input="vector me")
        print(f"'{emb_model}' → {len(out.data[0].embedding)}-dim vector")
    else:
        print("(no embeddings model configured — skipped)")


if __name__ == "__main__":
    main()
