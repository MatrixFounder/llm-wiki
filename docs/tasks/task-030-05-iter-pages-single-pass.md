# 030-05 — `iter_pages` single-pass rewrite (R-030-3/6, wired; closes R-X1-OBS-WALK)

**RTM:** R-030-3 + R-030-6. **UC:** UC-30-3. **Depends:** 030-00 (pins), 030-04.
**Mode:** `tdd-strict` (engine rewrite — TASK-019 precedent).

## Goal
Swap the per-glob `Path.glob` loop for ONE **iterative explicit-stack**
`os.scandir` walk threading the 030-04 per-pattern alive-sets, with first-match
attribution among ALIVE patterns and the P-2 single-stat via `DirEntry.stat()`.

## RED first
1. **Traversal-count tests (AC-3.3, RED on the current engine):** monkeypatched
   scandir counter — (i) obsidian-personal fixture: every directory scandir'd
   EXACTLY once (current: root 4×, `NN - Area/` 2×); (ii) fat-karpathy fixture:
   `.obsidian/`, `.git/`, `attachments/` scandir'd ZERO times (§3.5 "root
   subtrees never walked" by construction); (iii) `02 - Area/Sub/_raw/**`
   subtree: zero scandirs (real ignore-prune).
2. **AC-3.6:** empty vault → empty list, no error.
3. **AC-3.8 (spec-validator M-2):** ≥1500-deep nested fixture → walks without
   `RecursionError` (RED against a Python-recursive implementation).

## GREEN (the rewrite)
- **Iterative** walk (explicit stack of `(dir, alive_pattern_states)`):
  - dir entry: `is_dir(follow_symlinks=True)` + `entry.is_symlink()` gate
    (arch-review wording fix); advance every alive pattern via
    `_advance_alive(state, segment, is_symlink=…)` (Q-030-2 v3 symlink rule);
    descend iff the new alive-set ≠ ∅ and not `_prunable_ignore`.
  - file entry: suffix check → SYSTEM_FILES → autoindex/ignore string filters
    (ORDER per F-9) → **first-match attribution among patterns ALIVE at the
    containing dir** (declared order; prevents match-set inflation + attribution
    flips on overlap+symlink layouts — AC-3.5 iv/v) → `entry.stat()` (one stat;
    `S_ISREG`; `OSError → continue`) → `DiscoveredPage(..., mtime=st.st_mtime)`.
- Sort output by rel-POSIX path (unchanged); `seen`-set no longer needed (each
  file visited once; alive-set first-match replaces it) — keep an equivalent
  guard comment.
- NO new `resolve_layout_config` calls (R-X1-CFG-COST guard).

## Acceptance
- ✅ AC-3.3 i/ii/iii + AC-3.8 flip RED→GREEN; AC-3.1/AC-3.5(i..v) pins from
  030-00 stay green.
- ✅ AC-3.2: ALL existing suites green UNMODIFIED — engine
  (`test_discover_pages_engine`), karpathy golden (set+order), layouts e2e,
  slug-strategy, default-tags, upsert↔reindex parity, security (symlink escape),
  task017 single-stat detector. Any test edit = stop + re-review.
- ✅ Case-sensitivity delta (UC-30-3 A4) pinned by ONE new test (literal-case
  mismatch glob: documented consistent miss) + Q-024-residual-2 note queued for
  030-07.
- ✅ AC-3.7 (diff-review item): `scripts/wiki_skills/wiki_sync.py` walk untouched
  by this bead's diff.
- ✅ mypy strict; Sarcasmotron pass (engine bead = extra scrutiny).
