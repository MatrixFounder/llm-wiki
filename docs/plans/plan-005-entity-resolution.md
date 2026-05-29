# Development Plan: TASK 005 — Epic 7 completion (R-4 + R-5 + `wiki-merge`)

> **Status**: DRAFT (2026-05-29) — awaiting plan-reviewer sign-off.
> **Task ID**: 005 / Slug: `entity-resolution`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-4.1..R-4.7 + R-5.1..R-5.6; UC-09..UC-15; Decision Log D-005-1..5; constraints C-1..C-8).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §2 Entity Resolver component + §4 Data Model (EntityAlias activation, `is_candidate` Class A, merge path, **AM-3 ref-canonicalization**) + §5 Interfaces — already updated + reviewed (both gates APPROVED, see [docs/reviews/task-005-review.md](./reviews/task-005-review.md), [docs/reviews/architecture-005-review.md](./reviews/architecture-005-review.md)).
> **Methodology**: **Stub-First (TDD)**, **green-throughout** (every bead boundary keeps `pytest` green + `SQLiteRepository` instantiable + `mypy --strict` clean — abstractmethod + stub land together). Each code bead lands Phase-1 stubs + RED→GREEN tests before Phase-2 logic; the per-bead split is documented in §3.
> **Predecessor**: R-3 / TASK 003 v3.1 (`wiki-extract-concepts`) — SHIPPED 2026-05-28 (`43812f2`); produces the candidate entities this task makes resolvable + durable.
> **Closes**: KNOWN_ISSUES **L-4** (entity_aliases PK). **Unblocks**: ROADMAP **R-X5** (cross-project entity graph).
> **Out of scope** (TASK §5 C-5/C-7): RAG layer (R-6..R-8); cross-project graph (R-X5); vault-wide `[[...]]` wikilink rewriting (merge redirects via the alias table, not link rewrites); auto-promote log-event granularity (Q5 → safe default in 005-09).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| `_concepts/<slug>.md` / `_entities/<slug>.md` frontmatter (`is_candidate`, `aliases:`) | **Canonical** confirm-state + alias surfaces; merge outcome (deleted `from` page + `into.aliases`) | **Class A** |
| `entities`, `entity_aliases`, `page_entity_refs` rows | DB mirror; rebuilt by `wiki-reindex --full` | **Class B** |
| `IndexRepository` (ABC) + `SQLiteRepository` | All read/write SQL; new entity-resolution + merge methods | DAL boundary (skills never write raw SQL) |
| `wiki-confirm` / `wiki-alias` / `wiki-merge` (+ `wiki-search`/`wiki-lint` extensions) | Thin CLIs over the DAL; Class A frontmatter mutation via the shared `O_NOFOLLOW`+atomic-temp+`_sanitize_*` primitives | Skill Layer |

**TASK 005 invariants** (carried from architecture review):
1. **§D8 durability** — confirm-state, aliases, **and merges** reconstruct from Class A markdown alone after `wiki-reindex --full` (UC-14, UC-15 are the binding gates).
2. **AM-3 canonical-slug invariant** — a `page_entity_refs` row names the canonical entity whenever its raw `[[surface]]` target is a known alias; `reindex_full` canonicalizes at build time (phase order entities → aliases → refs → recompute_mentions) so `recompute_mentions`/`get_backlinks` survive a rebuild.
3. **DAL boundary** — every new behavior is an `IndexRepository` method first; CLIs are thin.
4. **Envelope invariant** — CWE-117/209: error envelopes are `{error, field?, reason}`, never echo the offending surface/value (extend the existing parametrised regression suite to alias/merge surfaces).
5. **No silent data loss** — alias PK collisions during reindex/merge are **report-and-skip**, never `INSERT OR IGNORE`.

---

## 1. Task Execution Sequence

### Phase 1 — Schema v3 + durability spine (the load-bearing core)

The §D8 round-trip is the binding acceptance gate, so the spine lands first. 005-01 (schema) blocks every alias path; 005-02/03 close the reindex read-side round-trip that the whole feature's durability rests on.

