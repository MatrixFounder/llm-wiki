"""TASK 005 Phase 2 — Index Layer DAL for entity resolution (R-4 + R-5).

One test class per bead:
- TestResolveEntity / TestOrphanAliasAware  → 005-04 (R-4.5, R-4.5d)
- TestCandidateLifecycle                    → 005-05 (R-4.2/4.3/4.4)
- TestAliasWrite                            → 005-06 (R-5.1/5.2)
- TestAliasRead                             → 005-07 (R-5.5/5.6)
- TestMergeEntities                         → 005-08 (R-4.7)

Refs are seeded directly (FK off) since page_entity_refs.entity_slug has no FK
and we don't need full page rows for DAL-level behavior.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import (
    AliasCollisionError,
    SQLiteRepository,
)


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    r = SQLiteRepository(tmp_path / "g.db")
    r.apply_schema()
    (tmp_path / "vault").mkdir()
    r.register_vault(Vault(
        vault_id="test-vault", name="v", root_path=tmp_path / "vault",
        schema_version="3.0", registered_at=datetime(2026, 5, 29),
    ))
    return r


def _mk_entity(
    repo: SQLiteRepository, slug: str, *,
    name: str | None = None, is_candidate: int = 0, etype: str = "concept",
) -> None:
    repo.upsert_entity(
        vault_id="test-vault", slug=slug, name=name or slug.title(),
        type=etype, is_candidate=is_candidate, canonicalized_by="test",
        first_seen="2026-05-29", last_updated="2026-05-29",
        file_path=f"_concepts/{slug}.md",
    )


def _seed_ref(
    repo: SQLiteRepository, page_slug: str, entity_slug: str, *,
    ref_type: str = "mentioned", trust: str = "medium",
) -> None:
    conn = repo._connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO page_entity_refs "
        "(vault_id, page_slug, page_project, entity_slug, ref_type, trust_level) "
        "VALUES ('test-vault', ?, '_vault_', ?, ?, ?)",
        (page_slug, entity_slug, ref_type, trust),
    )
    conn.execute("PRAGMA foreign_keys = ON")


# --------------------------------------------------------------------------- #
# 005-04 — resolve_entity + alias-aware find_orphan_links (R-4.5, R-4.5d)
# --------------------------------------------------------------------------- #
class TestResolveEntity:
    def test_by_slug(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        ent = repo.resolve_entity("test-vault", "hermes-agent")
        assert ent is not None and ent.slug == "hermes-agent"

    def test_through_alias(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        ent = repo.resolve_entity("test-vault", "Hermes")
        assert ent is not None and ent.slug == "hermes-agent"
        assert "Hermes" in ent.aliases

    def test_miss_returns_none(self, repo: SQLiteRepository) -> None:
        assert repo.resolve_entity("test-vault", "nope") is None


class TestOrphanAliasAware:
    def test_alias_target_not_orphan(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        _seed_ref(repo, "note", "Hermes")     # alias target → resolved
        _seed_ref(repo, "note", "ghost")      # truly unknown → orphan
        targets = {o.target_slug for o in repo.find_orphan_links("test-vault")}
        assert "Hermes" not in targets
        assert "ghost" in targets


# --------------------------------------------------------------------------- #
# 005-05 — candidate lifecycle (R-4.2/4.3/4.4)
# --------------------------------------------------------------------------- #
class TestCandidateLifecycle:
    def test_confirm_and_idempotent(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "foo", is_candidate=1)
        assert repo.set_entity_candidate("test-vault", "foo", 0) is True
        assert repo.set_entity_candidate("test-vault", "foo", 0) is False  # idempotent

    def test_undo_bypasses_min_guard(self, repo: SQLiteRepository) -> None:
        """A confirmed entity can be demoted back to candidate — the explicit
        setter bypasses the upsert MIN() downgrade-guard (R-4.3)."""
        _mk_entity(repo, "foo", is_candidate=0)
        assert repo.set_entity_candidate("test-vault", "foo", 1) is True
        ent = repo.resolve_entity("test-vault", "foo")
        # upsert_entity would have kept is_candidate=0 (MIN); the setter flips it.
        row = repo._connect().execute(
            "SELECT is_candidate FROM entities WHERE vault_id='test-vault' AND slug='foo'"
        ).fetchone()
        assert row["is_candidate"] == 1

    def test_list_candidates(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "cand", is_candidate=1)
        _mk_entity(repo, "conf", is_candidate=0)
        slugs = {e.slug for e in repo.list_candidates("test-vault")}
        assert slugs == {"cand"}

    def test_recompute_mentions(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "foo")
        _seed_ref(repo, "p1", "foo")
        _seed_ref(repo, "p2", "foo")
        repo.recompute_mentions("test-vault")
        mc = repo._connect().execute(
            "SELECT mentions_count FROM entities WHERE vault_id='test-vault' AND slug='foo'"
        ).fetchone()[0]
        assert mc == 2

    def test_auto_promote_threshold_inclusive(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hot", is_candidate=1)
        _mk_entity(repo, "cold", is_candidate=1)
        for p in ("a", "b", "c"):
            _seed_ref(repo, p, "hot")    # 3 mentions
        _seed_ref(repo, "a", "cold")     # 1 mention
        promoted = repo.auto_promote_candidates("test-vault", 3)
        assert promoted == ["hot"]       # >= 3 boundary inclusive; cold stays
        assert repo.set_entity_candidate("test-vault", "hot", 0) is False  # already confirmed


# --------------------------------------------------------------------------- #
# 005-06 — alias write (R-5.1/5.2)
# --------------------------------------------------------------------------- #
class TestAliasWrite:
    def test_add_list(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        assert repo.list_aliases("test-vault", "hermes-agent") == ["Hermes"]

    def test_add_idempotent_same_target(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")  # no error, no dup
        assert repo.list_aliases("test-vault", "hermes-agent") == ["Hermes"]

    def test_add_collision_raises(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        _mk_entity(repo, "hermes-bus")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        with pytest.raises(AliasCollisionError) as ei:
            repo.add_alias("test-vault", "Hermes", "hermes-bus")
        assert ei.value.conflicting_slug == "hermes-agent"

    def test_remove(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        assert repo.remove_alias("test-vault", "Hermes") is True
        assert repo.remove_alias("test-vault", "Hermes") is False  # absent


# --------------------------------------------------------------------------- #
# 005-07 — alias read: expand + collisions (R-5.5/5.6)
# --------------------------------------------------------------------------- #
class TestAliasRead:
    def test_expand(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent", name="Hermes Agent")
        repo.add_alias("test-vault", "Hermes", "hermes-agent")
        repo.add_alias("test-vault", "HMS", "hermes-agent")
        assert set(repo.expand_query_aliases("test-vault", "Hermes")) == {
            "Hermes Agent", "Hermes", "HMS",
        }

    def test_expand_no_match(self, repo: SQLiteRepository) -> None:
        assert repo.expand_query_aliases("test-vault", "unknown") == []

    def test_collision_cross_slug(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "foo")
        _mk_entity(repo, "bar")
        # alias "foo" registered on bar collides with entity foo's slug
        repo.add_alias("test-vault", "foo", "bar")
        cols = repo.find_alias_collisions("test-vault")
        assert any(c.kind == "cross_slug" and c.alias == "foo" for c in cols)

    def test_collision_cross_name(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "foo", name="Foo Thing")
        _mk_entity(repo, "bar")
        repo.add_alias("test-vault", "Foo Thing", "bar")  # equals foo's name
        cols = repo.find_alias_collisions("test-vault")
        assert any(c.kind == "cross_name" and c.alias == "Foo Thing" for c in cols)


# --------------------------------------------------------------------------- #
# 005-08 — merge_entities (R-4.7)
# --------------------------------------------------------------------------- #
class TestMergeEntities:
    def test_basic_fold(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "hermes-agent", name="Hermes Agent")
        _mk_entity(repo, "hermes-framework", name="Hermes Framework")
        repo.add_alias("test-vault", "HF", "hermes-framework")
        _seed_ref(repo, "p1", "hermes-framework")
        report = repo.merge_entities("test-vault", "hermes-framework", "hermes-agent")
        # from entity gone
        assert repo.resolve_entity("test-vault", "hermes-agent") is not None
        gone = repo._connect().execute(
            "SELECT 1 FROM entities WHERE vault_id='test-vault' AND slug='hermes-framework'"
        ).fetchone()
        assert gone is None
        # ref re-pointed
        ref = repo._connect().execute(
            "SELECT entity_slug FROM page_entity_refs WHERE vault_id='test-vault' AND page_slug='p1'"
        ).fetchone()["entity_slug"]
        assert ref == "hermes-agent"
        assert report.refs_repointed == 1
        # from's alias absorbed + redirect aliases (slug + name) registered
        aliases = repo.list_aliases("test-vault", "hermes-agent")
        assert "HF" in aliases                       # absorbed
        assert "hermes-framework" in aliases         # slug redirect
        assert "Hermes Framework" in aliases         # name redirect
        # resolve through the redirect
        assert repo.resolve_entity("test-vault", "hermes-framework").slug == "hermes-agent"

    def test_ref_dedup_keeps_higher_trust(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "into")
        _mk_entity(repo, "from-dup")
        _seed_ref(repo, "p1", "into", trust="low")
        _seed_ref(repo, "p1", "from-dup", trust="high")  # same page+ref_type
        repo.merge_entities("test-vault", "from-dup", "into")
        rows = repo._connect().execute(
            "SELECT entity_slug, trust_level FROM page_entity_refs "
            "WHERE vault_id='test-vault' AND page_slug='p1'"
        ).fetchall()
        assert len(rows) == 1                       # deduped
        assert rows[0]["entity_slug"] == "into"
        assert rows[0]["trust_level"] == "high"     # higher trust kept

    def test_mentions_is_union(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "into")
        _mk_entity(repo, "from-dup")
        _seed_ref(repo, "p1", "into")
        _seed_ref(repo, "p2", "from-dup")
        repo.merge_entities("test-vault", "from-dup", "into")
        mc = repo._connect().execute(
            "SELECT mentions_count FROM entities WHERE vault_id='test-vault' AND slug='into'"
        ).fetchone()[0]
        assert mc == 2

    def test_third_entity_alias_collision_reported(self, repo: SQLiteRepository) -> None:
        _mk_entity(repo, "into")
        _mk_entity(repo, "from-dup", name="Dup Name")
        _mk_entity(repo, "third")
        # a third entity already owns the alias "Dup Name" → redirect skip+report
        repo.add_alias("test-vault", "Dup Name", "third")
        report = repo.merge_entities("test-vault", "from-dup", "into")
        assert "Dup Name" in report.aliases_skipped
