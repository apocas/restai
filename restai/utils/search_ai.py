"""Natural-language admin search backed by the system LLM.

The system LLM translates a plain-English query into a small structured
query DSL. The DSL is then validated against a strict whitelist and
executed against the database with RBAC applied.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy import or_

from restai.models.databasemodels import (
    ProjectDatabase,
    UserDatabase,
    TeamDatabase,
    LLMDatabase,
    EmbeddingDatabase,
)

logger = logging.getLogger(__name__)


# ── Allowed entities and fields ─────────────────────────────────────────
#
# Each entity lists (field → spec):
#   type: "str" | "bool" | "int" | "float" | "enum"
#   ops:  list of allowed operators from: eq, ne, contains, gt, gte, lt, lte
#   values: only for "enum" fields — closed set of allowed values
#   model_attr: how to look the field up on the SQLAlchemy model (defaults to field name)

ENTITIES = {
    "projects": {
        "model": ProjectDatabase,
        "fields": {
            "name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "human_name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "type": {"type": "enum", "ops": ["eq", "ne"], "values": ["rag", "agent", "block"]},
            "llm": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "public": {"type": "bool", "ops": ["eq"]},
            "team_name": {"type": "str", "ops": ["eq", "contains"]},  # virtual
            "creator_username": {"type": "str", "ops": ["eq", "contains"]},  # virtual
        },
    },
    "users": {
        "model": UserDatabase,
        "fields": {
            "username": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "is_admin": {"type": "bool", "ops": ["eq"]},
            "is_restricted": {"type": "bool", "ops": ["eq"]},
            "is_private": {"type": "bool", "ops": ["eq"]},
        },
    },
    "teams": {
        "model": TeamDatabase,
        "fields": {
            "name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "description": {"type": "str", "ops": ["contains"]},
        },
    },
    "llms": {
        "model": LLMDatabase,
        "fields": {
            "name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "class_name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "privacy": {"type": "enum", "ops": ["eq", "ne"], "values": ["public", "private"]},
            "context_window": {"type": "int", "ops": ["eq", "gt", "gte", "lt", "lte"]},
        },
    },
    "embeddings": {
        "model": EmbeddingDatabase,
        "fields": {
            "name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "class_name": {"type": "str", "ops": ["eq", "ne", "contains"]},
            "privacy": {"type": "enum", "ops": ["eq", "ne"], "values": ["public", "private"]},
            "dimension": {"type": "int", "ops": ["eq", "gt", "gte", "lt", "lte"]},
        },
    },
}


# ── Prompt building ─────────────────────────────────────────────────────


def _describe_schema() -> str:
    """Human-readable description of the entities/fields/ops for the LLM prompt."""
    lines = []
    for ent, spec in ENTITIES.items():
        lines.append(f"\n{ent}:")
        for field, fspec in spec["fields"].items():
            line = f"  - {field} ({fspec['type']}, ops: {', '.join(fspec['ops'])})"
            if fspec.get("values"):
                line += f" values={fspec['values']}"
            lines.append(line)
    return "\n".join(lines)


def build_translation_prompt(query: str) -> str:
    return f"""You are a query parser for a platform admin search. Translate the user's natural-language query into a JSON object.

Allowed entities and fields:
{_describe_schema()}

Output JSON schema:
{{
  "entity": "projects" | "users" | "teams" | "llms" | "embeddings",
  "filters": [
    {{"field": "<field name>", "op": "<op>", "value": <value>}}
  ],
  "limit": <integer, default 20, max 100>
}}

Rules:
1. Pick ONE entity based on what the user is searching for.
2. Only use fields and operators from the allowed list above.
3. For string "contains" searches the match is case-insensitive.
4. Booleans must be literal true/false (not "true"/"false").
5. If the user's query can't be answered with the allowed fields, still return your best-effort JSON and include a "note" string field at the top level explaining the limitation.
6. Keep filters minimal — only add filters the user explicitly mentioned.
7. If the query is ambiguous about entity type, prefer "projects".
8. If no filters are needed (e.g. "show me all projects"), return an empty filters array.

