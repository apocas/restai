"""Unit tests for restai/integrations/knowledge_graph.py — extraction +
persistence orchestration with a faked NER brain and real sqlite rows,
plus merge/dedup edge branches not covered by the router tests."""
import random

import pytest

from restai.database import open_db_wrapper
from restai.integrations import knowledge_graph as kg
from restai.models.databasemodels import (
    KGEntityDatabase,
    KGEntityMentionDatabase,
    KGEntityRelationshipDatabase,
)

PROJECT_ID = 900000 + random.randint(0, 99999)


class FakeBrain:
    """Brain stub — returns canned NER output."""
    def __init__(self, entities):
        self.entities = entities
        self.calls = []

    def extract_entities_from_text(self, text, model_name=None):
        self.calls.append((text, model_name))
        return self.entities


def _ner(word, group):
    return {"word": word, "entity_group": group}


@pytest.fixture()
def db():
    wrapper = open_db_wrapper()
    yield wrapper
    # Wipe everything this module created for PROJECT_ID.
    s = wrapper.db
    ids = [e.id for e in s.query(KGEntityDatabase)
           .filter(KGEntityDatabase.project_id == PROJECT_ID).all()]
    if ids:
        s.query(KGEntityMentionDatabase).filter(
            KGEntityMentionDatabase.entity_id.in_(ids)).delete(synchronize_session=False)
    s.query(KGEntityRelationshipDatabase).filter(
        KGEntityRelationshipDatabase.project_id == PROJECT_ID).delete(
        synchronize_session=False)
    s.query(KGEntityDatabase).filter(
        KGEntityDatabase.project_id == PROJECT_ID).delete(synchronize_session=False)
    s.commit()
    s.close()


def _entities(db):
    return (
        db.db.query(KGEntityDatabase)
        .filter(KGEntityDatabase.project_id == PROJECT_ID)
        .order_by(KGEntityDatabase.id)
        .all()
    )


# ─── normalize / find_entities_in_text ──────────────────────────────────

def test_normalize_entity_name():
    assert kg.normalize_entity_name("  Acme   Corp ") == "acme corp"
    assert kg.normalize_entity_name("«Acme!»") == "acme"
    assert kg.normalize_entity_name(None) == ""
    assert kg.normalize_entity_name("!!!") == ""


def test_find_entities_filters_types_and_dedupes():
    brain = FakeBrain([
        _ner("Ada Lovelace", "PER"),        # PER → PERSON
        _ner("ada  lovelace", "PER"),       # dup after normalization
        _ner("London", "GPE"),              # GPE → LOC
        _ner("widget", "PRODUCT"),          # disallowed type dropped
        _ner("", "ORG"),                    # empty word dropped
        _ner("!!!", "ORG"),                 # normalizes to empty → dropped
        {"word": "Acme", "entity": "ORG"},  # legacy 'entity' key
    ])
    out = kg.find_entities_in_text("some text", brain)
    assert ("Ada Lovelace", "PERSON") in out
    assert ("London", "LOC") in out
    assert ("Acme", "ORG") in out
    assert len(out) == 3


def test_find_entities_empty_text_short_circuits():
    brain = FakeBrain([_ner("Acme", "ORG")])
    assert kg.find_entities_in_text("", brain) == []
    assert brain.calls == []


# ─── extract_and_persist ────────────────────────────────────────────────

def test_extract_and_persist_creates_entities_mentions_edges(db):
    brain = FakeBrain([
        _ner("Acme", "ORG"),
        _ner("Ada", "PER"),
        _ner("Acme", "ORG"),  # second mention of same entity
    ])
    count = kg.extract_and_persist(PROJECT_ID, "doc1.pdf", "text", brain, db)
    assert count == 2  # distinct entities

    ents = {e.normalized: e for e in _entities(db)}
    assert ents["acme"].entity_type == "ORG"
    assert ents["acme"].mention_count == 2
    assert ents["ada"].entity_type == "PERSON"
    assert ents["ada"].mention_count == 1

    mentions = (
        db.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.project_id == PROJECT_ID)
        .all()
    )
    assert {(m.source, m.mention_count) for m in mentions} == {("doc1.pdf", 2), ("doc1.pdf", 1)}

    edges = (
        db.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == PROJECT_ID)
        .all()
    )
    assert len(edges) == 1
    assert edges[0].weight == 1
    assert edges[0].from_entity_id < edges[0].to_entity_id  # sorted pair


