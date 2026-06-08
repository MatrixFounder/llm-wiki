# task-022-07 — `wiki-init` local-DB across subcommands [R-022-3]

**Goal:** `wiki-init` can create/register a vault whose `vaults` row + index live in a local DB, and
writes `index_db:` into `WIKI_SCHEMA.md`.

**Context (read/edit):**
- `scripts/wiki_skills/wiki_init.py` — `scaffold_new`, `register_existing`, `reconcile`, the
  `WIKI_SCHEMA.md.tmpl` render, the `make_repo`/`register_vault` call.
- `templates/WIKI_SCHEMA.md.tmpl` — add an optional `index_db:` line.
- Depends on task-022-02.

**Steps:**
1. argparse: `--local` (store_true ⇒ `index_db = ".wiki/index.db"`) and `--index-db <relpath>`
   (explicit; mutually exclusive with `--local`). Accept on `scaffold_new` + `register_existing`.
2. When set: render/post-write `index_db: <relpath>` into the vault's `WIKI_SCHEMA.md`.
3. Build the repo via `build_repo_config(vault_id, vault_root=<the vault>, db_path_flag=args.db_path)`
   so `register_vault` writes the row into the **local** DB (global untouched).
4. `reconcile`: resolve a declared `index_db` (build_repo_config) before `get_vault_by_root_path` — no
   silent global open for a moved local-DB vault.

**Verification:** `pytest tests/test_wiki_init_local.py -q`
- `wiki-init --register-existing --vault <abs> --local` (NO `--db-path`; m-4 — single scenario): assert
  `index_db: .wiki/index.db` in `WIKI_SCHEMA.md`; `vaults` row present in `<root>/.wiki/index.db`; NO
  new row in the platform global DB (isolate "global" via a `--db-path`-pinned scratch global to assert
  "no row"); JSON envelope `db_path` points at the local DB. (Precedence `--db-path > index_db` is
  already covered by 02-02 + 02-09 — not retested here.) Full `pytest` + `mypy --strict`.