Examples:
"projects using GPT-4" → {{"entity": "projects", "filters": [{{"field": "llm", "op": "contains", "value": "gpt-4"}}], "limit": 20}}
"restricted users" → {{"entity": "users", "filters": [{{"field": "is_restricted", "op": "eq", "value": true}}], "limit": 20}}
"rag projects in team engineering" → {{"entity": "projects", "filters": [{{"field": "type", "op": "eq", "value": "rag"}}, {{"field": "team_name", "op": "eq", "value": "engineering"}}], "limit": 20}}
"public llms" → {{"entity": "llms", "filters": [{{"field": "privacy", "op": "eq", "value": "public"}}], "limit": 20}}
"admin users" → {{"entity": "users", "filters": [{{"field": "is_admin", "op": "eq", "value": true}}], "limit": 20}}

User query: {query}

Output ONLY the JSON object. No markdown fences, no prose.
"""


# ── Parsing and validation ──────────────────────────────────────────────


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_llm_response(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def validate_query(parsed: dict) -> tuple[dict, list[str]]:
    """Validate and clamp a parsed query. Returns (cleaned_query, warnings)."""
    warnings: list[str] = []
    if not isinstance(parsed, dict):
        raise ValueError("Query must be an object")

    entity = parsed.get("entity")
    if entity not in ENTITIES:
        raise ValueError(f"Unknown entity: {entity}")

    spec = ENTITIES[entity]
    allowed_fields = spec["fields"]
    cleaned_filters = []

    for f in parsed.get("filters", []) or []:
        if not isinstance(f, dict):
            continue
        field = f.get("field")
        op = f.get("op")
        value = f.get("value")
        if field not in allowed_fields:
            warnings.append(f"Ignored unknown field: {field}")
            continue
        fspec = allowed_fields[field]
        if op not in fspec["ops"]:
            warnings.append(f"Ignored unsupported op '{op}' on field '{field}'")
            continue
        # Type coercion
        if fspec["type"] == "bool":
            if isinstance(value, str):
                value = value.lower() in ("true", "1", "yes")
            value = bool(value)
        elif fspec["type"] == "int":
            try:
                value = int(value)
            except (TypeError, ValueError):
                warnings.append(f"Ignored non-int value on '{field}'")
                continue
        elif fspec["type"] == "float":
            try:
                value = float(value)
            except (TypeError, ValueError):
                warnings.append(f"Ignored non-float value on '{field}'")
                continue
        elif fspec["type"] == "enum":
            if str(value) not in fspec["values"]:
                warnings.append(f"Ignored out-of-range value '{value}' on '{field}'")
                continue
            value = str(value)
        else:  # str
            if value is None:
                continue
            value = str(value)
        cleaned_filters.append({"field": field, "op": op, "value": value})

    try:
        limit = int(parsed.get("limit", 20) or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    return (
        {"entity": entity, "filters": cleaned_filters, "limit": limit},
        warnings,
    )


# ── Query execution ─────────────────────────────────────────────────────


def _apply_filter(query, model, entity: str, f: dict):
    field = f["field"]
    op = f["op"]
    value = f["value"]

    # Handle virtual fields on projects
    if entity == "projects":
        if field == "team_name":
            from restai.models.databasemodels import TeamDatabase
            query = query.join(TeamDatabase, ProjectDatabase.team_id == TeamDatabase.id)
            col = TeamDatabase.name
        elif field == "creator_username":
            from restai.models.databasemodels import UserDatabase
            query = query.join(UserDatabase, ProjectDatabase.creator == UserDatabase.id)
            col = UserDatabase.username
        else:
            col = getattr(model, field)
    else:
        col = getattr(model, field)

    if op == "eq":
        query = query.filter(col == value)
    elif op == "ne":
        query = query.filter(col != value)
    elif op == "contains":
        query = query.filter(col.ilike(f"%{value}%"))
    elif op == "gt":
        query = query.filter(col > value)
    elif op == "gte":
        query = query.filter(col >= value)
    elif op == "lt":
        query = query.filter(col < value)
    elif op == "lte":
        query = query.filter(col <= value)
    return query


def _apply_rbac(query, entity: str, user):
    """Apply permission scoping to the query based on the user's role."""
    if getattr(user, "is_admin", False):
        return query

    if entity == "projects":
        accessible_ids = set(user.get_project_ids()) if hasattr(user, "get_project_ids") else {p.id for p in (user.projects or [])}
        if user.admin_teams:
            admin_team_ids = {t.id for t in user.admin_teams}
            query = query.filter(
                or_(
                    ProjectDatabase.id.in_(accessible_ids),
                    ProjectDatabase.team_id.in_(admin_team_ids),
                )
            )
        else:
            query = query.filter(ProjectDatabase.id.in_(accessible_ids))
    elif entity == "users":
        # Regular users: can only see themselves. Team admins: members of their teams.
        visible_ids = {user.id}
        for team in (user.admin_teams or []):
            for u in getattr(team, "users", []) or []:
                visible_ids.add(u.id)
            for u in getattr(team, "admins", []) or []:
                visible_ids.add(u.id)
        query = query.filter(UserDatabase.id.in_(visible_ids))
    elif entity == "teams":
        # Regular users: only teams they belong to. Team admins: teams they admin.
        team_ids = {t.id for t in (user.teams or [])} | {t.id for t in (user.admin_teams or [])}
        query = query.filter(TeamDatabase.id.in_(team_ids))
    elif entity in ("llms", "embeddings"):
        # Regular users: only entities their teams have access to
        accessible_ids = set()
        for team in (user.teams or []) + (user.admin_teams or []):
            items = getattr(team, entity, []) or []
            for item in items:
                accessible_ids.add(item.id)
        model = ENTITIES[entity]["model"]
        query = query.filter(model.id.in_(accessible_ids))

    return query


