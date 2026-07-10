async def search_knowledge(query: str, **kwargs) -> str:
    """Search the project's configured knowledge base (a RAG project) and return
    the most relevant answer and supporting sources.

    Use this whenever you need facts, documents, or context that live in the
    knowledge base to answer the user. The knowledge base is fixed by the
    project's configuration — you only choose WHAT to search for, never WHICH
    knowledge base.

    Args:
        query (str): A focused natural-language search query describing the
            information you need (e.g. "refund policy for damaged items").
    """
    import json

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")
    user = kwargs.get("_user")

    if brain is None or project_id is None or user is None:
        return (
            "ERROR: search_knowledge requires the RESTai agent loop "
            "(set Agent Loop to 'RESTai' on this project)."
        )

    from restai.database import open_db_wrapper
    from restai.auth import user_can_access_project
    from restai.models.models import ChatModel
    from restai.projects.rag import RAG

    db = open_db_wrapper()
    try:
        agent_proj = db.get_project_by_id(int(project_id))
        if agent_proj is None:
            return f"ERROR: project {project_id} not found."

        try:
            opts = json.loads(agent_proj.options) if agent_proj.options else {}
        except Exception:
            opts = {}

        target_name = (opts.get("search_knowledge_project") or "").strip()
        if not target_name:
            return (
                "ERROR: no knowledge-search project configured for this agent. "
                "Set it in project edit → Tools → Knowledge Search."
            )

        target = db.get_project_by_name(target_name)
        if target is None:
            return f"ERROR: configured knowledge project '{target_name}' no longer exists."
        if target.type != "rag":
            return f"ERROR: knowledge project '{target_name}' is not a RAG project."

        # Structural boundary: the consumed RAG project must live in the same
        # team as this agent project.
        if target.team_id is None or target.team_id != agent_proj.team_id:
            return f"ERROR: knowledge project '{target_name}' is not in this agent's team."

        # Permission boundary: the user running this agent must also have access
        # to the consumed RAG project. Never reveal its contents otherwise.
        if not user_can_access_project(user, target.id, db):
            return f"ERROR: you do not have access to the knowledge project '{target_name}'."

        proj = brain.find_project(target.id, db)
        if proj is None:
            return f"ERROR: failed to load knowledge project '{target_name}'."

        q = ChatModel(question=query, stream=False, id=None)
        result = None
        async for line in RAG(brain).chat(proj, q, user, db):
            if isinstance(line, dict):
                result = line
            break

        if not result:
            return f"No results found in '{target_name}' for: {query}"

        # Account this nested RAG inference against the target knowledge project
        # (it bypasses chat_main, so it would otherwise be off the books).
        try:
            from restai.tools import log_inference
            result.setdefault("question", query)
            log_inference(proj, user, result, db)
        except Exception:
            pass

        answer = (result.get("answer") or "").strip()
        sources = result.get("sources") or []

        parts = []
        if answer:
            parts.append(f"ANSWER:\n{answer}")
        if sources:
            lines = []
            for i, s in enumerate(sources[:8], 1):
                if isinstance(s, dict):
                    score = s.get("score")
                    text = (s.get("text") or "").strip().replace("\n", " ")
                    if len(text) > 500:
                        text = text[:500] + "…"
                    origin = s.get("source") or s.get("id") or ""
                    score_str = f"({score:.2f}) " if isinstance(score, (int, float)) else ""
                    suffix = f" — {origin}" if origin else ""
                    lines.append(f"[{i}] {score_str}{text}{suffix}")
                else:
                    lines.append(f"[{i}] {str(s)[:500]}")
            parts.append("SOURCES:\n" + "\n".join(lines))

        if not parts:
            return f"No results found in '{target_name}' for: {query}"
        return f"Knowledge base '{target_name}':\n\n" + "\n\n".join(parts)
    except Exception as e:
        return f"ERROR: knowledge search failed: {e}"
    finally:
        db.db.close()
