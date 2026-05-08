def search_memories(query: str, k: int = 5, **kwargs) -> str:
    """Search this project's full conversation history for past turns
    semantically related to `query`. Returns the top-`k` matches sorted
    by relevance, with the date, chat id, and the original Q/A text.

    Use this whenever the user asks about something that might have come
    up in a previous chat — instead of guessing or saying you don't
    remember, search first. Examples of when to call:
      - "Have we talked about X before?"
      - "What did I decide last month about Y?"
      - "Remind me what we agreed on regarding Z."

    Args:
        query (str): What to find. Be specific — multi-keyword queries
            ("auth flow rollout decisions") work better than single
            words ("auth").
        k (int): Max results to return, clamped to [1, 20]. Default 5.
    """
    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")
    if brain is None or project_id is None:
        return "ERROR: search_memories requires project context."
    if not query or not query.strip():
        return "ERROR: query is required."

    try:
        k = int(k)
    except Exception:
        k = 5
    k = max(1, min(20, k))

    from restai.database import open_db_wrapper
    from restai import memory_search

    db = open_db_wrapper()
    try:
        project = db.get_project_by_id(int(project_id))
        if project is None:
            return "ERROR: project not found."
        embedding_name = (project.embeddings or "").strip()
        if not embedding_name:
            return (
                "ERROR: search_memories requires an embedding configured "
                "on this project. Ask an admin to set one in project settings."
            )
        embedding = brain.get_embedding(embedding_name, db)
        if embedding is None:
            return (
                f"ERROR: embedding '{embedding_name}' is not resolvable. "
                "Ask an admin to verify it in /admin/embeddings."
            )

        try:
            qvec = list(embedding.embedding.get_text_embedding(query))
        except Exception as e:
            return f"ERROR: failed to embed query: {e}"

        try:
            hits = memory_search.search(int(project_id), qvec, k)
        except Exception as e:
            return f"ERROR: memory search failed: {e}"
    finally:
        db.db.close()

    if not hits:
        return "No memories matched this query."

    # Format header + per-hit blocks. We bound total output to ~3000
    # chars so a chatty hit set can't crowd the agent's context budget;
    # truncate the per-hit text first, then drop oldest hits if still
    # over budget.
    OUTPUT_BUDGET = 3000
    PER_HIT_TEXT_CAP = 800

    blocks: list[str] = []
    for h in hits:
        date_short = (h.get("date_iso") or "")[:10] or "—"
        chat_short = (h.get("chat_id") or "")[:8] or "—"
        score = h.get("score") or 0.0
        text = (h.get("document") or "").strip()
        if len(text) > PER_HIT_TEXT_CAP:
            text = text[: PER_HIT_TEXT_CAP - 1].rstrip() + "…"
        blocks.append(
            f"[{date_short} · chat {chat_short} · score {score:.2f}]\n{text}"
        )

    header = f'Found {len(blocks)} memory match(es) for "{query.strip()}":'
    out = header + "\n\n" + "\n\n".join(blocks)

    # If we're over budget, drop oldest hits (end of list) until we fit.
    while len(out) > OUTPUT_BUDGET and len(blocks) > 1:
        blocks.pop()
        out = header + "\n\n" + "\n\n".join(blocks) + "\n\n[…older matches truncated]"

    return out
