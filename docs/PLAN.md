# Development Plan: TASK 004 — wiki-ingest-vendoring (Python-import-only vendor)

> **Status**: DRAFT (2026-05-27) — awaiting plan-reviewer sign-off.
> **Task ID**: 004 / Slug: `wiki-ingest-vendoring`
> **Source spec**: [docs/TASK.md](./TASK.md) (RTM R-45..R-57, Issues I-V.1..I-V.11, UC-V1/UC-V2, Decisions 11-14, 7-step smoke recipe).
> **Architecture spec**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md) §1.5.2 (PRIMARY + FALLBACK paths), §1.5.7 (vendored module anatomy), §7.4 (vendoring policy) — already updated by Architecture Phase in commit `3b57d81`.
> **Methodology**: **Stub-First (TDD)**. Every bead with code surface lands Phase-1 stubs + E2E tests (Red→Green on stubs) before Phase-2 logic. Documentation-only beads (I-V.8, I-V.10) skip the stub phase.
> **Predecessor**: TASK 003 (`wiki-extract-concepts`) — PAUSED; resumes after this task ships.
> **Out of scope (carried forward from TASK.md §1.2)**: `--manifest-stdin`/`--manifest-file` (TASK 003 / I-7.15); Universal-skills repo edits; PyPI publication (future TASK 005+); refactors outside `wiki_enrich.py` + `tests/test_wiki_enrich.py` + vendored module.

---

## 0. Architectural Foundation (Reference)

| Layer | Owns | Class (ADR-002 §D8) |
|---|---|---|
| `scripts/wiki_ingest/` (new vendored package) | File-level CRUD (additive merge, footnote rendering, lint); in-process `ingest()` API + standalone CLI surface preserved | Class A producer (writes vault markdown files) |
| `scripts/wiki_skills/wiki_enrich.py` (refactored) | Path-selection (primary in-process / fallback subprocess); manifest validation; index upsert via `IndexRepository` | Glue layer |
| `IndexRepository` + SQLite | Index, FTS5, log_events | Class B (cache) + Class C (operational) |

**TASK 004 invariant** (architecture review carried forward): transport-layer change only. No DAL methods added; no DB schema changes; multi-vault `vault_id` predicate preserved on every page write.

---

## 1. Task Execution Sequence

### Phase 1 — Bootstrap (vendoring + sync tooling + provenance)

Stand up the vendored directory, the sync script, and the third-party notices. Without I-V.1 landing first, **no other bead can import or test against the vendored module**. I-V.2 and I-V.10 may proceed in parallel after I-V.1's `VENDORED_FROM.md` format is established.

- [R-45] [I-V.1] Bootstrap `scripts/wiki_ingest/` package + `VENDORED_FROM.md` skeleton
  - Description File: [docs/tasks/task-004-01-vendor-bootstrap.md](./tasks/task-004-01-vendor-bootstrap.md)
  - Priority: Critical (blocks every other bead)
  - Dependencies: none
  - Estimated time: 0.5 day

- [R-49] [I-V.2] `scripts/sync_wiki_ingest.sh` snapshot sync script (SHA256 divergence-check + `--dry-run` + `VENDORED_FROM.md` rewrite)
  - Description File: [docs/tasks/task-004-02-sync-script.md](./tasks/task-004-02-sync-script.md)
  - Priority: High
  - Dependencies: task-004-01 (needs `VENDORED_FROM.md` format)
  - Estimated time: 0.75 day

- [R-55] [I-V.10] `THIRD_PARTY_NOTICES.md` + optional `scripts/wiki_ingest/LICENSE-upstream`
  - Description File: [docs/tasks/task-004-10-third-party-notices.md](./tasks/task-004-10-third-party-notices.md)
  - Priority: Medium
  - Dependencies: task-004-01 (needs snapshot SHA from `VENDORED_FROM.md`)
  - Estimated time: 0.25 day

### Phase 2 — Refactor (programmatic API + mypy compliance)

Extract `ingest()` from the vendored `execute()` and bring the whole vendored tree under `mypy --strict`. I-V.4 runs after I-V.3 so the new `ingest()` signature/`IngestError` are typed in one pass; the time-box (≤ 2 h of fixups) is enforced per Decision-14 + task-reviewer nit.

