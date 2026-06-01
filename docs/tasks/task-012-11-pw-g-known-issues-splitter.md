# Task 012-11: PW-G — KNOWN_ISSUES splitter (one-shot) + partial-confidence report

> **`skill-tdd-strict`** (round-trip parity = no silent data loss).

## Use Case Connection
- UC-32: split `docs/KNOWN_ISSUES.md` → per-issue `docs/issues/<id>-<slug>.md` (Class A).

## Task Goal
A one-shot, fixture-driven splitter that parses THIS repo's actual `KNOWN_ISSUES.md` format
into per-issue Class-A files, emitting a partial-confidence report for anything it can't
round-trip — **flag, never silently drop** (PW-G / NFR-6).

## Grounded format (THIS repo, NOT the proposal's Universal-skills sketch)
`docs/KNOWN_ISSUES.md` uses `## [YYYY-MM-DD] <title> [STATUS: open|fixed|wontfix]` headers
with `- **Symptom** / **Root cause** / **Affected components** / **Fix plan** / **Prevention**`
fields (some entries also carry an inline `**Resolution (...)**` block, severity letters like
`L-4`/`SEV-1`, and `## ` section groupings). The splitter + fixture target THIS shape.

## Changes Description

### New Files

#### File: `scripts/migrate_known_issues_to_files.py` (NEW)
- Parse `##`/`###` issue headers → extract `id` (e.g. `L-4`, `P-1`, derived from the title
  prefix), `title`, `status` (from `[STATUS: ...]`), `opened_at` (the `[YYYY-MM-DD]`),
  `category` (best-effort from the grouping section / prefix: L→logic, P→performance, etc.),
  the `**Affected components**` list → `affected_components`, and any `related_*`/ADR links.
- Emit `docs/issues/<id>-<slug>.md` per issue: frontmatter (`id`, `type: known-issue`,
  `status`, `opened_at`, `closed_at`, `category`, `severity?`, `slug`, `affected_components`,
  `related_adrs`, `related_tasks`, `related_issues`) + the full body verbatim (no lossy reflow).
- Emit `docs/issues/.migration-report.md` listing every issue with incomplete/ambiguous
  frontmatter (no parseable id, ambiguous status, unrecognised category) — for manual review.
- `--dry-run` (default OFF writes files); `--vault-root`; reuse `atomic_write_text` +
  `validate_inside_vault` for every write.
- **No DB writes** — the splitter only produces Class-A files; indexing happens via reindex.

### New Test Fixture
#### Dir: `tests/fixtures/known_issues_migration/` (NEW)
- `input.md` — a curated 5–15-issue slice of the REAL `docs/KNOWN_ISSUES.md` covering the
  messy shapes: inline `**Resolution**` blocks, severity letters, multi-field entries,
  ADR/backlog cross-links, a `wontfix`, an `open`, a `fixed`.
- `expected_issues/` — the expected per-issue files (the round-trip contract).
- `expected_report_ids.txt` — the ids the splitter SHOULD flag as low-confidence.

### Changes in Test Files
#### File: `tests/test_known_issues_splitter.py` (NEW, tdd-strict)
- Split `input.md` → per-issue files match `expected_issues/` (frontmatter + verbatim body).
- **Round-trip parity:** split → (PW-H render, 012-09) reproduces `input.md` modulo whitespace
  + the GENERATED-AT header (the acceptance bar).
- Low-confidence issues appear in `.migration-report.md` (== `expected_report_ids.txt`),
  and are STILL emitted as files (flagged, not dropped).
- Path-guard: writes refused outside the vault root.

## Acceptance Criteria
- ✅ Fixture round-trips (split→render == original modulo whitespace + GENERATED-AT).
- ✅ Low-confidence issues flagged in the report, never silently dropped.
- ✅ `mypy --strict` clean; suite green.

## Stub-First (`skill-tdd-strict`)
Phase 1: splitter emits one file + an empty report. Phase 2: the parser + report emitter +
round-trip test (RED-first against the fixture).
