# TASK 006 — Consolidation / hardening sweep (schema hygiene + correctness + lint perf)

> **VDD MODE.** A bounded cleanup task: batch the *cheap, safe, regardless-of-scale*
> deferred items from the `docs/KNOWN_ISSUES.md` ledger that accumulated across
> TASKs 003/004/005. Scale-gated perf and threat-model-gated security items stay
> deferred (they keep their ledger triggers).

### 0. Meta Information

- **Task ID:** 006
- **Slug:** `consolidation-hardening`
- **Mode:** VDD (`/vdd-start-feature` → `/vdd-plan` → `/vdd-develop-all`)
- **Source:** `docs/KNOWN_ISSUES.md` deferred ledger (operator-selected scope
  2026-05-29: "Hygiene + correctness + lint perf"). RTM rows are keyed by their
  **ledger id**, not new ROADMAP R-numbers.
- **Predecessor:** TASK 005 (Epic 7 entity resolution) shipped 2026-05-29
  (`8a6491e`). This sweeps the hygiene debt before the next feature (ROADMAP
  R-6 `wiki-query`).
- **Schema:** introduces **v3 → v4** (drop dead index + dead enum value +
  GENERATED column). DB is Class B rebuildable → migration is
  `wiki-reindex --full` (no in-place ALTER), same pattern as v2→v3.

---

### 1. General Description

Three big feature tasks (003/004/005) each deferred low-priority items to the
ledger. This task closes the subset that is **cheap, low-risk, and worth doing
independent of vault scale** — dead-code/dead-index removal, a schema-level
correctness guarantee, an entity-display-name correctness fix, a maintainability
dedup, one clean lint-perf+correctness rewrite, and doc clarifications.

**Explicitly NOT in scope** (kept deferred with their ledger triggers intact):
scale-gated perf (P-1, P-2, P-3, P-4, P-6, P-7, P-8, P-9, P-11, H-PERF-3 —
trigger: real vault > 1k/10k pages); threat-model-gated security (D-1, D-2, H-5,
H-6, Q17, the vdd-multi multi-tenant TOCTOU note — trigger: multi-tenant /
untrusted scope); Epic-gated (L-3 — Epic 6); by-design (DF-2 — reindex-healed).
Fixing scale/threat items now would be speculative (no 1k-vault exists; scope is
single-user-trusted) — `developer-guidelines` §1.6 prohibits speculative work.

#### 1.1 Grounded facts (verified in repo)

| Fact | Consequence |
|---|---|
| `idx_pages_vault_tags ON pages(vault_id, json_extract(frontmatter_json,'$.tags'))` is referenced **only** in the DDL — no query uses it. | P-5: drop it (maintained on every write for nothing). |
| No code path creates a `pages` row with `type='log'` (grep clean). | L-5: drop `'log'` from the `pages.type` CHECK enum. |
| `append_log_event` computes + inserts `event_date = event.event_ts.date().isoformat()` ([sqlite_repository.py:656](../scripts/wiki_index/sqlite_repository.py)). | L-2: make the column `GENERATED ALWAYS AS (substr(event_ts,1,10)) STORED` **and** stop the inserter setting it. |
| `reindex_full` registers `entities.name = updated_fm.get("title", slug)` ([reindex.py](../scripts/wiki_index/reindex.py)); concept pages emit `name:` not `title:`. | L-8: fall back `title → name → slug` so display names survive. |
| The correlated `mentions_count` UPDATE is hand-copied at **4 sites** (sqlite_repository.py:889/904/1138 + reindex.py:409). | F12c: extract one private helper. |
| Concept/entity pages are upserted into `pages` with `frontmatter_json` (incl. `aliases`); lint's `_scan_frontmatter_alias_collisions` instead re-`frontmatter.load()`s every file (a 2nd O(N) YAML sweep) and swallows parse errors. | P-10 (+F12b): read `aliases` from `pages.frontmatter_json` via SQL — no file re-parse, no swallowed errors. |
| DB is Class B rebuildable; `apply_schema` is `CREATE … IF NOT EXISTS` (cannot ALTER live columns/PK). | Migration = bump `PRAGMA user_version 3→4` + `wiki-reindex --full` (no ALTER). |

