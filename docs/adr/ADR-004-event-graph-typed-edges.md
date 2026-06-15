# ADR-004: Event Graph — typed page-to-page edges, auto-inverse derivation, and graph-aware RAG

- **Status**: Accepted (2026-06-15)
- **Decider**: kuptsov.sergey@gmail.com
- **Supersedes**: nothing — **realizes [ADR-003](./ADR-003-typed-knowledge-classes.md) D4** (the Phase-2 "event graph" deferred there) and follows the **TASK 008** precedent (schema v4→v5 added a typed page-class + a `ref_type` + an event in one cohesive migration).
- **Empirical basis**: TASK 031 shipped 7 typed knowledge classes (`decision`/`requirement`/`risk`/`incident`/`hypothesis`/`fact`/`event`) as zero-DDL classification, with the relation keys (`implements`/`supersedes`/`superseded_by`/`caused_by`/`relates_to`) **authored-but-inert** in `templates/page-types/*`. The canonical Markdown already carries the edge data; this ADR turns it into a queryable graph.
- **Related**: [docs/TASK.md](../TASK.md) (TASK 032, RTM R-032-1..8, recon F1-F9), ROADMAP **R-13 Phase 2**, [ADR-002](./ADR-002-multi-vault-bottleneck-corrections.md) §D8 (Class-A canonical / Class-B rebuildable).

## Context

The wiki indexes page-to-page references in `page_entity_refs(vault_id, page_slug, page_project, entity_slug, ref_type)` with a CHECK enum of 5 kinds (`mentioned`, `defined-here`, `related`, `cited`, `verifies`). Reindex extracts `mentioned` from the body and `cited`/`verifies` from frontmatter (`reindex._frontmatter_refs`, db_type-gated). The DB is a Class-B rebuildable cache; a new CHECK enum value is a v→v+1 migration applied by **drop+recreate + `wiki-reindex --full`** (SQLite cannot ALTER-relax a CHECK on a populated table — `sql/wiki-index-v2.sql:454-460`); there is no runtime migrator.

TASK 032 makes the typed classes *link*: a Decision `implements` a Requirement and is `caused_by` an Incident; the graph of system evolution (decision → task → incident → release). The operator chose the full tier: typed edges + a traversal reader + **graph-aware RAG** (`wiki-query` follows edges at retrieval), the full ADR-003 edge set, and **auto-derived inverse edges**.

The sharp design constraint (task-review C-1): an inverse edge for `supersedes: B` on page A is the row `(page_slug=B, entity_slug=A, ref_type='superseded-by')` — it lives on a **different** page (B) than the one being reindexed (A). `_replace_refs_in_txn` is per-page **delete-all-then-insert** scoped to `page_slug`, so the inverse row **cannot** ride A's single `replace_refs`. This drives D3/D4 below.

## Decision

### D1. Schema v6 — an inverse-closed `ref_type` enum, `relates_to` reuses `related`

`page_entity_refs.ref_type` CHECK gains **6** values (forward + inverse pairs); `PRAGMA user_version` → **6**:

| pair | forward | inverse |
|---|---|---|
| implementation | `implements` | `implemented-by` |
| supersession | `supersedes` | `superseded-by` |
| causation | `causes` | `caused-by` |
| relation (symmetric) | `related` (existing — **reused**) | `related` |

**No parallel `relates-to` value is added** — the existing, currently-unwritten symmetric `related` covers it (avoids a near-duplicate). The full v6 enum: `mentioned`, `defined-here`, `related`, `cited`, `verifies`, `implements`, `implemented-by`, `supersedes`, `superseded-by`, `causes`, `caused-by`. Migration = Class-B rebuild (D7), tested per the TASK-008 shape (a v5-populated DB *rejects* a v6-only ref_type → the rebuild is mandatory, not optional).

### D2. Edge target resolution = like body mentions (NOT the `cited` "project/slug" form)

