"""RAG quickstart — the full lifecycle of a Retrieval-Augmented Generation project.

    team  →  project  →  ingest knowledge  →  ask (grounded answer + sources)
          →  semantic search  →  cleanup

This is the modern replacement for the old PHP `main.php` demo. Run it against a
server that has at least one LLM and one embeddings model configured (see
../README.md). Models are auto-discovered — nothing is hard-coded.

    python rag_quickstart.py
"""

import os

from restai_client import RestaiClient, RestaiError

PROJECT_NAME = "examples_rag_quickstart"


def main() -> None:
    client = RestaiClient()
    print(f"→ RESTai at {client.base_url}")

    # 1. Discover which models this server actually has, and make sure a team
    #    can use them. Projects must belong to a team that's been granted the
    #    LLM + embeddings.
    llm = client.pick_llm()
    embeddings = client.pick_embeddings()
    print(f"→ using LLM '{llm}' and embeddings '{embeddings}'")
    team_id = client.ensure_team("examples", llms=[llm], embeddings=[embeddings])

    # 2. Create the RAG project (idempotent — reuse if it already exists).
    project_id = client.get_or_create_project(
        PROJECT_NAME, "rag", team_id,
        llm=llm, embeddings=embeddings, vectorstore="chroma",
        human_name="RAG Quickstart",
        human_description="Example knowledge base created by rag_quickstart.py",
    )
    print(f"→ project id {project_id}")

    # Optional: tune retrieval and give it a persona. Everything here is a PATCH
    # on the project; `options` carries the retrieval knobs.
    client.edit_project(
        project_id,
        system="Answer only from the provided context. If it isn't there, say you don't know.",
        options={"k": 4, "score": 0.0},
    )

    # 3. Ingest knowledge. You can push raw text or have the server crawl a URL.
    client.ingest_text(
        project_id,
        text=(
            "RESTai is an AIaaS platform for building AI projects and consuming them over "
            "a REST API. It supports three project types: RAG (retrieval-augmented "
            "generation, optionally with natural-language-to-SQL), agent (LLM chat with "
            "optional tool calling and MCP), and block (a visual logic builder). "
            "The meaning of life, the universe, and everything is 42."
        ),
        source="restai-overview",
        keywords=["restai", "platform", "rag", "agent", "block"],
    )
    print("→ ingested text")

    try:
        url = "https://raw.githubusercontent.com/apocas/restai/master/README.md"
        info = client.ingest_url(project_id, url, chunks=512)
        print(f"→ ingested {url} ({info['chunks']} chunks)")
    except RestaiError as e:
        # URL ingest needs outbound network + a working web reader; don't fail the demo.
        print(f"→ skipped URL ingest ({e.detail})")

    # 4. Ask a grounded question. The answer comes back with the source chunks
    #    that were retrieved to produce it.
    print("\n── Question ─────────────────────────────────────────")
    print("Q: What is the meaning of life, and what project types does RESTai support?")
    reply = client.chat(
        project_id,
        "What is the meaning of life, and what project types does RESTai support?",
    )
    print(f"A: {reply['answer']}")
    sources = reply.get("sources") or []
    print(f"   ({len(sources)} source chunk(s) used)")

    # 5. Pure semantic search over the knowledge base (no LLM call).
    print("\n── Semantic search ─────────────────────────────────")
    for hit in client.search(project_id, "project types", k=3):
        print(f"   score={hit['score']:.3f}  source={hit['source']}")

    # 6. Cleanup. Comment this out if you want to inspect the project in /admin.
    if os.getenv("KEEP", "") not in ("1", "true", "yes"):
        client.delete_project(project_id)
        print(f"\n→ deleted project {project_id} (set KEEP=1 to keep it)")


if __name__ == "__main__":
    try:
        main()
    except RestaiError as e:
        raise SystemExit(f"RESTai error: {e}")