- [R-5.4] **005-01** — Schema v2→v3: `entity_aliases` PK → `(vault_id, alias)`; drop redundant `idx_aliases_lookup`; add `idx_aliases_entity (vault_id, entity_slug)`; bump `PRAGMA user_version 2→3` + `schema_meta`; ADR-002 §D8 amendment note.
  - Description File: [docs/tasks/task-005-01-schema-v3-alias-pk.md](./tasks/task-005-01-schema-v3-alias-pk.md)
  - Priority: Critical (blocks all alias DAL + reindex mirror) · Dependencies: none · Est: 0.5 day

- [R-4.1] **005-02** — `reindex_full` reads `is_candidate` from entity-page frontmatter (replaces the `INSERT OR IGNORE` default-0); absent key ⇒ confirmed (`0`).
  - Description File: [docs/tasks/task-005-02-reindex-is-candidate.md](./tasks/task-005-02-reindex-is-candidate.md)
  - Priority: Critical (R-4 durability) · Dependencies: none · Est: 0.5 day

- [R-5.3, AM-3] **005-03** — `reindex_full` mirrors `aliases:` frontmatter → `entity_aliases` (report+skip on hard-PK collision) **and** canonicalizes `page_entity_refs.entity_slug` through the alias table at build time (phase order entities → aliases → refs → recompute).
  - Description File: [docs/tasks/task-005-03-reindex-alias-mirror-canonicalize.md](./tasks/task-005-03-reindex-alias-mirror-canonicalize.md)
  - Priority: Critical (durability spine + AM-3) · Dependencies: 005-01 · Est: 1 day

### Phase 2 — Index Layer DAL (methods behind the CLIs)

All new `IndexRepository` ABC abstractmethods land **with** their `SQLiteRepository` stub in the same bead (green-throughout). Each bead is stub-first internally (see §3).

- [R-4.5] **005-04** — `resolve_entity(vault_id, slug)` (slug *or* alias surface → `Entity`; `None` on miss) + make `find_orphan_links` **alias-aware** (R-4.5d).
  - Description File: [docs/tasks/task-005-04-resolve-entity-alias-aware-orphans.md](./tasks/task-005-04-resolve-entity-alias-aware-orphans.md)
  - Priority: High · Dependencies: 005-01 · Est: 0.75 day

- [R-4.2, R-4.3, R-4.4] **005-05** — candidate-lifecycle DAL: `set_entity_candidate` (explicit setter, **bypasses** the `MIN()` guard), `list_candidates`, `recompute_mentions` (set-based), `auto_promote_candidates(threshold)`.
  - Description File: [docs/tasks/task-005-05-candidate-lifecycle-dal.md](./tasks/task-005-05-candidate-lifecycle-dal.md)
  - Priority: High · Dependencies: none (entities table exists) · Est: 1 day

- [R-5.1, R-5.2] **005-06** — alias-write DAL: `add_alias` (raises on hard-PK collision), `remove_alias`, `list_aliases`.
  - Description File: [docs/tasks/task-005-06-alias-write-dal.md](./tasks/task-005-06-alias-write-dal.md)
  - Priority: High · Dependencies: 005-01 · Est: 0.5 day

- [R-5.5, R-5.6] **005-07** — alias-read DAL: `expand_query_aliases(term)` (canonical name + sibling aliases, bounded) + `find_alias_collisions` (in-DB + cross-table) + `AliasCollision` model.
  - Description File: [docs/tasks/task-005-07-alias-read-dal.md](./tasks/task-005-07-alias-read-dal.md)
  - Priority: High · Dependencies: 005-01, 005-04 · Est: 0.75 day

- [R-4.7] **005-08** — `merge_entities(from, into) → MergeReport`: re-point refs (PK-dedup keep higher trust), re-point/skip aliases, register redirect aliases (`former_name`), delete `from` row, recompute `into.mentions_count` — single transaction.
  - Description File: [docs/tasks/task-005-08-merge-entities-dal.md](./tasks/task-005-08-merge-entities-dal.md)
  - Priority: High · Dependencies: 005-04, 005-05 (recompute_mentions), 005-06 · Est: 1 day