def _row_to_result(entity: str, row) -> dict:
    """Normalize a DB row into a compact result dict for the frontend."""
    if entity == "projects":
        return {
            "entity": "projects",
            "id": row.id,
            "name": row.name,
            "subtitle": f"{row.type} · {row.llm or 'no llm'}",
            "path": f"/project/{row.id}",
        }
    if entity == "users":
        badges = []
        if row.is_admin:
            badges.append("admin")
        if row.is_restricted:
            badges.append("read-only")
        return {
            "entity": "users",
            "id": row.id,
            "name": row.username,
            "subtitle": ", ".join(badges) if badges else "user",
            "path": f"/user/{row.username}",
        }
    if entity == "teams":
        return {
            "entity": "teams",
            "id": row.id,
            "name": row.name,
            "subtitle": (row.description or "")[:80],
            "path": f"/team/{row.id}",
        }
    if entity == "llms":
        return {
            "entity": "llms",
            "id": row.id,
            "name": row.name,
            "subtitle": f"{row.class_name} · ctx {row.context_window}",
            "path": f"/llm/{row.id}",
        }
    if entity == "embeddings":
        return {
            "entity": "embeddings",
            "id": row.id,
            "name": row.name,
            "subtitle": f"{row.class_name} · dim {row.dimension}",
            "path": f"/embedding/{row.id}",
        }
    return {"entity": entity, "id": getattr(row, "id", None), "name": str(row), "subtitle": "", "path": ""}


def execute_query(db_wrapper, user, cleaned: dict) -> list[dict]:
    entity = cleaned["entity"]
    model = ENTITIES[entity]["model"]
    query = db_wrapper.db.query(model).distinct()

    for f in cleaned["filters"]:
        query = _apply_filter(query, model, entity, f)

    query = _apply_rbac(query, entity, user)
    query = query.limit(cleaned["limit"])

    rows = query.all()
    return [_row_to_result(entity, r) for r in rows]


# ── Top-level orchestration ─────────────────────────────────────────────


async def run_search(brain, db_wrapper, user, query_text: str) -> dict:
    """Translate the natural-language query with the system LLM and execute it."""
    system_llm = brain.get_system_llm(db_wrapper)
    if system_llm is None:
        raise ValueError("No system LLM is configured. Set one in Settings → Platform.")

    prompt = build_translation_prompt(query_text)
    try:
        result = system_llm.llm.complete(prompt)
        text = result.text if hasattr(result, "text") else str(result)
    except Exception as e:
        logger.exception("System LLM failed during search translation")
        raise ValueError(f"System LLM call failed: {e}")

    parsed = parse_llm_response(text)
    if parsed is None:
        raise ValueError("System LLM returned invalid JSON")

    note = parsed.get("note") if isinstance(parsed, dict) else None
    cleaned, warnings = validate_query(parsed)
    rows = execute_query(db_wrapper, user, cleaned)

    return {
        "query": cleaned,
        "results": rows,
        "warnings": warnings,
        "note": note,
    }
