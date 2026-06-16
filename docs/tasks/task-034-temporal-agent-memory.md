# TASK 034 — Temporal core (`wiki-search --as-of`) + agent-memory edge types & classes

## 0. Meta
- **Task ID:** 034 · **Slug:** `task-034-temporal-agent-memory`
- **Mode:** VDD (full pipeline). Code task (`scripts/`, `tests/`, `docs/`), Stub-First,
  green-throughout, mypy `--strict`. **One schema bump** (`user_version` **6 → 7**,
  Class-B rebuild — the TASK 032 precedent); additive + backward-compatible; no new deps;
  **no `import anthropic`**.
- **Source:** operator request 2026-06-16 — work through a 6-RFC "agent memory system"
  proposal from a second agent. Audit found ~60-70 % already expressible (TASK 031/032/033).
  Operator chose to build the one genuinely-new high-leverage slice (RFC-001 temporal core
  + the cheap RFC-001/002 edge & classification wins). **Operator design correction:** the
  RFC's `valid_from`/`valid_to` are awkward (`valid_to` unfillable at authoring time;
  `valid_from` duplicates the existing `date`) → temporality is **derived** from the indexed
  `pages.date` + the supersession/invalidation graph; `valid_from`/`valid_to` survive only as
  **optional overrides** (never required). Plan file: `~/.claude/plans/merry-wishing-seal.md`.
- **Status:** ✅ **COMPLETE / merge-ready** 2026-06-16 (uncommitted per operator rule,
  branch `task-034-temporal-agent-memory`). Full VDD pipeline + **`/vdd-multi` converged**
  (Security ✓ clean-pass; Performance ✓ — 2 LOW, both pre-existing accepted cost class
  [R-X3-MF-SCAN sibling], no new regression; Logic ✓ — iter-1 found 2 MED on untested
  input classes, both **empirically reproduced + fixed + re-verified clean-pass**: MED-1
  cross-project successor ambiguity → COUNT=1 guard mirroring `_derive_inverse_edges`
  [conservative "stay active when ambiguous", aligned with the data layer]; MED-2
  datetime-valued `valid_to`/`valid_from` override → `substr(…,1,10)` date-part compare
  to hold the half-open day boundary; + 3 LOW documented). **Live CLI dogfood GREEN** on
  `samples/cybos-dogfood` (vault-local `index_db`): `--as-of 2026-04-20` → the one
  active decision `dec-db-global` (the RFC acceptance test, no LLM), flips to
  `dec-db-local` at `2026-06-01`; `wiki-graph chain --kind supersedes` lineage,
  `backlinks ocr --kind implements` → claude-code, `neighbors inc-42 --kind invalidates`
  → dec-sync-v1. Dogfood found + fixed **DF-034-1** (SEV-2): `wiki-graph`'s `--kind`
  allow-list was a hardcoded TASK-032 list that silently dropped the v7 edge kinds → now
  **derived from `reindex._INVERSE_REF_TYPE`** (single source of truth, drift-proof) +
  regression test. **1443 pytest (+50 over the 1393 baseline), mypy strict (76 files).**
  **Post-ship operator-requested `/vdd-multi` re-verification (2026-06-16) — CONVERGED
  clean** over the full final changeset (evidence: 1443 pytest green, mypy strict clean,
  security scan = 8 pattern-CRITICALs ALL pre-existing/outside the diff): Security
  **clean-pass**, Performance **clean-pass** (the inner `COUNT=1` sub-subquery is
  index-backed via the `(vault_id, slug)` PK-prefix; `substr` is free on the already-paid
  `json_extract`; predicate gated `if as_of is not None` → zero-cost when unused), Logic
  **bikeshedding-only** (2 LOW, both non-blocking: non-ISO `valid_to`/`valid_from` override
  fails open = documented "garbage-in" SKILL caveat; pre-existing "`user_version` stays 5"
  per-feature docstrings in `repository.py`/`sqlite_repository.py` — historical TASK-019
  zero-DDL notes, correctly NOT bumped, untouched by 032 either). No fixes required.

## 1. Problem

Three gaps the current primitives cannot reach, all on the "agent memory" axis:

