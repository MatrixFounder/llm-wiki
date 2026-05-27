# Task 004-09: ARCHITECTURE.md verification (architect already shipped — confirm no drift) [VERIFY — no stub]

## Meta

- **Bead ID**: `task-004-09-architecture-verify`
- **Slug**: `architecture-verify`
- **Maps to**: Issue **I-V.9**; RTM rows **R-54**
- **Depends on**: `task-004-05-wiki-enrich-refactor`, `task-004-07-test-suite-update` (so verifier has the actual shipped semantics in hand)
- **Estimated time**: 0.25 day
- **Priority**: Low

## Use Case Connection

- **Cross-cutting** (documentation quality gate): keep architecture description in sync with code.

## Task Goal

**Per operator briefing**, the architect already updated `docs/ARCHITECTURE.md` in commit `3b57d81` (sections §1.5.2 PRIMARY + FALLBACK paths, §1.5.7 vendored module anatomy, §7.4 vendoring policy). This bead is a **verification pass**: compare the shipped semantics (from I-V.3, I-V.5, I-V.7) against the architecture document and confirm no further updates are needed. If drift is detected, write minimal corrections.

**This is NOT a from-scratch documentation pass.** Acceptance is "verified no further updates needed" rather than "wrote a new section".

## Stub-First Plan

**No stub phase** — verification work. Per `tdd-stub-first` skill, no code surface = no stub.

**Approach**:
1. `Read` ARCHITECTURE.md §1.5.2 (the path-decision branch + PRIMARY/FALLBACK diagrams).
2. Cross-check each diagram step against the actual `scripts/wiki_skills/wiki_enrich.py` (post-I-V.5) and `scripts/wiki_ingest/commands/ingest.py` (post-I-V.3):
   - PRIMARY step 1: lazy import + `_VENDORED_AVAILABLE` flag — confirm matches the code.
   - PRIMARY step 2: `_vendored_ingest(...)` signature — confirm matches `ingest()` signature.
   - FALLBACK trigger: `WIKI_ENRICH_NO_VENDORED=1` + `shutil.which("wiki-ingest")` — confirm decision branch matches.
   - Error envelope: `WIKI_INGEST_UNAVAILABLE` (no vendored + no PATH) and `WIKI_INGEST_FAILED` (vendored raised IngestError) — confirm exit codes (both 6) match.
3. `Read` §1.5.7 — confirm the vendored module directory layout matches the actual `scripts/wiki_ingest/` post-I-V.1 + I-V.3 + I-V.4.
4. `Read` §7.4 — confirm vendoring policy (drift detection mechanism, `local_patches`, sync script flags) matches I-V.2's actual implementation.
5. If any drift is detected: write minimal corrections (single-line edits). Do NOT restructure or rewrite — just patch the drift.
6. If no drift: this bead lands as a documentation-only commit noting "verified ARCHITECTURE.md §1.5.2 + §1.5.7 + §7.4 against shipped code; no changes required" (or simply mark this bead as complete with zero diff).

## Changes Description

### New Files

- None.

### Changes in Existing Files

#### File: `docs/ARCHITECTURE.md`

- **Expected**: zero or minimal edits (drift patches only).
- If §1.5.2 PRIMARY step 2 references a function signature that drifted between architect's commit `3b57d81` and I-V.3's final impl → update the signature reference.
- If §1.5.7 directory listing missed a file from the actual `scripts/wiki_ingest/` tree → add the missing entry.
- If §7.4 references a sync script flag that was renamed during I-V.2 → update the flag name.

### Component Integration

- No new components introduced.
- This bead's output is the "ARCHITECTURE.md matches code" invariant required by every project that lives by ADR-driven architecture (this repo is one of them).

## Files Touched (explicit list)

- `docs/ARCHITECTURE.md` (modified — minimal drift patches OR no edits at all)

## Test Surface

- **No automated tests**.
- **Manual verification checklist** (verified during the bead):
  - [ ] `grep -n "PRIMARY PATH\|FALLBACK PATH\|WIKI_ENRICH_NO_VENDORED" docs/ARCHITECTURE.md` returns expected hits.
  - [ ] §1.5.2 decision-branch pseudocode matches `scripts/wiki_skills/wiki_enrich.py::main()`.
  - [ ] §1.5.7 file list matches `ls scripts/wiki_ingest/` (sans `__pycache__`).
  - [ ] §7.4 sync script flag names match `scripts/sync_wiki_ingest.sh --help` output.

## Acceptance

- [ ] R-54(a): §1.5.2 cross-process diagram is replaced/supplemented with an in-process flow diagram showing the vendored import path — **verified present** in current `docs/ARCHITECTURE.md` from commit `3b57d81`.
- [ ] R-54(b): Subprocess path is shown as "fallback (disabled by default when vendored module present)" — verified present.
- [ ] R-54(c): §1.5.3 note "external `wiki-ingest` binary: no longer required for standard operation; vendored copy at `scripts/wiki_ingest/` is primary" — verified present.
- [ ] No drift between ARCHITECTURE.md and the shipped code at the time of this bead's completion. If drift was found, it has been patched.
- [ ] A short note added to this bead file (or to the git commit message) confirming the verification result: either "zero drift, no edits" or "patched <N> drift points: <list>".

## Rollback

`git checkout docs/ARCHITECTURE.md`. If no edits were made, this is a no-op. If drift patches were applied, rollback returns the doc to its commit-`3b57d81` state.

## Notes

- **This bead is intentionally light.** The architect already did the heavy lifting in commit `3b57d81`. The risk being mitigated is "shipped code drifted from architecture during the implementation beads" — common when I-V.3 / I-V.5 surface choices evolve mid-implementation.
- If significant drift is detected (e.g., the `ingest()` signature in §5.3 of TASK.md differs materially from the shipped signature), **STOP** and escalate to the architect rather than silently patching ARCHITECTURE.md — the architecture document is owned by the Architecture Phase, not the Planning Phase.
- This bead is **Low** priority and may be done in parallel with I-V.8 and I-V.11 prep.
