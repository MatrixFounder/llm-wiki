# Task 019.07: [LOGIC] D2b mirror + extended regex + ReDoS guard — `skill-tdd-strict`

## Use Case Connection
- UC-2 · E2.3 · AC-3, AC-3b, AC-12

## Task Goal
Implement the filesystem mirror detector (the index-independent fallback) with both match
strategies and the extended, ReDoS-guarded regex key.

## Changes Description
#### File: `scripts/wiki_skills/_resummarize.py`
- Add `_mirror_match(path, *, vault_root, mirror: MirrorConfig) -> bool`, called from
  `summary_exists` (returns `'mirror'` on hit):
  - **anchor** = nearest ancestor of `path` whose dir-name ∈ `mirror.raw_dirs`; if none → `False`.
  - **scope** = `anchor.parent / mirror.summary_dir` (or `anchor.parent` when `summary_dir == "."`).
  - **`stem-relpath`**: check `scope / <relpath-of-path-under-anchor-with-summary_ext>` exists.
  - **`group-key`**: `rkey = compose(mirror.key.raw_regex, path.stem)`; for each summary in
    scope (`*.summary_ext`, recursive) `skey = compose(summary_regex, s.stem)`; hit iff some
    `skey == rkey != None`. `group_key` shorthand = same regex both sides; default `^(\d+)`.
  - `compose(regex, stem)` = run `key.template` over named groups; ints normalized
    (`int(g)` when numeric) so `01`==`1`.
- **ReDoS guard:** operator `raw_regex`/`summary_regex` run via
  `layout_config.guarded_search` (PyPI `regex` engine + per-file deadline `WIKI_REDOS_BUDGET_S`);
  a **load-gate** (mirror of `_redos_budget_check`) validates them at config-parse — a
  catastrophic pattern → `INVALID_SYNC_CONFIG` (value not echoed); a per-file timeout →
  treat as no-key (no mirror match) + WARN, never hang.

## Test Cases
### Unit (RED-first per `skill-tdd-strict`)
1. **TC-07-1 (group-key N:1):** `Transcripts/02-1..02-4.txt` + `Summary/02 - ….md` → all skip:mirror.
2. **TC-07-2 (negative):** `08-1.txt` with no `08 - ….md` → not skipped.
3. **TC-07-3 (stem-relpath same-dir):** `Resources/X.docx` + `Resources/X.md`, `summary_dir:"."` → skip:mirror.
4. **TC-07-4 (asymmetric regex):** raw `M01_L02_part3` (`M\d+_L(?P<lesson>\d+)`) ↔ summary `02 - …` (`^(?P<lesson>\d+)`), `template '${lesson}'` → match.
5. **TC-07-5 (date-key):** `Lessons` `^(\d{8})` matches `20260326-01.txt` ↔ `20260326_….md`.
6. **TC-07-6 (ReDoS load-gate):** a catastrophic `(a+)+$` regex → `INVALID_SYNC_CONFIG` at load.
7. **TC-07-7 (ReDoS per-file):** a gate-slipping pattern that times out → no-match + WARN, no hang.

## Acceptance Criteria
- [ ] Both strategies; extended regex; ReDoS-guarded (reuses TASK 017 infra).
- [ ] `mypy --strict` clean; regression green.

## Notes
Reuse `layout_config.guarded_search` (`:150`) + `_redos_budget_check` (`:417`) + `WIKI_REDOS_BUDGET_S`.