Frontmatter edge values are authored as `[[wikilink]]` or a bare slug (e.g. `caused_by: [[inc-queue-overflow]]`), list- or scalar-valued, and resolved to `entity_slug` through the layout's `slug_strategy` + the alias map — **identical to body `mentioned` refs**. This is the natural hand-authoring shape (the templates show `[[…]]` / IDs), and it means a `[[Req X]]` edge target slugifies the same as a `[[Req X]]` body mention. (Contrast `cited`/`verifies`, which use the machine-written `"project/slug"` form because `wiki-query`/`wiki-verify` emit them.)

**Key→ref_type map** (frontmatter key, underscore → enum value, hyphen) — pinned by a unit test:
`implements`→`implements` · `implemented_by`→`implemented-by` · `supersedes`→`supersedes` · `superseded_by`→`superseded-by` · `causes`→`causes` · `caused_by`→`caused-by` · `relates_to`→`related`. Each member is **both authorable and derivable** (the templates author `superseded_by` directly).

### D3. Forward edges ride the per-page write (M-1 intact); inverses are a GLOBAL post-pass

- **Forward edges**: a new `reindex._edge_refs` (mirroring `_cited_refs`) is called **always-on inside `_frontmatter_refs`** (not db_type-gated — any page may carry edges). Its refs are **unioned into the source page's single `replace_refs`** (the existing contract — `_frontmatter_refs` docstring already forbids a 2nd write). **M-1 unchanged.** Karpathy pages carry no edge keys → `_edge_refs` returns `[]` → byte-identity holds (D7).
- **Inverse edges**: derived in a **global post-pass over all `page_entity_refs`** — a *sibling* of the existing Step-2.5 / AM-3 alias-canonicalization pass (`reindex_full:842-879`). **Ordering: it runs AFTER AM-3 (so both endpoint slugs are canonical) and BEFORE Step 3 `_recompute_mentions`** (`reindex_full:884`) so the count recompute sees the complete closure (arch-review M2). Edge-derived rows **deliberately contribute to `mentions_count`** (consistent with how `cited`/`verifies` already count — `_recompute_mentions` is ref_type-agnostic; documented, not a bug). For every forward-edge row `(A→B, fwd)` it ensures the inverse `(B→A, inv)` exists — **but only when B resolves to an existing `pages` row** (arch-review M1): the inverse row's `page_slug` is the TARGET B, and `page_entity_refs` has an **enforced** FK `(vault_id, page_slug, page_project)→pages` (`PRAGMA foreign_keys=ON`), so an inverse on an **orphan** target (e.g. `caused_by: [[not-yet-written]]`) would raise `IntegrityError`. The pass therefore **joins `entity_slug` against `pages.slug` within the vault, skips non-page targets** (they stay forward-only orphan refs, exactly like `mentioned`/`cited` orphans), and reads the **target's `page_project`** from that join for the inverse row's PK/FK (it is NOT the source's project). Idempotent (PK `(vault, page_slug, project, entity_slug, ref_type)` dedups, INSERT-OR-IGNORE on conflict); **no self-loops** (skip A==B); **bidirectional-author convergence** (if the author also wrote `superseded_by: A` on B, the derived row is the same PK → one row, no conflict). The symmetric `related` derives its mirror `(B→A, related)`. (`implemented_by` is derive-primary / author-optional — extracted if authored, else derived from `implements`.)

### D4. Delta-inverse-closure = scoped reconciliation for changed sources; rename/swap residual repaired by `--full`

`reindex_delta` has **no** global ref pass. Decision (refined during dev — see the
provenance note): after the delta batch, run inverse **ADDITIONS only, SCOPED to the
TOUCHED source pages** — `_derive_inverse_edges(conn, vault_id, source_slugs=touched)`,
i.e. derive inverses from `f.page_slug IN touched` (same orphan-target skip + target-project
resolution as full, M1; gated on `touched or deleted`). An edge added/changed on a re-walked
source materializes its inverse on the (possibly un-walked) target.