---

### 2. Requirements Traceability Matrix (RTM)

| Ledger id | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **P-5** | Drop the dead `idx_pages_vault_tags` functional index. | ✅ | (a) remove the `CREATE INDEX` from `sql/wiki-index-v2.sql` + `docs/SCHEMA-v2.sql`; (b) confirm no query/`.AGENTS.md` references it; (c) tag query path stays `pages_fts.tags` (unchanged). |
| **L-5** | Remove the dead `'log'` value from the `pages.type` CHECK enum. | ✅ | (a) drop `'log'` from the CHECK in both DDL files; (b) regression test: inserting a `type='log'` page now fails the CHECK; (c) confirm `wiki-index-render` / upsert never emit it. |
| **L-2** | `log_events.event_date` becomes a STORED generated column. | ✅ | (a) DDL → `event_date TEXT GENERATED ALWAYS AS (substr(event_ts,1,10)) STORED`; (b) `append_log_event` stops inserting `event_date` (drop the column + value); (c) `query_log_events` date-slice + `idx_log_vault_date` still work; (d) regression: inserted event's `event_date` == `event_ts[:10]` with no inserter help. |
| **L-8** | `reindex_full` preserves entity display name (`title → name → slug`). | ✅ | (a) entity registration uses `updated_fm.get("title") or updated_fm.get("name") or slug`; (b) regression: a concept page with `name:` (no `title:`) round-trips with `entities.name == name` (not slug). |
| **F12c** | Single private helper for the `mentions_count` recompute. | ✅ | (a) `_recompute_mentions(conn, vault_id, slug=None)` issuing the correlated UPDATE on the caller's connection/tx; (b) all 4 sites call it (reindex Step 3, `recompute_mentions`, `auto_promote_candidates`, `merge_entities`); (c) behavior byte-identical (existing tests green). |
| **P-10** + **F12b** | `wiki-lint` frontmatter-alias scan reads the DB, not files. | ✅ | (a) detect frontmatter alias collisions from `pages.frontmatter_json` (`json_extract`/`json_each '$.aliases'`) — no per-file `frontmatter.load`; (b) surface unparseable/garbage rather than silently `continue` (F12b); (c) lint output (`kind="frontmatter"`) byte-identical for the dogfood fixtures; (d) one fewer O(N) disk+YAML sweep. |
| **MIG** | Schema **v3 → v4** migration. | ✅ | (a) bump `PRAGMA user_version 3→4` + `schema_meta` in both DDL files; (b) ADR-002 §D8 amendment: migration = `wiki-reindex --full` (Class B); (c) update `test_schema_smoke.py` (`user_version==4`); (d) no in-place ALTER. |
| **L-1, L-6, L-7** | Doc / schema-comment clarifications. | ✅ | (a) L-1: inline comment on the `entities.file_path` UNIQUE invariant; (b) L-6: document `known_concepts` view cold-call cost in its header; (c) L-7: add the "verified consistent" note to the ADR-002 §D8 anti-pattern row. Docs-only. |

---

### 3. Use Cases

#### 3.1 UC-16 — Schema v3→v4 migration via reindex (no data loss)
- **Actors:** Operator; System (`wiki-reindex --full`).
- **Preconditions:** A vault on schema v3.
- **Main scenario:** operator bumps to the v4 DDL, deletes the DB (or it is fresh),
  runs `wiki-reindex --full`; all Class A content reconstructs under v4 (dead index
  gone, `event_date` generated, `'log'` enum removed).
- **Acceptance:** `PRAGMA user_version == 4`; `idx_pages_vault_tags` absent;
  `log_events.event_date` is generated; a fresh apply + reindex of a real vault is
  byte-identical modulo timestamps.

