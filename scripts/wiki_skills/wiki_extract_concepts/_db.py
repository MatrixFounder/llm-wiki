"""DB / entity / manifest leaf for the concept extractor (TASK 016).

Depends only on `_validation` (`_parse_source_span`) + stdlib + the DAL models
(`scripts.wiki_index.models.PageRef`, lazily imported inside `upsert_entity_refs`
to match the pre-016 source). Takes an already-open `repo` — does NOT construct
one (`make_repo` stays in the facade, a lock symbol).

**Patch-target-lock carve-out (R-016-2):** `load_known_entities` and
`update_idempotency_state` are monkeypatched by tests at the facade
(`scripts.wiki_skills.wiki_extract_concepts.<name>`). The facade re-imports them
from here and its callers (`_load_known_and_drift`/`_apply_write`/`apply` call
`load_known_entities`; `_try_update_idempotency_state` calls
`update_idempotency_state`) reference them as bare facade globals, so a
`mock.patch` on the facade still intercepts. Do NOT call these qualified
(`_db.load_known_entities`) from the facade — that would break the lock.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ._errors import ExtractionParseError
from ._validation import _parse_source_span, _sanitize_definition

# source_kind partition key for `source_state` idempotency rows (used only by
# check_idempotency / update_idempotency_state, both below).
_SOURCE_KIND = "extract-concepts"


def check_page_slug_collisions(
    repo: Any,
    vault_id: str,
    create_list: list[dict[str, Any]],
    vault_root: Path,
    concepts_dir: Path,
    source_slug: str,
) -> None:
    """★★ F6 (TASK 064) — REFUSE A CONCEPT THAT WOULD **EVICT AN EXISTING PAGE**.

    `pages` is `UNIQUE(vault_id, slug, project)`. Writing a concept page whose slug
    equals an existing page's slug in the same project makes the indexer's `upsert_page`
    silently REPLACE that row — its `type` and its `file_path`. The victim page is then
    GONE from the index: not in `wiki-search`, not in the graph, no error, no warning, no
    lint issue. Exit 0.

    The easy live case is the SOURCE NOTE'S OWN SLUG — extract the concept `backtesting`
    from `_sources/backtesting.md` and the note evicts itself. Reproduced end to end:
    `pages` went from ('backtesting','summary','_sources/backtesting.md') to
    ('backtesting','concept','_concepts/backtesting.md'), rc=0.

    Every other gate on this rail compares candidates against the `entities` table and the
    on-disk `_concepts/` pages — **never against `pages`**, which is the table that
    actually gets evicted. `wiki-import`'s `derive_candidates` has guarded exactly this for
    a year (`self-collision` + `collides-existing-page` in `_authoring.py`); the guard was
    simply never ported to this rail. This is that port: pre-write, zero-file.

    ⚠️ THE GHOST-ROW CARVE-OUT (TASK 053 / R3). A `pages` row whose `file_path` IS the
    concept page we are about to write is not a victim — it is a STALE row for a page that
    was deleted without a reindex, and re-creating that page is the self-heal the
    classifier just asked for. Compare `file_path`, not merely `slug`.

    CWE-209: the violation names the model's own slug and the VAULT-RELATIVE path of the
    page it would evict (the same shape the success envelope already emits in
    `written[].path`) — never an absolute path, never a byte of either file's content.
    """
    from scripts.wiki_index.layout_config import derive_project_for_path

    if not create_list:
        return
    conn = repo._connect()
    violations: list[dict[str, Any]] = []
    for cand in create_list:
        slug = str(cand["slug"])
        target = concepts_dir / f"{slug}.md"
        target_rel = target.relative_to(vault_root).as_posix()
        project = derive_project_for_path(target, vault_root)
        row = conn.execute(
            "SELECT type, file_path FROM pages "
            "WHERE vault_id = ? AND slug = ? AND project = ?",
            (vault_id, slug, project),
        ).fetchone()
        if row is None:
            continue
        page_type, file_path = str(row[0]), str(row[1])
        if file_path == target_rel:
            continue  # the ghost row for the very page we are re-creating — self-heal
        violations.append({
            "slug": slug,
            "occupied_by": file_path,
            "page_type": page_type,
            "is_source_note": slug == source_slug,
        })
    if violations:
        raise ExtractionParseError(
            f"{len(violations)} candidate slug(s) collide with an existing page",
            error="SLUG_COLLIDES_WITH_PAGE",
            field="slug",
            reason=("this slug is already taken by a DIFFERENT page in the index "
                    "(`occupied_by`). Filing a concept there would EVICT that page from "
                    "the index — it would vanish from wiki-search with no error. If the "
                    "collision is with the source note itself, the concept is the note's "
                    "own topic: it does not need a concept page. Otherwise, give the "
                    "concept a more specific name."),
            violations=violations,
        )


def load_known_entities(repo: Any, vault_id: str) -> list[dict[str, Any]]:
    """SELECT entities LEFT JOIN entity_aliases WHERE vault_id=?.

    Returns CONTRACT §2 known-concepts format:
        [{"slug": "...", "name": "...", "type": "...", "aliases": [...]}]
    Empty vault → empty list (R-32c). Multi-vault isolation enforced via
    the `vault_id = ?` predicate (ADR-002 §D1.1).

    Implementation note: raw SQL via ``repo._connect()`` rather than a new
    DAL method, per TASK.md §1.3 non-goal (DAL extension surface tight).
    Same pattern used by ``scripts/wiki_index/reindex.py``.
    """
    conn = repo._connect()
    rows = conn.execute(
        "SELECT slug, name, type FROM entities WHERE vault_id = ? ORDER BY slug",
        (vault_id,),
    ).fetchall()
    if not rows:
        return []
    aliases_by_slug: dict[str, list[str]] = {}
    alias_rows = conn.execute(
        "SELECT entity_slug, alias FROM entity_aliases "
        "WHERE vault_id = ? ORDER BY entity_slug, alias",
        (vault_id,),
    ).fetchall()
    for entity_slug, alias in alias_rows:
        aliases_by_slug.setdefault(entity_slug, []).append(alias)
    return [
        {
            "slug": slug,
            "name": name,
            "type": type_,
            "aliases": aliases_by_slug.get(slug, []),
        }
        for slug, name, type_ in rows
    ]


def _lookup_entity_row(
    repo: Any, vault_id: str, slug: str,
) -> dict[str, Any] | None:
    """Direct lookup bypassing repo.resolve_entity (still a stub per
    Phase 3a — TASK.md §1.3 keeps it as NotImplementedError until R-4)."""
    row = repo._connect().execute(
        "SELECT slug, name, is_candidate, first_seen, type "
        "FROM entities WHERE vault_id = ? AND slug = ?",
        (vault_id, slug),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def upsert_extracted_entity(
    repo: Any,
    vault_id: str,
    candidate: dict[str, Any],
    source_slug: str,
    today: date,
    orchestrator_id: str = "orchestrator",
    concepts_rel: str = "_concepts",
) -> str:
    """Upsert an extracted entity row with defensive downgrade-guard.

    Returns one of:
        - "confirmed"  — existing row had is_candidate=0; SKIPPED (no write).
        - "created"    — row did not exist; INSERTED with is_candidate=1.
        - "updated"    — existing candidate row was UPDATED.

    The SQL-level guard in ``upsert_entity`` (003-07a) is the *primary*
    defense; this call-layer skip is defense-in-depth — both let confirmed
    entities (R-37b) survive intact. Skipping at the call layer also
    avoids a no-op write that would touch last_updated unnecessarily.

    v3.1 (003-v3-05 / H-8): the ``orchestrator_id`` parameter populates
    ``canonicalized_by = f"llm:{orchestrator_id}@{today}"``. Defaults to
    the literal string ``"orchestrator"`` so operators who omit
    ``--orchestrator-id`` get an honest unknown rather than a hallucinated
    model attribution (Q9-v3.1).
    """
    existing = _lookup_entity_row(repo, vault_id, candidate["slug"])
    if existing is not None and existing.get("is_candidate") == 0:
        return "confirmed"
    today_iso = today.isoformat() if isinstance(today, date) else str(today)
    canonicalized_by = f"llm:{orchestrator_id}@{today_iso}"
    first_seen = existing["first_seen"] if existing else today_iso
    repo.upsert_entity(
        vault_id=vault_id,
        slug=candidate["slug"],
        name=candidate["name"],
        type=candidate["entity_type"],
        is_candidate=1,
        canonicalized_by=canonicalized_by,
        first_seen=first_seen,
        last_updated=today_iso,
        # TASK 037 / R-5: `concepts_rel` is the vault-relative dir the page was
        # actually written to (`_concepts` for Karpathy vault-tier — byte-
        # identical default; `<area>/<sub>/_concepts` for PARA) so the entity's
        # recorded path matches the on-disk file and `wiki-lint` doesn't flag it
        # missing-on-disk.
        file_path=f"{concepts_rel}/{candidate['slug']}.md",
        # ★ R-23 / DF-064-1 — THE SANITIZED definition, NOT the raw candidate.
        #
        # `write_concept_page` puts `_sanitize_definition(candidate["definition"])` into the
        # page body. The body is Class A — canonical — and `wiki-reindex --full` reads the
        # definition back OUT of it. So the row must hold exactly those bytes, or the very
        # first `--full` rebuild would CHANGE the column and ADR-002 §D8 (Class B is a
        # 100%-rebuildable cache of Class A) would be broken by this write.
        #
        # Same pure function, same input, on both sides ⇒ identical string by construction.
        # `test_the_definition_ROUND_TRIPS_byte_identically` is the gate that keeps it so.
        definition=_sanitize_definition(str(candidate["definition"])),
    )
    return "updated" if existing else "created"


def upsert_entity_refs(
    repo: Any,
    vault_id: str,
    source_slug: str,
    source_project: str,
    all_candidates: list[dict[str, Any]],
) -> None:
    """Atomic ``replace_refs`` for all extracted entities (create + mention).

    R-38, R-40. Atomic DELETE+INSERT keyed on (vault_id, page_slug, project)
    so re-extraction on a changed body (UC-09 Scenario B) does not leave
    stale refs interleaved with new ones.
    """
    from scripts.wiki_index.models import PageRef
    refs: list[PageRef] = []
    for cand in all_candidates:
        line_start, line_end = _parse_source_span(cand["source_span"])
        refs.append(PageRef(
            vault_id=vault_id,
            page_slug=source_slug,
            page_project=source_project,
            entity_slug=cand["slug"],
            ref_type="mentioned",
            trust_level="medium",
            line_start=line_start,
            line_end=line_end,
            source_quote=cand["source_quote"],
        ))
    repo.replace_refs(
        vault_id=vault_id,
        page_slug=source_slug,
        page_project=source_project,
        refs=refs,
    )


def check_idempotency(
    repo: Any,
    vault_id: str,
    source_slug: str,
    current_hash: str,
) -> bool:
    """Return True if source page is unchanged since last extraction.

    R-39, UC-09 Scenario A. Query ``source_state`` for the recorded hash;
    match → caller should short-circuit (no LLM call, no DB mutations).

    L-V3.2 (vdd-multi 2026-05-28): explicit NULL check on row["value"].
    The schema declares ``value TEXT NOT NULL`` so this case shouldn't
    arise, but defensive — if a row exists with NULL (corruption / future
    schema change) we treat it as "unknown" → False → re-extract,
    avoiding silent misuse.
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
    repo: Any,
    vault_id: str,
    source_slug: str,
    new_hash: str,
) -> None:
    """Upsert the source_state row with the new hash.

    Called from ``main()`` at the END of a successful extraction so that
    partial failures leave the row un-updated → next run retries.
    """
    conn = repo._connect()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO source_state "
            "(vault_id, source_kind, scope, key, value, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(vault_id, source_kind, scope, key) DO UPDATE SET "
            "value = excluded.value, updated_at = excluded.updated_at",
            (vault_id, _SOURCE_KIND, source_slug, "source_hash", new_hash, now),
        )