**Inverse REMOVAL is deferred to `--full`** (a documented residual, TASK 030 A5 posture —
widened from "rename only" to "any edge/source deletion"), for a **provenance** reason
discovered in dev: a stored `(B→A, superseded-by)` row is **INDISTINGUISHABLE** from an edge
B *authored directly* (`superseded_by:` on B) — both are the same `ref_type` with no
provenance column. So a "delete stale inverse" step could clobber a legitimately-authored
edge, and (worse) the symmetric derivation makes a stale inverse **resurrect** its removed
forward (deriving inverse-of-the-inverse) unless the pass is scoped away from un-walked pages.
Therefore delta **never deletes an inverse** and scopes additions to touched sources;
`--full`'s wipe+rebuild is authoritative (ADR-002 §D8). **NOT a blanket `delta == full`.** A
provenance/`derived` flag (to enable safe scoped removal) is a possible future refinement,
out of scope. `reindex_delta` has no `_recompute_mentions` (full-only — confirmed), so the M2
"edges count toward mentions" choice is full-only; any delta/full `mentions_count` drift is the
same A5-class residual.

### D5. Graph-aware RAG — `wiki-query prepare --follow-edges`, default OFF, deterministic

`wiki-query prepare` gains `--follow-edges` (**default OFF** — preserves today's retrieval semantics + `question_hash` for everyone not opting in). When on: after the FTS hits, follow typed edges (depth **1** default, `--edge-depth` capped at 3) from each hit to pull neighbor pages into the retrieval set, **excluding `type=query`/`type=verification` neighbors** (mirrors `_retrieve`'s existing exclude-prior-answers). Canonical order: neighbors appended **after** the FTS hits, sorted by `(ref_type, project, slug)`, deduped against the hit set. The expansion is folded into `question_hash` so `apply`'s re-derivation round-trips without `QUESTION_CHANGED` (C1 / TASK 028 precedent). The envelope gains an edge-provenance field (`via_edge: {from, ref_type}`) on pulled hits.

### D6. Traversal reader = a new `wiki-graph` CLI (the 16th CLI)

A new read-only `wiki-graph` skill with subcommands `neighbors <slug>` / `chain <slug>` / `backlinks <slug>`, flags `--kind <ref_type>`, `--direction {in,out,both}`, `--depth N` (capped, cycle-safe), JSON envelope, injection-safe (slug/kind allowlist-validated, bound params, no value echo on error — TASK 013 posture). Built on the DAL reads (D-DAL). A new `wiki-graph` CLI (not `wiki-search --edges`) keeps graph traversal cleanly separate from FTS.

### D-DAL. Typed-edge DAL reads (additive, ABC + impl in lockstep)

