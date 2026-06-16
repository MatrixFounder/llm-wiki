# TASK 034 — Real-vault dogfood report

**Date:** 2026-06-16 · **Vault:** `/Users/sergey/Downloads/TestVault/ObsidianNotes-Test`
(vault_id `personal`, layout `obsidian-personal` + `.wiki/layout.yaml` override, vault-local
`index_db`, **2493 pages**, real PARA Obsidian vault, mostly Russian) · **Verdict: ✅ всё
работает корректно — 0 дефектов.**

## Scope

Hands-on dogfood of the now-`v7` toolchain (post-TASK-034) against the user's real adoption
vault, then an adversarial-verification Workflow (5 agents, 39 independent checks, each
re-deriving the expected answer from the markdown before comparing — not trusting the
hands-on run). Two parts: **A** — migration + full regression on the real 2493-page vault;
**B** — the TASK-034 *new* surfaces (4 new edge types, 6 agent-memory classes, multi-date
`--as-of` flips) in an isolated `samples/` sandbox (the real vault's data/layout doesn't
author them, so they can't be exercised on it without mutation).

## Part A — real vault (the core ask)

### A1. v6→v7 Class-B migration (the headline)
The DB was at `user_version=6` (indexed before the v7 bump). Ran the documented migration:
delete `.db/-wal/-shm` → `wiki-init --register-existing` → `wiki-reindex --full`.

| Metric | v6 (before) | v7 (after) | Result |
|---|---|---|---|
| `user_version` | 6 | **7** | ✅ bumped |
| pages | 2493 | **2493** | ✅ identical |
| `page_entity_refs` | 6973 | **6973** | ✅ identical |
| refs by type | (18 typed + 6955 mentioned) | **identical** | ✅ all TASK-032 edges survived |
| distinct projects | 77 | **77** | ✅ identical |
| skipped / slug_collisions | — | **0 / 0** | ✅ (the per-vault Learning `paths` granularity resolved the 2 prior collisions) |
| wall time | — | **2.2s** | ✅ |

The migration is **byte-faithful**: the DB rebuilt from markdown matches v6 exactly, and the
v7 CHECK enum now admits all 8 new ref_types (verified insert+rollback; a bogus value is
still rejected → the CHECK is live, not absent). Independent re-derivation confirmed the
2493 count (an ignore-aware walk found 2495 indexable `.md`, minus `CLAUDE.md` +
`WIKI_SCHEMA.md` ∈ `SYSTEM_FILES` = 2493; **zero** DB-only rows), and the 18 typed edges are
an EXACT set-match to a by-hand re-derivation of the 8 CybOS-demo files' authored edges +
auto-derived inverses (no missing/extra, no leakage onto the other 2485 pages).

### A2. Regression battery (all GREEN)
- **FTS** (Latin + Cyrillic): `Kafka`→2, `переговоры`→6 — top hits genuinely contain the term.
- **Stemming**: a page containing only `продаж`/`продажах` is found by the inflection
  `продаже` (291 stemmed hits) and **not** by `--exact` (47) — proves real stemming.
- **ё/е fold**: `--exact объемами` matches a body that only has `объёмами` — proves the
  index-time + query-time ё→е fold (isolated from stemming via `--exact`).
- **Typed-class `--tag`**: `--tag decision` → exactly the 2 `eg-decision` pages (a `tags[]`
  member match, vs 50 pages for the FTS word `decision` — confirms membership, not word).
- **`--as-of` on real data** (TASK 034): `eg-decision-kafka` (date 2026-06-15) excluded
  as-of `2026-06-14`, included as-of `2026-06-16`; the undated `eg-decision-rabbitmq` always
  excluded; inclusive lower bound at `2026-06-15`. Bad date → `INVALID_FILTER` exit 2, value
  **not** echoed. Whitespace-only query → clean `INVALID_QUERY` (no stack trace).
- **`wiki-graph`**: `chain --kind supersedes` (kafka→rabbitmq lineage); `backlinks --kind
  implements` (→ both decisions); **`neighbors --kind invalidates` → `[]` not `INVALID_KIND`**
  (DF-034-1 fix confirmed on the real vault).
- **RAG**: `wiki-query prepare` retrieves correctly (the earlier "0 retrieved" was the
  documented multi-term implicit-AND — `wiki-search` gives 0 for the same over-specified
  query); **`--follow-edges`** pulled graph neighbors (`rabbitmq` via `supersedes`,
  `req-throughput` via `implements`) with `via_edge` provenance.
- **`wiki-lint`**: clean on the v7 schema (no hash-drift/type-mismatch). The 6541
  orphan-links are a **pre-existing PARA property** (indexed notes `[[link]]` into the
  ignored `_daily`/`_inbox`/`Attachments` areas + not-yet-created notes) — a function of
  markdown+layout, identical under v6, **not** a TASK-034 regression.

## Part B — new v7 surfaces (isolated `samples/cybos-v7-dogfood`)
A 14-page cybos sandbox exercised what the real vault can't:
- **4 new edge types** extracted + auto-inversed: `invalidated_by`↔`invalidates`,
  `activated_by`↔`activates`, `uses`↔`used-by`, `owns`↔`owned-by` — all traverse both
  directions ("who uses/owns/implements X" → the agent).
- **6 agent-memory classes** classify with 0 skips and are `--tag`-filterable
  (`agent`/`tool`/`workflow`/`capability`/`execution`/`pattern`).
- **Multi-date `--as-of` flips**: a `policy-v1←v2←v3` chain flips active decision across
  dates; `dec-cron` correctly **drops after its invalidation date** (active 04-01, gone
  06-01 — incident is 04-10); `dec-rollout` (only `activated_by`, never superseded) stays
  active throughout. Half-open boundaries exact (04-09 in / 04-10 out; 04-30 in / 05-01 out;
  06-30 in / 07-01 out).
- **RFC-003 angle**: `--tag execution --status failed` finds failed runs today (aggregate
  ranking — "which fails most" — remains the deferred GROUP-BY surface).

## Adversarial verification Workflow (5 agents, 39 checks, 0 bugs)
Independent verifiers (migration / search / graph / temporal) + a completeness-adversarial
critic. The critic closed every gap the verifiers left — built a `/tmp` probe to prove the
**explicit `valid_from`/`valid_to` override path** (neither vault authors it): a datetime
`valid_to` collapses to its day boundary (the `substr(…,1,10)` fix), and an authored
`valid_to` beats a graph successor (precedence). Also confirmed: **idempotency** (2nd
`reindex --full` byte-identical; `register-existing` on a live v7 DB leaves uv=7 intact),
**`reindex --delta`** (scoped auto-inverse on an edited page; documented edge-removal
deferral), **`wiki-index-upsert`** (layout-aware, forward-only until reindex), **FTS+tag+as-of
triple-AND**, and **all 8 v7 ref_types** recognized on the real vault. Probe cleaned up; both
real-vault DBs verified untouched.

## Observations (non-defects, worth knowing)
1. **`wiki-graph neighbors --direction out` needs `--project` on a multi-project vault.** The
   CybOS demo pages live under project `CybOS Demo` (not `_vault_`), and `refs_from`/neighbors
   filter on the exact stored `page_project`; outbound neighbors returned empty until
   `--project "CybOS Demo"` was supplied (documented in the command's own `--project` help).
   `backlinks`/`chain` are unaffected. UX detail, not a data issue.
2. **Real-vault adoption gaps (not defects).** The explicit `valid_from`/`valid_to` overrides
   and the 6 agent-memory classes are exercised only in synthetic fixtures — the real
   2493-page vault adopts neither, so their behavior at full PARA scale / with Cyrillic slugs
   is proven only in the sandbox. To adopt the agent-memory classes in the real vault, add
   them to `.wiki/layout.yaml` `type_mapping` (the same UNION pattern already used for the 7
   knowledge classes).

## Final state
- Real vault DB **migrated to v7** (2493 pages, 6973 refs) — the desired upgraded state.
- A **v6 backup** (`/.wiki/index.db.v6-backup`, 58 MB) was retained as a safety net; it is
  Class-B rebuildable and can be deleted (`rm .wiki/index.db.v6-backup`).
- Sandboxes under `samples/` (gitignored scratch): `cybos-v7-dogfood`, `cybos-dogfood`.

**Bottom line:** the v6→v7 migration and the entire toolchain work correctly on the real
vault; TASK 034's new temporal/edge/class features work correctly in the sandbox; the
adversarial pass found no defects.
