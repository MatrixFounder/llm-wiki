# PLAN — TASK 015 `perf-hardening-extract-concepts`

Stub-First, green-throughout. 11 beads. **Zero DDL** (`user_version` stays 5).
mypy `--strict` + full pytest green at every bead.

## Design (locked — see TASK.md + ARCHITECTURE.md functional-architecture §Concept Extractor)

### Phase 1 — H-PERF-3 + P-8: programmatic upsert entry-point + connection reuse (beads 01-03)
- **`upsert_one(vault_id, src, vault_root, repo) → dict`** added to
  `scripts/wiki_skills/wiki_index_upsert.py`. Contains the upsert logic extracted from
  `main()`; accepts an open `repo`, returns the envelope dict (does NOT call `emit()`).
  `main()` opens repo, calls `upsert_one`, calls `emit(result)`, closes repo.
- **`index_from_manifest(…, repo=None)`** — optional `repo` parameter added to
  `scripts/wiki_skills/_manifest_consumer.py`. When `repo=None`: opens+closes its own
  (backward-compat). When `repo` provided: uses it, does NOT close it. The upsert loop
  calls `upsert_one(vault_id, abs_path, vault_root, repo_to_use)` instead of `main(argv)`.
  The `append_log_event` call also uses `repo_to_use`. Single `make_repo` per call.

### Phase 2 — P-6: `--known-concepts-format` flag (beads 04-05)
- Add `--known-concepts-format {full,slugs-only}` to the `prepare` subparser
  (default `full`, backward-compat). In `prepare()`:
  `known_out = [e["slug"] for e in known] if slugs_only else known`.
  `known_concepts_format` attribute lives on the `prepare` sub-namespace;
  `apply` subparser does NOT have this flag.

### Phase 3 — P-7 prepare side: `--batch` (beads 06-07)
- `--batch <slugs.json>` mutex with `--source-page` on the `prepare` subparser.
- `_batch_prepare(args, repo) → int`: reads + validates slugs file (bounded
  `_read_file_bounded`; file may live outside vault — slugs-only, no content write);
  loads `known_concepts` once; for each slug calls `_recon_single(slug, vault_root,
  source_slug_resolved, repo)` (extracts the per-slug recon steps from `prepare()`);
  per-slug errors are non-fatal (stored as `{source_slug, error, message}` entries).
  Emits `{"batch": [...]}`.

### Phase 4 — P-7 apply side: `--batch-candidates` (beads 08-09)
- `--batch-candidates <combined.json>` mutex with `--candidates-file`/`--candidates-stdin`
  on the `apply` subparser.
- Factor out `_apply_candidates_to_db(source_path, source_hash, vault_id, vault_root,
  candidates, orchestrator_id, today, repo) → dict` from `apply()` — contains the
  DB writes (validate schema, preflight sanitize, classify, write pages, upsert entities,
  refs); takes an already-open `repo`; wraps writes in independent `BEGIN IMMEDIATE`
  transaction per call.
- `apply()` calls `_apply_candidates_to_db` after loading candidates from file/stdin
  (refactor only — no behaviour change).
- `_batch_apply(args, repo) → int`: open repo once; for each entry in combined.json:
  call `_apply_candidates_to_db`; if `--ingest` call
  `index_from_manifest(manifest, vault_id, vault_root, db_path, repo=repo)` per entry
  (shared repo, N calls); emit `{"batch": [...]}`.

## Beads