### Phase 3 — Skill Layer (CLI surface)

Thin CLIs over the DAL. New CLIs reuse the `O_NOFOLLOW`+atomic-temp+`_sanitize_*` primitives for every Class A frontmatter mutation.

- [R-4.2, R-4.3, R-4.4] **005-09** — `wiki-confirm` CLI + `bin/wiki-confirm`: frontmatter write-back (`is_candidate`, tags) then `set_entity_candidate`; `--undo`; `--auto [--threshold N] [--dry-run]`; envelopes (3/4). One `entity-confirmed` log event per promotion (Q5 default).
  - Description File: [docs/tasks/task-005-09-wiki-confirm-cli.md](./tasks/task-005-09-wiki-confirm-cli.md)
  - Priority: High · Dependencies: 005-05 · Est: 1 day

- [R-5.1, R-5.2] **005-10** — `wiki-alias` CLI + `bin/wiki-alias`: `--add`/`--remove`/`--list`, `--type`; frontmatter `aliases:` mutation + DB mirror; collision → `ALIAS_COLLISION` (exit 5).
  - Description File: [docs/tasks/task-005-10-wiki-alias-cli.md](./tasks/task-005-10-wiki-alias-cli.md)
  - Priority: High · Dependencies: 005-06, 005-07 · Est: 0.75 day

- [R-4.7] **005-11** — `wiki-merge` CLI + `bin/wiki-merge`: **Class A first** (append `into.aliases`, delete `from` page atomically) then `merge_entities`; `--dry-run`; envelopes 3/4/5/6 (incl. `INVALID_MERGE`, `MERGE_MIRROR_FAILED`).
  - Description File: [docs/tasks/task-005-11-wiki-merge-cli.md](./tasks/task-005-11-wiki-merge-cli.md)
  - Priority: High · Dependencies: 005-08 · Est: 1 day

- [R-5.5] **005-12** — `wiki-search` CLI: alias expansion **on by default** via `expand_query_aliases`; `--no-expand-aliases` opt-out (byte-identical to current output).
  - Description File: [docs/tasks/task-005-12-wiki-search-alias-expansion.md](./tasks/task-005-12-wiki-search-alias-expansion.md)
  - Priority: Medium · Dependencies: 005-07 · Est: 0.5 day

- [R-5.6] **005-13** — `wiki-lint` CLI: new alias-collision category (`find_alias_collisions` + Class A frontmatter scan) with `--json` parity; advisory exit only under `--strict`.
  - Description File: [docs/tasks/task-005-13-wiki-lint-alias-collision.md](./tasks/task-005-13-wiki-lint-alias-collision.md)
  - Priority: Medium · Dependencies: 005-07 · Est: 0.5 day

### Phase 4 — Verify + docs + symlinks + acceptance gate

- [R-4.6] **005-14** — extract-concepts Class A flag regression guard: pin `is_candidate: true` in `write_concept_page`; regression test that an applied candidate survives `reindex --full` as a candidate.
  - Description File: [docs/tasks/task-005-14-extract-concepts-regression.md](./tasks/task-005-14-extract-concepts-regression.md)
  - Priority: Medium · Dependencies: 005-02 · Est: 0.25 day

- [C-1] **005-15** — skill/command/workflow docs + symlinks for `wiki-confirm`, `wiki-alias`, `wiki-merge` (3 × `skills/<name>/SKILL.md` + `commands/<name>.md` + `workflows/<name>.md` + `.claude/`/`.agent/` symlink set).
  - Description File: [docs/tasks/task-005-15-skills-commands-symlinks.md](./tasks/task-005-15-skills-commands-symlinks.md)
  - Priority: Medium · Dependencies: 005-09, 005-10, 005-11 · Est: 0.5 day

