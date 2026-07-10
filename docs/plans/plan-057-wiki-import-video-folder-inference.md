# PLAN — TASK 057: wiki-import video robustness (W1) · folder inference (W2) · announcement detection (W3)

Design pinned in ARCHITECTURE §2.3.5 + Q-057-1..4. Stub-First is **degenerate for the
existing-module beads** (W1/W3 edit `_fetch.py`/`__init__.py` in place — per-bead TDD: failing
test → fix → targeted run → suite); the ONE new module (`_folder.py`, W2) gets a real
stub-first scaffold bead (057-00) before its logic beads. Every RTM ID from `docs/TASK.md`
maps to exactly one checklist item. Sub-task files: `docs/tasks/task-057-XX-*.md`.

## Phase 1 — scaffold (stubs + red→green import tests)

- [ ] **057-00** `_folder.py` scaffold: typed signatures + `FolderInference` result dataclass,
  stub bodies; `tests/test_import_folder_inference.py` scaffold (import + signature tests
  green; behavior tests land per-bead). Gate: `mypy --strict scripts/` + targeted pytest.
  → `docs/tasks/task-057-00-folder-module-scaffold.md`

## Phase 2 — logic beads (atomic, ordered)

- [ ] **[W1-1]** + **[W1-2]** transcript robustness flags pass through end-to-end:
  `_fetch_transcript(concurrent_fragments=None, media_timeout_sec=None)` → argv append
  (non-None only); forwarded by `dispatch_fetch`, `_fetch_x_status_with_video`,
  `_append_embedded_videos`; prepare CLI `--transcript-concurrency` / `--transcript-media-timeout`
  (argparse positive-int type, default None). Offline argv assertions on all three call paths.
  → `docs/tasks/task-057-01-transcript-flags-passthrough.md`
- [ ] **[W1-3]** scoped wall-clock: `_transcript_timeout(primary: bool)` — env
  `WIKI_TRANSCRIPT_TIMEOUT_S` set → overrides both roles; else 3600 primary / 300 embeds
  (Q-057-2). Callers tag their role. Tests: default split, env override, invalid env.
  → `docs/tasks/task-057-02-scoped-wallclock.md`
- [ ] **[W3-1]** pure announcement heuristic `_announcement_only(md) -> str | None` +
  `_X_ANNOUNCEMENT_PROSE_FLOOR = 600` + first-party broadcast/space absolute-URL regex
  (allowlisted hosts; reuses the `_is_x_login_wall` prose normalization, extracted to a shared
  helper). Unit tests: 004-shaped fixture → URL; substantive tweet + link → None; short tweet
  no link → None. → `docs/tasks/task-057-03-announcement-heuristic.md`
- [ ] **[W3-2]** + **[W3-3]** dispatch/prepare wiring: `dispatch_fetch` runs the heuristic on
  the `ambiguous_x_status` html-ok path only when `video=False`; on match reclaims the html
  temp/attachments dir and returns the typed marker (`error.details.kind="announcement_only"` +
  `broadcast_url`); `prepare` short-circuits BEFORE `_raw` write + kind detection → emits
  `{action:"announcement_only", broadcast_url, hint}` exit 0, vault byte-identical. Regression:
  `--video` concat path untouched (existing `test_import_video.py` green unmodified); plain-tweet
  no-regression test. → `docs/tasks/task-057-04-announcement-prepare-wiring.md`
- [ ] **[W2-2]** series-stem inference logic in `_folder.py`: `series_stem(title)` (ONE trailing
  episode/index marker stripped; floor ≥ 8 chars AND ≥ 2 words else None), `folder_for_hit
  (file_path, source_subdir)` (strip ONE trailing subdir segment; empty → subdir itself;
  machinery-segment exclusion), `infer_folder(repo, vault, title, layout)` (FTS5-quoted phrase
  → `search_pages(query, vaults=[vault], limit=10)` → sibling filter title/filename-stem
  startswith → distinct-folder decision + ranked candidates). Unit tests incl. seeded-repo
  sibling → single folder; multi-folder → candidates; stem floor aborts.
  → `docs/tasks/task-057-05-series-stem-inference.md`
- [ ] **[W2-3]** active-note secondary hint `active_note_folder(vault_root)`:
  `shutil.which("obsidian-active-note")`, `folder --format json`, 10 s timeout, ANY non-zero
  exit / absent / outside-vault / timeout → None (never raises). Tests with a stub executable
  on PATH (success / exit 3 / outside-vault). → `docs/tasks/task-057-06-active-note-hint.md`
- [ ] **[W2-1]** + **[W2-4]** prepare no-`--folder` flow: `--folder` optional (required on
  `apply` unchanged); folder-validation gate conditional; after fetch (+W3 short-circuit):
  inference chain (series-sibling → active-note → unresolved); **no vault write on any
  no-folder outcome** (html temp reclaimed); staging to persistent out-of-vault tempfile
  `wiki-import-staged-*.md` with `_fm_safe`-stamped `source:`/title/author/date (H-6);
  envelopes `folder_proposed` (exit 0) / `FOLDER_UNRESOLVED` + `candidates` (exit 2, Q-057-1),
  both carrying `staged_path` + detected `kind`/`title`. Tests: proposal, unresolved, no-write
  assertion (vault tree snapshot), fetch-free staged re-run keeps title/date, `--folder` given
  → byte-identical legacy path. → `docs/tasks/task-057-07-prepare-no-folder-flow.md`
- [ ] **[W2-5]** + **[NF-2]** docs + contract: `templates/CLAUDE.md.tmpl` (series-sibling
  inference FIRST, active-note demoted), `skills/wiki-import/SKILL.md` (new flags, new
  actions/exit codes table row for `folder_proposed`/`FOLDER_UNRESOLVED`/`announcement_only`,
  the embed-wall-clock-clips note from ARCH MINOR-4), `workflows/wiki-import.md` (confirm/
  override loop recipe). Envelope contract additive-only — regression-tested in 057-04/07.
  → `docs/tasks/task-057-08-docs-and-envelope-contract.md`
- [ ] **[NF-1]** final gates: full `pytest tests/` green + `mypy --strict scripts/` clean;
  install-propagation check not needed (no new bin/command).
  → `docs/tasks/task-057-09-final-gates.md`

## Dependencies / order

057-00 → {057-05, 057-06} → 057-07; 057-01 → 057-02; 057-03 → 057-04; 057-04 before 057-07
(both edit `prepare` — serialize to keep diffs reviewable); 057-08 after all code beads;
057-09 last.

## Verification checkpoints

1. Per bead: targeted pytest (named in each sub-task file) green.
2. After 057-07: the W2 acceptance pair from TASK §3 (UC-2/UC-3) reproduced in tests.
3. 057-09: full suite + mypy strict (NF-1).
4. Phase 4 adversarial review (vdd-adversarial) converged per the workflow bar.
