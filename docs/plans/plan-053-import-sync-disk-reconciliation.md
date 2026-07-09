# PLAN 053 — import/sync robustness: disk-reconciliation, Unicode keys, no junk `_raw` dupes

Stub-First / TDD: write the failing tests (RED) first, then the minimal implementation
(GREEN), then verify the full regression + mypy. Each item is tagged with its RTM ID.
Fixes are ordered small-and-independent first (R1, R3, R5, R4) so the tree stays green,
then the medium multi-file change (R2), then docs (R7).

## Phase 0 — Tests first (RED)

- [ ] **[R6]** `tests/test_source_state_unicode.py` — `set_source_state(scope=NFD-"й")`
  then `get_source_state(scope=NFC-"й")` (and reverse) hit the same row; ASCII scope
  unchanged. Fails today (byte-exact miss).
- [ ] **[R6]** `tests/test_wiki_sync_resummarize.py` (extend) — marker present but recorded
  `note_path` target absent on disk ⇒ action back to `ingest`/`convert+ingest` +
  `reason=stale-marker-target-missing` + WARN. Mirror-mode case stays self-healing.
- [ ] **[R6]** `tests/test_wiki_extract_concepts.py` (extend) — seed an `entities` row via
  the raw-insert helper WITHOUT writing `_concepts/<slug>.md`; full `apply` ⇒ slug in
  `create`/`written`, page created. Normal (file present) still `mention`, no double-write.
- [ ] **[R6]** `tests/test_import_article_apply.py` (extend) — `apply --note-file
  <path OUTSIDE vault_root>` still succeeds (locks in the deliberate divergence).
- [ ] **[R6]** `tests/test_import_junk_raw.py` — (a) drop `_raw/My Notes.md` (clean `.md`),
  run `prepare` ⇒ no second `_raw/*.md`, `action: unchanged` (or in-place stamp, same
  path); (b) a plain topic/URL import still writes `_raw/<slug>.md` unchanged; (c)
  `wiki-sync --consume-source` on a `.txt` inbox original relocates it under `_raw/` only
  after success.

## Phase 1 — R1 (DF-6) Unicode DAL choke point [small]

- [ ] **[R1]** `scripts/wiki_index/sqlite_repository.py`: add `import unicodedata`;
  `scope = unicodedata.normalize("NFC", scope)` as the first statement of BOTH
  `get_source_state` and `set_source_state`. No call-site edits (covers scan read,
  `record` write, and the two `_resummarize.py` D1 reads at once). GREEN for the R6 unicode
  test.

## Phase 2 — R3 (DF-8) concept self-heal [small]

- [ ] **[R3]** `scripts/wiki_skills/wiki_extract_concepts/__init__.py` `_apply_write`:
  build a present-on-disk concept-slug set from `_all_concepts_dirs(vault_root)` and pass
  `effective_known = known_slugs & present` (NEW local — do NOT rebind `known_slugs`, the
  batch path mutates it in place) to `classify_candidates`. Thread a shared
  `present_concept_files` set scanned once in `_batch_apply` to avoid an O(N·walk) per
  entry. `classify_candidates` in `_validation.py` stays a pure slug-set classifier.

## Phase 3 — R5 (JUNK) no duplicate `_raw` capture [medium]

- [ ] **[R5]** `scripts/wiki_skills/wiki_import_article/__init__.py` `prepare` (before
  `raw_path` derivation ~:276): if `--source` is not a URL, `src_real =
  Path(source).expanduser().resolve()`; if `src_real.is_relative_to(vault_root)` AND
  `"_raw" in rel.parts` AND suffix ∈ {`.md`,`.markdown`}, adopt in place
  (`raw_path = src_real`). Runs with/after the existing symlink guards; the `is_unchanged`
  block then no-ops on a byte-identical adopt. The normal URL/topic path is untouched.
- [ ] **[R5] — DEFERRED (documented, not shipped).** The opt-in `wiki-sync
  --consume-source` (move a consumed `.txt/.vtt`/office inbox original under `_raw/` after a
  successful import+marker) is deferred: safe file-moving needs after-apply-success threading
  and moves user files. Instead, `workflows/wiki-sync.md` documents the recommended
  `/wiki-import <file>` single-capture flow + manual quarantine (see TASK Out-of-scope).

## Phase 4 — R4 (DF-9) document the `--note-file` divergence [small]

- [ ] **[R4]** `scripts/wiki_skills/wiki_import_article/__init__.py`: expand the
  `--note-file` argparse help to state the path MAY live outside `--vault-root`
  (orchestrator scratch), + a code comment in `_load_note_json` explaining why no
  containment check (contrast `--candidates-file`). Mirror a note by
  `wiki_extract_concepts/_sourcing.py`'s `--candidates-file`. Optional (belt-and-braces):
  regular-file + `O_NOFOLLOW` read guard (no containment) on `--note-file`.

## Phase 5 — R2 (DF-7) gate reconciles with disk [medium, multi-file]

- [ ] **[R2]** `scripts/wiki_skills/wiki_sync.py` `record`: add `--note-path` arg; when
  present, `set_source_state(..., key="note_path", value=<vault-rel note path>)` alongside
  the existing `source_hash` row (separate row — zero-DDL).
- [ ] **[R2]** `scripts/wiki_skills/_resummarize.py` D1 (`:193-196`): after finding the
  `source_hash` marker, read the `note_path` row; if present and `(vault_root/note_path)`
  does not exist, return None (→ re-summarize) and surface
  `reason=stale-marker-target-missing` + a WARN (same style as the mirror dead-detector
  warn). If no `note_path` row (legacy marker), keep today's behaviour (skip) — backward
  compatible.
- [ ] **[R2]** `scripts/wiki_skills/_resummarize.py` D2a (`:200-220`): add a cheap
  per-match `find_pages_citing_source → file_path → Path.exists()` fallback before
  returning `"provenance"`. D2b mirror: NO change (already disk-checked).
- [ ] **[R2]** `workflows/wiki-sync.md`: thread the produced note path into the
  `wiki-sync record --note-path` step.

## Phase 6 — Verify + docs (R7)

- [ ] **[R6]** `pytest tests/` green; `mypy --strict scripts/` clean; a manual
  `wiki-reindex --full` on a scratch vault still rebuilds (rebuildability gate).
- [ ] **[R7]** Mark `docs/issues/df-6..df-9` `status: resolved` with a one-line
  fix-pointer; regenerate the Class-B ledger (`wiki-index-render --auto-indexes` →
  `docs/KNOWN_ISSUES.md`); add the "never re-type a non-ASCII path" + "a `skip` is only as
  trustworthy as a prior `wiki-lint`; `--force` is the stale-marker recovery" caveats to
  `workflows/wiki-sync.md`.

## Phase 7 — Adversarial VDD review (Wave 1)

- [ ] Spawn `critic-logic`, `critic-security`, `critic-performance` in parallel + a
  `code-reviewer` gate over the diff; resolve any CRITICAL/MAJOR before commit.
