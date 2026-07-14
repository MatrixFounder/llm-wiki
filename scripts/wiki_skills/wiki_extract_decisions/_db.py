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
