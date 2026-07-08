---
id: DF-10
type: known-issue
status: fixed
opened_at: 2026-07-08
resolved_at: 2026-07-08
resolved_by: TASK 053 (R5)
category: hygiene
severity: SEV-3
slug: df-10-prepare-mints-duplicate-raw-capture-for-in-vault-source
---

# `wiki-import prepare` mints a duplicate `_raw/<slug>.md` when the `--source` is a file already inside the vault

> **Resolution (TASK 053 / R5, fixed 2026-07-08).** `prepare` now **adopts in
> place** a clean markdown source (`.md`/`.markdown`) that already lives under a
> `_raw/` dir inside the vault (`raw_path = src_real` instead of minting
> `_raw/<slug>.md`). The existing symlink guards + the TASK 051 `is_unchanged`
> short-circuit make this a no-op (byte-identical → `action: unchanged`) or an
> in-place `source:` stamp (SAME path → no dup). A URL / out-of-vault / symlinked
> source naturally fails the guards and falls through to the normal mint.
> Regressions: `tests/test_import_article_prepare.py::
> test_prepare_adopts_in_place_md_already_in_raw` and `::test_prepare_does_not_adopt_txt_in_raw`.

- **Symptom** (dogfood, live personal vault): the user manually copied a transcript
  into a synced zone's `_raw/` and ran `wiki-sync`; the pipeline wrote a SECOND file
  (`_raw/<derived-slug>.md`) beside the original. Because the derived slug rarely
  equals the on-disk stem (any `.txt`/`.vtt`/office source, or a `.md` whose name has
  spaces/caps/dates), the capture landed at a distinct path → a visible "duplicate
  transcript" the user did not expect.
- **Root cause**: `prepare` computed `raw_path = raw_dir / f"{slug}.md"` and wrote it
  unconditionally, with no awareness that `--source` may itself be a local file already
  inside the vault. The TASK 051 `is_unchanged` guard compares the DERIVED `raw_path`
  hash against the fresh bytes; on the first run that path does not yet exist, so the
  guard was skipped and a fresh file minted. The re-ingest LOOP was mitigated at the
  workflow layer (dual commit-marker) but the physical dup file was not.
- **Residual (deliberately deferred to a follow-up, not this task)**: for a
  `.txt`/`.vtt`/office original dropped in a TOPIC folder, the converted `_raw/<slug>.md`
  is a genuinely better artifact (converted + relocated), so adopt-in-place does NOT
  apply there — the leftover is the INBOX ORIGINAL. Consuming/quarantining that original
  after a successful import (e.g. an opt-in `wiki-sync --consume-source` that moves it
  under `_raw/`, never deletes) is a more opinionated increment; for now the recommended
  flow — call `/wiki-import <file>` (a single capture) rather than manually dropping a
  raw then running sync — is documented in `workflows/wiki-sync.md` and the
  `wiki-import` skill. Moving user files safely needs after-apply-success threading, so
  it is tracked separately rather than shipped as a risky file-mover here.
- **Related**: [[df-7-resummarize-gate-trusts-source-state-without-disk-check]] and
  [[df-8-stale-entity-rows-block-concept-page-recreation]] share the "reconcile the
  pipeline with on-disk reality" family, but this is a distinct root cause (an
  unconditional capture WRITE, not a stale-marker READ);
  [[task-044-x-status-slug-instability]] is the sibling "nondeterministic slug → duplicate
  `_raw`" for x.com imports.
