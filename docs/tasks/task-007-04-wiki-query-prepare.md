# Task 007-04: `wiki-query prepare` + CLI scaffold + shared retrieval helper

## Use Case Connection
- UC-16: Ask a question → cited answer page (the retrieval pass).
- UC-17: Idempotent re-run (`is_unchanged`).
- UC-18: No/low retrieval → anti-hallucination refusal (`NO_CONTEXT`).

## Task Goal
Implement the deterministic retrieval pass of `wiki-query` (RTM R-6.1) — `prepare "<question>"` — plus the `bin/wiki-query` wrapper and the argparse skeleton (`prepare`/`apply` subparsers; `apply` stubbed for 007-05/06). Retrieval **reuses** `wiki-search`'s alias-expanded FTS by extracting a shared helper (C-6) so the two CLIs never diverge and `wiki-search` output stays byte-identical.

## Changes Description

### New Files
- `scripts/wiki_skills/wiki_query.py` — the `wiki-query` skill (this bead: argparse + `prepare`; `apply` is a stub raising a clear "implemented in 007-05/06" message / non-zero exit).
- `bin/wiki-query` — thin wrapper (`exec python -m scripts.wiki_skills.wiki_query "$@"`), mode +x, matching the `bin/wiki-search` pattern.
- `scripts/wiki_skills/_retrieval.py` — shared retrieval helper (extracted from `wiki_search.py`): `expand_query(repo, query, vaults_list) -> str` (the `_expand_query` logic) + `fts_quote(surface) -> str`.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_search.py`
- Replace the local `_fts_quote` / `_expand_query` with imports from `scripts.wiki_skills._retrieval` (`fts_quote`, `expand_query`). **No behavior change** — `wiki-search` output must be byte-identical.

#### File: `scripts/wiki_skills/wiki_query.py`
- `_build_parser()` → `add_subparsers(dest="cmd", required=True)` with `prepare` and `apply` subparsers.
- `prepare` flags: `question` (positional), `--vault`, `--vault-root`, `--vaults`, `--types`, `--project`, `--limit` (type=int, **default 10**), `--no-expand-aliases` (store_true), `--slug`, `--min-hits` (type=int, default 1), `--db-path`.
- `prepare(args) -> int`:
  1. Build repo via `make_repo` (same factory_vault/`GLOBAL_VAULT_SENTINEL` logic as `wiki_search.main`).
  2. Validate question (non-empty, ≤ cap → `INVALID_QUESTION` exit 2 on violation).
  3. `match_query = expand_query(...)` unless `--no-expand-aliases`; run `repo.search_pages(...)` with the same DF-1 hyphen quoted-phrase fallback as `wiki_search` (→ `INVALID_QUERY` exit 2 if un-parseable).
  4. `hits = [{vault_id, slug, project, type, title, bm25_score, snippet}, …]` (vault-relative; no absolute paths).
  5. `if len(hits) < args.min_hits:` emit `{"error":"NO_CONTEXT","field":"retrieved_count","reason":"<n> hits < --min-hits <m>"}` exit 2.
  6. `query_slug = args.slug or _derive_query_slug(question)` (`slugify`, truncated to a filesystem-safe length, kebab-validated → `INVALID_SLUG` exit 2 if `--slug` is non-kebab).
  7. `question_hash = sha256(question ‖ "\n".join(f"{h['project']}/{h['slug']}" for h in hits in BM25 order)).hexdigest()` (Q-A6 binding shape).
  8. `is_unchanged = (repo.check_query_state(vault_id, query_slug) == question_hash)`.
  9. `emit({"vault_id", "question", "query_slug", "question_hash", "is_unchanged", "retrieved_count", "hits"})` exit 0.
- `_derive_query_slug(question: str) -> str` — `slugify(question, ...)` truncated; deterministic.
- `apply(args) -> int` — **stub** this bead: emit a clear envelope / exit non-zero "apply lands in 007-05/06". (Keeps the class/CLI importable + `--help` working.)

### Component Integration
`prepare` consumes `repo.expand_query_aliases` + `repo.search_pages` (via `_retrieval`) + `repo.check_query_state` (007-03). Emits the envelope the orchestrator feeds to the `wiki-query-synthesis` skill (007-07).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01:** `wiki-query --help` and `wiki-query prepare --help` exit 0; missing subcommand → argparse error exit (non-zero).
2. **TC-E2E-02 (retrieval):** fixture vault with pages mentioning "Hermes"; `prepare "Hermes routing" --vault v --vault-root <p>` → envelope with `retrieved_count ≥ 1`, hits carry the 7 keys, `query_slug == "hermes-routing"`, a 64-hex `question_hash`.
3. **TC-E2E-03 (NO_CONTEXT):** a question matching nothing → `{"error":"NO_CONTEXT",…}` exit 2; nothing written.
4. **TC-E2E-04 (is_unchanged):** pre-seed `record_query_state(v, slug, <same hash>)` → `is_unchanged: true`.
5. **TC-E2E-05 (alias expansion parity):** default expands (`--no-expand-aliases` narrows); a page mentioning only a sibling alias is retrieved by the canonical term (default on).

### Unit Tests
1. **TC-UNIT-01:** `_derive_query_slug("How does X work?")` → kebab, truncated, deterministic.
2. **TC-UNIT-02:** `question_hash` changes when the retrieved-slug set changes (corpus-sensitivity, Q-A6) but is stable for identical question+hits.
3. **TC-UNIT-03 (refactor safety):** `wiki-search` output is **byte-identical** before/after the `_retrieval` extraction (golden-output test on a fixture).

### Regression Tests
- All existing `wiki-search` tests stay green (the extraction is behavior-preserving).
- DF-1 hyphen-query fallback still works in both CLIs.

## Acceptance Criteria
- [ ] `bin/wiki-query` + `scripts/wiki_skills/wiki_query.py` with `prepare`/`apply` subparsers (`apply` stubbed).
- [ ] `_retrieval.py` shared helper; `wiki-search` imports it and is byte-identical (TC-UNIT-03).
- [ ] `prepare` emits the retrieval envelope; `NO_CONTEXT`/`INVALID_QUESTION`/`INVALID_QUERY`/`INVALID_SLUG` exit 2.
- [ ] `is_unchanged` reflects `check_query_state`; `question_hash` = `sha256(question ‖ ordered hit project/slug set)`.
- [ ] Full `pytest` green; `mypy --strict scripts/` clean.

## Notes
Stub-First: Phase-1 = argparse + `bin/` wrapper + `_retrieval` extraction (with the byte-identical RED/green test) + `apply` stub; Phase-2 = `prepare` logic. The shared-helper extraction must land green before any `prepare` logic so the `wiki-search` refactor risk (Risk R-4) is retired first.