- [R-46] [I-V.3] Programmatic `ingest()` + `IngestError` extraction in `scripts/wiki_ingest/commands/ingest.py` (**stub-first canonical bead**)
  - Description File: [docs/tasks/task-004-03-programmatic-ingest-api.md](./tasks/task-004-03-programmatic-ingest-api.md)
  - Priority: Critical (blocks I-V.5)
  - Dependencies: task-004-01
  - Estimated time: 1 day

- [R-50] [I-V.4] `mypy --strict scripts/wiki_ingest/` clean (with 2 h time-box → `# type: ignore[<error>]` + UPSTREAM-ISSUE fallback)
  - Description File: [docs/tasks/task-004-04-mypy-strict-vendored.md](./tasks/task-004-04-mypy-strict-vendored.md)
  - Priority: High
  - Dependencies: task-004-03 (signature must land before typing fixups)
  - Estimated time: 0.5 day (time-boxed)

### Phase 3 — Integration (consumer refactor + launcher)

Rewire `wiki_enrich.py` to call the vendored `ingest()` on the primary path; keep subprocess as a guarded fallback. Update the bash launcher so it no longer hard-requires `wiki-ingest` on PATH.

- [R-47, R-48] [I-V.5] `wiki_enrich.py` primary in-process path + subprocess fallback retained
  - Description File: [docs/tasks/task-004-05-wiki-enrich-refactor.md](./tasks/task-004-05-wiki-enrich-refactor.md)
  - Priority: Critical
  - Dependencies: task-004-03 (imports `ingest`, `IngestError`)
  - Estimated time: 1 day

- [R-52] [I-V.6] `bin/wiki-enrich` launcher: drop the `which wiki-ingest` guard
  - Description File: [docs/tasks/task-004-06-launcher-no-path-guard.md](./tasks/task-004-06-launcher-no-path-guard.md)
  - Priority: Medium
  - Dependencies: task-004-05
  - Estimated time: 0.1 day

### Phase 4 — Verify (tests + docs + regression sweep)

I-V.7 backfills mocks against the new vendored module entry point. I-V.8 trims README install steps. I-V.9 is a **verify-no-further-changes** bead (architect already updated ARCHITECTURE.md in commit `3b57d81`). I-V.11 is the final acceptance gate — runs all 7 smokes + 298+ pytest + `mypy --strict`.

- [R-51] [I-V.7] `tests/test_wiki_enrich.py` — replace subprocess mocks with `_vendored_ingest` mocks; add 3 fallback-path cases
  - Description File: [docs/tasks/task-004-07-test-suite-update.md](./tasks/task-004-07-test-suite-update.md)
  - Priority: Critical (gates regression sweep)
  - Dependencies: task-004-05
  - Estimated time: 0.75 day

- [R-53] [I-V.8] README install simplification (drop `ln -s wiki-ingest`; note PATH presence is optional)
  - Description File: [docs/tasks/task-004-08-readme-install-update.md](./tasks/task-004-08-readme-install-update.md)
  - Priority: Medium
  - Dependencies: task-004-05 (so the doc reflects shipped behavior)
  - Estimated time: 0.25 day

- [R-54] [I-V.9] ARCHITECTURE.md verification (confirm §1.5.2 + §1.5.7 + §7.4 already match implementation per commit `3b57d81`; tweak only on drift)
  - Description File: [docs/tasks/task-004-09-architecture-verify.md](./tasks/task-004-09-architecture-verify.md)
  - Priority: Low
  - Dependencies: task-004-05, task-004-07 (so verifier has the actual shipped semantics in hand)
  - Estimated time: 0.25 day

- [R-50, R-51, R-57, **all RTM**] [I-V.11] Regression sweep — 298+ pytest, `mypy --strict scripts/`, manual Smokes 1-7
  - Description File: [docs/tasks/task-004-11-regression-sweep.md](./tasks/task-004-11-regression-sweep.md)
  - Priority: Critical (acceptance gate)
  - Dependencies: **all prior** task-004-01..task-004-10
  - Estimated time: 0.5 day

---

## 2. Dependency DAG (critical-path view)

