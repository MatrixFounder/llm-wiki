# task-022-06 — `wiki-enrich` internal-site threading (no split-brain) [R-022-2]

**Goal:** `wiki-enrich` against a local-DB vault writes into the LOCAL DB, not global — close the
split-brain the arch review (M-2) flagged.

**Context (read/edit):**
- `scripts/wiki_skills/wiki_enrich.py` — `main` (currently passes `db_path=args.db_path` into the
  manifest consumer).
- `scripts/wiki_skills/_manifest_consumer.py::index_from_manifest(..., db_path: str | None)` — EXISTING
  kwarg (no signature change); it calls `make_repo`. `wiki_index_upsert.upsert_one` inherits via the
  open `repo`.
- Depends on task-022-02.

**Steps:**
1. In `wiki_enrich.main`, resolve `vault_root` (it already has `--vault-root`); build
   `config = build_repo_config(args.vault, vault_root=vault_root, db_path_flag=args.db_path)`.
2. Pass `config.get("db_path")` as the `db_path=` argument into `index_from_manifest(...)` (and any
   other `make_repo` call on that path), so the ingest writes to the SAME resolved DB as the rest.

**Verification:** `pytest tests/test_cli_local_db_resolution.py::test_enrich_writes_local -q`
- register a sample vault with `index_db`; run `wiki-enrich` on a tiny source; assert the new page row
  is in `<root>/.wiki/index.db` and NOT in `global.db`. Full `pytest` + `mypy --strict`.