- [UC-14, UC-15] **005-16** — durability round-trip acceptance tests (the §D8 gate): confirmed/candidate state + aliases + merge all reconstruct from Class A after `wiki-reindex --full`; merged `into.mentions_count` = de-dup union **survives** reindex (AM-3); merged-away slug not orphaned.
  - Description File: [docs/tasks/task-005-16-durability-acceptance.md](./tasks/task-005-16-durability-acceptance.md)
  - Priority: Critical (acceptance) · Dependencies: 005-02, 005-03, 005-09, 005-10, 005-11 · Est: 0.75 day

- [all RTM] **005-17** — regression sweep + docs: ADR-002 §D8 amendment (or ADR-003 stub) for the v2→v3 PK change; ROADMAP R-4/R-5 → DONE; KNOWN_ISSUES **L-4** closed; README + `.AGENTS.md` updates; full `pytest tests/` + `mypy --strict scripts/`. Acceptance gate.
  - Description File: [docs/tasks/task-005-17-regression-and-docs.md](./tasks/task-005-17-regression-and-docs.md)
  - Priority: Critical (acceptance gate) · Dependencies: **all prior** 005-01..005-16 · Est: 0.75 day

---

## 2. Dependency DAG (critical-path view)

```text
   005-01 schema-v3 ──┬────────────► 005-03 reindex-mirror+AM-3 ─┐
   (R-5.4)            │              (R-5.3, AM-3)               │
                      ├─► 005-04 resolve+orphan (R-4.5)          │
                      ├─► 005-06 alias-write (R-5.1/5.2) ─┐      │
                      └─► 005-07 alias-read (R-5.5/5.6) ◄─┘      │
   005-02 reindex-is_candidate (R-4.1) ──► 005-14 regression     │
   005-05 candidate-DAL (R-4.2/4.3/4.4) ──┐                      │
                                          ▼                      │
                            005-08 merge_entities (R-4.7) ◄──────┘
                            (deps 005-04, 005-05, 005-06)
        ┌───────────── Phase 3 CLIs ─────────────┐
   005-05 ─► 005-09 wiki-confirm                  │
   005-06,07 ─► 005-10 wiki-alias                 │
   005-08 ─► 005-11 wiki-merge                    │
   005-07 ─► 005-12 wiki-search                   │
   005-07 ─► 005-13 wiki-lint                     │
        └──────────────────┬──────────────────────┘
   {005-09,10,11} ─► 005-15 skills/symlinks
   {005-02,03,09,10,11} ─► 005-16 durability-acceptance (UC-14/15)
   ALL ─► 005-17 regression + docs (ACCEPTANCE GATE)
```

**Critical path** (longest blocking chain): 005-01 → 005-03 → 005-08 → 005-11 → 005-16 → 005-17.
**Parallel-safe after 005-01 lands**: {005-02, 005-04, 005-05, 005-06}. **After DAL lands**: {005-09, 005-10, 005-12, 005-13}.

---

