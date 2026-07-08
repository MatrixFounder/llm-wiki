---
id: DF-7
type: known-issue
status: fixed
opened_at: 2026-07-08
resolved_at: 2026-07-08
resolved_by: TASK 053 (R2)
category: class-b-integrity
severity: SEV-2
slug: df-7-resummarize-gate-trusts-source-state-without-disk-check
---

# `wiki-sync`'s resummarize gate (`source_state`/`provenance_ref`/`mirror`) never checks that the output it claims exists is still on disk

> **Resolution (TASK 053 / R2, fixed 2026-07-08).** `wiki-sync record` gained an
> optional `--note-path` that stores the produced note's vault-rel path as a
> SECOND `source_state` row (`key='note_path'` — zero-DDL, `user_version` stays
> 7). The D1 `source_state` detector (the shipped default) now reads that row and,
> if the note is gone on disk, WARNs and falls through so the gate re-summarises
> instead of skipping forever. A legacy marker with no `note_path` row keeps
> today's skip (backward compatible). Failure direction is safe (a false "stale"
> only re-summarises, never drops content). **Verified wrong in the DF:** D2b
> `mirror` ALREADY stat-checks (`is_file()`/`rglob`) and self-heals — only D1 and
> D2a were DB-only. **Residual (scoped follow-up, not this task):** the D2a
> `provenance_ref` per-match existence fallback — D2a is off-by-default, so the
> shipped-default vulnerability is fully closed by the D1 fix. Regression:
> `tests/test_wiki_sync_resummarize.py::test_d1_note_path_missing_target_resummarises`
> (+ present/legacy siblings) and `tests/test_wiki_sync.py::test_record_note_path_records_second_row`.
> Workflow threading of `--note-path` documented in `workflows/wiki-sync.md`.

- **Symptom**: a raw transcript had previously been summarized — `wiki-sync` had recorded a
  `source_state` commit-marker and `wiki-import apply` had (at the time) written a summary
  note + 12 concept pages. Later, the summary note and all 12 concept pages were removed
  from disk (outside this tool's control — e.g. an interrupted prior run, or manual
  deletion), but the `pages`/`entities` rows and the `source_state` marker were never
  cleaned up. A subsequent `wiki-sync scan <zone>` reported `skip:
  summary-exists:source_state` — i.e. "nothing to do, already summarized" — even though
  **none of the claimed output existed**. Only a manual, separately-invoked `wiki-lint`
  surfaced the truth (13 `missing-on-disk` rows). Nothing in the `wiki-sync`/`wiki-import`
  path itself would ever have caught this; an operator (or an agent following the
  `wiki-sync` workflow literally) would see a clean `skip` and conclude the content is safe,
  when it has silently evaporated.
- **Root cause**: all three `resummarize` detectors (`source_state` — TASK 018,
  `provenance_ref` — TASK 019, `mirror` — TASK 019) answer "does a record of a prior summary
  exist" purely from DB/frontmatter state. None of them additionally check "does the file
  that record points at still exist on disk". `wiki-lint`'s `missing-on-disk` check is the
  only code path that verifies this, and it is a separate, manually-invoked command that
  `wiki-sync scan` never calls or consults before deciding to skip.
- **Why this matters more than a typical Class-B drift**: most Class-B drift (stale
  `file_hash`, dangling refs) self-heals on the next `wiki-reindex --full` because reindex
  rebuilds purely from disk. This one does NOT self-heal on reindex — reindex will happily
  drop the now-orphaned `pages`/`entities` rows for the missing files (correct), but it has
  no opinion on the **raw source**, whose `source_state` row (Class-C, deliberately spared
  by `--full` — see `reindex_full`'s comment "a Class-B rebuild must not destroy Class-C
  state") survives untouched. So even a full reindex leaves `wiki-sync scan` reporting
  `skip` forever for a raw whose entire output has vanished — there is no built-in recovery
  path short of an operator noticing via `wiki-lint` and manually re-running with `--force`.
- **Affected components**: `scripts/wiki_skills/_resummarize.py` (`apply_policy` and its
  three detectors), `scripts/wiki_skills/wiki_sync.py` (`scan`).
- **Fix options** (not mutually exclusive):
  1. Cheapest: have the `source_state`/`provenance_ref`/`mirror` detectors additionally
     `Path.exists()`-check the summary file (`provenance_ref`) or a representative filed
     page (`source_state` doesn't currently carry a target path, only a hash — would need to
     also record the note's file_path at write time) before returning "summary exists"; on a
     miss, degrade to the same `ingest`/`convert+ingest` decision as if no marker were found,
     surfaced as a NEW skip-reason-turned-action e.g. `reason: "stale-marker-target-missing"`
     so the operator sees WHY it re-ran, not just that it re-ran.
  2. Have `wiki-sync scan` optionally cross-reference `wiki-lint`'s `missing-on-disk` set (or
     run an equivalent lightweight existence check) for entries it's about to `skip`, and
     downgrade a `skip` to `ingest` + a loud warning when the previously-filed target is
     gone.
  3. At minimum, document the gap: `workflows/wiki-sync.md` currently gives no guidance for
     "the scan says skip but I suspect the output is gone" — add a troubleshooting note
     recommending `wiki-lint` before trusting a `skip` after any manual file deletion in a
     synced zone, and a documented `--force` remediation path (there is currently no
     dedicated "forget this source" command — `--force` at the `wiki-sync scan` layer
     happens to work because it bypasses the resummarize gate outright, but this is not
     called out anywhere as the intended recovery procedure for stale-marker-missing-target).
- **Related**: [[df-6-source-state-scope-unicode-normalization-mismatch]] (a different way
  the same `source_state` table produces a wrong trust decision);
  [[df-8-stale-entity-rows-block-concept-page-recreation]] (the same "trust a DB row without
  checking the file it names still exists" pattern, one layer down at the concept-entity
  level).
