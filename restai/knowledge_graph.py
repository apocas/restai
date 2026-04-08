"""Knowledge graph helpers: entity extraction, persistence, dedup, merge.

Stores extracted entities at the source level (not chunk level) in three tables:
- kg_entities: unique entities per project (deduped by normalized name + type)
- kg_entity_mentions: which sources each entity appears in
- kg_entity_relationships: co-occurrence edges between entities
"""
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from restai.models.databasemodels import (
    KGEntityDatabase,
    KGEntityMentionDatabase,
    KGEntityRelationshipDatabase,
)

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"PER", "PERSON", "ORG", "LOC", "MISC", "DATE", "GPE"}
TYPE_NORMALIZATION = {
    "PER": "PERSON",
    "GPE": "LOC",
}


def normalize_entity_name(name: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation around the edges."""
    s = (name or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^[^\w]+|[^\w]+$", "", s)
    return s


def _normalize_type(t: str) -> str:
    return TYPE_NORMALIZATION.get(t, t)


def find_entities_in_text(text: str, brain, model_name: Optional[str] = None) -> list[tuple[str, str]]:
    """Run NER and return [(canonical_name, type), ...] deduped within this call."""
    if not text:
        return []
    raw = brain.extract_entities_from_text(text, model_name=model_name)
    seen: dict[tuple[str, str], str] = {}
    for ent in raw:
        word = (ent.get("word") or "").strip()
        etype = _normalize_type((ent.get("entity_group") or ent.get("entity") or "").upper())
        if not word or etype not in ALLOWED_TYPES:
            continue
        normalized = normalize_entity_name(word)
        if not normalized:
            continue
        key = (normalized, etype)
        if key not in seen:
            seen[key] = word
    return [(canonical, etype) for (norm, etype), canonical in seen.items()]


def extract_and_persist(project_id: int, source: str, text: str, brain, db) -> int:
    """Extract entities from text and persist them. Returns the count of distinct entities found.

    `db` is the DBWrapper instance (uses db.db for the SQLAlchemy session).
    """
    if not text:
        return 0
    raw = brain.extract_entities_from_text(text, model_name=None)
    if not raw:
        return 0

    # Aggregate counts within this source
    per_source_counts: Counter = Counter()
    canonical_names: dict[tuple[str, str], str] = {}
    for ent in raw:
        word = (ent.get("word") or "").strip()
        etype = _normalize_type((ent.get("entity_group") or ent.get("entity") or "").upper())
        if not word or etype not in ALLOWED_TYPES:
            continue
        normalized = normalize_entity_name(word)
        if not normalized:
            continue
        key = (normalized, etype)
        per_source_counts[key] += 1
        if key not in canonical_names:
            canonical_names[key] = word

    if not per_source_counts:
        return 0

    now = datetime.now(timezone.utc)
    session = db.db
    entity_ids: dict[tuple[str, str], int] = {}

    # Upsert entities
    for (normalized, etype), count in per_source_counts.items():
        existing = (
            session.query(KGEntityDatabase)
            .filter(
                KGEntityDatabase.project_id == project_id,
                KGEntityDatabase.normalized == normalized,
                KGEntityDatabase.entity_type == etype,
            )
            .first()
        )
        if existing:
            existing.mention_count = (existing.mention_count or 0) + count
            existing.updated_at = now
            entity_ids[(normalized, etype)] = existing.id
        else:
            ent = KGEntityDatabase(
                project_id=project_id,
                name=canonical_names[(normalized, etype)],
                normalized=normalized,
                entity_type=etype,
                mention_count=count,
                created_at=now,
                updated_at=now,
            )
            session.add(ent)
            session.flush()
            entity_ids[(normalized, etype)] = ent.id

    # Upsert mentions (entity × source)
    for (normalized, etype), count in per_source_counts.items():
        eid = entity_ids[(normalized, etype)]
        existing_mention = (
            session.query(KGEntityMentionDatabase)
            .filter(
                KGEntityMentionDatabase.entity_id == eid,
                KGEntityMentionDatabase.source == source,
            )
            .first()
        )
        if existing_mention:
            existing_mention.mention_count = (existing_mention.mention_count or 0) + count
        else:
            session.add(KGEntityMentionDatabase(
                entity_id=eid,
                project_id=project_id,
                source=source,
                mention_count=count,
                created_at=now,
            ))

    # Co-occurrence edges: for every pair of distinct entities in this source,
    # increment the edge weight (or create the edge).
    ids_in_source = sorted(entity_ids.values())
    for i, a in enumerate(ids_in_source):
        for b in ids_in_source[i + 1:]:
            existing_edge = (
                session.query(KGEntityRelationshipDatabase)
                .filter(
                    KGEntityRelationshipDatabase.project_id == project_id,
                    KGEntityRelationshipDatabase.from_entity_id == a,
                    KGEntityRelationshipDatabase.to_entity_id == b,
                )
                .first()
            )
            if existing_edge:
                existing_edge.weight = (existing_edge.weight or 0) + 1
            else:
                session.add(KGEntityRelationshipDatabase(
                    project_id=project_id,
                    from_entity_id=a,
                    to_entity_id=b,
                    weight=1,
                    created_at=now,
                ))

    session.commit()
    return len(per_source_counts)


def extract_and_persist_safe(project_id: int, source: str, text: str, brain, db_factory) -> None:
    """Background-task safe wrapper. Creates a fresh DB session and handles errors."""
    try:
        db = db_factory()
        try:
            extract_and_persist(project_id, source, text, brain, db)
        finally:
            try:
                db.db.close()
            except Exception:
                pass
    except Exception as e:
        logger.exception("Background entity extraction failed for project %s source %s: %s", project_id, source, e)


def merge_entities(db, primary_id: int, secondary_id: int) -> bool:
    """Merge secondary entity into primary. Moves all mentions and relationships, then deletes secondary.

    Returns True if successful, False if either entity doesn't exist or they're the same.
    """
    if primary_id == secondary_id:
        return False
    session = db.db
    primary = session.query(KGEntityDatabase).filter(KGEntityDatabase.id == primary_id).first()
    secondary = session.query(KGEntityDatabase).filter(KGEntityDatabase.id == secondary_id).first()
    if not primary or not secondary or primary.project_id != secondary.project_id:
        return False

    now = datetime.now(timezone.utc)

    # Move mentions: if a mention of the same source exists for primary, sum counts; otherwise repoint
    secondary_mentions = (
        session.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id == secondary_id)
        .all()
    )
    for sm in secondary_mentions:
        existing = (
            session.query(KGEntityMentionDatabase)
            .filter(
                KGEntityMentionDatabase.entity_id == primary_id,
                KGEntityMentionDatabase.source == sm.source,
            )
            .first()
        )
        if existing:
            existing.mention_count = (existing.mention_count or 0) + (sm.mention_count or 0)
            session.delete(sm)
        else:
            sm.entity_id = primary_id

    # Move relationships: any edge involving secondary → repoint to primary, dedup
    secondary_edges = (
        session.query(KGEntityRelationshipDatabase)
        .filter(
            (KGEntityRelationshipDatabase.from_entity_id == secondary_id)
            | (KGEntityRelationshipDatabase.to_entity_id == secondary_id)
        )
        .all()
    )
    for edge in secondary_edges:
        new_from = primary_id if edge.from_entity_id == secondary_id else edge.from_entity_id
        new_to = primary_id if edge.to_entity_id == secondary_id else edge.to_entity_id
        if new_from == new_to:
            session.delete(edge)
            continue
        # Normalize order so we can dedup
        a, b = sorted([new_from, new_to])
        existing = (
            session.query(KGEntityRelationshipDatabase)
            .filter(
                KGEntityRelationshipDatabase.project_id == primary.project_id,
                KGEntityRelationshipDatabase.from_entity_id == a,
                KGEntityRelationshipDatabase.to_entity_id == b,
            )
            .first()
        )
        if existing and existing.id != edge.id:
            existing.weight = (existing.weight or 0) + (edge.weight or 0)
            session.delete(edge)
        else:
            edge.from_entity_id = a
            edge.to_entity_id = b

    primary.mention_count = (primary.mention_count or 0) + (secondary.mention_count or 0)
    primary.updated_at = now
    session.delete(secondary)
    session.commit()
    return True


def compute_potential_duplicates(db, project_id: int, threshold: float = 0.85, limit: int = 100) -> list[dict]:
    """Find entity pairs with similar names within the same type."""
    session = db.db
    entities = (
        session.query(KGEntityDatabase)
        .filter(KGEntityDatabase.project_id == project_id)
        .all()
    )
    by_type: dict[str, list[KGEntityDatabase]] = defaultdict(list)
    for e in entities:
        by_type[e.entity_type].append(e)

    candidates: list[dict] = []
    for etype, ents in by_type.items():
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                a, b = ents[i], ents[j]
                if a.normalized == b.normalized:
                    continue  # Already merged
                ratio = SequenceMatcher(None, a.normalized, b.normalized).ratio()
                if ratio >= threshold:
                    candidates.append({
                        "entity_a_id": a.id,
                        "entity_a_name": a.name,
                        "entity_b_id": b.id,
                        "entity_b_name": b.name,
                        "similarity": round(ratio, 3),
                    })
    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    return candidates[:limit]
