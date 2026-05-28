# Task 003-v3-14: update `docs/ROADMAP.md` + `docs/KNOWN_ISSUES.md` (housekeeping)

## Meta

- **Bead ID**: `task-003-v3-14-roadmap-known-issues-update`
- **Slug**: `roadmap-known-issues-update`
- **Maps to**: Issue **I-V3.9**; RTM rows **R-30**, **R-42**; housekeeping.
- **Depends on**: task-003-v3-06 (code shipped — basis for ROADMAP "Done" entry).
- **Estimated time**: 0.25 day
- **Priority**: Low.

## Use Case Connection

- Housekeeping. Keeps `ROADMAP.md` Done section + `KNOWN_ISSUES.md` deferred items aligned with what actually shipped.

## Task Goal

### `docs/ROADMAP.md`

Append (or amend) the R-3 entry under "Done" with the v3.1 ship state:

```markdown
- **R-3 wiki-extract-concepts v3.1** (2026-05-NN) — Deterministic refactor per Decision-17 + post-vdd-multi + Option A green-throughout hardening. **19 beads shipped** (Phase -1: 11a; Phase 0: 00; Phase 1: 01-06; Phase 2: 07-10; Phase 3: 11-12; Phase 4: 13-17). Pytest ≥ 436 passed; mypy --strict clean. **BREAKING CHANGE**: operator-facing CLI surface split into `prepare` + `apply` subcommands; legacy invocation errors out with helpful pointer.
```

### `docs/KNOWN_ISSUES.md`

1. **Mark L-V3.3 obsolete**: the v2 CWE-209 exception-chain SDK-leak entry. Reason: the LLM call site has been deleted; `LLMUnavailableError` no longer exists; exception-chain question is moot. Add: `STATUS: obsolete (v3.1, 2026-05-NN)`.
2. **Add P-6** (perf SEV-2): "known_concepts payload O(N) per `prepare` invocation. At ~100 entities scale (trade-agents) ~5 KB; at 10k entities ~500 KB. Deferred mitigation: `--known-concepts-format=slugs-only` (compact payload) — adds operator-side resolution against the SKILL.md prompt."
3. **Add P-7** (perf SEV-2): "No batch surface for N-source-page workflows. Each source page requires a separate `prepare` + orchestrator-synth + `apply` round-trip. Deferred mitigation: `prepare --batch <slugs.json>` + `apply --batch-candidates <combined.json>` — adds significant complexity to schema validation + manifest aggregation."
4. **Add P-8** (perf SEV-3): "WAL PRAGMA setup cost is doubled by two-process `prepare`+`apply` workflow vs v2's single process. Each subprocess opens a fresh sqlite connection + runs the WAL/journal/synchronous PRAGMAs. ~10ms overhead per invocation. Deferred mitigation: PRAGMA caching via connection pool — out of scope for v3.1."
5. **Add P-9** (perf SEV-3): "`missing_concept_files` O(N) stat sweep in `prepare`. At ~100 entities scale ~10ms; at 10k entities approaches 1000ms. Documented in TASK Q16. Deferred mitigation: `--check-drift` flag (lazy) OR SQL-JOIN against materialized manifest table."
6. **Add nit row (Q17 / iteration-2 security NEW-3)**: "`SOURCE_NOT_FOUND` vs `INVALID_SOURCE_PATH` envelope differentiation is an information-disclosure oracle. Practical impact tiny (slugs are operator-known; vault structure is operator-trusted). Defer collapse to single envelope as future hardening if multi-tenant scenarios emerge. Operator-trust scope, not blocking."

## Stub-First Plan

n/a (documentation edits only).

## Changes Description

### Edited files

- `docs/ROADMAP.md`: append v3.1 R-3 entry.
- `docs/KNOWN_ISSUES.md`: mark L-V3.3 obsolete; add P-6/P-7/P-8/P-9 + Q17 nit row.

## Files Touched

- `docs/ROADMAP.md`
- `docs/KNOWN_ISSUES.md`

## Acceptance Criteria

- [ ] ROADMAP has v3.1 R-3 entry under "Done" with BREAKING CHANGE call-out.
- [ ] KNOWN_ISSUES has L-V3.3 marked obsolete.
- [ ] KNOWN_ISSUES has P-6, P-7, P-8, P-9 entries with SEV markers.
- [ ] KNOWN_ISSUES has Q17 nit row.

## Verification

```bash
grep "v3.1" docs/ROADMAP.md | head -3
# expect: at least one line mentioning v3.1 under "Done"

grep "BREAKING CHANGE" docs/ROADMAP.md | head -3
# expect: at least one line

grep -E "L-V3.3|P-6|P-7|P-8|P-9" docs/KNOWN_ISSUES.md | head -10
# expect: at least one match each for L-V3.3, P-6, P-7, P-8, P-9
```

## Rollback

`git checkout HEAD~1 docs/ROADMAP.md docs/KNOWN_ISSUES.md`.

## Notes

- The exact P-NN numbering depends on what already exists in KNOWN_ISSUES.md — bead executor checks the current file and assigns the next sequential numbers. TASK §1.2 catalogues these as P-6..P-9 but the actual file may have different sequence (e.g., perf SEV-1 set flagged 2026-05-26). Use the next available numbers, not necessarily literally 6/7/8/9.