```text
                  ┌───────────────────────────┐
                  │ task-004-01 vendor-boot   │ (I-V.1, R-45)
                  └────────────┬──────────────┘
                               │
            ┌──────────────────┼──────────────────────────────┐
            ▼                  ▼                              ▼
   ┌──────────────────┐  ┌──────────────────┐   ┌────────────────────────┐
   │ task-004-02      │  │ task-004-10      │   │ task-004-03            │
   │ sync-script      │  │ third-party-     │   │ programmatic-ingest    │
   │ (I-V.2, R-49)    │  │ notices          │   │ (I-V.3, R-46) STUB-1ST │
   └────────┬─────────┘  │ (I-V.10, R-55)   │   └────────────┬───────────┘
            │            └──────────────────┘                │
            │                                                ▼
            │                                     ┌────────────────────────┐
            │                                     │ task-004-04 mypy-strict │
            │                                     │ (I-V.4, R-50)           │
            │                                     └────────────┬───────────┘
            │                                                  │
            │                                                  ▼
            │                                     ┌────────────────────────┐
            │                                     │ task-004-05            │
            │                                     │ wiki-enrich-refactor   │
            │                                     │ (I-V.5, R-47/R-48)     │
            │                                     └────┬──────┬──────┬─────┘
            │                                          │      │      │
            │                                          ▼      ▼      ▼
            │                                   ┌─────────┐ ┌─────┐ ┌──────────┐
            │                                   │ 004-06  │ │04-07│ │ 004-08   │
            │                                   │ launcher│ │tests│ │ readme   │
            │                                   │ (I-V.6) │ │I-V.7│ │ I-V.8    │
            │                                   └────┬────┘ └──┬──┘ └─────┬────┘
            │                                        │         │           │
            │                                        ▼         ▼           ▼
            │                                  ┌────────────────────────────────┐
            │                                  │ task-004-09 architecture-verify│
            │                                  │ (I-V.9, R-54)                  │
            │                                  └────────────────┬───────────────┘
            │                                                   │
            └─────► (02 → 11 direct edge: sync script must work for Smoke 7)
                                 │
                                 ▼
                  ┌─────────────────────────────────────┐
                  │ task-004-11 regression-sweep        │
                  │ (I-V.11) — acceptance gate          │
                  │ All paths converge here:            │
                  │ 02→11 (Smoke 7 sync dry-run),       │
                  │ 09→11 (final ARCH verify),          │
                  │ 10→11 (notices file present)        │
                  └─────────────────────────────────────┘
```

**Critical path** (longest blocking chain): 01 → 03 → 04 → 05 → 07 → 11.
**Parallel-safe pairs** (after 01 lands): {02, 03, 10}; (after 05 lands): {06, 07, 08, 09}.

---

## 3. Stub-First Application (per `tdd-stub-first`)

| Bead | Code surface? | Phase-1 stub | Phase-1 test (Red→Green on stub) | Phase-2 logic |
|---|---|---|---|---|
| 004-01 | yes (package layout) | `__init__.py` + dir tree only | `from scripts.wiki_ingest.commands.ingest import execute` succeeds | rsync the actual modules |
| 004-02 | yes (bash script) | `sync_wiki_ingest.sh` prints `"NOT IMPLEMENTED"` and exits 0 | shell test asserts exit-0 + presence of `--dry-run` flag | full divergence-check + rsync + `VENDORED_FROM.md` rewrite |
| 004-03 | **yes (canonical stub-first)** | `def ingest(...) -> dict: raise NotImplementedError` + `class IngestError(Exception): ...` | `pytest -k "test_ingest_stub_raises"` asserts `NotImplementedError` raised; import succeeds | refactor `execute()` body into `ingest()`; convert `_safety.die()` → `raise IngestError` |
| 004-04 | yes (type annotations) | n/a — runs against post-stub code | n/a — direct mypy check | apply `# VENDORED-PATCH:` fixups OR `# type: ignore` + UPSTREAM-ISSUE |
| 004-05 | yes (wiki_enrich.py) | `_vendored_ingest` symbol resolved + `_VENDORED_AVAILABLE` flag; `main()` calls stub | `pytest -k "test_primary_path_calls_vendored"` mocks `_vendored_ingest` → asserts called once | branch logic + `IngestError` → exit 6 + fallback retention |
| 004-06 | yes (bash launcher) | n/a (single-line diff) | shell smoke: `bin/wiki-enrich --help` succeeds without `wiki-ingest` on PATH | direct edit |
| 004-07 | yes (test file) | new test placeholders with `pytest.skip("phase-2")` | collection-level: pytest discovers all new tests | unskip + assert real behavior |
| 004-08 | **no — docs** | n/a | n/a | direct write |
| 004-09 | **no — verify** | n/a | n/a | grep-diff check, no edits if drift = 0 |
| 004-10 | **no — docs** | n/a | n/a | direct write |
| 004-11 | no — verify | n/a | n/a | run smokes; gate the task |

