# TASK 063-12 — write typed pages · forward edges · manifest · idempotency

**Phase**: 4 (write) · **RTM**: R-063-3 (G4 write side), R-063-4, R-063-5 · **Type**: code · **Effort**: 4h
**Depends on**: 063-02, 063-09, 063-10, 063-11 · **Unblocks**: 063-13, 063-14, 063-15

## Goal

`apply` actually writes — to the **config-derived, glob-verified** typed dirs — builds the manifest,
dispatches to the indexer, and records idempotency state.

## The write

`_pages.write_typed_page(vault_root, cand, *, typed_dir, source_slug, today, vault_id)`:
- target dir from **`resolve_typed_write_dir`** (063-02) — never a hardcoded `decisions/`, never a
  hardcoded "sibling".
- **atomic** write (`os.replace`), **symlink refuse before any read/hash/write**, content-hash skip —
  clone `wiki_extract_concepts/_pages.py::write_concept_page` (lines 48-190), including the
  `O_NOFOLLOW` re-read that defends the TOCTOU window.
- frontmatter: `type: <class>`, `status`, `date`, `title`, `extracted_from: <source_slug>`,
  `classification` (063-11), plus **forward edges only**.

## ★ Forward edges only — inverses AUTO-DERIVE (R-063-4, M-1 intact)

Author `implements: [[req-x]]`. **Never** author `implemented-by:`. The inverse is derived by
`wiki-reindex --full` (ADR-004).

> ⚠️ **`--full`, NOT `--delta`.** Inverse derivation is precisely what `--delta` leaves transiently
> stale (`lint.py:298`) — and this row's acceptance *depends on the inverse existing*. A `--delta`
> verification here is a check that examined nothing.

## The manifest — G5's precondition

**Every page `apply` touches is in the manifest it indexes.** In this bead that is the written pages;
063-13 extends it to the **patched** supersede targets (a mutated file whose DB row still carries the
old hash is a `hash-mismatch` — a lint issue we would have *created*).

Dispatch via `_manifest_consumer.index_from_manifest` on the already-open repo (Decision-15/16 — the
in-process, no-subprocess path; reuse the precedent's `dispatch_to_indexer` shape and its module-top
import so the patch target stays stable).

## Idempotency (R-063-5)

`source_state`, `source_kind = "extract-decisions"` (its **own** partition — never collides with the
concepts rail). Unchanged source ⇒ `action: unchanged`, **zero writes**. `--force` bypasses.
**A post-validation index failure leaves `source_state` UNSET** ⇒ `PARTIAL_INDEX_FAILURE`, exit 5,
retry safe (the C-1 invariant, carried over verbatim).

## Context — files

- **Edit** `_pages.py`, `_db.py`, `__init__.py` (`_apply_write`).
- **Read** `wiki_extract_concepts/_pages.py` (the atomic/symlink/hash-skip machinery),
  `_db.py::build_manifest`, `check_idempotency`, `update_idempotency_state`, and
  `__init__.py::_try_update_idempotency_state` (the H-3 graceful-degradation wrapper).

## Tests (RED first) — `tests/test_extract_decisions_write.py` (new)

- `test_writes_to_the_layout_derived_dir` — cybos ⇒ `decisions/<slug>.md` at the **vault root**;
  obsidian-personal ⇒ the **sibling** dir. Same candidate, two layouts, two placements.
  **MUT:** hardcode the sibling ⇒ the cybos assertion RED (and the page would be glob-invisible —
  the silent loss G4 exists to prevent).
- `test_forward_edges_only_on_disk` — the written frontmatter has `implements:` and **no**
  `implemented-by:`. Then `wiki-reindex --full` ⇒ the inverse **is** in `page_entity_refs`.
  **MUT:** author the inverse ⇒ RED (M-1 broken).
- `test_symlink_target_refused` — pre-create the target as a symlink ⇒ refuse before any write.
- `test_unchanged_source_is_a_noop` — second run ⇒ `action: unchanged`, mtimes unchanged.
- `test_partial_index_failure_leaves_source_state_unset` — patch the indexer to fail ⇒ exit 5, and
  the next run **re-extracts** (retry is safe). **MUT:** update `source_state` before the index
  succeeds ⇒ RED (the retry silently no-ops and the pages never index).
- `test_every_written_page_is_in_the_manifest` — see the grep gate below.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "every page we touch is in the manifest" is a denominator claim (G5).**
      Assert it as a **set equality computed from the filesystem**, never as a spot-check:
      ```python
      touched = {p.relative_to(vault_root).as_posix()
                 for d in typed_dirs.values()
                 for p in (vault_root / d).glob("*.md")}          # what is on disk
      manifested = {e["file_path"] for e in manifest["pages"]}    # what we told the indexer
      assert touched == manifested            # not `<=`, not "len equal" — EQUALITY
      ```
      `<=` would pass a manifest that lists pages we never wrote; `>=` would pass one that misses a
      page we did. Only equality is the claim.
- [ ] The typed dir used at write time is the **same value** `prepare`'s preflight verified — assert
      the envelope's `typed_dirs` equals the on-disk parent of every written page.

## Rollback

`_apply_write` → stub. Everything upstream stays green.