def build_manifest(
    vault_id: str,
    source_slug: str,
    source_hash: str,
    create_list: list[dict[str, Any]],
    mention_list: list[dict[str, Any]],
    log_event: dict[str, Any],
    vault_root: Path,
    concepts_rel: str = "_concepts",
) -> dict[str, Any]:
    """Assemble wiki-ingest v1.1-compatible manifest dict (R-35).

    Two distinct ``action`` semantics live here (planner note + R-35):
      - ``written[i].action`` ∈ {"created", "unchanged"} — page-file write
        outcome; ``write_concept_page`` returns the path either fresh or
        pre-existing. Caller annotates ``file_write_action`` on the
        candidate dict before passing in.
      - top-level ``mentioned[i].action`` ∈ {"created","updated","confirmed",
        "mentioned"} — entity-row outcome from ``upsert_extracted_entity``
        (for create_list items) or "mentioned" for pure mention_list items.

    Output is contract-checked against
    ``_manifest_consumer.validate_manifest`` by R-43(b) tests so this
    skill's output is consumable by ``index_from_manifest`` in-process.
    """
    written: list[dict[str, Any]] = []
    for cand in create_list:
        page_action = cand.get("file_write_action", "created")
        written.append({
            "kind": "concept",
            # TASK 037 / R-5: real vault-relative path (PARA folders own a
            # nested `_concepts/`); defaults to `_concepts` → byte-identical
            # manifest for Karpathy vault-tier.
            "path": f"{concepts_rel}/{cand['slug']}.md",
            "action": page_action,
            "scope": "vault",
            "slug": cand["slug"],
        })
    mentioned: list[dict[str, Any]] = []
    for cand in create_list:
        # entity_action from 003-07b: created / updated / confirmed
        mentioned.append({
            "slug": cand["slug"],
            "action": cand.get("entity_action", "created"),
        })
    for cand in mention_list:
        mentioned.append({
            "slug": cand["slug"],
            "action": "mentioned",
        })
    return {
        "status": "ok",
        "vault_id": vault_id,
        "source": {"slug": source_slug, "hash": source_hash},
        "written": written,
        "mentioned": mentioned,
        "log_event": log_event,
        "extraction_summary": {
            "create_count": len(create_list),
            "mention_count": len(mention_list),
        },
    }