---

## 4. Use Case Coverage

| Use Case | Description | Beads |
|---|---|---|
| **UC-V1** | Operator updates vendored snapshot via sync script (R-49, R-45) | task-004-01, task-004-02 |
| **UC-V2** | End-user installs via single command, no external wiki-ingest required (R-45, R-46, R-47, R-52, R-53) | task-004-01, task-004-03, task-004-05, task-004-06, task-004-08 |

---

## 5. RTM Coverage Matrix

| RTM ID | Requirement | Bead(s) | Phase |
|---|---|---|---|
| R-45 | Vendor copy package + `VENDORED_FROM.md` present | task-004-01 | 1 |
| R-46 | Programmatic `ingest()` + `IngestError` | task-004-03 | 2 |
| R-47 | `wiki_enrich.py` primary in-process path | task-004-05 | 3 |
| R-48 | `wiki_enrich.py` subprocess fallback retained | task-004-05 | 3 |
| R-49 | `sync_wiki_ingest.sh` snapshot script | task-004-02 | 1 |
| R-50 | `mypy --strict scripts/wiki_ingest/` clean | task-004-04, task-004-11 | 2, 4 |
| R-51 | Tests: vendored path + fallback coverage | task-004-07, task-004-11 | 4 |
| R-52 | `bin/wiki-enrich` launcher no longer requires PATH | task-004-06 | 3 |
| R-53 | README install simplified | task-004-08 | 4 |
| R-54 | ARCHITECTURE.md §1.5.2 updated (verification only — already committed in `3b57d81`) | task-004-09 | 4 |
| R-55 | `THIRD_PARTY_NOTICES.md` + LICENSE-upstream | task-004-10 | 1 |
| R-56 | TASK 003 surface preserved (`--source` `required=True`, no mutual-exclusion) | task-004-05 (no-touch invariant), task-004-11 (regression) | 3, 4 |
| R-57 | Standalone `wiki-ingest` CLI behavior unchanged + vendored CLI surface preserved (Smoke 4) | task-004-03 (`execute()` wraps `ingest()`), task-004-11 (Smoke 4) | 2, 4 |

**1-1 issue mapping** (no orphans): R-45→I-V.1, R-46→I-V.3, R-47/R-48→I-V.5, R-49→I-V.2, R-50→I-V.4, R-51→I-V.7, R-52→I-V.6, R-53→I-V.8, R-54→I-V.9, R-55→I-V.10, R-56/R-57→I-V.11 (regression + Smoke 4).

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-1** | **`mypy --strict` time-box overrun** — upstream wiki-ingest type debt forces > 2 h of fixups in the vendored copy | Medium | Medium (delays Phase 2) | Time-box per Decision-14 + task-reviewer nit: at 2 h elapsed, **stop deep-fixing**; insert `# type: ignore[<error>]` + `# UPSTREAM-ISSUE: <link>` comments; file an issue on Universal-skills/wiki-ingest. Document local patches in `VENDORED_FROM.md::local_patches`. Acceptance bullet on task-004-04 explicitly allows this fallback. |
| **R-2** | **Divergence-check edge cases in sync script** — SHA256 hash comparison mis-identifies a no-op rsync as divergent (e.g., trailing-newline differences, encoding) | Medium | Medium (blocks UC-V1 routine) | Normalize file bytes for hashing (read mode `"rb"` only; no `decode()`); include explicit unit test for "identical content via different sync runs produces identical hashes"; `--accept-local-divergence` escape hatch in script per TASK.md R-49(b). |
| **R-3** | **Fallback-path test flakiness** — `WIKI_ENRICH_NO_VENDORED=1` + `shutil.which("wiki-ingest")` test cases are sensitive to PATH state in CI; can pass locally / fail in CI or vice versa | Medium | High (would fail Smoke 2/3) | Tests use `monkeypatch.setenv` for env var and `unittest.mock.patch("scripts.wiki_skills.wiki_enrich.shutil.which")` for PATH probe — **never** rely on the real CI environment's PATH. Documented in task-004-07 Test Plan. |
| **R-4** | **TASK 003 surface accidentally broken** — refactor of `wiki_enrich.py` touches the `--source required=True` argparse declaration or `WikiIngestError` class (R-56 invariants) | Low | High (blocks TASK 003 resume) | Acceptance bullet on task-004-05 + task-004-11 explicitly greps for `required=True` on the `--source` flag and asserts `class WikiIngestError(Exception)` survives. Regression sweep runs full 295+ pytest before gate. |