def test_extract_and_persist_reruns_increment_counts(db):
    brain = FakeBrain([_ner("Acme", "ORG"), _ner("Ada", "PER")])
    kg.extract_and_persist(PROJECT_ID, "doc1.pdf", "text", brain, db)
    kg.extract_and_persist(PROJECT_ID, "doc1.pdf", "text", brain, db)   # same source
    kg.extract_and_persist(PROJECT_ID, "doc2.pdf", "text", brain, db)   # new source

    ents = {e.normalized: e for e in _entities(db)}
    assert len(ents) == 2  # no duplicate entity rows
    assert ents["acme"].mention_count == 3

    mentions = (
        db.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id == ents["acme"].id)
        .all()
    )
    by_source = {m.source: m.mention_count for m in mentions}
    assert by_source == {"doc1.pdf": 2, "doc2.pdf": 1}

    edge = (
        db.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == PROJECT_ID)
        .one()
    )
    assert edge.weight == 3  # one bump per run


def test_extract_and_persist_short_circuits(db):
    brain = FakeBrain([])
    assert kg.extract_and_persist(PROJECT_ID, "s", "", brain, db) == 0  # empty text
    assert brain.calls == []
    assert kg.extract_and_persist(PROJECT_ID, "s", "text", brain, db) == 0  # no NER hits

    only_junk = FakeBrain([_ner("thing", "PRODUCT"), _ner("", "ORG"), _ner("!!!", "ORG")])
    assert kg.extract_and_persist(PROJECT_ID, "s", "text", only_junk, db) == 0
    assert _entities(db) == []


def test_extract_and_persist_safe_swallows_factory_errors():
    def bad_factory():
        raise RuntimeError("db unreachable")
    kg.extract_and_persist_safe(PROJECT_ID, "s", "text", FakeBrain([]), bad_factory)


def test_extract_and_persist_safe_closes_db(db):
    closed = []
    real = open_db_wrapper()

    def factory():
        real.db.close = lambda: closed.append(1) or type(real.db).close(real.db)
        return real
    kg.extract_and_persist_safe(
        PROJECT_ID, "safe.pdf", "text", FakeBrain([_ner("Acme", "ORG")]), factory)
    assert closed == [1]

    ents = {e.normalized for e in _entities(db)}
    assert "acme" in ents


# ─── merge_entities ─────────────────────────────────────────────────────

def _seed_pair(db, name_a="Acme Corp", name_b="Acme"):
    brain_a = FakeBrain([_ner(name_a, "ORG"), _ner("Ada", "PER")])
    brain_b = FakeBrain([_ner(name_b, "ORG"), _ner("Ada", "PER")])
    kg.extract_and_persist(PROJECT_ID, "a.pdf", "t", brain_a, db)
    kg.extract_and_persist(PROJECT_ID, "b.pdf", "t", brain_b, db)
    ents = {e.normalized: e for e in _entities(db)}
    return ents[kg.normalize_entity_name(name_a)], ents[kg.normalize_entity_name(name_b)]


def test_merge_entities_guard_branches(db):
    a, b = _seed_pair(db)
    assert kg.merge_entities(db, a.id, a.id, PROJECT_ID) is False       # same id
    assert kg.merge_entities(db, a.id, 99999999, PROJECT_ID) is False   # missing secondary
    assert kg.merge_entities(db, 99999999, b.id, PROJECT_ID) is False   # missing primary


def test_merge_entities_moves_mentions_and_rewires_edges(db):
    a, b = _seed_pair(db)
    ada = next(e for e in _entities(db) if e.normalized == "ada")

    assert kg.merge_entities(db, a.id, b.id, PROJECT_ID) is True

    # Secondary gone; mention counts summed onto primary.
    assert db.db.query(KGEntityDatabase).filter(KGEntityDatabase.id == b.id).first() is None
    db.db.refresh(a)
    assert a.mention_count == 2

    sources = {
        m.source for m in db.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id == a.id).all()
    }
    assert sources == {"a.pdf", "b.pdf"}

    # Both ORG→Ada edges collapse onto (a, ada) with combined weight.
    edges = (
        db.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == PROJECT_ID)
        .all()
    )
    assert len(edges) == 1
    pair = sorted([edges[0].from_entity_id, edges[0].to_entity_id])
    assert pair == sorted([a.id, ada.id])
    assert edges[0].weight == 2


def test_merge_entities_drops_self_edges(db):
    a, b = _seed_pair(db)
    # Force a direct edge between the two entities being merged.
    db.db.query(KGEntityRelationshipDatabase).filter(
        KGEntityRelationshipDatabase.project_id == PROJECT_ID).delete(
        synchronize_session=False)
    lo, hi = sorted([a.id, b.id])
    from datetime import datetime, timezone
    db.db.add(KGEntityRelationshipDatabase(
        project_id=PROJECT_ID, from_entity_id=lo, to_entity_id=hi,
        weight=4, created_at=datetime.now(timezone.utc)))
    db.db.commit()

    assert kg.merge_entities(db, a.id, b.id, PROJECT_ID) is True
    remaining = (
        db.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == PROJECT_ID)
        .all()
    )
    assert remaining == []  # self-edge deleted, not kept


