---
id: DF-6
type: known-issue
status: fixed
opened_at: 2026-07-08
resolved_at: 2026-07-08
resolved_by: TASK 053 (R1)
category: dogfood
severity: SEV-2
slug: df-6-source-state-scope-unicode-normalization-mismatch
---

# `source_state.scope` is compared byte-exact — an NFC/NFD-normalized path never matches the on-disk NFD form

> **Resolution (TASK 053 / R1, fixed 2026-07-08).** `scope` is now
> `unicodedata.normalize("NFC", scope)`-ed at the single DAL choke point — the
> first statement of BOTH `get_source_state` and `set_source_state` in
> `scripts/wiki_index/sqlite_repository.py` — so an NFD filesystem-walk key and an
> NFC operator/LLM/JSON key resolve to the same row. This covers all four call
> sites (scan read, `record` write, both `_resummarize` D1 reads) in one edit;
> ASCII scopes are a no-op. Regression: `tests/test_wiki_sync.py::
> test_source_state_scope_nfc_nfd_equivalence`. The DF's call-site fix was
> rejected as footgun-prone; the §Blast-radius audit of `pages.file_path`/
> `entities.slug` was assessed as NOT a live defect (no confirmed FS↔authored
> asymmetry) and left as a separate hedge, out of scope here.

- **Symptom**: `wiki-sync record <path> --source-hash <h>` was called with a path string
  containing Cyrillic "й" typed/round-tripped as the **precomposed** codepoint (NFC,
  `U+0439`), matching how the string looks when printed, pasted, or produced by
  `json.dumps`/an LLM. The actual file on this iCloud/APFS volume is named with the
  **decomposed** form (NFD, `и` `U+0438` + combining breve `U+0306`) — the macOS-native
  normalization for a filename containing a diacritic, applied whenever the file was
  created/renamed via Finder or synced from another NFD-producing tool. The next
  `wiki-sync scan` walks the filesystem, gets the NFD string back as `cand.rel`, computes
  `entry["is_unchanged"] = source_hash == repo.get_source_state(vault_id, "sync", cand.rel,
  "source_hash")` — and the lookup **misses** even though the file, hash, and recorded value
  are all logically identical. The raw source keeps re-planning as `ingest` on every scan
  forever (an unbounded re-summarize loop for any zone containing a decomposable character),
  UNTIL the marker happens to be (re-)written with the exact byte sequence the filesystem
  walk produces.
- **Repro**: on a case-insensitive-but-normalization-preserving macOS volume (APFS/iCloud
  Drive), create a note whose filename contains "й"/"ё" or any other precomposed
  Latin/Cyrillic letter+diacritic via Finder rename or iCloud sync (→ stored NFD); run
  `wiki-sync scan <zone>` to ingest it, then `wiki-sync record` with a **hand-typed or
  LLM-generated** copy of that path (→ NFC); re-run `wiki-sync scan --dry-run` — the entry
  shows `action: ingest`, `is_unchanged: false`, not `skip: summary-exists:source_state`,
  despite an unchanged file and hash.
- **Root cause**: no `unicodedata.normalize()` call anywhere on the path string before it is
  used as a `source_state.scope` DB key or compared against one — confirmed absent in
  `scripts/wiki_index/sqlite_repository.py` (`get_source_state`/`set_source_state`),
  `scripts/wiki_skills/wiki_sync.py`, and `scripts/wiki_skills/_sync.py`. SQLite `TEXT`
  comparison is byte-exact; the two Unicode normal forms are different byte sequences for
  the same rendered string. The OS filesystem API is normalization-insensitive for lookups
  (so `Path.read_text()`/`stat()` succeed either way — a Python `open()` **write** call, in
  particular, does NOT re-normalize the name it's given, so anything the pipeline itself
  creates keeps whatever form the code passed in, typically NFC), which is exactly why the
  bug is invisible in every file-I/O path and only surfaces in DB-key equality.
- **Blast radius**: not limited to `wiki-sync`'s `source_state` table — the same
  no-normalization gap likely applies to any other path/slug-keyed DB lookup fed a
  filesystem-derived string on one side and a hand-authored/LLM-authored/JSON-round-tripped
  string on the other (worth a broader audit, not just the sync path this repro hit).
- **Fix**: normalize every path string to one canonical form (NFC is the pragmatic choice —
  it's what JSON/most tooling already produces) at the single choke point where a
  filesystem-walk-derived `rel` path is turned into a DB key (`scan`'s `cand.rel`
  construction) AND where an operator/orchestrator-supplied path is accepted (`record`'s
  positional `path` arg, `wiki-index-upsert --source`, etc.) — i.e. `unicodedata.normalize
  ("NFC", rel)` at ingestion into every `*_source_state`/`pages.file_path`/`entities.slug`
  write and read path, not just at the call site that happened to trigger this repro.
- **Workaround (until fixed)**: never hand-type or reconstruct a non-ASCII vault-relative
  path when calling `wiki-sync record` / `wiki-index-upsert` / similar — always extract it
  verbatim from the tool's own JSON output (`scan`'s `entries[].path`, `prepare`'s
  `raw_path`) so the byte sequence matches what the next `scan` will produce. Worth adding
  as an explicit caveat in `workflows/wiki-sync.md` (which currently gives no guidance on
  this) for any agent driving the CLI by hand.