`get_backlinks(vault_id, entity_slug, ref_type=None)` gains an optional kind filter (default = today's all-kinds; **`repository.py` ABC + `sqlite_repository.py` impl updated together**, mypy strict); a new outbound `refs_from(vault_id, page_slug, project, ref_type=None)`; and a bounded `neighbors`/`chain` traversal (depth-capped, visited-set cycle-safe). `idx_refs_type`/`idx_refs_entity`/`idx_refs_page` already support these.

### D7. Karpathy byte-identity + migration

The always-on `_edge_refs` is a no-op without edge frontmatter, so karpathy discovery/pages/refs are byte-identical (golden anchor + `test_karpathy_config_matches_layout_constants` stay green). Existing v5 DBs migrate by the documented Class-B rebuild (delete `.db/-wal/-shm` → `wiki-init --register-existing` → `wiki-reindex --full`); edges materialize from the canonical Markdown — no re-authoring.

## Consequences

### Positive
- The typed classes become a queryable **graph of system evolution**; "what did decision X cause / what implements it / the supersession lineage" are first-class reads.
- Auto-inverse means authoring ONE direction yields bidirectional queryability — less authoring, no drift (the inverse is derived, never hand-maintained).
- Forward edges keep M-1 untouched; the inverse pass reuses a proven seam (AM-3). Karpathy + all non-edge vaults are byte-identical and `--follow-edges`-OFF by default → zero behavior change unless opted in.
- Markdown stays canonical (ADR-002 §D8): the edges were authored in Phase 1, indexed now.

### Negative
- **DDL** (schema v6) → an existing index needs a one-time Class-B rebuild. Bounded, documented, TASK-008-shaped.
- **Delta is approximate** for cross-page inverses in rename/swap edge cases (D4 residual) — `--full` repairs. A deliberate fast-vs-authoritative trade-off.
- Graph-RAG adds a determinism surface to `question_hash` (mitigated by the canonical ordering + default-OFF).

### Neutral
- `wiki-graph` is the 16th CLI; read-only, opt-in.
- The symmetric `related` value, dormant since v1, becomes the `relates_to` home.

## Implementation Path (bead order)

1. **Schema v6** (DDL + models + `test_schema_v6` incl. the populated-DB rejection) — `tdd-strict`.
2. **`_edge_refs` extraction** (key→ref_type map, always-on in `_frontmatter_refs`) — forward edges only; Karpathy anchor green.
3. **Global-pass inverse derivation** (full) + **delta scoped reconciliation** — `tdd-strict` (idempotency, bidirectional-author convergence, delta contract).
4. **DAL reads** (`get_backlinks(kind=)` + `refs_from` + `neighbors`/`chain`, ABC lockstep).
5. **`wiki-graph` CLI** (the traversal reader).
6. **Graph-aware RAG** (`wiki-query --follow-edges`, deterministic hash) — the separable final bead (splittable to a follow-up if hash-convergence is slow).
7. **Activate + docs** (flip the inert-edges test; ROADMAP R-13 Phase-2 → SHIPPED; ARCHITECTURE; manuals EN/RU; `docs/layouts/cybos.md`).

## References
- TASK 008 — the v4→v5 typed-class + ref_type + event migration recipe + test shape.
- ADR-003 D4 — the deferred Phase-2 this realizes; the reserved-but-inert edge keys.
- ADR-002 §D8 — Class-A canonical / Class-B rebuildable (why a Class-B rebuild migration is safe).

## Post-ship `/vdd-multi` (3 critics + adversarial verify; converged)

5 findings confirmed (empirically reproduced before acceptance), 2 dropped. **3 FIXED, 2
accepted-residual** (no HIGH):

- **MED-1 (logic) FIXED** — the inverse pass JOINed the target on slug only, so in a
  multi-project vault (karpathy course tier / any `project_pattern` layout) a same-slug
  page in *another* project got a phantom `implemented-by`/etc. The project-less forward
  edge can't disambiguate which project was meant → `_derive_inverse_edges` now derives the
  inverse **only when the target slug resolves to EXACTLY ONE page** (`COUNT(*)=1` guard);
  ambiguous slugs get no inverse (no phantom). Pinned by `test_inverse_skips_ambiguous_cross_project_slug` (+ unambiguous control).
- **LOW-1 (logic) FIXED** — AM-3 alias canonicalization (Step 2.5, before the inverse pass)
  can rewrite a forward edge target to the source's own slug → a post-extraction `(A,A)`
  self-loop the `_edge_refs` guard (pre-canonical) never saw. The inverse pass now DELETEs
  post-AM-3 typed-edge self-loops. Pinned by `test_self_loop_edge_row_cleaned`.
- **LOW-2 (perf) FIXED** — `edge_chain` BFS used `list.pop(0)` (O(n) dequeue → O(V²)); now
  `collections.deque.popleft` (O(1)).
- **MED-2 (perf) ACCEPTED-RESIDUAL** — `_follow_edges` is an N+1 (per-hit `neighbors()` +
  per-candidate `get_page()`). It is on the **opt-in** (`--follow-edges` default OFF),
  depth-capped (≤3) + hits-capped (`--limit`) graph-RAG path, so the cost is bounded
  (≈ limit × degree × depth indexed point-lookups) on an interactive `prepare` that already
  does FTS + per-token alias expansion. A batched fetch is a future optimization.
- **MED-3 (perf) ACCEPTED-RESIDUAL** — `edge_chain` loads ALL edges of the requested kind
  for the vault into an in-memory adjacency before BFS-from-start. Bounded by edges-of-kind
  (small for supersedes/causes lineages); on an interactive `wiki-graph chain` read. A
  reachability-scoped recursive CTE is a future optimization.

Dropped (2 LOW, verified non-issues): the same-project outbound-neighbor resolution (a
documented `--follow-edges` limitation) and the absence of a total edge-pull cap (already
bounded by depth × hits).

### Second `/vdd-multi` pass (operator re-verify — "correct & complete, nothing broken")

A repeat 3-critic run (Security **clean-pass**; Logic + Performance issues-found, all
empirically traced) re-opened the edge-pull cap that the first pass had dropped, plus one
new logic divergence class. **PERF-032-1 + self-loop observability + comment FIXED; the
delta divergence DOCUMENTED + test; cross-project outbound re-confirmed documented:**

- **PERF-032-1 (perf, MED) FIXED** — the first pass dropped "no total edge-pull cap"
  as bounded-by-depth×hits, but frontier fan-out is **multiplicative across levels**: a hub
  `decision`/`incident` on a dense `cybos` vault under `--edge-depth 3` can pull a large
  fraction of the corpus into one answer (+ per-candidate `get_page` N+1). `_follow_edges`
  now enforces `_MAX_EDGE_PULLED = 50` as a **deterministic sorted truncation** (applied to
  the already-canonically-sorted candidate stream → prepare/apply still agree on
  `question_hash`, C1). Pinned by `test_follow_edges_capped_and_deterministic`. This
  supersedes MED-2's "bounded by `--limit`" framing (the N+1 is now hard-capped too).
- **Logic MED (delta divergence class 2) DOCUMENTED + test** — under **bidirectional
  authoring** (`d1 superseded_by:[[d2]]` ∧ `d2 supersedes:[[d1]]`), removing only d2's
  forward re-walks only d2; the delta inverse pass is source-scoped to `{d2}`, so it never
  reprocesses d1's still-authored `superseded_by` to re-derive `(d2→d1, supersedes)` → the
  graph is temporarily **asymmetric** (the supersedes edge MISSING) until `--full`. This is
  the *complement* of D4's class (1) stale-inverse residual, and is the deliberate cost of
  the same source-scoping that *prevents* class (1)'s resurrection (broadening to
  `entity_slug IN touched` would close it but reintroduce resurrection — a stored inverse is
  indistinguishable from an authored forward without a provenance column, out of scope).
  Both classes are `--full`-repaired (ADR-002 §D8 / TASK 030 A5 best-effort-delta posture);
  documented in `reindex_delta` Step 4.5, pinned by
  `test_delta_missing_derivation_from_untouched_source_repaired_by_full`.