## 3. Stub-First Application (per `tdd-stub-first`, green-throughout)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 005-01 | yes (DDL) | n/a — DDL is declarative | `apply_schema` on fresh DB → `PRAGMA user_version==3`; PK insert-collision raises `IntegrityError`; `idx_aliases_entity` present, `idx_aliases_lookup` absent | n/a (single-pass DDL + migration note) |
| 005-02 | yes (reindex.py) | reindex still defaults is_candidate (record current behavior) | RED: vault w/ `is_candidate: true` page → after `reindex_full` DB row `is_candidate==1` (fails on default-0) | read flag from frontmatter; absent ⇒ 0 |
| 005-03 | yes (reindex.py) | alias mirror no-op; refs stored raw | RED: entity page w/ `aliases:` → `entity_aliases` populated; ref to alias surface stored under canonical slug; collision in `skipped` | mirror `aliases:` (report+skip); canonicalize ref targets via alias map (phase order) |
| 005-04 | yes (DAL) | ABC abstractmethod + `SQLiteRepository` stub `resolve_entity` → `None`; `find_orphan_links` unchanged | RED: `resolve_entity(slug)`/`(alias)` → expected Entity; orphan-of-alias not flagged | slug+alias lookup; LEFT JOIN alias in orphan query |
| 005-05 | yes (DAL) | stubs (`set_entity_candidate`/`list_candidates`/`recompute_mentions`/`auto_promote_candidates`) raise/return `[]` | RED: flip 1→0 & 0→1 (bypass MIN); list candidates; mentions recomputed; promote ≥N | explicit UPDATE setter; set-based recompute; threshold select |
| 005-06 | yes (DAL) | stubs (`add_alias`/`remove_alias`/`list_aliases`) | RED: add → row; dup → collision raises; remove; list | parameterized INSERT/DELETE/SELECT; PK-collision → raise |
| 005-07 | yes (DAL) | stubs (`expand_query_aliases`→`[]`; `find_alias_collisions`→`[]`) + `AliasCollision` model | RED: expand "Hermes" → [name, siblings]; in-table + cross-table collisions found | sibling-alias gather (idx_aliases_entity); collision SQL (GROUP BY HAVING + cross-join) |
| 005-08 | yes (DAL) | `merge_entities` stub → empty `MergeReport`; `MergeReport` model | RED: refs re-pointed+deduped; aliases absorbed+redirect registered; `from` row gone; mentions=union | single-tx UPDATE/DELETE; PK-dedup keep higher trust |
| 005-09 | yes (CLI) | `wiki_confirm.py` arg parse + handlers call stubs; `bin/wiki-confirm` | RED: `--help` ok; `confirm` flips frontmatter+DB (mocked DAL); idempotent | frontmatter rewrite (atomic) + DAL mirror; `--auto`/`--dry-run`; envelopes |
| 005-10 | yes (CLI) | `wiki_alias.py` arg parse; `bin/wiki-alias` | RED: `--help` ok; `--add` writes frontmatter+DB; collision → exit 5 | frontmatter `aliases:` mutation + DAL; remove/list |
| 005-11 | yes (CLI) | `wiki_merge.py` arg parse; `bin/wiki-merge` | RED: `--help` ok; `--dry-run` reports, no write; self-merge → exit 5 | Class-A-first (append+delete) then `merge_entities`; mirror-fail → exit 6 |
| 005-12 | yes (wiki_search.py) | `--no-expand-aliases` flag parsed, default-on path = current behavior | RED: default expands (page w/ only "Hermes Framework" hit by "Hermes"); `--no-expand-aliases` byte-identical | OR-expand FTS MATCH via `expand_query_aliases` |
| 005-13 | yes (wiki_lint.py) | new `alias-collision` category key present, empty | RED: in-table/cross-table/frontmatter collisions reported; `--json` parity; `--strict` exit | wire `find_alias_collisions` + frontmatter scan |
| 005-14 | yes (test + 1-line pin) | confirm `is_candidate: true` pin present in `write_concept_page` | RED: applied candidate → `reindex --full` → still candidate | regression test only (pin already exists) |
| 005-15 | **no — docs/symlinks** | n/a | n/a | write SKILL/command/workflow md + run `bin/link-*.sh` |
| 005-16 | yes (acceptance tests) | test scaffolding w/ `pytest.skip` | collection discovers UC-14/UC-15 tests | full §D8 round-trip + AM-3 mentions-survive assertions |
| 005-17 | **no — verify/docs** | n/a | n/a | doc edits + run full suite; gate the task |

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-09** | Confirm a candidate entity | 005-05, 005-09 |
| **UC-10** | Auto-promote candidates by mention threshold | 005-05, 005-09 |
| **UC-11** | Register / manage an alias | 005-06, 005-07, 005-10 |
| **UC-12** | Search with alias expansion | 005-04, 005-07, 005-12 |
| **UC-13** | Lint detects alias collision | 005-07, 005-13 |
| **UC-14** | Durability round-trip (confirm + alias) | 005-02, 005-03, 005-16 |
| **UC-15** | Merge a duplicate entity | 005-03, 005-04, 005-08, 005-11, 005-16 |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement | Bead(s) | Phase |
|---|---|---|---|
| R-4.1 | `is_candidate` Class A round-trip (reindex reads frontmatter) | 005-02 | 1 |
| R-4.2 | `wiki-confirm <slug>` promote | 005-05 (DAL), 005-09 (CLI) | 2,3 |
| R-4.3 | `wiki-confirm --undo` demote (bypass MIN) | 005-05, 005-09 | 2,3 |
| R-4.4 | `wiki-confirm --auto [--threshold N=3]` | 005-05, 005-09 | 2,3 |
| R-4.5 | `resolve_entity` implemented (+ R-4.5d alias-aware `find_orphan_links`) | 005-04 | 2 |
| R-4.6 | extract-concepts keeps Class A flag (regression) | 005-14 | 4 |
| R-4.7 | `wiki-merge <from> <into>` duplicate fold | 005-08 (DAL), 005-11 (CLI) | 2,3 |
| R-5.1 | `wiki-alias --add` | 005-06 (DAL), 005-10 (CLI) | 2,3 |
| R-5.2 | `wiki-alias --remove` / `--list` | 005-06, 005-10 | 2,3 |
| R-5.3 | reindex mirrors `aliases:` (report+skip) | 005-03 | 1 |
| R-5.4 | `entity_aliases` PK → `(vault_id, alias)` (L-4) + index swap + user_version | 005-01 | 1 |
| R-5.5 | `wiki-search` alias expansion (default on) | 005-07 (DAL), 005-12 (CLI) | 2,3 |
| R-5.6 | `wiki-lint` alias collision (in-DB + cross-table + frontmatter) | 005-07 (DAL), 005-13 (CLI) | 2,3 |
| AM-3 | reindex ref-canonicalization (merge durability) | 005-03 | 1 |

