"""Search domain of the SQLite DAL (TASK 056).

`search_pages` relocated from the pre-056 monolith and decomposed (R4) into
module-private helpers — one per filter family — with the public method as
the orchestrator: FTS5 BM25 retrieval + alias-expanded MATCH, metadata
`where_fields` filters, the TASK 034 `--as-of` temporal graph filter,
TASK 035 FTS-narrowed tag membership, and the TASK 049/050
classification/trust policy filters. Every SQL literal and the bound-param
order are byte-identical to the monolith; the existing search/as-of/
membership suites are the equivalence gate.

Declared mixin-dependency edge: `_SearchMixin(_PagesMixin)` — the hit
mapper reuses the private `_row_to_page`, which stays owned by the pages
domain. Per the TASK 056 C3 rule, the composite class lists `_SearchMixin`
and OMITS `_PagesMixin` (inherited transitively).

dialect: SQLite-only core — FTS5 `MATCH` + `bm25()` + `snippet()` and
`json_extract`/`json_each` have no drop-in Postgres equivalent; the
`postgres_repository/` mirror reimplements this module over
tsvector/ts_rank/ts_headline + `jsonb` (see docs/SQLITE-VS-POSTGRES.md §3.2).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from scripts.wiki_index.models import PageHit
from scripts.wiki_index.policy import EXTERNAL_PROVENANCE_KEYS
from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_index.sqlite_repository._base import SQLiteRepositoryBase
from scripts.wiki_index.sqlite_repository._pages import _PagesMixin

# Shared page-column projection for both paths so `_row_to_page` sees an
# identical row shape.
_PAGE_COLS = (
    "p.vault_id, p.slug, p.project, p.type, p.title, p.file_path, "
    "p.tldr, p.date, p.last_modified, p.file_hash, p.frontmatter_json, "
    "p.body_excerpt, p.is_frozen"
)

# TASK 050 (R-6) / TASK 061 (R-061-3) / 061 VDD fix-loop (M2) — the SQL half of
# the external-origin predicate, RENDERED FROM `policy.EXTERNAL_PROVENANCE_KEYS`
# so it can never drift from the Python half (`policy._is_external`) that Q-050-3
# pins it to. The keys are deliberately NOT re-enumerated here: import the constant.
#
# ONE `json_each` PASS (M2) — a pure refactor: SEMANTICS ARE UNCHANGED, and the
# untouched trust suite is the equivalence gate.
#
# WHY. `json_extract` is a row-dependent scalar call and SQLite does no CSE on
# those, so the old form re-parsed the WHOLE frontmatter blob once per
# (key x scheme) — 6 parses/row at TASK 050, and silently 12 after TASK 061-06
# doubled the key list. That is the tell that the "accepted 6x json_extract" note
# (open-questions §11j) was never an acceptance but an unowned debt: its cost grew
# with an edit nobody re-measured. This form parses the blob ONCE per row for ALL
# keys and short-circuits on the first match, so cost is FLAT in the key count.
#
# WHERE IT BITES. The predicate rides all three query shapes, and the *metadata*
# shape (`FROM pages p WHERE 1=1 ... ORDER BY p.project, p.slug`) has no index for
# that ordering: SQLite scans the vault partition and sorts it in a TEMP B-TREE,
# so the LIMIT does NOT bound predicate evaluation — every row in the partition is
# tested, and per-row cost IS the cost. (`EXPLAIN QUERY PLAN` confirms: `SEARCH p
# USING INDEX idx_pages_vault_date` + `USE TEMP B-TREE FOR ORDER BY`.) Fixing this
# by query SHAPE, not by adding an index — P-5 holds, and no DDL (user_version 7).
#
# Precedent for the shape: `_where_fields_clauses` below already does
# `EXISTS (SELECT 1 FROM json_each(p.frontmatter_json, ?) ...)`.
#
# Rationale of each literal:
#   * `_` is a LIKE wildcard, so the `_raw` path segment is ESCAPE'd;
#   * the `http(s)://` prefix is EXACT — never bare `http`, so `httpx://` cannot
#     match; LIKE's default ASCII-ci fold mirrors the Python half's `.lower()`;
#   * `je.key IN (...)` is a case-SENSITIVE binary compare — the deliberate twin
#     of the Python half iterating the constant (enumerate, don't fold: Q-061-2);
#   * `je.type = 'text'` is the exact twin of Python's `isinstance(val, str)`, and
#     preserves the old form's semantics: `json_extract` of a NON-scalar yielded
#     `[`/`{` text which the prefix LIKE rejected, so a list/object-valued key was
#     not external on either half. It still isn't — THIS COMMIT CHANGES NO
#     BEHAVIOR. (That scalar-only semantic is itself the H2 fail-open, fixed in
#     the NEXT commit; keeping the two apart is what makes each reviewable.)
#   * NO COALESCE is needed any more (and none is present): the old form needed it
#     because `json_extract` of an ABSENT key yields NULL and `FALSE OR NULL` =
#     NULL would make `NOT (<ext>)` exclude EVERY unadorned page (three-valued
#     logic). `EXISTS` is 2-valued — 0 or 1, never NULL — so that hazard is gone
#     STRUCTURALLY, not by a guard someone must remember. `json_each(NULL)` yields
#     ZERO ROWS (verified, not assumed), so a NULL-frontmatter row is correctly
#     non-external; malformed JSON raises here exactly as it did under
#     `json_extract` (same pre-existing exposure, no new one); and `file_path` is
#     `NOT NULL` in the schema, so the two path LIKEs cannot be NULL either.
# Fixed literals, no bound params. LIKE count is now a CONSTANT 4 (2 path + 2
# scheme), independent of the key count.
_KEYS_SQL: str = ", ".join(f"'{k}'" for k in EXTERNAL_PROVENANCE_KEYS)


def _http_like(col: str) -> str:
    """`<col>` carries an exact, ASCII-ci `http(s)://` prefix."""
    return f"({col} LIKE 'http://%' OR {col} LIKE 'https://%')"


_EXTERNAL_ORIGIN_SQL: str = (
    "(p.file_path LIKE '\\_raw/%' ESCAPE '\\'"
    " OR p.file_path LIKE '%/\\_raw/%' ESCAPE '\\'"
    # ONE parse of p.frontmatter_json, for ALL keys.
    " OR EXISTS (SELECT 1 FROM json_each(p.frontmatter_json) je"
    f"           WHERE je.key IN ({_KEYS_SQL})"
    f"             AND je.type = 'text' AND {_http_like('je.value')})"
    ")"
)


def _scope_clauses(
    vaults: list[str] | None,
    types: list[str] | None,
    exclude_types: list[str] | None,
    project: str | None,
) -> tuple[list[str], list[Any]]:
    """Vault/type/project scoping predicates (the original clause head)."""
    parts: list[str] = []
    params: list[Any] = []
    if vaults is not None:
        clause, vals = SQLiteRepositoryBase._in_clause("p.vault_id", vaults)
        parts.append(f" AND {clause}")
        params.extend(vals)
    if types is not None:
        clause, vals = SQLiteRepositoryBase._in_clause("p.type", types)
        parts.append(f" AND {clause}")
        params.extend(vals)
    if exclude_types:
        # TASK 007: applied in SQL BEFORE the LIMIT (not post-filtered) so an
        # excluded type cannot consume a top-`limit` slot and evict a real hit.
        placeholders = ",".join("?" * len(exclude_types))
        parts.append(f" AND p.type NOT IN ({placeholders})")
        params.extend(exclude_types)
    if project is not None:
        parts.append(" AND p.project = ?")
        params.append(project)
    return parts, params


def _classification_clauses(
    allowed_classifications: list[str] | None,
    classification_default: str | None,
    classification_home_vault: str | None,
) -> tuple[list[str], list[Any]]:
    """TASK 049 (R-2 / ADR-009) policy visibility filter."""
    if (allowed_classifications is None) != (classification_default is None):
        # TASK 049: both-or-neither (library-caller defense, arch-review
        # MED-2) — a lone allowed-list would make an UNCLASSIFIED page
        # vanish via COALESCE(NULL, NULL) instead of falling back to the
        # vault default_level.
        raise ValueError(
            "allowed_classifications and classification_default must be "
            "provided together")
    parts: list[str] = []
    params: list[Any] = []
    if allowed_classifications is not None:
        if not allowed_classifications:
            raise ValueError("allowed_classifications must be non-empty")
        # TASK 049 (R-2 / ADR-009): the policy visibility filter. Fixed
        # literal JSON path; default + every level bound; applied via the
        # shared clause_parts so it lands on all three query shapes BEFORE
        # the LIMIT (exclude_types rationale — a filtered page must never
        # consume a top-limit slot). CAST normalizes a numeric/boolean
        # authored value to text (the where_fields scalar-branch rationale).
        # Unknown/foreign labels are excluded automatically — fail-closed.
        placeholders = ",".join("?" * len(allowed_classifications))
        if classification_home_vault is not None:
            # vdd-multi SEC-2: the default_level fallback applies ONLY to
            # the profile's HOME vault — a foreign vault's UNCLASSIFIED
            # page must not inherit it (its own vault may intend a higher
            # default). CASE yields NULL for foreign rows → COALESCE stays
            # NULL → `NULL IN (...)` is not true → fail closed; a foreign
            # page explicitly labeled with an in-ladder level still passes.
            parts.append(
                " AND COALESCE(CAST(json_extract(p.frontmatter_json,"
                " '$.classification') AS TEXT),"
                " CASE WHEN p.vault_id = ? THEN ? END)"
                f" IN ({placeholders})"
            )
            params.append(classification_home_vault)
            params.append(classification_default)
        else:
            # No known home vault (built-in ladder outside any vault, or
            # an unregistered root): the default applies uniformly —
            # documented; matches the single-vault case where every page
            # IS the home vault's.
            parts.append(
                " AND COALESCE(CAST(json_extract(p.frontmatter_json,"
                " '$.classification') AS TEXT), ?)"
                f" IN ({placeholders})"
            )
            params.append(classification_default)
        params.extend(allowed_classifications)
    return parts, params


def _min_trust_clauses(min_trust: str | None) -> list[str]:
    """TASK 050 (R-6) derived-trust floor — fixed literals, no params."""
    parts: list[str] = []
    if min_trust is not None:
        # TASK 050 (R-6): derived-trust floor, pre-LIMIT on all three query
        # shapes. The external-origin predicate is `_EXTERNAL_ORIGIN_SQL`
        # above — fixed literals (no params), rendered from the SAME
        # `policy.EXTERNAL_PROVENANCE_KEYS` as the Python half it is
        # test-pinned to (Q-050-3).
        if min_trust not in ("external", "internal", "verified"):
            raise ValueError(
                "min_trust must be one of external|internal|verified")
        if min_trust in ("internal", "verified"):
            parts.append(f" AND NOT {_EXTERNAL_ORIGIN_SQL}")
        if min_trust == "verified":
            parts.append(
                " AND EXISTS (SELECT 1 FROM page_entity_refs vr"
                "             WHERE vr.vault_id = p.vault_id"
                "               AND vr.entity_slug = p.slug"
                "               AND vr.ref_type = 'verifies')")
        # min_trust == 'external' imposes no clause (the lowest floor).
    return parts


def _where_fields_clauses(
    where_fields: list[tuple[str, str]] | None,
) -> tuple[list[str], list[Any]]:
    """TASK 013/033 metadata filters (scalar equality OR list membership)."""
    parts: list[str] = []
    params: list[Any] = []
    for field, value in where_fields or []:
        # TASK 013 (R-X3-META-FILTER) + TASK 033 (R-1, list membership):
        # library-caller defense — re-validate the field name (CLI validates
        # too), then bind the JSON path and the value as parameters (FOUR per
        # field, order `(path, value, path, value)` — B-1; positional `?` can't
        # be reused across the two subexpressions). No operator string ever
        # reaches the SQL text.
        #
        # Branch 1 — SCALAR equality. `CAST(... AS TEXT)` matches by STRING
        #   representation: `json_extract` returns the value in its native JSON
        #   storage class (INTEGER 1 for `priority: 1`), which SQLite will NOT
        #   equate to a TEXT-bound `'1'`; the CAST normalises both sides so a
        #   numeric/boolean frontmatter value matches the (always-string) CLI
        #   value, while string values stay byte-identical.
        # Branch 2 — LIST MEMBERSHIP (TASK 033). `json_each` over a list field
        #   (`tags: [eg-demo, decision]` — the TASK-031 typed-class tag) yields
        #   one row per member, so `value = ?` matches a single member that the
        #   scalar branch's whole-array text never could. Over a SCALAR field
        #   json_each yields one row equal to the scalar (so the OR is a strict
        #   superset → scalar `--status`/`--severity` result sets are UNCHANGED,
        #   AC-3); over an ABSENT path it yields zero rows (no match, no error).
        #   This is the proven `find_pages_citing_source` shape (M-1: the
        #   membership branch is text-only — no CAST — so a NUMERIC list member
        #   is not string-coerced; the typed-class `tags[]` use case is all text).
        validate_filter_field(field)
        parts.append(
            " AND (CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?"
            " OR EXISTS (SELECT 1 FROM json_each(p.frontmatter_json, ?)"
            "            WHERE value = ?))"
        )
        json_path = f"$.{field}"
        params.append(json_path)
        params.append(value)
        params.append(json_path)
        params.append(value)
    return parts, params


def _as_of_clauses(as_of: str | None) -> tuple[list[str], list[Any]]:
    """TASK 034 / R-1 — temporal "active as of DATE" filter."""
    parts: list[str] = []
    params: list[Any] = []
    if as_of is not None:
        # TASK 034 / R-1 — temporal "active as of DATE" filter. A page is active
        # iff its effective_from <= DATE AND DATE < its effective_to, where:
        #   effective_from = COALESCE(authored valid_from, pages.date)
        #   effective_to   = authored valid_to  (explicit override, half-open),
        #                    ELSE the date of the earliest page that SUPERSEDES or
        #                    INVALIDATES it (the TASK 032/034 graph), ELSE +inf.
        # Frontmatter dates are stored as ISO strings (`_json_safe`, normalization
        # .py) and `pages.date` is `.isoformat()` TEXT, so the comparisons are
        # lexicographic = chronological. The `valid_from`/`valid_to` JSON paths are
        # FIXED literals (no user field name → no allowlist needed); DATE is bound
        # 3× as a parameter (never interpolated). A page with neither valid_from nor
        # a `date` is EXCLUDED (the IS NOT NULL clause) so non-temporal pages do not
        # pollute the result. The `NOT EXISTS` successor-walk rides idx_refs_page +
        # the pages PK and is bounded by the outer LIMIT.
        # `substr(...,1,10)` takes the DATE part of an authored valid_from/valid_to
        # so a datetime-valued override (`2026-02-01 14:30` → ISO `...T14:30:00`)
        # keeps the half-open [from, to) DAY boundary (vdd-multi logic MED-2);
        # bare-date overrides are unchanged (`substr` is a no-op on `YYYY-MM-DD`).
        # `pages.date` is already a pure ISO date (Page.date.isoformat()), so it is
        # NOT wrapped. The successor walk excludes a target slug that resolves to >1
        # page: the project-less `entity_slug` cannot disambiguate, so — mirroring
        # `_derive_inverse_edges`' COUNT=1 guard — an unrelated same-slug page in
        # ANOTHER project can never wrongly retire P (vdd-multi logic MED-1; a no-op
        # on single-project vaults where every slug is unique, conservative
        # "stay active when ambiguous" otherwise).
        parts.append(
            " AND COALESCE(substr(json_extract(p.frontmatter_json, '$.valid_from'), 1, 10),"
            "              p.date) IS NOT NULL"
            " AND COALESCE(substr(json_extract(p.frontmatter_json, '$.valid_from'), 1, 10),"
            "              p.date) <= ?"
            " AND (substr(json_extract(p.frontmatter_json, '$.valid_to'), 1, 10) > ?"
            "      OR (json_extract(p.frontmatter_json, '$.valid_to') IS NULL"
            "          AND NOT EXISTS (SELECT 1 FROM page_entity_refs r"
            "             JOIN pages s ON s.vault_id = r.vault_id"
            "                         AND s.slug = r.entity_slug"
            "             WHERE r.vault_id = p.vault_id AND r.page_slug = p.slug"
            "               AND r.ref_type IN ('superseded-by', 'invalidated-by')"
            "               AND s.date IS NOT NULL AND s.date <= ?"
            "               AND (SELECT COUNT(*) FROM pages tc"
            "                    WHERE tc.vault_id = r.vault_id"
            "                      AND tc.slug = r.entity_slug) = 1)))"
        )
        params.append(as_of)
        params.append(as_of)
        params.append(as_of)
    return parts, params


def _metadata_rows(
    conn: sqlite3.Connection,
    clause_sql: str,
    clause_params: list[Any],
    where_fields: list[tuple[str, str]] | None,
    use_fts_narrowing: bool,
    limit: int,
) -> list[sqlite3.Row]:
    """TASK 013 metadata path (no MATCH term), incl. TASK 035 FTS narrowing."""
    # TASK 013 metadata path: pure listing, no BM25 (score 0.0, empty
    # snippet); deterministic (project, slug, vault_id) ordering — vault_id
    # breaks ties across vaults in an all-vaults listing.
    meta_cols = f"SELECT {_PAGE_COLS}, 0.0 AS bm25_score, '' AS snip "
    meta_tail = clause_sql + " ORDER BY p.project, p.slug, p.vault_id LIMIT ?"
    scan_sql = meta_cols + "FROM pages p WHERE 1=1" + meta_tail
    scan_params: list[Any] = [*clause_params, limit]

    # TASK 035 (R-X3-MF-SCAN, ADR-005): when an only-metadata query carries a
    # `tags` membership predicate, narrow the candidate set through the
    # ALREADY-EXISTING, already-maintained `pages_fts.tags` index ("FTS
    # narrows, json_each confirms") instead of scanning the whole partition.
    # The json_each(...) = ? confirm above stays, so the result is BYTE-
    # IDENTICAL to the scan: the FTS column-match is a superset (the same
    # unicode61 tokenizer folds both sides, so an exact array element's
    # tokens always appear in that element's FTS text — all-or-nothing per
    # value), and the confirm removes the FTS extras.
    fts_value: str | None = None
    if use_fts_narrowing:
        for field, value in where_fields or []:
            # `isinstance(str)` guards a non-str library-caller value (the CLI
            # only ever sends str): an int/float `value` would crash
            # `any(c.isalnum() ...)` AND has no FTS-phrase form — skip
            # narrowing → the scan binds it into json_each exactly as before
            # (vdd-multi critic-logic MED; the scan path never crashed on it).
            # `any(isalnum)` is then a PERF fast-path only (skip the FTS probe
            # for an obviously-tokenless value) — NOT the correctness gate;
            # that is the FTS-empty→scan fallback below (ADR-005 D3).
            if (field == "tags" and isinstance(value, str)
                    and any(c.isalnum() for c in value)):
                fts_value = value
                break
    if fts_value is not None:
        # `tags` is a FIXED literal column name; the value is the single bound
        # MATCH parameter, FTS-phrase-quoted ('"'-doubled) so any FTS operator
        # or quote inside it is inert (the SQL text carries only `MATCH ?`).
        # Mirror of `scripts/wiki_skills/_retrieval.fts_quote`, inlined to
        # avoid a wiki_index→wiki_skills layering inversion (ADR-005 D5).
        match_param = 'tags : "' + fts_value.replace('"', '""') + '"'
        fts_sql = (
            meta_cols + "FROM pages_fts JOIN pages p "
            "ON pages_fts.rowid = p.id WHERE pages_fts MATCH ?" + meta_tail
        )
        try:
            rows = conn.execute(
                fts_sql, [match_param, *scan_params]).fetchall()
        except sqlite3.OperationalError:
            # Belt-and-braces: a degenerate MATCH (near-unreachable — the
            # phrase-quote always emits a valid FTS literal) → fall back.
            rows = conn.execute(scan_sql, scan_params).fetchall()
        else:
            # Load-bearing safety net (ADR-005 D3): a value FTS can't tokenize
            # (e.g. `½`/`②` — isalnum-true but no unicode61 token) yields ∅,
            # which — because the match is all-or-nothing per value — is
            # indistinguishable from a genuinely-empty result. Re-run the scan
            # so a literal-tag page can never be silently under-matched.
            if not rows:
                rows = conn.execute(scan_sql, scan_params).fetchall()
    else:
        rows = conn.execute(scan_sql, scan_params).fetchall()
    return rows


class _SearchMixin(_PagesMixin):
    """FTS5 search (task-001-17 lineage, R-29 multi-vault)."""

    def search_pages(
        self,
        query: str | None,
        *,
        vaults: list[str] | None = None,
        types: list[str] | None = None,
        exclude_types: list[str] | None = None,
        project: str | None = None,
        where_fields: list[tuple[str, str]] | None = None,
        as_of: str | None = None,
        allowed_classifications: list[str] | None = None,
        classification_default: str | None = None,
        classification_home_vault: str | None = None,
        min_trust: str | None = None,
        limit: int = 20,
        _use_fts_narrowing: bool = True,
    ) -> list[PageHit]:
        # `_use_fts_narrowing` is a PRIVATE test seam (TASK 035) — not in the ABC
        # contract. Default True = production (FTS-narrow the metadata `tags`
        # membership path); the equivalence tests pass False to drive the REAL plain
        # scan over the same input and assert byte-identical results (ADR-005 D2).
        conn = self._connect()
        has_match = bool(query)
        if not has_match and not where_fields and not as_of:
            # TASK 013: a search with neither an FTS term nor a metadata filter
            # (TASK 034: nor an `as_of` temporal filter) is meaningless. The CLI
            # refuses this before calling; the DAL defends the library-caller path.
            raise ValueError(
                "search_pages requires a non-empty query, at least one "
                "where_fields predicate, or an as_of date"
            )
        # TASK 035: the AND-clauses below are IDENTICAL across the FTS-query path, the
        # metadata scan, and the metadata FTS-narrowed path — built ONCE (helper by
        # helper, in the original in-line order, separate from the SELECT prefix) so
        # the three query shapes can never drift.
        clause_parts: list[str] = []
        clause_params: list[Any] = []
        for parts, params in (
            _scope_clauses(vaults, types, exclude_types, project),
            _classification_clauses(
                allowed_classifications,
                classification_default,
                classification_home_vault,
            ),
            (_min_trust_clauses(min_trust), []),
            _where_fields_clauses(where_fields),
            _as_of_clauses(as_of),
        ):
            clause_parts.extend(parts)
            clause_params.extend(params)
        clause_sql = "".join(clause_parts)

        if has_match:
            # FTS path (today's behaviour): BM25-ranked. Untouched by TASK 035 —
            # the issue notes the json_extract/json_each predicates run only on the
            # already-small MATCH candidate set here (a non-issue).
            sql = (
                f"SELECT {_PAGE_COLS}, bm25(pages_fts) AS bm25_score, "
                "snippet(pages_fts, -1, '<b>', '</b>', '...', 16) AS snip "
                "FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id "
                "WHERE pages_fts MATCH ?"
                + clause_sql + " ORDER BY bm25_score ASC LIMIT ?"
            )
            rows = conn.execute(sql, [query, *clause_params, limit]).fetchall()
        else:
            rows = _metadata_rows(
                conn, clause_sql, clause_params,
                where_fields, _use_fts_narrowing, limit,
            )

        hits: list[PageHit] = []
        for row in rows:
            page = self._row_to_page(row)
            hits.append(PageHit(
                page=page,
                bm25_score=row["bm25_score"],
                snippet=row["snip"] or "",
            ))
        return hits
