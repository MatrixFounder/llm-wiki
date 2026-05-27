# Task 004-04: `mypy --strict scripts/wiki_ingest/` clean (with 2 h time-box) [LOGIC]

## Meta

- **Bead ID**: `task-004-04-mypy-strict-vendored`
- **Slug**: `mypy-strict-vendored`
- **Maps to**: Issue **I-V.4**; RTM rows **R-50**
- **Depends on**: `task-004-03-programmatic-ingest-api` (the new `ingest()` signature is the largest type surface; typing it in-flight is more efficient than retrofitting)
- **Estimated time**: 0.5 day (time-boxed)
- **Priority**: High

## Use Case Connection

- **Cross-cutting** (quality gate): supports the Definition of Done invariant that `mypy --strict scripts/` is clean across the entire tree.

## Task Goal

Run `mypy --strict scripts/wiki_ingest/` and resolve every reported error. For each fix, either (a) add proper type annotations to the vendored file and record a `# VENDORED-PATCH: TASK 004 / I-V.4 — <reason>` comment above the change, OR (b) if the fix is non-trivial / risky / would require deep upstream knowledge, add `# type: ignore[<error>]  # UPSTREAM-ISSUE: <link>` and file an issue on the Universal-skills/wiki-ingest tracker.

**Time-box (Decision-14 + task-reviewer nit)**: if cumulative type-fixup time exceeds **2 hours**, immediately switch from "fix locally" to "type: ignore + UPSTREAM-ISSUE" for all remaining errors. Goal: prevent the vendoring task from being held hostage by upstream typing debt.

## Stub-First Plan

This bead has no stub phase — it's a verification + edit pass against existing (already-stub-ed-by-I-V.3) code. The acceptance is binary: `mypy --strict` exits 0 or it doesn't.

**Approach** (single phase):
1. Run `mypy --strict scripts/wiki_ingest/` and capture the full error list (typically 20-50 errors on first run for upstream code that wasn't authored under strict mode).
2. **Triage**: group errors by file and by category (missing return type, untyped `Any`, missing parameter annotation, untyped decorator, etc.).
3. **Fix loop** (until 2 h elapsed):
   - Apply minimal type annotations to the vendored file. Prefer `from __future__ import annotations` if not already present so forward refs work cleanly.
   - For every modified line, add a single-line comment `# VENDORED-PATCH: TASK 004 / I-V.4 — <one-line reason>`.
   - Record each modified file in `VENDORED_FROM.md::local_patches` with: relative path, brief reason, target upstream issue (will be filed in step 4).
   - Re-run mypy after each file; commit-ready when zero errors.
4. **At 2 h elapsed (if not done)**:
   - For all remaining mypy errors, insert `# type: ignore[<error-code>]  # UPSTREAM-ISSUE: TBD (TASK 004 / I-V.4 time-box)`.
   - File a single tracking issue on Universal-skills/wiki-ingest titled "Type annotation gaps surface under mypy --strict in vendored consumers" listing each `# type: ignore` site.
   - Update the comments with the actual issue URL.
   - Re-run mypy → must exit 0.
5. Update `VENDORED_FROM.md::local_patches` with all patches (mix of real fixes and `# type: ignore` shims).

## Changes Description

### New Files

- None (all edits land in existing vendored files).

### Changes in Existing Files

#### Files in `scripts/wiki_ingest/` — touched as needed

Likely candidates (based on a typical strict-mode pass on a non-strict-authored codebase):
- `commands/ingest.py` (already partially typed by I-V.3 — finalize)
- `_safety.py`
- `_dispatch.py`
- `_frontmatter.py`
- `_markdown.py`
- `_page_merge.py`
- `commands/upsert_page.py`
- `commands/update_index.py`
- `commands/register_summary.py`
- `commands/append_log.py`
- `commands/log_event.py`

Each modification carries an inline `# VENDORED-PATCH: ...` or `# type: ignore[...]  # UPSTREAM-ISSUE: ...` comment.

#### File: `scripts/wiki_ingest/VENDORED_FROM.md`

`local_patches` block populated. Example:
```markdown
## local_patches

- **commands/ingest.py** (lines: top + `execute()` body): TASK 004 / I-V.3 — extracted programmatic `ingest()` + `IngestError` (logic refactor; not a typing fix).
- **commands/ingest.py** (lines: ~150-160): TASK 004 / I-V.4 — added explicit `dict[str, Any]` return type for `_load_known_concepts()` helper. UPSTREAM-ISSUE: <URL>
- **_safety.py** (lines: ~80): TASK 004 / I-V.4 — `# type: ignore[arg-type]` on `_safety.die()` argparse interaction. UPSTREAM-ISSUE: <URL>
- ... (one entry per modified file)
```

### Component Integration

- This bead does not alter runtime behavior — only adds annotations and `# type: ignore` shims. The Phase-2 logic from I-V.3 is preserved verbatim.
- Recorded `local_patches` block must survive the I-V.2 sync script's `VENDORED_FROM.md` rewriter (per I-V.2 implementation note).

## Files Touched (explicit list)

- `scripts/wiki_ingest/**/*.py` (incremental — only files with mypy errors)
- `scripts/wiki_ingest/VENDORED_FROM.md` (modified — populate `local_patches`)

## Test Surface

- **No new test files**. The mypy invocation **is** the test.
- **Implicit regression**: I-V.11 regression sweep includes `mypy --strict scripts/` (full tree) — this bead must leave it green.

## Acceptance

- [ ] R-50(a): `mypy --strict scripts/wiki_ingest/` exits 0 (`Success: no issues found`).
- [ ] R-50(b): Every type-annotation gap fix is documented with an inline `# VENDORED-PATCH: TASK 004 / I-V.4 — <reason>` comment.
- [ ] R-50(c): All local fixups (whether real fixes or `# type: ignore` shims) are listed in `VENDORED_FROM.md::local_patches`. The sync script (I-V.2) will warn before overwriting these.
- [ ] If `# type: ignore` was used, the corresponding upstream issue URL is referenced in both the inline comment and `VENDORED_FROM.md`.
- [ ] All 295+ previous tests still pass (no runtime regression from annotation churn).
- [ ] If time-box was hit, an entry in this bead's "Notes" section records how many fixes landed vs how many `# type: ignore` shims, plus the total elapsed time.

## Rollback

`git checkout scripts/wiki_ingest/`. The vendored copy returns to its I-V.3 state. Mypy will fail again but no runtime regression.

## Notes

- **Time-box rationale (R-1 risk mitigation)**: upstream wiki-ingest was authored before strict typing became the project standard. Driving the whole vendored tree to 100% strict-clean in a single bead would risk multi-day overrun. The 2 h budget keeps the task on its 4.25-day critical path.
- **Why time-box and not "do later"**: deferring leaves I-V.11's full-tree mypy check red and blocks acceptance. Hybrid (real fixes where cheap, `# type: ignore` where expensive) is the explicit Plan A.
- After the upstream issue is filed and (eventually) fixed, a follow-up TASK should pull the upstream fix in via sync script and remove the local `# type: ignore` shims. Tracked in `docs/KNOWN_ISSUES.md` (operator to add the entry after this bead lands).
- The `# type: ignore` site MUST always use the specific error code (`# type: ignore[arg-type]`), not the bare `# type: ignore`. Bare ignores fail `mypy --strict` lint policy.