- **LOW (self-loop observability) FIXED** — `_edge_refs` self-referential / slugify-to-empty
  edge-target drops now emit a `skipped` note (were silent) — matches the CWE-117-safe
  report-and-skip posture (key name only, never the untrusted value). Pinned in
  `test_self_loop_skipped_and_dedup`.
- **LOW (cross-project outbound in `_follow_edges`) re-confirmed DOCUMENTED** — outbound
  neighbors resolve in the source page's project, so a cross-project outbound target on a
  `project_pattern` layout is skipped (inbound carries the real project, unaffected). Noted
  in the `_follow_edges` docstring and the `wiki-graph --project` help.
- **LOW (comment accuracy) FIXED** — the delta Step 4.5 comment said "SECOND connection";
  `repo._connect()` returns the **cached singleton** (same `conn`). Corrected.
- **Security: clean-pass** — all 8 static-scanner CRITICALs touching TASK-032 code confirmed
  false positives: the `eval` hit is a `…retrie**val**…` comment substring; every f-string
  SQL fragment (`_derive_inverse_edges` CASE/IN, `_REF_COLS`) is composed of module-internal
  constants with all runtime values **bound**; malformed-frontmatter skips never echo the
  value; v5→v6 migration **fails safe** (IntegrityError on a populated-v5 over-apply, not
  silent corruption); edge targets are slugified text, never filesystem paths.