---

## 7. Definition of Done (acceptance gate — task-004-11)

The task is "Done" iff **all** of the following hold:

- [ ] All 11 beads (task-004-01..task-004-11) marked complete with green acceptance bullets.
- [ ] `pytest tests/ -q` → **298+ passed, 0 failed** (baseline 295 + ≥3 new test cases from I-V.7).
- [ ] `mypy --strict scripts/` (full tree) → **Success: no issues found**.
- [ ] Smoke 1 (in-process path WITHOUT `wiki-ingest` on PATH) → exit 0, output JSON has `action: enriched`.
- [ ] Smoke 2 (subprocess fallback via `WIKI_ENRICH_NO_VENDORED=1`) → exit 0, output JSON has `action ∈ {enriched, partial}`.
- [ ] Smoke 3 (ImportError on vendored AND `wiki-ingest` absent) → exit 6, error envelope = `WIKI_INGEST_UNAVAILABLE`.
- [ ] Smoke 4 (`python -m scripts.wiki_ingest.commands.ingest --source X --vault Y --output-format json`) → exit 0, manifest has `status: ok` (proves `execute()` wrapper around `ingest()` did not regress CLI surface).
- [ ] Smoke 5 (`mypy --strict scripts/wiki_ingest/` + `mypy --strict scripts/wiki_skills/wiki_enrich.py`) → both clean.
- [ ] Smoke 6 (`pytest tests/ -q`) → 298+ green.
- [ ] Smoke 7 (`bash scripts/sync_wiki_ingest.sh --dry-run`) → prints would-be-synced list, no mutations + `VENDORED_FROM.md` fields `source_commit`, `synced_at`, `source_path`, `file_hashes` all present.
- [ ] `Universal-skills/skills/wiki-ingest/` directory untouched (`git status` in that repo = clean).
- [ ] `wiki_enrich.py::--source` flag still `required=True` (R-56 invariant).

---

## 8. Effort Summary

| Metric | Value |
|---|---|
| Beads count | 11 |
| Total working-time estimate (single-developer, sequential) | ~6.0 days |
| Critical-path estimate (with parallelization where DAG permits) | ~4.25 days |
| Acceptance-gate effort (task-004-11 alone) | 0.5 day |

---

## 9. Open Issues / Planner Judgement Calls

1. **I-V.9 (ARCHITECTURE.md update) demoted to "verify-only"** — operator briefing explicitly says the architect already shipped §1.5.2 + §1.5.7 + §7.4 changes in commit `3b57d81`. Task-004-09 accepts on a clean grep diff; only writes if drift is detected. This avoids redundant work.
2. **I-V.4 (mypy) ordering choice** — placed after I-V.3 (not parallel) because the new `ingest()` signature is the largest type-annotation surface and benefits from being typed in-flight rather than retro-fitted.
3. **I-V.2 (sync script) bootstrap chicken-and-egg** — task-004-01 runs `rsync` manually (or `cp -R`) for the initial copy because `sync_wiki_ingest.sh` doesn't exist yet. Task-004-02 then formalizes the sync pipeline.
4. **Stub-first relaxation on docs-only beads (I-V.8, I-V.10)** — no code surface = no stub phase. Plan explicitly notes "direct write" in §3.

---

## 10. Start Signal

Plan-reviewer gate next. After sign-off, start with **task-004-01** (vendor-bootstrap). Phase 1 beads {02, 10} may begin in parallel once 01 lands.
