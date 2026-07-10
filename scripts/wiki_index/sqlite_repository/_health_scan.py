"""Structural-integrity scans of the SQLite DAL (TASK 056).

Methods relocated verbatim from the pre-056 monolith: find_orphan_links,
find_classification_leaks, find_invalid_classifications, find_verified_slugs,
find_pages_missing_in_index, check_drift (+ its private helpers
_is_intentional_mapping / _extract_frontmatter_type),
find_cross_vault_concept_duplicates. These need no declared rules — they
compare the index against itself or against the on-disk vault.

`check_drift` calls the public `get_vault` (vaults domain) — that call
type-checks against the `IndexRepository` ABC inherited via the base; no
mixin-dependency edge is needed for public methods.

dialect: mixed — `json_extract` over `frontmatter_json` (Postgres `jsonb`)
plus portable joins; check_drift's file-hash walk is Python-side.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.wiki_index.models import (
    ClassificationLeakHit,
    DriftReport,
    InvalidClassificationHit,
    OrphanLink,
)
from scripts.wiki_index.sqlite_repository._base import (
    SQLiteRepositoryBase,
    VaultRegistrationError,
)


class _HealthScanMixin(SQLiteRepositoryBase):
    """Lint-layer structural scans (task-001-18 lineage)."""

    def find_orphan_links(self, vault_id: str | None = None) -> list[OrphanLink]:
        # R-4.5d (TASK 005): alias-aware. A ref whose target is a registered
        # alias resolves to its canonical entity → NOT an orphan. This is what
        # keeps a merged-away `from` slug (still `[[from-slug]]` in source bodies)
        # from polluting lint after a `wiki-merge`.
        sql = (
            "SELECT r.vault_id, r.page_slug, r.page_project, r.entity_slug, "
            "r.line_start, r.source_quote "
            "FROM page_entity_refs r "
            "LEFT JOIN entities e ON e.vault_id = r.vault_id AND e.slug = r.entity_slug "
            "LEFT JOIN pages p ON p.vault_id = r.vault_id AND p.slug = r.entity_slug "
            "LEFT JOIN entity_aliases a ON a.vault_id = r.vault_id AND a.alias = r.entity_slug "
            "WHERE e.slug IS NULL AND p.slug IS NULL AND a.alias IS NULL"
        )
        params: list[Any] = []
        if vault_id is not None:
            sql += " AND r.vault_id = ?"
            params.append(vault_id)
        rows = self._connect().execute(sql, params).fetchall()
        return [
            OrphanLink(
                vault_id=r["vault_id"],
                source_page_slug=r["page_slug"],
                source_page_project=r["page_project"],
                target_slug=r["entity_slug"],
                line_start=r["line_start"],
                source_quote=r["source_quote"],
            )
            for r in rows
        ]

    def find_classification_leaks(
        self, vault_id: str, levels: list[str], default_level: str,
    ) -> list[ClassificationLeakHit]:
        # TASK 049 (R-6) — SQL fetches candidate ('cited','verifies') ref pairs
        # with both sides' classification; RANK COMPARISON IS IN PYTHON (the
        # partitions are small; SQL rank gymnastics rejected — P-5 posture).
        # The target join through the project-less entity_slug carries the
        # COUNT=1 same-slug guard (Q-049-3 — mirrors the --as-of successor walk
        # + _derive_inverse_edges) so an unrelated same-slug page in another
        # project can never flag a phantom leak. The ref_type pair is a fixed
        # literal (an enum constant, same style as the as-of walk); vault_id is
        # bound. Read-only; zero DDL.
        conn = self._connect()
        rank = {lvl: i for i, lvl in enumerate(levels)}
        sql = (
            "SELECT r.page_slug, r.page_project, r.ref_type, "
            "CAST(json_extract(src.frontmatter_json, '$.classification') AS TEXT)"
            " AS src_cls, "
            "t.slug AS tgt_slug, "
            "CAST(json_extract(t.frontmatter_json, '$.classification') AS TEXT)"
            " AS tgt_cls "
            "FROM page_entity_refs r "
            "JOIN pages src ON src.vault_id = r.vault_id "
            "               AND src.slug = r.page_slug "
            "               AND src.project = r.page_project "
            "JOIN pages t ON t.vault_id = r.vault_id AND t.slug = r.entity_slug "
            "WHERE r.vault_id = ? AND r.ref_type IN ('cited', 'verifies') "
            "AND (SELECT COUNT(*) FROM pages tc WHERE tc.vault_id = r.vault_id "
            "     AND tc.slug = r.entity_slug) = 1 "
            "ORDER BY r.page_project, r.page_slug, t.slug, r.ref_type"
        )
        out: list[ClassificationLeakHit] = []
        for row in conn.execute(sql, (vault_id,)).fetchall():
            src = row["src_cls"] if row["src_cls"] is not None else default_level
            tgt = row["tgt_cls"] if row["tgt_cls"] is not None else default_level
            if src not in rank or tgt not in rank:
                # Out-of-ladder label — rank-incomparable; the
                # invalid-classification check surfaces it separately.
                continue
            if rank[tgt] > rank[src]:
                out.append(ClassificationLeakHit(
                    vault_id=vault_id, page_slug=row["page_slug"],
                    page_project=row["page_project"], page_level=src,
                    target_slug=row["tgt_slug"], target_level=tgt,
                    ref_type=row["ref_type"],
                ))
        return out

    def find_invalid_classifications(
        self, vault_id: str, levels: list[str],
    ) -> list[InvalidClassificationHit]:
        # TASK 049 (R-6) — an authored, non-null classification that is not a
        # declared level (out-of-ladder string OR any non-string value) fails
        # closed out of every scoped retrieval; surface the page (NEVER the
        # value — CWE-209/NFR-4). Absent / JSON-null extract to SQL NULL and
        # are skipped (null ≡ absent). All level values bound.
        conn = self._connect()
        placeholders = ",".join("?" * len(levels))
        sql = (
            "SELECT p.slug, p.project FROM pages p "
            "WHERE p.vault_id = ? "
            "AND json_extract(p.frontmatter_json, '$.classification') IS NOT NULL "
            "AND (json_type(p.frontmatter_json, '$.classification') <> 'text' "
            f"     OR CAST(json_extract(p.frontmatter_json, '$.classification') "
            f"        AS TEXT) NOT IN ({placeholders})) "
            "ORDER BY p.project, p.slug"
        )
        return [
            InvalidClassificationHit(
                vault_id=vault_id, page_slug=r["slug"], page_project=r["project"])
            for r in conn.execute(sql, [vault_id, *levels]).fetchall()
        ]

    def find_verified_slugs(
        self, pairs: list[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        # TASK 050 (R-5) — batched inbound-`verifies` membership, grouped BY
        # VAULT (vdd-multi perf-MED): the `vault_id = ? AND entity_slug IN
        # (...)` shape is guaranteed to seek idx_refs_entity(vault_id,
        # entity_slug), whereas a row-value `(a,b) IN (VALUES ...)` plan is
        # cost-model-dependent and could degrade to an O(refs) scan on the
        # UNCONDITIONAL prepare path. Chunk 400 slugs: well under both the
        # 999-variable cap AND (for the record — vdd-multi logic-LOW) the
        # SQLITE_MAX_COMPOUND_SELECT=500 limit that bounds long VALUES lists.
        # Read-only; zero DDL.
        if not pairs:
            return set()
        conn = self._connect()
        by_vault: dict[str, list[str]] = {}
        for vid, slug in pairs:
            by_vault.setdefault(vid, []).append(slug)
        out: set[tuple[str, str]] = set()
        chunk = 400
        for vid, slugs in by_vault.items():
            for i in range(0, len(slugs), chunk):
                part = slugs[i:i + chunk]
                placeholders = ",".join("?" * len(part))
                rows = conn.execute(
                    "SELECT DISTINCT r.entity_slug FROM page_entity_refs r "
                    "WHERE r.vault_id = ? AND r.ref_type = 'verifies' "
                    f"AND r.entity_slug IN ({placeholders})",
                    [vid, *part],
                ).fetchall()
                out.update((vid, row["entity_slug"]) for row in rows)
        return out

    def find_pages_missing_in_index(
        self, vault_id: str, vault_root: Path
    ) -> list[Path]:
        # TASK 012 / architecture-review C1: route through the one config-driven
        # walk (discover_pages) and compare on (slug, project) — NOT bare f.stem.
        # The old inline walk compared slug-only, which false-negatived a
        # course-tier page sharing a stem with a vault-tier page. Lazy-import to
        # avoid the reindex↔SQLiteRepository import cycle (mirrors check_drift).
        from scripts.wiki_index.reindex import discover_pages

        db_keys = {
            (r["slug"], r["project"])
            for r in self._connect().execute(
                "SELECT slug, project FROM pages WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        }
        missing = [
            f for (f, slug, project) in discover_pages(vault_root)
            if (slug, project) not in db_keys
        ]
        return sorted(missing)

    def check_drift(self, vault_id: str, *, trust_mtime: bool = False) -> DriftReport:
        """Detect Class A↔B drift. **Default = always full sha256** (D-017-B,
        integrity-first: a preserved-mtime tamper must not slip). `trust_mtime=True`
        (the opt-in `wiki-lint --mtime-skip`) skips the read+hash for files whose
        stored `last_modified` still matches disk mtime — fast, integrity-relaxed."""
        from scripts.wiki_source.parsing import compute_file_hash

        conn = self._connect()
        db_rows = {
            (r["slug"], r["project"]): (
                r["type"], r["file_hash"], r["file_path"], r["frontmatter_json"],
                r["last_modified"],
            )
            for r in conn.execute(
                "SELECT slug, project, type, file_hash, file_path, frontmatter_json, "
                "last_modified FROM pages WHERE vault_id = ?", (vault_id,)
            ).fetchall()
        }
        vault = self.get_vault(vault_id)
        if vault is None:
            raise VaultRegistrationError(f"vault_id={vault_id!r} not registered")
        vault_root = vault.root_path

        missing_in_db: list[Path] = []
        hash_mismatch: list[tuple[str, str]] = []
        type_mismatch: list[tuple[str, str, str, str]] = []
        seen_on_disk: set[tuple[str, str]] = set()

        # Walk via iter_pages — the canonical config-driven walk that
        # discover_pages wraps — so each DiscoveredPage carries the SINGLE walk
        # stat's mtime, reused by the P-3 --mtime-skip fast-path (no second stat,
        # TASK 017). The (slug, project) set is identical to discover_pages, so this
        # still mirrors the reindex walk (no false missing-on-disk). layout_config
        # does not import SQLiteRepository → cycle-free local import.
        from scripts.wiki_index.layout_config import iter_pages, resolve_layout_config
        config = resolve_layout_config(vault_root)
        for disc in iter_pages(vault_root, config):
            f, slug, project = disc.path, disc.slug, disc.project
            seen_on_disk.add((slug, project))
            key = (slug, project)
            if key not in db_rows:
                missing_in_db.append(f)
                continue
            db_type, db_hash, _, db_fm, db_lastmod = db_rows[key]
            # P-3 --mtime-skip (opt-in, integrity-relaxed): stored mtime == disk
            # mtime → treat as unchanged, skip read+sha256+type. Default ALWAYS
            # hashes (trust_mtime=False, D-017-B). Comparison is crash-proof: an
            # aware-vs-naive datetime (TypeError) or a malformed stored value
            # (ValueError) degrades to hashing — never raises (fail-safe).
            if trust_mtime and db_lastmod is not None and disc.mtime is not None:
                try:
                    unchanged = (datetime.fromtimestamp(disc.mtime)
                                 == datetime.fromisoformat(db_lastmod))
                except (TypeError, ValueError):
                    unchanged = False
                if unchanged:
                    continue
            # Adapter convention: hash full file bytes (frontmatter + body).
            # See manual.py for why frontmatter-aware hashing matters.
            raw = f.read_bytes()
            cur_hash = compute_file_hash(raw)
            if cur_hash != db_hash:
                hash_mismatch.append((slug, project))
            file_type = self._extract_frontmatter_type(
                raw.decode("utf-8", errors="replace")
            )
            if file_type and file_type != db_type:
                if not self._is_intentional_mapping(file_type, db_type, db_fm or "",
                                                    config.type_mapping):
                    type_mismatch.append((slug, project, file_type, db_type))

        missing_on_disk: list[tuple[str, str]] = [
            (slug, project) for (slug, project) in db_rows
            if (slug, project) not in seen_on_disk
        ]
        return DriftReport(
            missing_in_db=missing_in_db,
            missing_on_disk=missing_on_disk,
            hash_mismatch=hash_mismatch,
            type_mismatch=type_mismatch,
        )

    @staticmethod
    def _is_intentional_mapping(
        file_type: str, db_type: str, db_fm_json: str,
        type_mapping: dict[str, tuple[str, str | None]] | None = None,
    ) -> bool:
        """§6.1 type-mapping: a file's raw `type:` legitimately mapped onto the
        stored `db_type` is NOT drift. Sources, unioned (layout takes precedence):

        - **DF-017-1**: the resolved layout's `type_mapping` (config-driven, TASK 012)
          — without it, non-karpathy layouts (dev-project `known-issue→research`,
          `task/plan→brief`, …) false-positive every mapped page as `type-mismatch`.
        - the karpathy §6.1 defaults (back-compat / when no layout mapping is passed).

        A mapping carrying a marker `tag` additionally requires that tag in the db
        frontmatter — this disambiguates raw types that share a `db_type`
        (lesson-summary/summary-light → summary; dev-project task/plan → brief), so a
        genuine raw-type change is still caught. A null-marker mapping (the layout maps
        the raw type unconditionally) needs only the `db_type` to match."""
        mapping: dict[str, tuple[str, str | None]] = {
            "lesson-summary": ("summary", "lesson-summary"),
            "summary-light": ("summary", "summary-light"),
            "meeting-summary": ("summary", "meeting-summary"),
        }
        if type_mapping:
            mapping = {**mapping, **type_mapping}
        entry = mapping.get(file_type)
        if entry is None:
            return False
        expected_db_type, marker = entry
        if db_type != expected_db_type:
            return False
        if marker is None:
            return True
        try:
            fm = json.loads(db_fm_json) if db_fm_json else {}
        except json.JSONDecodeError:
            return False
        tags = fm.get("tags") or []
        return marker in tags

    # P-3 (TASK 017): line-anchored fast-path for the common `type: <bare-slug>`
    # case, avoiding a full PyYAML parse per page in check_drift. The strict token
    # class is exactly the real type vocabulary (concept, lesson-summary, query, …);
    # because it is letter-led and anchored to EOL, ANY non-trivial value — quoted,
    # flow `[`/`{`, folded/literal `|`/`>`, anchor `&`, inline `# comment`, spaces,
    # or numeric — simply fails to match and falls back to PyYAML, so the result is
    # byte-identical to the previous always-PyYAML behaviour on the corpus. The `[ \t]+`
    # (≥1 space) after the colon mirrors YAML's mapping rule: `type:foo` (no space) is a
    # plain scalar, NOT a mapping → must fall back to PyYAML (yields None), not match "foo".
    _FM_TYPE_RE = re.compile(r"^type:[ \t]+([A-Za-z][A-Za-z0-9._-]*)[ \t]*$", re.MULTILINE)

    @staticmethod
    def _extract_frontmatter_type(body: str) -> str | None:
        """Return the frontmatter `type:` value or None (regex fast-path → PyYAML
        fallback for anything non-trivial; see `_FM_TYPE_RE`)."""
        if not body.startswith("---\n"):
            return None
        parts = body.split("---\n", 2)
        if len(parts) < 3:
            return None
        fm_block = parts[1]
        m = _HealthScanMixin._FM_TYPE_RE.search(fm_block)
        if m is not None:
            return m.group(1)            # clean bare-slug type → trust the fast path
        import yaml as _yaml
        try:
            fm = _yaml.safe_load(fm_block) or {}
        except _yaml.YAMLError:
            return None
        if isinstance(fm, dict):
            val = fm.get("type")
            return val if isinstance(val, str) else None
        return None

    def find_cross_vault_concept_duplicates(self) -> list[tuple[str, list[str]]]:
        rows = self._connect().execute(
            "SELECT slug, GROUP_CONCAT(vault_id, ',') AS vaults, "
            "       COUNT(DISTINCT vault_id) AS n "
            "FROM entities WHERE type = 'concept' "
            "GROUP BY slug HAVING n > 1 ORDER BY slug"
        ).fetchall()
        return [(r["slug"], sorted(r["vaults"].split(","))) for r in rows]