1. **No temporal query.** `wiki-search --where` is **equality-only**
   ([sqlite_repository.py:642](../scripts/wiki_index/sqlite_repository.py#L642)). The
   question *"which decisions were active on the incident date?"* — RFC-001's acceptance
   test — cannot be answered without an LLM, even though `pages.date` (indexed) and the
   `superseded_by` graph (TASK 032) already hold the facts.
2. **Missing typed edges.** The event graph (TASK 032) ships
   `implements`/`supersedes`/`causes`/`relates_to` but not `invalidated_by`/`activated_by`
   (RFC-001 temporal causality) or `uses`/`owns` (RFC-002 agent↔tool/workflow). `invalidated-by`
   is also the edge the temporal `valid_to` walk reads.
3. **No agent-memory classes.** `agent`/`tool`/`workflow`/`capability`/`execution`/`pattern`
   are not classifiable types, so RFC-002/003/005/006 notes fall to `_vault_`/`UnmappedType`.

## 2. Goal / Non-Goals

**Goal:** add `wiki-search --as-of DATE` (graph-derived, zero required new fields, optional
`valid_from`/`valid_to` overrides), the four new inverse-closed edge pairs, and the six
agent-memory page types — so RFC-001 is fully answerable without an LLM and RFC-002/005's
classification + lineage work today.

**Non-Goals (explicit, ROADMAP):** RFC-004 `wiki-extract-decisions` (separate — clones the
`wiki-extract-concepts` rail); RFC-006 `wiki-consolidate` (separate, greenfield); RFC-003
aggregation reporting ("fails most often" — needs a GROUP-BY read surface); redundant CLIs
`wiki-agent graph` / `wiki-workflow status` / `wiki-graph timeline` (Decision-17 — compose
`wiki-graph`/`wiki-search`); generalizing `--where` to comparison operators.

## 3. Requirements Traceability Matrix

| ID | Requirement | Acceptance Criteria | Verify |
|----|-------------|---------------------|--------|
| **R-1** | `wiki-search --as-of DATE` temporal filter (graph-derived). | A page is "active as of DATE" iff `effective_from = COALESCE(valid_from, pages.date) ≤ DATE` **and** `DATE < effective_to` where `effective_to` = authored `valid_to` (if present) else the earliest superseding/invalidating successor's `date` (else ∞). `--as-of` composes with FTS query, `--where`, `--status`, `--types`; valid alone (relaxed empty-search guard). | `tests/test_wiki_search_as_of.py` |
| **R-1a** | `--as-of` input validation. | Non-ISO-`YYYY-MM-DD` → `INVALID_FILTER` exit 2, **no value echo** (CWE-209/117). | unit |
| **R-1b** | Optional explicit overrides. | Authored `valid_from` (future-effective: inactive before it) / `valid_to` (sunset, half-open: inactive on/after it) win over the derived ends; explicit `valid_to` short-circuits the graph walk. | unit |
| **R-1c** | Back-compat. | Equality `--where`/`--status`/`--severity`/`--tag` result sets **unchanged** (no `as_of` → byte-identical SQL). | regression |
| **R-2** | Four new inverse-closed typed-edge pairs (schema v6→v7). | `invalidated_by↔invalidates`, `activated_by↔activates`, `uses↔used-by`, `owns↔owned-by` authorable in either direction; inverse auto-derived (global pass), orphan-target-skipped, idempotent. `wiki-graph neighbors/backlinks/chain --kind <new>` traverses them. | `tests/test_event_graph*.py` |
| **R-2a** | Schema migration. | `PRAGMA user_version = 7`; `ref_type` CHECK admits the 8 new values; a v6 DB rebuilds cleanly via the documented Class-B path. | unit + manual |
| **R-3** | Six agent-memory page types (config only). | `agent`/`tool`/`workflow`/`capability`/`execution`/`pattern` classify via the `cybos` layout `type_mapping` + `paths` globs; per-type templates; **zero Python**. | `tests/test_layout*.py` + dogfood |
| **R-4** | Karpathy byte-identity preserved. | No edge keys / no temporal fields / no new types on a Karpathy vault → indexing + search SQL unchanged. | regression |
| **R-5** | Docs lockstep. | `wiki-search` SKILL.md (+eval) + manuals EN/RU + `cybos.md`/`cybos.yaml` comment + CLAUDE.md narrative + ROADMAP updated; stale cybos "deferred Phase-2" comment fixed. | review |

## 4. Design notes (locked)

- **`--as-of` SQL** (DATE bound 3×; `valid_from`/`valid_to` paths fixed — no user field name,
  no allowlist needed; ref_types are internal constants):
  ```sql
  AND COALESCE(json_extract(p.frontmatter_json,'$.valid_from'), p.date) IS NOT NULL
  AND COALESCE(json_extract(p.frontmatter_json,'$.valid_from'), p.date) <= ?
  AND ( json_extract(p.frontmatter_json,'$.valid_to') > ?
        OR ( json_extract(p.frontmatter_json,'$.valid_to') IS NULL
             AND NOT EXISTS (SELECT 1 FROM page_entity_refs r
               JOIN pages s ON s.vault_id=r.vault_id AND s.slug=r.entity_slug
               WHERE r.vault_id=p.vault_id AND r.page_slug=p.slug
                 AND r.ref_type IN ('superseded-by','invalidated-by')
                 AND s.date IS NOT NULL AND s.date <= ?) ) )
  ```
  Frontmatter dates are stored as ISO strings by
  [`_json_safe`](../scripts/wiki_index/normalization.py#L41) → text comparison is sound. `p.date`
  is `.isoformat()` TEXT. Half-open interval `[effective_from, effective_to)`.
- **Edge set** — extends the plan table to **both authorable directions** per TASK 032 parity
  (free; `_INVERSE_REF_TYPE` already carries both ways). 8 new authorable keys, 8 new `ref_type`
  enum values, 4 new inverse pairs. `invalidated-by`/`superseded-by` are what R-1's walk reads.
- **Migration** — `ref_type` CHECK cannot be ALTER-relaxed on a populated table; DB is Class-B
  rebuildable: delete `*.db/-wal/-shm` → `wiki-init --register-existing` → `wiki-reindex --full`.

## 5. Risks

- **CHECK-enum drift** between SQL, `_EDGE_KEY_TO_REF_TYPE`, `_INVERSE_REF_TYPE`, `models.py`
  docstring → a test asserts the three code maps agree with the SQL enum.
- **`--as-of` perf** — the `NOT EXISTS` correlated subquery per candidate row. Rides
  `idx_refs_page` + `pages` PK; bounded by the `limit`. Same unindexed-`json_extract` class as
  the open R-X3-MF-SCAN for the override branch (documented, not a regression).
- **Date hygiene** — a page with neither `valid_from` nor `date` is **excluded** from `--as-of`
  (first clause), so non-temporal pages never pollute the result.
