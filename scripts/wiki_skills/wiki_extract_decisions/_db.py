"""DB reads for the extraction rail (TASK 063) — `source_state` + typed pages.

ZERO-DDL: `user_version` stays 7. Everything here rides existing columns +
`frontmatter_json`. The rail adds no table and no index (P-5 — no speculative
indexes; these reads are bounded and run once per invocation, not per file).

Raw SQL via `repo._connect()` rather than new DAL methods — the established
pattern for skill-local reads (`wiki_extract_concepts/_db.py`, and `reindex.py`
does the same). Multi-vault isolation rides the `vault_id = ?` predicate on EVERY
query (ADR-002 §D1.1); there is no query here without one.

★ THE TYPED CLASS IS `frontmatter_json.$.type`, NOT `pages.type`. The column is
the COARSE db_type (concept / research / brief / …) that a layout's `type_mapping`
routes a class ONTO; the authored class survives only in the frontmatter. Every
R-15/R-19 rule keys on `$.type` for exactly this reason (`_health_rules.py`) — and
a query here using `pages.type` would silently match the wrong population, because
`decision` and `risk` BOTH route to `research`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# A DISTINCT partition key. `source_state` is shared with the concepts rail, and a
# shared key would let one rail's extraction mark the other's source "unchanged" —
# each must be able to re-run a source the other has already consumed.
_SOURCE_KIND = "extract-decisions"


def check_idempotency(
    repo: Any, vault_id: str, source_slug: str, current_hash: str
) -> bool:
    """True iff THIS rail has already extracted this exact source body (R-063-5).

    The explicit NULL check is defensive: the schema says `value TEXT NOT NULL`, so
    a NULL means corruption or a future schema — and the safe answer there is
    False (re-extract), which is worth stating rather than arriving at by accident.
    """
    row = repo._connect().execute(
        "SELECT value FROM source_state "
        "WHERE vault_id = ? AND source_kind = ? AND scope = ? AND key = ?",
        (vault_id, _SOURCE_KIND, source_slug, "source_hash"),
    ).fetchone()
    if row is None or row["value"] is None:
        return False
    return bool(row["value"] == current_hash)


def update_idempotency_state(
    repo: Any, vault_id: str, source_slug: str, new_hash: str
) -> None:
    """Record that this rail has extracted this body.

    ★ CALLED LAST, AND ONLY ON FULL SUCCESS (the C-1 invariant). If the index step
    failed, this row must stay UNSET — otherwise the retry sees "unchanged", no-ops,
    and the written pages never reach the index. A source marked done before the work
    finished is worse than one not marked at all: the second is retried, the first is
    silently abandoned."""
    now = datetime.now(timezone.utc).isoformat()
    repo._connect().execute(
        "INSERT INTO source_state (vault_id, source_kind, scope, key, value, "
        "                          updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (vault_id, source_kind, scope, key) DO UPDATE SET "
        "  value = excluded.value, updated_at = excluded.updated_at",
        (vault_id, _SOURCE_KIND, source_slug, "source_hash", new_hash, now),
    )
    repo._connect().commit()


def load_typed_pages(
    repo: Any, vault_id: str, roster: tuple[str, ...]
) -> list[dict[str, Any]]:
    """The vault's EXISTING typed pages — what `prepare` hands the REASON step so
    it can LINK to prior knowledge instead of silently duplicating it.

    Without it, extracting a second protocol re-mints a decision that already
    exists under a different slug, and the graph grows two nodes for one fact — a
    loss no lint rule can catch, because both pages are individually valid."""
    if not roster:
        return []
    placeholders = ",".join("?" for _ in roster)
    rows = repo._connect().execute(
        f"SELECT slug, project, title, file_path, "
        f"       json_extract(frontmatter_json, '$.type')   AS cls, "
        f"       json_extract(frontmatter_json, '$.status') AS status "
        f"FROM pages "
        f"WHERE vault_id = ? "
        f"  AND json_extract(frontmatter_json, '$.type') IN ({placeholders}) "
        f"ORDER BY slug",
        (vault_id, *roster),
    ).fetchall()
    return [
        {"slug": r["slug"], "class": r["cls"], "status": r["status"],
         "title": r["title"], "file_path": r["file_path"]}
        for r in rows
    ]


def load_existing_page_slugs(repo: Any, vault_id: str) -> list[str]:
    """Every page slug — the collision-guard SNAPSHOT `prepare` hands out.

    A SNAPSHOT, and `apply` RE-CHECKS it: between the two calls the orchestrator
    reasons, which takes real time, and a slug minted meanwhile (a concurrent
    import, the operator typing) would collide. A slug collision does not error —
    it OVERWRITES."""
    rows = repo._connect().execute(
        "SELECT DISTINCT slug FROM pages WHERE vault_id = ? ORDER BY slug",
        (vault_id,),
    ).fetchall()
    return [str(r["slug"]) for r in rows]


def load_own_page_slugs(repo: Any, vault_id: str, source_slug: str) -> set[str]:
    """Slugs of pages THIS rail already wrote FROM THIS SOURCE (`extracted_from`).

    ★ THE OWNERSHIP LINE (R-063-9). The existing-page-collision drop exists to protect
    SOMEONE ELSE'S page — never our own. Without this distinction a re-extraction
    (`--force`, or a corrected source) would DROP every page the previous run wrote,
    because their slugs now exist, and the rail would become a one-shot: it could
    create knowledge but never correct it.

    Found by the idempotency test, not by review: after `--ingest`, the rail's own
    pages are in the index, and the very next `--force` run treated them as foreign.

    A page NOT carrying our `extracted_from` is somebody else's — a hand-authored
    page, or one from another source — and Class A is the operator's: we drop the
    candidate rather than overwrite it.
    """
    rows = repo._connect().execute(
        "SELECT slug FROM pages "
        "WHERE vault_id = ? "
        "  AND json_extract(frontmatter_json, '$.extracted_from') = ?",
        (vault_id, source_slug),
    ).fetchall()
    return {str(r["slug"]) for r in rows}


def load_resolvable_targets(repo: Any, vault_id: str) -> set[str]:
    """Everything an authored ref may legally point at: page slugs ∪ entity slugs
    ∪ **entity ALIASES** — all three (R-063-2).

    The aliases are the half that is easy to omit and expensive to miss: the
    operator's vault resolves `[[Айва]]` onto the `aiva` entity through an alias
    row, so a G2 check that knew only slugs would refuse a ref the index resolves
    perfectly well — the rail would refuse a CORRECT batch, and the operator would
    learn to pass `--force`."""
    conn = repo._connect()
    out: set[str] = set()
    for sql in (
        "SELECT slug  FROM pages          WHERE vault_id = ?",
        "SELECT slug  FROM entities       WHERE vault_id = ?",
        "SELECT alias FROM entity_aliases WHERE vault_id = ?",
    ):
        out.update(str(r[0]) for r in conn.execute(sql, (vault_id,)).fetchall())
    return out


def resolve_target_classes(
    repo: Any, vault_id: str, slugs: list[str]
) -> dict[str, str]:
    """slug → typed class, for edge targets OUTSIDE the batch.

    G1's RANGE check needs this. Without it the check could only see targets inside
    the batch — and an edge into the EXISTING graph (`supersedes: dec-old-thing`)
    is precisely where a range error hides, because that is where the model is
    reasoning about a page it never read."""
    if not slugs:
        return {}
    placeholders = ",".join("?" for _ in slugs)
    rows = repo._connect().execute(
        f"SELECT slug, json_extract(frontmatter_json, '$.type') AS cls "
        f"FROM pages WHERE vault_id = ? AND slug IN ({placeholders})",
        (vault_id, *slugs),
    ).fetchall()
    return {str(r["slug"]): str(r["cls"]) for r in rows if r["cls"]}


def load_target_statuses(
    repo: Any, vault_id: str, slugs: list[str]
) -> dict[str, str]:
    """slug → its AUTHORED `status` scalar, for G3's precondition.

    Only a SCALAR text status is read (`json_type(...) = 'text'`) — the SAME predicate
    the drift rule itself uses (`_health_rules.py:311`). An absent status, or a
    non-scalar one (`status: [superseded]` json_extract's to the TEXT `["superseded"]`
    and would phantom-match), NEVER drifts — so it must never be patched either.
    Reading it with a different predicate than the rule fires on is how a "fix" comes
    to edit a page that was never drifting."""
    if not slugs:
        return {}
    placeholders = ",".join("?" for _ in slugs)
    rows = repo._connect().execute(
        f"SELECT slug, CAST(json_extract(frontmatter_json, '$.status') AS TEXT) AS st "
        f"FROM pages "
        f"WHERE vault_id = ? AND slug IN ({placeholders}) "
        f"  AND json_type(frontmatter_json, '$.status') = 'text'",
        (vault_id, *slugs),
    ).fetchall()
    return {str(r["slug"]): str(r["st"]) for r in rows}


def load_page_paths(repo: Any, vault_id: str, slugs: list[str]) -> dict[str, str]:
    """slug → vault-relative `file_path`. The column is `file_path` (never
    `source_path`) — going through the index rather than a filesystem search is what
    makes this work on an iCloud vault with Cyrillic, spaces and `.icloud`
    placeholders."""
    if not slugs:
        return {}
    placeholders = ",".join("?" for _ in slugs)
    rows = repo._connect().execute(
        f"SELECT slug, file_path FROM pages "
        f"WHERE vault_id = ? AND slug IN ({placeholders})",
        (vault_id, *slugs),
    ).fetchall()
    return {str(r["slug"]): str(r["file_path"]) for r in rows}


def count_open_commitments(repo: Any, vault_id: str) -> int:
    """Requirements carrying no `implemented-by` edge — reported as DATA, exit 0.

    ★ NEVER A DEFECT TO CLOSE (Q-063-4). This is the one number in the envelope
    that must not read as a failure. If an open commitment looked like something
    the run ought to have fixed, the model's cheapest path to a clean report would
    be to INVENT a decision that closes it. A gap in the knowledge graph is a FACT
    about the engagement: TASK 062 surfaced three from the operator's own protocols
    and every one was a real open question with a real client.
    """
    row = repo._connect().execute(
        "SELECT COUNT(*) AS n FROM pages p "
        "WHERE p.vault_id = ? "
        "  AND json_extract(p.frontmatter_json, '$.type') = 'requirement' "
        "  AND NOT EXISTS ("
        "     SELECT 1 FROM page_entity_refs r "
        "     WHERE r.vault_id = p.vault_id AND r.page_slug = p.slug "
        "       AND r.ref_type = 'implemented-by')",
        (vault_id,),
    ).fetchone()
    return int(row["n"]) if row else 0