**1-1 sanity** (no orphan requirements): every R-4.x/R-5.x + AM-3 maps to ≥1 bead; every bead carries ≥1 RTM ID in its `[R-x.y]` tag. UC-14/UC-15 are verified end-to-end by 005-16.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **AM-3 canonicalization implemented per-ref in Python** → N×M reindex regression on large vaults (cf. KNOWN_ISSUES P-2/P-3). | Medium | High | 005-03 acceptance bullet requires a **set-based** approach: build an in-memory `{alias→canonical}` map once per vault, resolve during the existing ref-build loop (no per-ref SQL). Benchmark note: no extra DB round-trip per ref. |
| **R-2** | **Merge write-order crash** (C-8): Class A mutated, DB transaction fails → stale DB. | Low | High | 005-11 emits `MERGE_MIRROR_FAILED` (exit 6) pointing at `wiki-reindex --delta`; 005-16 adds a simulated mid-merge-failure test asserting `--delta` restores consistency from Class A. |
| **R-3** | **Default-on search expansion changes existing output** → surprises callers / breaks existing search tests. | Medium | Medium | 005-12 keeps `--no-expand-aliases` **byte-identical** to today; expansion is a no-op when the term matches no alias; existing search tests run under the no-alias fixture unchanged. NFR-6 documents the behavior change. |
| **R-4** | **Schema v3 breaks existing DBs** (no ALTER framework). | Low | Medium | DB is Class B/rebuildable + gitignored. 005-01 bumps `user_version` 2→3; migration = `wiki-reindex --full` (documented in the ADR amendment); `apply_schema` (`CREATE IF NOT EXISTS`) cannot mutate a live PK, so the rebuild path is mandatory and tested on a fresh DB. |
| **R-5** | **Alias / merge surface injection** into YAML frontmatter (CWE-117/209, YAML-delimiter). | Medium | Medium | 005-10/005-11 reuse `_sanitize_*` + length caps; 005-17 extends the parametrised envelope-never-echoes-content regression suite to alias + merge surfaces (architecture review m-2). |
| **R-6** | **`get_backlinks` not alias-aware** → backlinks miss merged-away refs between reindexes. | Low | Medium | AM-3 canonicalizes refs at reindex; between reindexes `merge_entities` re-points refs immediately. 005-16 asserts backlinks for `into` include re-pointed refs both immediately and post-reindex. |

