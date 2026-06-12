# 030-02 — DAL txn-free DML helpers (R-030-2a)

**RTM:** R-030-2 (helper leg). **UC:** UC-30-2. **Depends:** —.

## Goal
Zero-behavior-change refactor: extract the DML bodies of `upsert_page` /
`replace_refs` into private txn-free helpers; public methods keep their own-tx
semantics by delegating.

## RED first
1. **Mechanical own-tx oracle (AC-2.2):** test — open `BEGIN IMMEDIATE` externally
   on `repo._connect()`, call public `upsert_page` → `sqlite3.OperationalError`
   ("cannot start a transaction within a transaction") exactly as today; then call
   `_upsert_page_in_txn(conn, page)` inside the same open tx → succeeds; COMMIT →
   row visible. Same pair for `replace_refs`/`_replace_refs_in_txn`. (RED: helpers
   don't exist.)
2. **Privacy pin:** helpers are `_`-prefixed and ABSENT from `repository.py` ABC
   (assert via `hasattr(IndexRepository, ...) is False`).

## GREEN
- `SQLiteRepository._upsert_page_in_txn(conn, page, *, skip_unchanged_check: bool)`
  — the ON CONFLICT statement (+ optional hash pre-SELECT when
  `skip_unchanged_check=False`, returning the Literal for the public wrapper).
- `SQLiteRepository._replace_refs_in_txn(conn, vault_id, slug, project, refs)` —
  dedup + DELETE + executemany INSERT.
- Public `upsert_page`/`replace_refs`: BEGIN IMMEDIATE → helper → COMMIT/ROLLBACK —
  byte-equivalent behavior (M-4 comment block untouched; docstrings note the
  helper split + the owns-OR-delegates wording).

## Acceptance
- ✅ Full suite green UNMODIFIED (zero behavior change); new oracle tests green.
- ✅ mypy `--strict`; ABC untouched; M-4 wording preserved in `repository.py`.
- ✅ `.AGENTS.md` for `scripts/wiki_index/` updated (helper contract: "txn-free,
  caller MUST hold an open transaction").
- ✅ Sarcasmotron pass.