def test_merge_entities_same_source_mentions_combined(db):
    """Both entities mentioned in the SAME source → mention rows merge."""
    brain = FakeBrain([_ner("Acme Corp", "ORG"), _ner("Acme", "ORG")])
    kg.extract_and_persist(PROJECT_ID, "one.pdf", "t", brain, db)
    ents = {e.normalized: e for e in _entities(db)}
    a, b = ents["acme corp"], ents["acme"]

    assert kg.merge_entities(db, a.id, b.id, PROJECT_ID) is True
    mentions = (
        db.db.query(KGEntityMentionDatabase)
        .filter(KGEntityMentionDatabase.entity_id == a.id)
        .all()
    )
    assert len(mentions) == 1
    assert mentions[0].source == "one.pdf"
    assert mentions[0].mention_count == 2


def test_merge_entities_rewires_edge_when_primary_has_none(db):
    """Secondary→third edge moves onto primary when no combined edge exists."""
    lonely = FakeBrain([_ner("Solo Corp", "ORG")])
    pair = FakeBrain([_ner("Solo", "ORG"), _ner("Ada", "PER")])
    kg.extract_and_persist(PROJECT_ID, "a.pdf", "t", lonely, db)
    kg.extract_and_persist(PROJECT_ID, "b.pdf", "t", pair, db)
    ents = {e.normalized: e for e in _entities(db)}
    primary, secondary, ada = ents["solo corp"], ents["solo"], ents["ada"]

    assert kg.merge_entities(db, primary.id, secondary.id, PROJECT_ID) is True
    edge = (
        db.db.query(KGEntityRelationshipDatabase)
        .filter(KGEntityRelationshipDatabase.project_id == PROJECT_ID)
        .one()
    )
    assert sorted([edge.from_entity_id, edge.to_entity_id]) == sorted(
        [primary.id, ada.id])
    assert edge.weight == 1


def _foreign_entity(db, name):
    from datetime import datetime, timezone
    row = KGEntityDatabase(
        project_id=PROJECT_ID + 1, name=name, normalized=name.lower(),
        entity_type="ORG", mention_count=1,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.db.add(row)
    db.db.commit()
    return row


def test_merge_entities_cross_project_refused(db):
    a, _b = _seed_pair(db)
    foreign = _foreign_entity(db, "Foreign")
    try:
        assert kg.merge_entities(db, a.id, foreign.id, PROJECT_ID) is False
    finally:
        db.db.delete(foreign)
        db.db.commit()


def test_merge_entities_refuses_pair_outside_authorized_project(db):
    """GHSA-r3px-wf48-988x regression.

    Both entities live in a FOREIGN project, so they are perfectly consistent
    with each other — the old `primary.project_id != secondary.project_id`
    check passed and the merge went through, destroying another tenant's data.
    Scoping both lookups to the caller's project is what actually refuses it.
    """
    _seed_pair(db)
    f1 = _foreign_entity(db, "VictimOne")
    f2 = _foreign_entity(db, "VictimTwo")
    try:
        assert f1.project_id == f2.project_id  # self-consistent pair
        assert kg.merge_entities(db, f2.id, f1.id, PROJECT_ID) is False

        # Nothing in the foreign project was touched.
        for row in (f1, f2):
            assert db.db.query(KGEntityDatabase).filter(
                KGEntityDatabase.id == row.id).first() is not None
    finally:
        for row in (f1, f2):
            db.db.delete(row)
        db.db.commit()


# ─── compute_potential_duplicates ───────────────────────────────────────

def test_compute_potential_duplicates(db):
    brain = FakeBrain([
        _ner("Jonathan Smith", "PER"),
        _ner("Jonathon Smith", "PER"),   # near-duplicate
        _ner("Acme", "ORG"),             # different type — never compared
    ])
    kg.extract_and_persist(PROJECT_ID, "dup.pdf", "t", brain, db)

    dups = kg.compute_potential_duplicates(db, PROJECT_ID, threshold=0.85)
    assert len(dups) == 1
    names = {dups[0]["entity_a_name"], dups[0]["entity_b_name"]}
    assert names == {"Jonathan Smith", "Jonathon Smith"}
    assert dups[0]["similarity"] >= 0.85

    # Higher threshold filters it out; limit caps the list.
    assert kg.compute_potential_duplicates(db, PROJECT_ID, threshold=0.99) == []
    assert kg.compute_potential_duplicates(db, PROJECT_ID, threshold=0.1, limit=0) == []