---

## 7. Definition of Done (acceptance gate — 005-17)

Done iff **all** hold:

- [ ] All 17 beads (005-01..005-17) complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → all green (baseline 450+ + new cases), 0 failed.
- [ ] `mypy --strict scripts/` → Success: no issues found.
- [ ] **UC-14 §D8 gate** (005-16): delete DB → `wiki-reindex --full` → confirmed stays confirmed, candidate stays candidate, alias rebuilt — **from markdown alone**.
- [ ] **UC-15 §D8 gate** (005-16): after `wiki-merge` + `wiki-reindex --full` → `from` not re-materialised; `resolve_entity(from-surface)` → `into`; `into.mentions_count` = de-dup union (AM-3 survives); `[[from-slug]]` not orphaned.
- [ ] `wiki-search "<alias>"` returns pages mentioning only a sibling surface (default); `--no-expand-aliases` byte-identical to pre-005.
- [ ] `wiki-lint` reports in-table + cross-table + frontmatter alias collisions with `--json` parity.
- [ ] `entity_aliases` PK is `(vault_id, alias)`; `PRAGMA user_version == 3`; `idx_aliases_lookup` dropped; `idx_aliases_entity` present (L-4 closed).
- [ ] 3 new CLIs (`wiki-confirm`/`wiki-alias`/`wiki-merge`) have `bin/` wrappers + SKILL/command/workflow md + symlinks; `bin/<cmd> --help` exits 0.
- [ ] ROADMAP R-4/R-5 marked DONE; KNOWN_ISSUES L-4 marked fixed; ADR-002 §D8 amendment (or ADR-003) present.
- [ ] Envelope-never-echoes-content regression suite extended to alias + merge surfaces.

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | 17 |
| Total working-time estimate (single-dev, sequential) | ~11.0 days |
| Critical-path estimate (with DAG parallelization) | ~6.0 days |
| Acceptance-gate effort (005-16 + 005-17) | ~1.5 days |

---

## 9. Open Issues / Planner Judgement Calls

1. **Spine-first ordering** — 005-01/02/03 (schema + reindex round-trip + AM-3) land before any CLI because the §D8 durability gate is the binding acceptance criterion and every later bead depends on the round-trip being closed.
2. **DAL grouped by cohesion, not 1-per-method** — candidate-lifecycle (005-05) bundles 4 tightly-coupled methods; alias-read (005-07) bundles expand+collisions. Each remains a single testable bead (multiple TCs); the RTM matrix preserves 1-1 requirement traceability.
3. **Green-throughout** — abstractmethod + `SQLiteRepository` stub land in the same bead so the class is always instantiable and the suite is never red at a bead boundary (carried from TASK 003 v3.1 Option A).
4. **Q4 (expansion breadth cap)** + **Q5 (auto-promote log granularity)** resolved with safe defaults inside 005-07 / 005-09 (no transitive expansion; one log event per promotion) per the architecture-review minor notes.
5. **Q6 (`from`-page disposition)** — 005-11 hard-deletes the `from` page (git history is the audit trail); no `_merged/` tombstone dir (TASK §6 Q6 default).
6. **005-14 is regression-only** — `write_concept_page` already pins `is_candidate: true`; the bead adds the round-trip regression test, no behavior change.
7. **`skill-tdd-strict` (high-assurance) beads** — the correctness-critical beads run under strict TDD (test-first, full edge-case unit coverage, no over-mocking of the DB): **005-03** (AM-3 ref-canonicalization — the durability spine), **005-08** (`merge_entities` transactional integrity + PK-dedup), and **005-16** (the §D8 acceptance gate). All other code beads use standard Stub-First. Every bead is green-throughout (suite never red at a boundary).

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **005-01** (schema v3 — blocks all alias work). Phase-1 beads {005-02} may proceed in parallel; {005-04, 005-05, 005-06} unlock once 005-01 lands.
