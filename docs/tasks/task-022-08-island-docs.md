# task-022-08 — island contract + nested-vault docs [R-022-5]

**Goal:** document the island model (a local-DB vault is self-contained; `--vault all` spans only the
connected DB; no cross-DB federation) and the nested-vault consequence.

**Context (read/edit):**
- `README.md` (CLI/DB section), `docs/manuals/obsidian-llm-wiki_manual.md` (add a short "where the DB
  lives: global vs in-vault" note + the precedence chain + island), `scripts/wiki_index/.AGENTS.md`
  (factory/config_loader resolution), `scripts/wiki_skills/.AGENTS.md` (`build_repo_config`).
- No new code beyond confirming `--vault all`/`--all-vaults` never silently means global for a local
  invocation (it already spans only the connected DB via `repo.list_vaults()`).

**Steps:**
1. Document: precedence `--db-path > index_db (WIKI_SCHEMA.md, identity) > global`; relative in-vault
   vs absolute non-synced (cloud) form; iCloud guard backstop.
2. Document the **island** contract + the **nested-vault** consequence (a sub-vault with its own
   `index_db` routes to a different DB — `find_vault_root` returns the nearest `WIKI_SCHEMA.md`).
   Note (M-2): for `wiki-search`, `build_repo_config` resolves the DB off `vault_root` **independent**
   of the possibly-sentinel `vault_id`, so `--vaults all --vault-root <root>` reaches the local DB and
   `--vaults all` then spans only that connected (local) DB — the island contract holds for search.
3. Add a one-line `build_repo_config` / `resolve_index_db_path` entry to the two `.AGENTS.md`.

**Verification:** `pytest tests/test_cli_local_db_resolution.py::test_all_vaults_island -q`
- a local-DB connection with one vault → `wiki-lint --all-vaults` (or `wiki-search --vault all`)
  enumerates only that DB's vault(s). Doc grep: README + manual + both `.AGENTS.md` mention the island
  + nested-vault note.
