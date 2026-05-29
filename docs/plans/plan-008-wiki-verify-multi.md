# Development Plan: TASK 008 — Epic 7 RAG layer: `wiki-verify-multi` (R-8)

> **Status**: DRAFT (2026-05-29) — awaiting plan-reviewer sign-off.
> **Task ID**: 008 / Slug: `wiki-verify-multi`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-8.1..R-8.10 + R-8.5e; UC-22..UC-28; Decision Log D-008-1..7; constraints C-1..C-12).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §2 **Verification Layer** component + §4 Data Model (verdict page as first-class compounding `type=verification`; `ref_type='verifies'` + R-8.5e reindex read-side; `source_state` reuse; **schema v4→v5**) + §5 Interfaces + the ADR-002 §D8 v4→v5 amendment — updated in place + reviewed (both gates APPROVED, see [docs/reviews/task-008-review.md](./reviews/task-008-review.md), [docs/reviews/architecture-008-review.md](./reviews/architecture-008-review.md)).
> **Methodology**: **Stub-First (TDD)**, **green-throughout** (every bead boundary keeps `pytest` green + `SQLiteRepository` instantiable + `mypy --strict` clean — ABC abstractmethod + `SQLiteRepository` stub land together). Each code bead lands Phase-1 stubs + RED→GREEN tests before Phase-2 logic; the per-bead split is documented in §3.
> **Predecessors**: R-6 / TASK 007 (`wiki-query`, the Decision-17 `prepare`/`apply` + R-6.5e reindex read-side template) `c6c249d`; current HEAD `81d8abf` (schema **v4**).
> **Unblocks**: nothing gates on R-8; it strengthens R-X1 readiness (a second `HOST_ONLY_SUBDIRS` member proves the role-split generalises).
> **Out of scope** (TASK §5 C-4): R-7 (`wiki-research`, web enrichment) — separate + independent; auto-invocation by `wiki-query` (R-8 is off-by-default, R-8.10); embeddings/vector verification (FTS5 + the cited source bodies only).

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| `_verifications/<slug>.md` frontmatter (`type: verification`, `verifies: project/query-slug`, `verdict: pass\|fail`, `critics:`, `answer_hash:`, `date:`, optional `cites:`, `tags:[verification]`) + sanitised findings body | **Canonical** verdict + the verdict→query edge | **Class A** |
| `pages` row (`type='verification'`) + `page_entity_refs` (`ref_type='verifies'` + optional `'cited'`) + `log_events` (`event_type='verify'`) | DB mirror; rebuilt by `wiki-reindex --full` | **Class B** |
| `source_state` (`source_kind='verification'`) | Verify idempotency (`verify_hash`); recomputed on re-verify | **Class C** |
| `IndexRepository` (ABC) + `SQLiteRepository` | All read/write SQL; new `check_verify_state`/`record_verify_state`; reuses `get_page`/`upsert_page`/`replace_refs`; reindex `_frontmatter_refs` read-side | DAL boundary (skills never write raw SQL) |
| `wiki-verify-multi` (`prepare`/`apply`) + `wiki-verify` prompt skill | Thin CLI over the DAL + orchestrator-owned 4-critic audit (Decision-17) | Skill Layer |