| # | Bead | Files | Stub-First RED → GREEN | Acceptance (RTM) |
|---|------|-------|------------------------|------------------|
| **015-00** | No-regression anchor | `tests/test_perf_hardening.py` (new) | Create test file; run `pytest -q` + `mypy --strict scripts/` to capture baseline. 1 smoke test (import `wiki_index_upsert`). | R-015-NF3 |
| **015-01** | Stub `upsert_one` signature | `scripts/wiki_skills/wiki_index_upsert.py`, `tests/test_perf_hardening.py` | Add `upsert_one(vault_id, src, vault_root, repo) → dict` stub (`raise NotImplementedError`); write RED test `test_upsert_one_returns_envelope`. | R-015-1 partial |
| **015-02** | Implement `upsert_one`; `main()` delegates | `scripts/wiki_skills/wiki_index_upsert.py` | Extract body from `main()` into `upsert_one`; `main()` opens repo + calls `upsert_one` + `emit`; `test_upsert_one_returns_envelope` GREEN; add `test_upsert_one_no_argparse`. | R-015-1, AC-015-2 |
| **015-03** | `index_from_manifest` single-repo + `upsert_one` | `scripts/wiki_skills/_manifest_consumer.py`, `tests/test_perf_hardening.py` | Add optional `repo` param; loop calls `upsert_one` (not `main(argv)`); `append_log_event` on same repo; add `test_index_from_manifest_single_connection`. | R-015-2, AC-015-1 |
| **015-04** | Stub `--known-concepts-format` flag | `scripts/wiki_skills/wiki_extract_concepts.py`, `tests/test_perf_hardening.py` | Add flag to `prepare` subparser (default `full`); `prepare()` reads `args.known_concepts_format` but ignores it (stub); write RED `test_prepare_slugs_only_format`. | R-015-3 partial |
| **015-05** | Implement `slugs-only` path | `scripts/wiki_skills/wiki_extract_concepts.py` | `known_out = [e["slug"] for e in known] if slugs_only else known`; `test_prepare_slugs_only_format` GREEN; add `test_prepare_full_default` regression. | R-015-3, AC-015-3, AC-015-4 |
| **015-06** | Stub `prepare --batch` | `scripts/wiki_skills/wiki_extract_concepts.py`, `tests/test_perf_hardening.py` | Add `--batch` (mutex `--source-page`); route to `_batch_prepare(args, repo)` stub returning `{"batch": []}`; write RED `test_prepare_batch_multi_page`. | R-015-4 partial |
| **015-07** | Implement batch prepare | `scripts/wiki_skills/wiki_extract_concepts.py` | Full `_batch_prepare`: bounded slugs-file read, `known_concepts` once, per-slug recon, per-entry error isolation; `test_prepare_batch_multi_page` + `test_prepare_batch_partial_failure` GREEN. | R-015-4, AC-015-5, AC-015-6 |
| **015-08** | Stub `apply --batch-candidates` | `scripts/wiki_skills/wiki_extract_concepts.py`, `tests/test_perf_hardening.py` | Add `--batch-candidates` (mutex `--candidates-*`); route to `_batch_apply(args, repo)` stub returning `{"batch": []}`; write RED `test_apply_batch_candidates`. | R-015-5 partial |
| **015-09** | Implement batch apply | `scripts/wiki_skills/wiki_extract_concepts.py`, `scripts/wiki_skills/_manifest_consumer.py` | Factor out `_apply_candidates_to_db`; refactor single-page `apply()` to use it; `_batch_apply` opens one repo, per-entry independent transactions + shared-repo `index_from_manifest`; `test_apply_batch_candidates` + `test_apply_batch_with_ingest` GREEN. | R-015-5, AC-015-7, AC-015-8 |
| **015-10** | Close issues + docs gate | `docs/issues/h-perf-3-*.md`, `docs/issues/p-6-*.md`, `docs/issues/p-7-*.md`, `docs/issues/p-8-*.md`, `docs/KNOWN_ISSUES.md`, `.AGENTS.md`×2, `docs/ROADMAP.md` | Flip 4 issues `status: open→fixed`; re-render ledger; `wiki-lint` PW-Q clean; update AGENTS + ROADMAP. | R-015-NF1, AC-015-9..11 final gate |

## Dependency / order

```
015-00 (anchor, stays green throughout)
  → 015-01 (add signature)
  → 015-02 (implement upsert_one; main delegates)
  → 015-03 (index_from_manifest uses upsert_one + single repo)
  → 015-04 (add --known-concepts-format stub)
  → 015-05 (implement slugs-only)
  → 015-06 (add --batch stub)
  → 015-07 (implement batch prepare)
  → 015-08 (add --batch-candidates stub)
  → 015-09 (implement batch apply; needs _apply_candidates_to_db refactor)
  → 015-10 (docs + close issues)
```

## Verification (end-to-end)

1. `pytest -q` ≥ 852 + mypy `--strict scripts/` clean at every bead.
2. **AC-015-1** (single `make_repo` per `index_from_manifest` call): monkeypatch `make_repo`
   in `_manifest_consumer`; count calls.
3. **AC-015-2** (`upsert_one` no argparse): monkeypatch `_build_parser`; call `upsert_one`
   directly; assert parser NOT called.
4. **AC-015-3/4** (`slugs-only` / `full` regression): call `prepare` via a tmp vault with
   known entities; assert `known_concepts` is `list[str]` vs `list[dict]`.
5. **AC-015-5/6** (batch prepare): 3-slug batch; assert 3 entries; 1 invalid → assert
   2 success + 1 error dict, exit 0.
6. **AC-015-7** (batch apply shared repo): monkeypatch `make_repo`; assert called once.
7. **AC-015-8** (batch apply + ingest): monkeypatch `make_repo` + `index_from_manifest`;
   assert `make_repo` called once; `index_from_manifest` called N times (once per entry).
8. **Karpathy byte-identity** (AC-015-9): existing `test_karpathy_byte_identity` green.
9. **CWE-117 invariant** (R-015-NF4): `test_apply_error_envelopes_never_echo_content`
   still green (existing regression test).

## Use Case Coverage

| Use Case | Beads |
|----------|-------|
| UC-015-1 (single-page regression) | 015-00, 015-02, 015-03 |
| UC-015-2 (slugs-only mode) | 015-04, 015-05 |
| UC-015-3 (batch prepare) | 015-06, 015-07 |
| UC-015-4 (batch apply) | 015-08, 015-09 |
| UC-015-5 (upsert_one library use) | 015-01, 015-02 |

## Out of scope

- PRAGMA caching / connection pool (P-8 root-cause PRAGMA cost per call — deferred).
- Further refactoring of `wiki-enrich`'s `index_from_manifest` caller (it passes `repo=None`,
  gets existing behavior — a follow-up if measured).
- `wiki-query apply` and `wiki-verify-multi apply` anti-N+1 (they already use direct DAL,
  see `functional-architecture.md` note).
