# TASK 053 — import/sync robustness: reconcile-with-disk, Unicode-safe keys, no junk `_raw` dupes

## 0. Meta Information
- **Task ID**: 053
- **Slug**: import-sync-disk-reconciliation
- **Type**: VDD fix bundle (correctness / class-B-integrity / security / hygiene)
- **Effort**: M (four small code fixes + one medium record-side plumbing change + docs + tests)
- **Context**: Dogfood on the live personal vault surfaced five design findings
  (`docs/issues/df-6..df-9` + a junk-file complaint). All five were independently
  re-verified line-by-line against current code by a 5-agent adversarial workflow; three
  of the DF-proposed fixes were **rejected as unsafe/misplaced** and corrected here.
- **Architecture**: no structural change. Every fix rides existing columns/flows —
  **zero-DDL, `user_version` stays 7**; the karpathy byte-identity anchor and Decision-17
  (no `import anthropic` in the LLM-shaped skills) are preserved. `docs/ARCHITECTURE.md`
  untouched; at most a one-line note in the wiki-import / wiki-sync functional sub-docs.

## Problem / Motivation (root causes — verified against source)

A common family runs through four of the five: **act on a DB/marker record without
reconciling it against on-disk reality**, plus one Unicode-key mismatch and one
containment-asymmetry.

