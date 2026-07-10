"""Entity-merge domain of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: find_alias_collisions,
merge_entities, get_entity_file_path, find_entity_by_name.

Declared mixin-dependency edge: `_MergeMixin(_EntitiesMixin)` —
`merge_entities` calls the private `_recompute_mentions`, which stays owned
by the entities domain. Per the TASK 056 C3 rule, the composite class lists
`_MergeMixin` and OMITS `_EntitiesMixin` (inherited transitively).

dialect: generic SQL (pure-DML re-pointing + alias-as-redirect, R-4.7).
"""

from __future__ import annotations

from scripts.wiki_index.models import AliasCollision, MergeReport
from scripts.wiki_index.sqlite_repository._entities import _EntitiesMixin


class _MergeMixin(_EntitiesMixin):
    """Duplicate-entity fold (wiki-merge) + collision analysis (R-5.6)."""

    def find_alias_collisions(self, vault_id: str) -> list[AliasCollision]:
        """R-5.6: in-DB (legacy) + cross-table alias collisions. The Class A
        frontmatter scan lives in the Lint Layer."""
        conn = self._connect()
        out: list[AliasCollision] = []
        # in-table (only reachable on a legacy / pre-v3 DB; the v3 PK prevents
        # new ones): same alias → >1 entity_slug.
        for r in conn.execute(
            "SELECT alias, GROUP_CONCAT(entity_slug) AS slugs FROM entity_aliases "
            "WHERE vault_id = ? GROUP BY alias HAVING COUNT(DISTINCT entity_slug) > 1",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted((r["slugs"] or "").split(",")), kind="in_table",
            ))
        # cross-slug: alias equals a DIFFERENT entity's slug.
        for r in conn.execute(
            "SELECT a.alias, a.entity_slug, e.slug AS other FROM entity_aliases a "
            "JOIN entities e ON e.vault_id = a.vault_id AND e.slug = a.alias "
            "WHERE a.vault_id = ? AND e.slug != a.entity_slug",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted([r["entity_slug"], r["other"]]), kind="cross_slug",
            ))
        # cross-name: alias equals a DIFFERENT entity's name.
        for r in conn.execute(
            "SELECT a.alias, a.entity_slug, e.slug AS other FROM entity_aliases a "
            "JOIN entities e ON e.vault_id = a.vault_id AND e.name = a.alias "
            "WHERE a.vault_id = ? AND e.slug != a.entity_slug",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=r["alias"],
                slugs=sorted([r["entity_slug"], r["other"]]), kind="cross_name",
            ))
        # frontmatter (P-10/F12b, TASK 006): a surface claimed by ≥2 *entity*
        # pages' Class A `aliases:` blocks — read from pages.frontmatter_json
        # (already in the DB) via json_each, NOT a 2nd O(N) file+YAML sweep. The
        # frontmatter_json is always valid (json.dumps at upsert), so there is no
        # swallowed-parse case (F12b) — a malformed source file is recorded in the
        # reindex `skipped` report, never silently dropped here.
        # vdd-multi MED fix: JOIN entities to restrict to *entity* pages only —
        # the deleted file-scan walked only `_concepts`/`_entities` (the same
        # tier the reindex alias-mirror gates on). Without this join the scan
        # would also flag legal `aliases:` shared between `_sources/` summary
        # pages — a false collision (and an error under `--strict`).
        for r in conn.execute(
            "SELECT je.value AS alias, GROUP_CONCAT(DISTINCT p.slug) AS slugs "
            "FROM pages p "
            "JOIN entities e ON e.vault_id = p.vault_id AND e.slug = p.slug "
            "JOIN json_each(p.frontmatter_json, '$.aliases') je "
            "WHERE p.vault_id = ? "
            "  AND json_type(p.frontmatter_json, '$.aliases') = 'array' "
            "GROUP BY je.value HAVING COUNT(DISTINCT p.slug) > 1",
            (vault_id,),
        ).fetchall():
            out.append(AliasCollision(
                vault_id=vault_id, alias=str(r["alias"]),
                slugs=sorted((r["slugs"] or "").split(",")), kind="frontmatter",
            ))
        return out

    _TRUST_RANK = {"high": 3, "medium": 2, "low": 1}

    def merge_entities(
        self, vault_id: str, from_slug: str, into_slug: str
    ) -> MergeReport:
        """R-4.7: fold `from` into `into` in one transaction. See ABC docstring.

        Caller (`wiki-merge`) does the Class A mutations first (C-8)."""
        conn = self._connect()
        refs_repointed = 0
        aliases_absorbed = 0
        aliases_skipped: list[str] = []

        conn.execute("BEGIN IMMEDIATE")
        try:
            # F2 (vdd-multi): read from_name INSIDE the tx — sampling it in
            # autocommit was a TOCTOU window on the shared multi-vault DB. Raise
            # if the row vanished so the DAL is self-consistent (the CLI's
            # resolve_entity pre-check is itself outside this tx).
            from_row = conn.execute(
                "SELECT name FROM entities WHERE vault_id = ? AND slug = ?",
                (vault_id, from_slug),
            ).fetchone()
            if from_row is None:
                raise ValueError(f"merge source entity {from_slug!r} not found")
            from_name = from_row["name"]
            # 1. re-point page_entity_refs, dedup on the PK keeping higher trust.
            from_refs = conn.execute(
                "SELECT rowid AS rid, page_slug, page_project, ref_type, "
                "trust_level FROM page_entity_refs "
                "WHERE vault_id = ? AND entity_slug = ?",
                (vault_id, from_slug),
            ).fetchall()
            for fr in from_refs:
                existing = conn.execute(
                    "SELECT rowid AS rid, trust_level FROM page_entity_refs "
                    "WHERE vault_id = ? AND page_slug = ? AND page_project = ? "
                    "AND entity_slug = ? AND ref_type = ?",
                    (vault_id, fr["page_slug"], fr["page_project"],
                     into_slug, fr["ref_type"]),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "UPDATE page_entity_refs SET entity_slug = ? WHERE rowid = ?",
                        (into_slug, fr["rid"]),
                    )
                else:
                    if (self._TRUST_RANK.get(fr["trust_level"], 0)
                            > self._TRUST_RANK.get(existing["trust_level"], 0)):
                        conn.execute(
                            "UPDATE page_entity_refs SET trust_level = ? "
                            "WHERE rowid = ?",
                            (fr["trust_level"], existing["rid"]),
                        )
                    conn.execute(
                        "DELETE FROM page_entity_refs WHERE rowid = ?", (fr["rid"],)
                    )
                refs_repointed += 1

            # 2. re-point from's existing aliases to into (alias PK unique → no
            #    collision possible; simple set-based UPDATE).
            cur = conn.execute(
                "UPDATE entity_aliases SET entity_slug = ? "
                "WHERE vault_id = ? AND entity_slug = ?",
                (into_slug, vault_id, from_slug),
            )
            aliases_absorbed += cur.rowcount

            # 3. register the durable redirect: from's slug + name as
            #    former_name aliases of into. Skip+report on a third-entity PK
            #    collision (never silent).
            for surface in [s for s in (from_slug, from_name) if s]:
                ex = conn.execute(
                    "SELECT entity_slug FROM entity_aliases "
                    "WHERE vault_id = ? AND alias = ?",
                    (vault_id, surface),
                ).fetchone()
                if ex is not None:
                    if ex["entity_slug"] != into_slug:
                        aliases_skipped.append(surface)
                    continue
                conn.execute(
                    "INSERT INTO entity_aliases "
                    "(vault_id, alias, entity_slug, alias_type) "
                    "VALUES (?, ?, ?, 'former_name')",
                    (vault_id, surface, into_slug),
                )
                aliases_absorbed += 1

            # 4. delete the from entity row.
            conn.execute(
                "DELETE FROM entities WHERE vault_id = ? AND slug = ?",
                (vault_id, from_slug),
            )

            # 5. recompute into.mentions_count within the same tx (F12c helper).
            self._recompute_mentions(conn, vault_id, slug=into_slug)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return MergeReport(
            refs_repointed=refs_repointed,
            aliases_absorbed=aliases_absorbed,
            aliases_skipped=aliases_skipped,
        )

    def get_entity_file_path(self, vault_id: str, slug: str) -> str | None:
        row = self._connect().execute(
            "SELECT file_path FROM entities WHERE vault_id = ? AND slug = ?",
            (vault_id, slug),
        ).fetchone()
        return row["file_path"] if row else None

    def find_entity_by_name(self, vault_id: str, name: str) -> str | None:
        row = self._connect().execute(
            "SELECT slug FROM entities WHERE vault_id = ? AND name = ? "
            "ORDER BY slug LIMIT 1",
            (vault_id, name),
        ).fetchone()
        return row["slug"] if row else None