**TASK 008 invariants** (carried from the two review gates):
1. **§D8 durability** — the verdict page + its `verifies` ref reconstruct from Class A markdown alone after `wiki-reindex --full` (**UC-26** is the binding gate). This rests on R-8.5e (the reindex read-side) **and** the `TYPE_MAPPING["verification"]` mapping — without the mapping the page is skipped on reindex (Arch M-1), so the read-side never runs.
2. **The §D8 spine is a THREE-PART change that must land together** (Arch M-1): `layout.py` (`VERIFICATIONS_SUBDIR ∈ HOST_ONLY_SUBDIRS`) + `normalization.py` (`TYPE_MAPPING["verification"]` + `_PATH_TYPE_FALLBACK`) + `reindex.py` (the `verifies:`→`'verifies'` read-side). "layout.py alone is insufficient" (the TASK 007 C-1 lesson, re-surfaced for R-8).
3. **R-8.5e same-table merge, NOT a 2nd `replace_refs`** — `verifies`/`cited` refs are **unioned into the page's `out.refs` set before the single Step-2 `replace_refs`** (delete-all-then-insert; a second pass would clobber body-`mentioned` refs). Generalise `_cited_refs_from_frontmatter` → `_frontmatter_refs(db_type, …)` (DRY — C-6), unioned in **both** `reindex_full` **and** `reindex_delta` (delta-symmetry).
4. **Reindex phase order (AM-3)** — Step 2 (union `verifies`/`cited` into `out.refs`) → Step 2.5 (canonicalize `entity_slug` through aliases; `ref_type` **preserved** → no `verifies`→`mentioned` degradation) → Step 3 recompute.
5. **Decision-17** — no LLM call in Python; the 4-critic audit is orchestrator-owned via the `wiki-verify` prompt skill; `wiki-verify-multi` is a deterministic `prepare`/`apply` pair.
6. **Grounding enforced in Python** — `prepare` refuses `NO_SOURCES` (empty `cites:`); `apply` rejects any `findings[].source` not in the examined set (`FINDING_SOURCE_NOT_EXAMINED`) and an out-of-enum verdict (`INVALID_VERDICT`), keyed on the full **`project/slug`** tuple. Never trusted to the LLM.
7. **FAIL = record + non-zero exit, never mutate the answer** (D-008-3) — on a FAIL verdict `apply` files the verdict page + returns **exit 6 `VERDICT_FAIL`**; the `_queries/<slug>.md` answer is byte-identical before/after. `--fail-on=none` → exit 0. **Note (SEC-4):** `6` is the family's generic *error* code, so here it is a documented *deliberate divergence* — `VERDICT_FAIL` is a SUCCESS envelope (no `error` key); callers MUST branch on the stdout envelope (`verdict:"fail"`), not on `$?==6 ⇒ error`. The SKILL/workflow docs (008-08) state this.
8. **Layout-agnostic source access** (C-8/NFR-7, operator-binding) — the answer + every cited source body is read via `pages.file_path` + the DAL, never a reconstructed `<subdir>/<slug>.md`; the verdict surface is declared **only** in `layout.py`. A grep guard asserts no `PAGE_SUBDIRS` literal in `wiki_verify_multi.py` (UC-28).
9. **No H-PERF-3/P-8 N+1** — `apply` self-indexes the one verdict page via **direct `upsert_page` + `replace_refs` on one connection**, never `index_from_manifest`→`main(argv)`.
10. **Two distinct hashes** — `answer_hash = sha256(answer body)` is the TOCTOU guard (`ANSWER_CHANGED`); `verify_hash = sha256(answer_hash ‖ ordered examined project/slug set)` is the `source_state` idempotency key (`is_unchanged`).
11. **Schema v4→v5 (NOT zero-DDL)** — `pages.type+='verification'`, `ref_type+='verifies'`, `event_type+='verify'`, `index_meta` view; `PRAGMA user_version` 4→5. The migration on a **populated** v4 DB is **delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`** (the deletion forces a fresh v5 schema apply; bare `wiki-reindex --full` only DELETEs rows and **cannot** relax a CHECK on an existing table — DUR-2). No in-place ALTER; no `user_version`-gated auto-reseed exists.
12. **Envelope invariant** — CWE-117/209: `{error, field?, reason}` only; never echo the answer/source/finding/verdict content.

---

## 1. Task Execution Sequence

### Phase 1 — Schema + durability spine (the load-bearing core)

The §D8 round-trip (UC-26) is the binding acceptance gate, so the spine lands first: the schema must admit `verification` (008-01) and the type must be mapped + discoverable (008-02) before the reindex read-side (008-03) can round-trip it. The verify-state DAL (008-04) backs idempotency and is parallel-safe.

- [R-8.9] **008-01** — schema **v4→v5**: `sql/wiki-index-v2.sql` (+ `docs/SCHEMA-v2.sql` mirror): `pages.type` CHECK `+= 'verification'`; `page_entity_refs.ref_type` CHECK `+= 'verifies'`; `log_events.event_type` CHECK `+= 'verify'`; `index_meta` view WHERE `+= 'verification'`; `PRAGMA user_version = 5`. Add `tests/test_schema_v5.py` (new enums admit a verification row/`verifies` ref/`verify` event; `user_version == 5`); update **all three** prior `user_version == 4` pins (`test_schema_v4.py:27`, `test_schema_smoke.py:67`+docstring, `test_schema_v3.py:31` — DEC-3/DUR-3) in the same bead (green-throughout). No `pages_fts_*` trigger change (they index all types). Migration on a populated v4 DB = **delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`** (Class B; bare `wiki-reindex --full` can't relax a CHECK on an existing DB — DUR-2).
  - Description File: [docs/tasks/task-008-01-schema-v5.md](./tasks/task-008-01-schema-v5.md)
  - Priority: Critical (blocks any verification-row insert) · Dependencies: none · Est: 0.5 day

- [R-8.5, C-8/NFR-7] **008-02** — layout + normalization (Arch M-1, parts 1+2 of the three-part spine): `layout.py` add `VERIFICATIONS_SUBDIR = "_verifications"` to `HOST_ONLY_SUBDIRS` (flows into `PAGE_SUBDIRS` → `discover_pages`/drift/render + `SCAFFOLD_DIRS`); `normalization.py` add `TYPE_MAPPING["verification"] = ("verification", None)` **and** `_PATH_TYPE_FALLBACK[VERIFICATIONS_SUBDIR] = "verification"`. **Without `TYPE_MAPPING` the verdict page raises `UnmappedTypeError` → silently skipped on reindex (found but never indexed)** — the load-bearing half of R-8.5e.
  - Description File: [docs/tasks/task-008-02-layout-normalization-verifications.md](./tasks/task-008-02-layout-normalization-verifications.md)
  - Priority: Critical (durability spine; blocks reindex read-side + apply index) · Dependencies: 008-01 · Est: 0.25 day

- [R-8.5e, AM-3] **008-03** — reindex read-side (the §D8 fix): generalise `_cited_refs_from_frontmatter` → `_frontmatter_refs(db_type, updated_fm, …)`; for a `type=verification` page parse `verifies:` (one `project/slug`) → a `ref_type='verifies'` `PageRef` **and** `cites:` → `ref_type='cited'` refs, and **union them into the page's `out.refs` set before the single Step-2 `replace_refs`** (Arch M-1) — in **both** `reindex_full` **and** `reindex_delta`. Confirm Step 2.5 (AM-3) canonicalizes `entity_slug` with `ref_type` preserved (no `verifies`→`mentioned`). Skip-and-report malformed entries. Keep the existing `type=query` `cites:` branch working (regression).
  - Description File: [docs/tasks/task-008-03-reindex-verifies-read-side.md](./tasks/task-008-03-reindex-verifies-read-side.md)
  - Priority: Critical (durability spine — UC-26 fails without it) · Dependencies: 008-01, 008-02 · Est: 1 day · **strict-TDD**

- [R-8.6] **008-04** — verify-state DAL: `check_verify_state(vault_id, verification_slug) → str | None` + `record_verify_state(vault_id, verification_slug, verify_hash) → None` — thin typed wrappers over `source_state` (`source_kind='verification'`, `scope=verification_slug`, `key='verify_hash'`), modelled exactly on TASK 007's `check/record_query_state`. ABC abstractmethod + `SQLiteRepository` impl land together (green-throughout). No raw SQL in skills (NFR-2).
  - Description File: [docs/tasks/task-008-04-verify-state-dal.md](./tasks/task-008-04-verify-state-dal.md)
  - Priority: Critical (idempotency) · Dependencies: none (`source_state` exists) · Est: 0.5 day

### Phase 2 — Skill (`prepare` / `apply`)

Thin skill over the DAL, modelled on `wiki-query`'s two-subcommand shape. Source access is **layout-agnostic** (via `pages.file_path`), enforced by a grep guard (C-8/NFR-7).

- [R-8.1, R-8.8-prepare, C-8/NFR-7] **008-05** — `wiki-verify-multi prepare <query-slug>` + `bin/wiki-verify-multi` wrapper + argparse (`prepare`/`apply` subparsers; `apply` stubbed). `get_page` the query page (`QUERY_NOT_FOUND` if absent/non-query); read answer body + `question:` + `cites:`; for each cited `project/slug`, `get_page` it + read its body via `pages.file_path` (**never** a reconstructed path); `NO_SOURCES` if `cites:` empty; compute `answer_hash`; derive `verification_slug` (`--slug` else `<query-slug>` derived); `check_verify_state` → `is_unchanged`; emit the verification envelope.
  - Description File: [docs/tasks/task-008-05-verify-prepare.md](./tasks/task-008-05-verify-prepare.md)
  - Priority: High · Dependencies: 008-04 · Est: 1 day

- [R-8.3, R-8.7, R-8.8-apply] **008-06** — `wiki-verify-multi apply` write-side: re-read the query page + recompute `answer_hash`, compare to `--answer-hash` (`ANSWER_CHANGED` on mismatch); validate the verdict JSON (`INVALID_VERDICT` / `VERDICT_PARSE_ERROR` / `VERDICT_TOO_LARGE`); enforce the **grounding gate** — every `findings[].source` ⊆ examined set keyed on **`project/slug`** (`FINDING_SOURCE_NOT_EXAMINED`); sanitise the verdict body via `_common.sanitize_markdown_text`; atomic-write `_verifications/<verification_slug>.md` (Class A; `O_NOFOLLOW` symlink-refuse + tempfile + content-hash skip; `--force` overrides skip; `INVALID_VERIFICATION_PAGE` on symlink); compute the PASS/FAIL verdict vs `--fail-on` (default `high`) → **exit 6 `VERDICT_FAIL`** on FAIL (page still filed), exit 0 on PASS or `--fail-on=none`. **The Class-A answer is NEVER edited.** **Stops at the file write — DB indexing is 008-07.**
  - Description File: [docs/tasks/task-008-06-verify-apply-write.md](./tasks/task-008-06-verify-apply-write.md)
  - Priority: High · Dependencies: 008-05 · Est: 1.25 day · **strict-TDD** (grounding gate + FAIL semantics + no-mutate-answer)

- [R-8.4, R-8.6-apply] **008-07** — `wiki-verify-multi apply` index-side: self-index the one verdict page via **direct `upsert_page` (`type=verification`) + `replace_refs` (`verifies` [+ optional `cited`] refs) on a single repo connection** — NOT `index_from_manifest`/`main(argv)` (H-PERF-3); reuse `reindex._build_page` + the new `_frontmatter_refs` for byte-identical rows; `record_verify_state`; append one `verify` `log_event` (subject = verification_slug; `--orchestrator-id` provenance in `details_json`). The verdict page is FTS-searchable immediately after.
  - Description File: [docs/tasks/task-008-07-verify-apply-index.md](./tasks/task-008-07-verify-apply-index.md)
  - Priority: High · Dependencies: 008-06, 008-04, **008-03** (reuses its `_frontmatter_refs("verification", …)` — DEC-2), 008-01, 008-02 · Est: 0.75 day · **strict-TDD** (the byte-identical-rows §D8 symmetry keystone that 008-09 leans on — TC-UNIT-01 written test-first)

### Phase 3 — Verdict-contract prompt skill + skill/command/workflow docs + symlinks

- [R-8.2, R-8.10, C-1] **008-08** — `wiki-verify` prompt-contract skill (repo-root `skills/wiki-verify/SKILL.md`, scaffolded via `skill-creator/init_skill.py` per the SKILL CREATION GATE; **SECURITY-SENSITIVE**) defining the 4 prose lenses (factual-grounding / logic-coherence / security-injection / completeness-faithfulness), the verdict JSON contract, the grounding rule (every `findings[].source` ∈ examined set), the **H-6 untrusted answer+source** prompt-armor, and the Layer-A `Agent` fan-out / sequential-fallback note (Q-008-d). Plus `skills/wiki-verify-multi/SKILL.md` (deterministic-CLI subcommand reference), `commands/wiki-verify-multi.md`, `workflows/wiki-verify-multi.md` (off-by-default; layered *after* a `wiki-query apply`), and the `.claude/`/`.agent/` symlink set via `bin/link-*.sh`.
  - Description File: [docs/tasks/task-008-08-verify-prompt-skill-and-docs.md](./tasks/task-008-08-verify-prompt-skill-and-docs.md)
  - Priority: Medium · Dependencies: 008-05, 008-06, 008-07 (final CLI surface) · Est: 0.75 day

### Phase 4 — Acceptance + regression + docs

- [UC-26] **008-09** — §D8 durability round-trip acceptance test (the binding gate): file a verdict page (via `apply`), snapshot the `pages` row + `verifies` ref, **delete the DB**, `wiki-reindex --full`, assert the verdict page is rediscovered as `type=verification` and its `verifies` ref is reconstructed from `verifies:` frontmatter alone — **`ref_type='verifies'`**, not degraded to `'mentioned'`, not clobbered. Repeat for `--delta` (delta-symmetry).
  - Description File: [docs/tasks/task-008-09-durability-acceptance.md](./tasks/task-008-09-durability-acceptance.md)
  - Priority: Critical (acceptance) · Dependencies: 008-01, 008-02, 008-03, **008-06** (write-side), 008-07 (index-side) · Est: 0.5 day · **strict-TDD**

- [UC-22, UC-23, UC-24, UC-25, UC-27, UC-28, C-8/NFR-7] **008-10** — end-to-end + compounding + **layout-agnostic** acceptance: UC-22 (verify→PASS, exit 0, verdict page written); UC-23 (FAIL → **exit 6** + verdict filed + the `_queries/<slug>.md` answer byte-identical; `--fail-on=none` → exit 0); UC-24 (idempotent re-verify `is_unchanged`; `--force` re-verifies; a changed answer re-triggers); UC-25 (`wiki-search --types verification` finds the verdict + the `verifies` backlink exists); UC-27 (`NO_SOURCES` on empty `cites:`; `FINDING_SOURCE_NOT_EXAMINED`; `ANSWER_CHANGED` — all refused, nothing written); **UC-28** (a cited source whose `pages.file_path` is NOT under a Karpathy subdir is still read by `prepare` + a grep guard asserts no `PAGE_SUBDIRS` literal in `wiki_verify_multi.py`).
  - Description File: [docs/tasks/task-008-10-e2e-compounding-layout-acceptance.md](./tasks/task-008-10-e2e-compounding-layout-acceptance.md)
  - Priority: Critical (acceptance) · Dependencies: 008-05, 008-06, 008-07, 008-09 · Est: 0.75 day

- [all RTM, C-4/C-9] **008-11** — regression sweep + docs (acceptance gate): full `pytest tests/` + `mypy --strict scripts/`; ROADMAP **R-8 → DONE** + a note that R-7 (`wiki-research`) stays independent; `docs/ARCHITECTURE.md` status header → SHIPPED (drop "IN DESIGN"); README + `CLAUDE.md` (CLIs + schema v5 + pointers) + `skills/.AGENTS.md` + `tests/.AGENTS.md` + `scripts/{wiki_skills,wiki_index}/.AGENTS.md`; extend the envelope-never-echoes-content regression suite to the `wiki-verify-multi` surfaces (answer/source/finding/verdict).
  - Description File: [docs/tasks/task-008-11-regression-and-docs.md](./tasks/task-008-11-regression-and-docs.md)
  - Priority: Critical (acceptance gate) · Dependencies: **all prior** 008-01..008-10 · Est: 0.5 day

---

## 2. Dependency DAG (critical-path view)

```text
   008-01 schema v4→v5 ─► 008-02 layout+normalization ─► 008-03 reindex verifies:→'verifies' (R-8.5e) ─┐
   (R-8.9)                (R-8.5, Arch M-1)               (AM-3 phase order)                            │
                                                                                                        │
   008-04 verify-state DAL (R-8.6) ─► 008-05 prepare (R-8.1) ─► 008-06 apply-write (R-8.3/7/8) ─► 008-07 apply-index (R-8.4)
   008-03 `_frontmatter_refs` ───────────────────────────────────────────────────────────────► 008-07 (reuses it; DEC-2)
                                                                                                  │            │
   008-05,06,07 ─► 008-08 wiki-verify prompt skill + docs + symlinks (R-8.2, R-8.10, C-1)        │            │
   {008-01,02,03, 008-06, 008-07} ─► 008-09 durability acceptance (UC-26, §D8 gate) ◄─────────────┴────────────┘
   {008-05,06,07, 008-09} ─► 008-10 e2e + compounding + layout-agnostic (UC-22/23/24/25/27/28) ◄───────────────┘
   ALL ─► 008-11 regression + docs (ACCEPTANCE GATE)
```

**Critical path** (longest blocking chain): 008-01 → 008-02 → 008-03 → 008-09 → 008-10 → 008-11, **and** 008-04 → 008-05 → 008-06 → 008-07 → 008-09 → 008-10 → 008-11.
**Parallel-safe at start**: {008-01, 008-04} (independent). **008-02** unlocks once 008-01 lands; **008-03** once 008-02 lands. The skill chain (008-05→06→07) runs alongside the spine (it only needs 008-04 to start; **008-07 needs 008-01/02 AND 008-03's `_frontmatter_refs`** for the `type=verification` upsert + byte-identical ref build — so 008-07 cannot land until 008-03 has, DEC-2).

---

## 3. Stub-First Application (per `tdd-stub-first`, green-throughout)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 008-01 | yes (DDL) | n/a — declarative DDL | RED: a fresh DB admits `INSERT pages(type='verification')`, `page_entity_refs(ref_type='verifies')`, `log_events(event_type='verify')`; `PRAGMA user_version == 5`; `index_meta` includes a verification row | edit the 3 CHECKs + view + `user_version`; update **all three** prior version-pin tests (v4/smoke/v3) |
| 008-02 | yes (layout/normalization constants) | n/a — declarative | RED: `discover_pages` over a vault with `_verifications/v.md` yields it; `SCAFFOLD_DIRS` includes `_verifications`; `normalize_frontmatter({'type':'verification',…})` → `("verification", None)` (no `UnmappedTypeError`); `_infer_type_from_path('_verifications/x.md')` → `"verification"` | add constant to `HOST_ONLY_SUBDIRS` + `TYPE_MAPPING` + `_PATH_TYPE_FALLBACK` |
| 008-03 | yes (reindex.py) | `_frontmatter_refs(db_type)` present, returns the existing `cites:`→`'cited'` for `query`, nothing for `verification` (records current behavior) | RED: a `type=verification` page with `verifies: _vault_/q` + body `[[bar]]` → after `reindex_full` AND `reindex_delta`, `page_entity_refs` has `(v, q, 'verifies')` **and** `(v, bar, 'mentioned')` (not clobbered); a `verifies:` target that is an alias is canonicalized (AM-3) with `ref_type` still `'verifies'`; `type=query` `cites:` still works (regression) | generalise to `_frontmatter_refs(db_type)`; add `verification` branch (`verifies:`→`'verifies'` + `cites:`→`'cited'`); union into `out.refs` before the single `replace_refs`; both full+delta; skip+report malformed |
| 008-04 | yes (DAL) | ABC abstractmethods + `SQLiteRepository` stubs (`check_verify_state`→`None`; `record_verify_state`→`pass`) | RED: `record_verify_state` then `check_verify_state` returns the hash; absent → `None`; second record UPSERTs; multi-vault isolation; NULL guard | parameterized SELECT / `INSERT … ON CONFLICT` on `source_state` |
| 008-05 | yes (CLI) | `wiki_verify_multi.py` argparse (`prepare`/`apply` subparsers; `apply`→exit "not impl" stub); `bin/wiki-verify-multi` | RED: `--help` ok; `prepare` on a query page with `cites:` emits the envelope (`examined[]` read via `pages.file_path`, `answer_hash`, `verification_slug`); non-query/absent slug → `QUERY_NOT_FOUND`; empty `cites:` → `NO_SOURCES` exit 2; unchanged hash → `is_unchanged:true`; **no literal `PAGE_SUBDIRS` string in the module** (grep guard) | wire `get_page` (query + each cited source); read bodies via `file_path`; hash; derive slug; `check_verify_state` |
| 008-06 | yes (CLI) | `apply` handler parses args, calls stubs; no write | RED: `--help` ok; `answer_hash` mismatch → `ANSWER_CHANGED`; finding source ∉ examined → `FINDING_SOURCE_NOT_EXAMINED`; bad verdict JSON → `INVALID_VERDICT`; valid PASS → `_verifications/<slug>.md` written (`type: verification`+`verifies:`+`verdict: pass`), exit 0; valid FAIL → file written + **exit 6**; `--fail-on=none` + FAIL → file written + exit 0; the source `_queries/<slug>.md` is **byte-identical** before/after (no mutation); re-run identical → content-hash skip; `--force` rewrites | re-read+hash-check; verdict validate; grounding gate (`project/slug`); `_sanitize_markdown_text`; atomic write; verdict/exit logic |
| 008-07 | yes (CLI + DAL calls) | `apply` index step stubbed (file written, not indexed) | RED: after `apply` the `pages` row `type=verification` exists; the `verifies` ref exists; `wiki-search --types verification` finds the page; `source_state` recorded (`verify_hash`); one `verify` log_event with `--orchestrator-id` in `details_json` | `upsert_page`+`replace_refs(verifies[+cited])` on one conn (reuse `_build_page`+`_frontmatter_refs`); `record_verify_state`; `append_log_event` |
| 008-08 | **no — skills/docs/symlinks** | n/a | n/a | `init_skill.py wiki-verify`; write SKILL/command/workflow md; run `bin/link-*.sh` |
| 008-09 | yes (acceptance test) | scaffolding w/ `pytest.skip` | collection discovers the UC-26 test | full §D8 round-trip: file → snapshot → drop DB → `reindex --full` (and `--delta`) → assert verdict page + `verifies` ref restored, `ref_type='verifies'`, not degraded |
| 008-10 | yes (acceptance tests) | scaffolding w/ `pytest.skip` | collection discovers UC-22/23/24/25/27/28 tests | e2e PASS/FAIL/exit-6/no-mutation + idempotency + compounding-search + grounding refusals + layout-agnostic (file_path on non-Karpathy layout + grep guard) |
| 008-11 | **no — verify/docs** | n/a | n/a | doc edits + run full suite + envelope-regression extension; gate the task |

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-22** | Verify a filed answer → PASS verdict page (happy path) | 008-05, 008-06, 008-07, 008-10 |
| **UC-23** | FAIL verdict → exit 6 + answer untouched | 008-06, 008-10 |
| **UC-24** | Idempotent re-verify (`is_unchanged`; `--force`) | 008-04, 008-05, 008-06, 008-10 |
| **UC-25** | Compounding — a later search finds the verdict + `verifies` backlink | 008-02, 008-07, 008-10 |
| **UC-26** | Durability round-trip (§D8 gate) | 008-01, 008-02, 008-03, 008-09 |
| **UC-27** | Grounding / answer-change violations refused at boundary | 008-05 (`NO_SOURCES`), 008-06 (`FINDING_SOURCE_NOT_EXAMINED`/`ANSWER_CHANGED`), 008-10 |
| **UC-28** | Layout-agnostic — verify works on a non-Karpathy vault | 008-05, 008-10 |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement | Bead(s) | Phase |
|---|---|---|---|
| R-8.1 | `prepare` deterministic verification envelope | 008-05 | 2 |
| R-8.2 | Orchestrator-owned 4-critic audit + verdict contract (Decision-17) | 008-08 (contract), 008-06 (grounding enforcement) | 2,3 |
| R-8.3 | `apply` writes Class A verdict page | 008-06 | 2 |
| R-8.4 | Compounding — indexed + `verifies` back-linked | 008-07 | 2 |
| R-8.5 | `_verifications/` discoverable **and type-mapped** | 008-02 | 1 |
| **R-8.5e** | Reindex `verifies:`→`'verifies'` read-side (§D8 fix) | 008-03 | 1 |
| R-8.6 | Idempotency / re-run | 008-04 (DAL), 008-05 (`is_unchanged`), 008-06/07 (`record`/`--force`) | 1,2 |
| R-8.7 | FAIL semantics — record + non-zero exit, no answer mutation | 008-06 | 2 |
| R-8.8 | Grounding / no-fabrication of findings | 008-05 (`NO_SOURCES`), 008-06 (`FINDING_SOURCE_NOT_EXAMINED`/`INVALID_VERDICT`) | 2 |
| R-8.9 | Schema v4→v5 | 008-01 | 1 |
| R-8.10 | Off-by-default opt-in | 008-08 (docs) + verified in 008-11 (`wiki-query` unchanged) | 3,4 |
| AM-3 | reindex ref-canonicalization (`verifies`/`cited` participate, `ref_type` preserved) | 008-03 | 1 |
| C-8 / NFR-7 | Layout-agnostic source access + verdict-surface role-split (binding R-X1/R-X2-compat) | 008-02 (role-split), 008-05 (file_path reads + grep guard), 008-10 (UC-28) | 1,2,4 |

**1-1 sanity** (no orphan requirements): every R-8.x + R-8.5e + AM-3 + C-8/NFR-7 maps to ≥1 bead; every code bead carries ≥1 RTM ID in its `[R-8.x]` tag. UC-22..UC-28 are verified end-to-end by 008-09 + 008-10.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **`TYPE_MAPPING["verification"]` omitted** (only `layout.py` + `reindex.py` changed) → `normalize_frontmatter` raises `UnmappedTypeError`, the verdict page is silently skipped on reindex, UC-26 fails before R-8.5e runs (the Arch M-1 / TASK-007-C-1 trap). | Medium | High | 008-02 makes the `normalization.py` addition an explicit, separately-tested bead; 008-09 asserts the page is **indexed** as `type=verification` (not in `skipped[]`) before checking the ref. The plan's invariant #2 names the three-part change. |
| **R-2** | **R-8.5e implemented as a 2nd `replace_refs`** → clobbers the body-`mentioned` refs (delete-all-then-insert). | Medium | High | 008-03 unions `verifies`/`cited` into `out.refs` before the single Step-2 `replace_refs` (Arch M-1); a Phase-1 RED test asserts the body `mentioned` ref **survives** alongside the `verifies` ref. |
| **R-3** | **AM-3 degrades `verifies`→`mentioned`** on reindex, breaking UC-26. | Low | High | 008-03 verifies Step 2.5 rewrites `entity_slug` only (AM-3); 008-09 asserts the reconstructed ref is `ref_type='verifies'`. |
| **R-4** | **`apply` mutates / quarantines the answer on FAIL** (violates D-008-3). | Medium | High | 008-06 strict-TDD: a test hashes `_queries/<slug>.md` before/after a FAIL `apply` and asserts byte-identity; the skill has **no write path** to `_queries/`. |
| **R-5** | **Grounding bypass** — a fabricated finding source slips through if the key is a bare slug across projects. | Medium | High | R-8.8b/UC-27 + 008-06 enforce the full **`project/slug`** tuple against the examined set; 008-10 UC-27 uses a cross-project same-slug fixture. |
| **R-6** | **Verdict-body injection** into Class A frontmatter/body (CWE-117/209, YAML-delimiter, wikilink/dataview) — findings quote untrusted answer/source text. | Medium | Medium | 008-06 reuses `_common.sanitize_markdown_text` (text-only allowlist) + caps; 008-11 extends the parametrised envelope-never-echoes-content regression to answer/source/finding/verdict. The `wiki-verify` skill (008-08) carries the H-6 untrusted-content armor. |
| **R-7** | **Self-index N+1** if `apply` reuses the manifest path. | Low | Medium | 008-07 mandates direct `upsert_page`+`replace_refs` on one connection (NFR-5); forbids `index_from_manifest`/`main(argv)`. |
| **R-8** | **`exit 6` is the wiki-family's generic *error* code** (`_common.emit` / `.AGENTS.md` convention), but `wiki-verify-multi` returns `6` as a *verdict-fail SUCCESS* signal — a naive cross-CLI consumer applying "`$?==6 ⇒ errored, nothing written`" would discard a filed FAIL verdict (SEC-4). | Medium | Medium | Documented **deliberate divergence**: 008-06 + 008-08 (SKILL/workflow) require callers to branch on the **stdout envelope** (`verdict:"fail"`, no `error` key), not `$?`; the sole consumer today is the off-by-default workflow. (Distinct from the verify CLI's OWN errors 2/4.) 008-10 asserts the exact code on a FAIL fixture. |
| **R-9** | **Layout-coupling sneaks in** (a reconstructed `_sources/<slug>.md` path) → breaks R-X1/R-X2-compat (C-8/NFR-7). | Medium | High | 008-05 reads every source body via `pages.file_path`; a **grep guard** test forbids any `PAGE_SUBDIRS` literal in `wiki_verify_multi.py`; 008-10 UC-28 proves it on a non-Karpathy `file_path` fixture. |
| **R-10** | **Schema v4→v5 migration breaks existing v4 DBs / version-pin tests.** | Medium | Medium | 008-01 updates **all three** version-pin tests in the same bead (green-throughout; DEC-3/DUR-3 — `test_schema_v4.py`/`test_schema_smoke.py`/`test_schema_v3.py`); the populated-DB migration is **delete-then-reregister-then-reindex** (NOT bare `wiki-reindex --full`, which can't relax a CHECK — DUR-2/DEC-4); `test_schema_v5.py` pins the new state. The false "`wiki-init` reads `user_version` and reseeds" claim is struck from 008-01 + TASK R-8.9(d). |

---

## 7. Definition of Done (acceptance gate — 008-11)

Done iff **all** hold:

- [ ] All 11 beads (008-01..008-11) complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → all green (baseline = the exact count captured at 008-01 start — ≈599 post-TASK-007; + the new TASK 008 cases), 0 failed.
- [ ] `mypy --strict scripts/` → Success: no issues found.
- [ ] **UC-26 §D8 gate** (008-09): file a verdict page → delete DB → `wiki-reindex --full` (and `--delta`) → verdict page rediscovered as `type=verification`; `verifies` ref reconstructed from `verifies:` frontmatter alone, **`ref_type='verifies'`** (not `'mentioned'`), body `mentioned` refs intact.
- [ ] **UC-22/23/24/25/27/28** (008-10): verify→PASS (exit 0); FAIL → **exit 6** + verdict filed + `_queries/<slug>.md` byte-identical; `--fail-on=none` → exit 0; idempotent re-verify (`is_unchanged`); `--force` re-verifies; `wiki-search --types verification` finds a filed verdict + the `verifies` backlink exists; `NO_SOURCES`/`FINDING_SOURCE_NOT_EXAMINED`/`ANSWER_CHANGED` refused (no write); layout-agnostic cited-source read on a non-Karpathy `file_path` + grep guard clean.
- [ ] `wiki-verify-multi` has a `bin/` wrapper + `skills/wiki-verify-multi/SKILL.md` + `commands/wiki-verify-multi.md` + `workflows/wiki-verify-multi.md` + the `wiki-verify` prompt skill + symlinks; `bin/wiki-verify-multi --help` exits 0.
- [ ] `pages.type='verification'`, `ref_type='verifies'`, `event_type='verify'` admitted; `PRAGMA user_version == 5`; migration = `wiki-reindex --full` (no ALTER).
- [ ] **No literal `PAGE_SUBDIRS` string in `wiki_verify_multi.py`** (grep guard green) — layout-agnostic invariant (C-8/NFR-7).
- [ ] `wiki-query` behaviour **unchanged** (R-8 is off-by-default; `wiki-query apply` never calls `wiki-verify-multi`).
- [ ] ROADMAP **R-8 → DONE**; `docs/ARCHITECTURE.md` status → SHIPPED (drop "IN DESIGN"); ADR-002 §D8 v4→v5 amendment in place.
- [ ] Envelope-never-echoes-content regression suite extended to `wiki-verify-multi` (answer/source/finding/verdict surfaces).

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | 11 |
| Total working-time estimate (single-dev, sequential) | ~7.25 days |
| Critical-path estimate (with DAG parallelization) | ~5 days |
| Acceptance-gate effort (008-09 + 008-10 + 008-11) | ~1.75 days |

---

## 9. Open Issues / Planner Judgement Calls

1. **Schema-bead first** — 008-01 (v4→v5) is the hard prerequisite: no `verification` row can be inserted (and no reindex round-trip can pass) until the CHECK admits it. It is its own bead because it has a dedicated test gate (`test_schema_v5.py`) and updates the version-pin assertion.
2. **The three-part durability spine is split 008-01/02/03 but reasoned as one unit** — invariant #2 (Arch M-1) is explicit that `layout.py` alone is insufficient; 008-02 carries the load-bearing `TYPE_MAPPING` addition and 008-09 asserts the page is *indexed*, not skipped.
3. **`apply` split into write (008-06) + index (008-07)** — Class-A-first write-order (file then DB) makes a clean Stub-First seam; each is a single testable bead. The FAIL-semantics + no-mutate-answer + grounding gate all live in the write bead (008-06, strict-TDD).
4. **Resolved open questions baked in:** Q-008-a `verifies` ref-type (008-01/03); Q-008-b `verify_hash = sha256(answer_hash ‖ ordered examined project/slug)` (008-04/05); Q-008-c `prepare` reads `cites:` (008-05); Q-008-d `wiki-verify` prompt skill + opt-in Layer-A fan-out (008-08); Q-008-e `--fail-on=high` default (008-06); Q-008-f optional `cites:` on the verdict page (008-03/06).
5. **SKILL CREATION GATE** — 008-08 scaffolds the `wiki-verify` prompt skill via `init_skill.py` (mandatory per CLAUDE.agentic.md); the product `skills/wiki-verify-multi/` CLI skill follows the repo-root + `bin/link-skill.sh` convention.
6. **`skill-tdd-strict` (high-assurance) beads** — the correctness-critical beads run under strict TDD (test-first, full edge-case unit coverage, no over-mocking of the DB): **008-03** (R-8.5e reindex read-side — the durability spine), **008-06** (the grounding gate + FAIL semantics + no-mutate-answer), **008-07** (the byte-identical-rows §D8 *symmetry keystone* — the `apply`-written `pages` row + `verifies` ref must equal a `reindex._build_page` rebuild byte-for-byte, else 008-09's round-trip comparison is vacuous; TC-UNIT-01 is written test-first — plan-review M-2), and **008-09** (the §D8 acceptance gate). All other code beads use standard Stub-First. Every bead is green-throughout.
7. **Layout-agnostic enforced by a grep guard** — 008-05 + 008-10 (UC-28) add a test asserting no `PAGE_SUBDIRS` literal appears in `wiki_verify_multi.py`; all source access goes through `pages.file_path` + the DAL (the operator-binding C-8/NFR-7 constraint).
8. **No vault dogfood in-repo** — the repo IS the implementation, not a vault (CLAUDE.md); 008-09/10 acceptance tests run on a throwaway `/tmp` fixture vault (TASK §6 Q-008-g default). A real-content dogfood (verifying a real `wiki-query` answer) is a post-merge step, as TASK 007 did.

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **008-01** (schema v4→v5 — blocks every verification-row insert). **008-04** (verify-state DAL) may proceed in parallel; **008-02** unlocks once 008-01 lands; **008-03** once 008-02 lands; the skill chain (008-05→06→07) starts once 008-04 lands.