- **DF-6 (SEV-2, idempotency break).** `source_state.scope` is compared byte-exact SQLite
  TEXT. The FS walk yields **NFD** paths (macOS/iCloud: `й` = и + ◌̆) at three read sites
  ([_sync.py:234](../scripts/wiki_skills/_sync.py#L234) → `wiki_sync.py:247`,
  `_resummarize.py:193`,`:274`); `wiki-sync record`'s path arg
  ([wiki_sync.py:363](../scripts/wiki_skills/wiki_sync.py#L363)) may be **NFC**
  (LLM/JSON/typed). No `unicodedata.normalize` on either side → an NFC-written marker never
  matches the NFD read key → the source re-summarizes on every scan. `_resummarize.py`
  already normalizes NFC but only for `provenance_ref`, not `source_state`.
- **DF-7 (SEV-2, class-B-integrity).** The resummarize gate reports
  `skip: summary-exists:source_state` even when the summary note + concept pages were
  deleted out-of-band. Verified: **D1 `source_state` (the shipped default) and D2a
  `provenance_ref` are DB-only** (no disk check); **D2b `mirror` already stat-checks and
  self-heals** (the DF's "all three" is wrong). `source_state` carries only a hash, not the
  output path, and `wiki-reindex --full` spares the Class-C marker → no self-heal.
- **DF-8 (SEV-2, correctness).** `wiki-extract-concepts apply` (and thus `wiki-import
  apply --concepts`) classifies a candidate as **"mention"** purely on `slug ∈
  known_slugs` ([_validation.py:340](../scripts/wiki_skills/wiki_extract_concepts/_validation.py#L340)),
  never checking the backing `_concepts/<slug>.md` exists. A ghost entity row (file
  deleted, not reindexed) → the page is silently **never re-created**; the envelope reads
  like a normal successful dedup. `prepare` already computes `missing_concept_files` but
  `apply` ignores it.
- **DF-9 (Low, security/consistency).** `wiki-import apply --note-file` reads any absolute
  path with no containment/symlink guard, while the sibling `wiki-extract-concepts apply
  --candidates-file` refuses one (`INVALID_CANDIDATES_PATH`). **The DF's fix (add
  containment) is unsafe** — `note.json` lives in the orchestrator scratchpad **outside**
  the vault by design (`--note-stdin` is primary); containment would break the documented
  flow and the tests wouldn't catch it.
- **JUNK (SEV-3, hygiene).** `prepare` unconditionally writes `_raw/<slug>.md`
  ([wiki_import_article/__init__.py:276](../scripts/wiki_skills/wiki_import_article/__init__.py#L276))
  with no awareness that `--source` may already be a file inside the vault. Because `slug ≠`
  the on-disk stem for `.txt/.vtt`/office/spaced-`.md`, a **second** file appears next to the
  user's original → the "duplicate `.md` in `_raw/`". The workflow's dual commit-marker
  stops the re-ingest LOOP, not the FILE.

## Requirements Traceability Matrix

| ID | Requirement | Verified fix location |
|----|-------------|----------------------|
| R1 | NFC-normalize the `source_state` scope key at the single DAL choke point (both accessors), covering all four call sites in one edit; ASCII is a no-op. | `sqlite_repository.py` `get_source_state` / `set_source_state` |
| R2 | Resummarize gate reconciles with disk: record the produced note's vault-rel path as a **separate `source_state` `key='note_path'`** row (zero-DDL); D1 stat-checks it and, on a miss, degrades to re-summarize + WARN + `reason=stale-marker-target-missing`; D2a provenance adds a cheap per-match file existence fallback; D2b mirror unchanged. | `_resummarize.py` (D1/D2a), `wiki_sync.py` `record` (+ `--note-path`), `workflows/wiki-sync.md` |
| R3 | Concept `apply` self-heals ghost rows: intersect `known_slugs` with the on-disk `_concepts/*.md` present-set (via `_all_concepts_dirs`), so a slug whose file is missing flips `mention → create`; ghost re-creations surface in the manifest `created` list. Must NOT rebind the batch-shared `known_slugs`; scan once in `_batch_apply`. | `wiki_extract_concepts/__init__.py` `_apply_write` / `_batch_apply` |
| R4 | Document `--note-file`'s outside-vault acceptance as deliberate (argparse help + code comment; symmetric note by `--candidates-file`); optionally add non-containment read-hardening (regular-file + `O_NOFOLLOW`). | `wiki_import_article/__init__.py` note-file branch + help; `_sourcing.py` note |
| R5 | Eliminate the junk `_raw` dupe: `prepare` adopts a clean `.md`/`.markdown` source already under `_raw/` **in place** (`raw_path = src_real`, byte-safe with the symlink guards + `is_unchanged`) instead of minting a copy. For a `.txt/.vtt`/office inbox original (NOT adopted — it needs conversion), document the recommended `/wiki-import <file>` single-capture flow + manual quarantine in `workflows/wiki-sync.md`. **Deferred (see Out of scope):** the opt-in `wiki-sync --consume-source` code flag (moving user files needs after-apply-success threading). | `wiki_import_article/__init__.py` `prepare` (~:276); `workflows/wiki-sync.md`, `skills/wiki-import` |
| R6 | Regression tests for every fix: DF-6 NFD-write↔NFC-read hit + end-to-end record→scan `is_unchanged`; DF-7 present-marker-absent-target → re-summarize + WARN; DF-8 seed entity-without-file → `create`; DF-9 `--note-file` outside vault still succeeds (guard against future accidental containment); JUNK drop `_raw/x.md` / `_raw/x.vtt` → no second `_raw/*.md`. | `tests/` |
| R7 | Close the loop in docs: mark `docs/issues/df-6..df-9` resolved-with-fix, regenerate the `KNOWN_ISSUES` Class-B ledger (`wiki-index-render --auto-indexes`), and add the "never re-type a non-ASCII path; a `skip` is only as trustworthy as a prior `wiki-lint`" caveats to `workflows/wiki-sync.md`. | `docs/issues/*`, `docs/KNOWN_ISSUES.md`, `workflows/wiki-sync.md` |

## Acceptance Criteria
- **AC-1 (R1):** `set_source_state` with an NFD-`й` scope and `get_source_state` with the
  NFC-`й` equivalent (and the reverse) resolve to the same row; a full
  `record(NFC-path)` → `scan` cycle yields `is_unchanged: true` / `skip:
  summary-exists:source_state` for an unchanged Cyrillic-named source. ASCII scopes behave
  identically to before.
- **AC-2 (R2):** with the summary note deleted but the marker present (recorded with
  `--note-path`), the D1 detector degrades — `summary_exists` returns `None` so the gate
  re-summarises (`ingest`/`convert+ingest`, not `skip`) and emits a WARN naming the missing
  note (consistent with the existing mirror dead-detector WARN; no distinct `reason` string —
  the action correctly reverts to its natural ingest reason). A legacy marker with no
  `note_path` row keeps skipping (backward compatible). `mirror`-mode is unchanged; no schema
  change (`user_version` == 7).
- **AC-3 (R3):** re-running `apply --concepts` for a source whose concept row exists but
  whose `_concepts/<slug>.md` was deleted re-creates the page (`create`, appears in
  `written`); the normal dedup case (file present) still classifies `mention` and does not
  double-write.
- **AC-4 (R4):** `wiki-import apply --note-file <path-outside-vault-root>` still succeeds;
  the divergence from `--candidates-file` is documented at both sites.
- **AC-5 (R5):** dropping `_raw/My Notes.md` (clean `.md`) and re-running import produces
  **no** second `_raw/*.md` (adopted in place → `action: unchanged`); a `.txt/.vtt` under
  `_raw/` is NOT adopted (a distinct `_raw/<slug>.md` is minted, original untouched); a plain
  URL/topic import still writes `_raw/<slug>.md` unchanged (byte-identity fixtures green). The
  inbox-original consume behaviour is documented recommended-flow guidance, not a shipped flag
  (see Out of scope).
- **AC-6:** `pytest tests/` green; `mypy --strict scripts/` clean; `wiki-reindex --full`
  rebuildability unaffected.

## Out of scope (deferred residuals — recorded, not shipped here)
- The broader "audit every path/slug-keyed lookup for NFC/NFD" hedge from DF-6 §Blast
  radius (`pages.file_path`/`entities.slug` are **not** confirmed live bugs) — separate
  follow-up if ever warranted.
- **DF-7 D2a provenance existence-fallback**: `provenance_ref` is off-by-default, so the
  shipped-default vulnerability is fully closed by the D1 fix; a per-match
  `find_pages_citing_source → file_path → exists()` check is a minor hardening best done
  when someone actually enables provenance. Cross-referencing `wiki-lint`'s
  `missing-on-disk` set from `wiki-sync scan` (DF-7 fix option 2) — rejected; does not cover
  the default source_state case.
- **DF-10 inbox-consume (`wiki-sync --consume-source`)**: R5 ships the safe prepare-side
  adopt-in-place for a clean `.md` under `_raw/`; consuming/relocating a `.txt`/`.vtt` inbox
  ORIGINAL after a successful import needs after-apply-success threading + moves user files,
  so it is documented as recommended-flow guidance (`workflows/wiki-sync.md`) and tracked as
  a separate opinionated increment rather than shipped as a risky file-mover.
- Relaxing `--candidates-file`'s containment to match `--note-file` (DF-9 option c) — that
  weakens the more-hardened CLI; keep the asymmetry, document it.

## Risks / invariants to preserve
- **Zero-DDL / `user_version` 7:** `note_path` is a second row in the generic
  `source_state` KV table — legal data, not a column. Do **not** pack it into the
  `source_hash` value (would break the `if-changed` hash compare at `_resummarize.py:274`).
- **Failure direction is safe:** a false "stale" degrades to re-summarize (extra LLM work),
  never drops content; the monotone gate only loosens back to `ingest`.
- **Byte-identity anchor:** R5's adopt-in-place must change only *which* path is adopted for
  an in-`_raw` `.md`; the normal URL/topic path must emit an identical `_raw/<slug>.md`.
- **R26 symlink posture:** `resolve()`/`is_relative_to` for adopt-in-place must run with the
  existing symlink guards so we never adopt through a swapped-in symlink.
- **Decision-17:** all touched skills stay `import anthropic`-free (pure `unicodedata` /
  `Path.exists` / filing logic).
