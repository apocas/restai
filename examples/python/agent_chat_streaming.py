"""Agent project: streaming a response, and multi-turn conversation memory.

An `agent` project is LLM chat that can optionally call tools / MCP servers. With
no tools enabled it behaves like a plain conversational LLM — all we need to show
streaming and memory.

Part 1 — Streaming (Server-Sent Events). Set {"stream": true} and the server emits:
    data: {"text": "Hel"}        ← incremental answer tokens (concatenate them)
    data: {"text": "lo"}
    ...
    data: {"answer": "...", "sources": [...], "type": "...", "id": "..."}   ← final object
  (Agent projects may also emit {"plan": [...]} and tool-activity objects.)

Part 2 — Memory. Reuse the same conversation `id` across turns and the agent
remembers earlier messages. We use non-streaming turns here: it keeps the example
simple and is the cleanest way to show continuity. (Streaming also accepts an `id`
for resumable reconnects — RESTai buffers an in-flight stream for ~5 minutes so a
dropped connection can re-attach without re-running the model.)

    python agent_chat_streaming.py
"""

from restai_client import RestaiClient, RestaiError, stream_answer

PROJECT_NAME = "examples_agent_chat"


def main() -> None:
    client = RestaiClient()
    print(f"→ RESTai at {client.base_url}")

    llm = client.pick_llm()
    print(f"→ using LLM '{llm}'")
    team_id = client.ensure_team("examples", llms=[llm])

    # Agent projects don't need embeddings or a vectorstore.
    project_id = client.get_or_create_project(
        PROJECT_NAME, "agent", team_id,
        llm=llm,
        human_name="Agent Chat",
        human_description="Streaming + memory example (agent_chat_streaming.py)",
    )
    client.edit_project(project_id, system="You are a concise, friendly assistant.")
    print(f"→ project id {project_id}\n")

    # ── Part 1: stream a single answer (no conversation id = ephemeral turn) ──
    print("── Streaming ───────────────────────────────────────")
    print("You: Explain what RESTai is in two sentences.")
    print("Bot: ", end="")
    answer = stream_answer(client.chat_stream(project_id, "Explain what RESTai is in two sentences."))
    # `answer` now holds the full text (stream_answer also printed it live).

    # ── Part 2: a multi-turn conversation that relies on memory ──────────────
    print("\n── Conversation (shared id → memory) ────────────────")
    conversation_id = "demo-conversation-1"  # any [A-Za-z0-9_-] string
    for question in [
        "My name is Ada. Remember it.",
        "What's my name, and what are RESTai's three project types?",  # needs turn-1 memory
    ]:
        print(f"You: {question}")
        reply = client.chat(project_id, question, chat_id=conversation_id)
        print(f"Bot: {reply['answer']}\n")


if __name__ == "__main__":
    try:
        main()
    except RestaiError as e:
        raise SystemExit(f"RESTai error: {e}")