#### 3.2 UC-17 — Lint at scale without a 2nd YAML sweep
- **Actors:** Operator; System (`wiki-lint`).
- **Main scenario:** `wiki-lint` detects frontmatter alias collisions from the DB
  (`pages.frontmatter_json`) instead of re-reading every `_concepts`/`_entities`
  file.
- **Acceptance:** the dogfood collision fixtures (cross_slug/cross_name/frontmatter)
  produce identical lint findings; no `frontmatter.load()` call remains in the
  collision scan; a malformed-frontmatter page is reported, not silently skipped.

#### 3.3 UC-18 — Entity display name survives reindex (L-8)
- **Acceptance:** a `_concepts/<slug>.md` with `name: "Foo Bar"` and no `title:`
  reindexes to `entities.name == "Foo Bar"` (was: `slug`).

#### 3.4 UC-19 — Generated event_date (L-2)
- **Acceptance:** `append_log_event` does not set `event_date`; the stored row's
  `event_date == event_ts[:10]`; `query_log_events` date filtering unchanged.

---

### 4. Non-functional Requirements

- **NFR-1 (no regression):** full `pytest tests/` green; `mypy --strict scripts/`
  clean; existing log/reindex/lint/search tests unaffected (byte-identical behavior
  except the intended changes).
- **NFR-2 (Class A/B, ADR-002 §D8):** the v3→v4 schema change is Class B —
  rebuildable by `wiki-reindex --full`. No new Class C. No in-place ALTER.
- **NFR-3 (no speculative work):** only the operator-selected subset; scale/threat
  items stay deferred (their ledger entries remain the triggers).
- **NFR-4 (green-throughout):** Stub-First where code changes; each bead keeps the
  suite green at its boundary.
- **NFR-5 (perf, P-10):** the lint frontmatter scan does **one** set-based DB read,
  not O(pages) file opens + YAML parses.

---

### 5. Constraints and Assumptions

- **C-1 No CLI surface change:** no new commands; `wiki-lint`/`wiki-reindex`/
  `wiki-append-log` keep their flags + envelopes.
- **C-2 Migration = reindex, not ALTER** (DB is Class B; `apply_schema` can't ALTER).
- **C-3 Ledger discipline:** mark the closed items `[STATUS: fixed]` in
  `KNOWN_ISSUES.md`; leave the deferred items + their triggers intact.
- **C-4 L-2 generated-column caveat:** SQLite STORED generated columns cannot be
  added by ALTER to a populated table — fine here (rebuild path). Verify the FTS5
  triggers / `log_events` inserts don't reference `event_date` as a settable column.
- **C-5 Env:** Python 3.14.4 via `.venv`; never global installs.

---

### 6. Open Questions

> Scope was operator-confirmed (Decision Log). Residual items are
> implementation-level (Planning/Dev), non-blocking.

- **Q1 (resolved → decided):** scope = Hygiene + correctness + P-10 lint perf;
  scale-gated perf + threat-gated security stay deferred. *(operator-confirmed 2026-05-29)*
- **Q2 (defer to Architecture):** does v4 warrant a real `scripts/migrations/`
  script, or is "bump user_version + reindex" sufficient (as for v2→v3)? Proposed:
  reindex-only (consistent with v2→v3); no migration framework yet (Q-A3).
- **Q3 (defer to Dev):** L-8 — fix in `reindex_full` (title→name→slug fallback) vs
  also emit `title:` in `write_concept_page`. Proposed: reindex fallback (one site);
  optionally also pin `title:` in the extractor for forward cleanliness.

#### Decision Log
- **D-006-1** Scope = the 8 RTM rows above; everything else in the ledger stays
  deferred with triggers. *(operator-confirmed)*
- **D-006-2** Schema v3→v4 migration = `wiki-reindex --full` (Class B), no ALTER —
  same contract as v2→v3 (ADR-002 §D8 amendment).
- **D-006-3** RTM keyed by ledger id (P-5/L-5/L-2/L-8/F12c/P-10/L-1/6/7 + MIG), not
  new ROADMAP R-numbers, since this consolidates existing ledger debt.
