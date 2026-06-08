# task-022-09 — full regression + real dogfood [R-022-6]

**Goal:** prove zero regression for global-DB vaults and a working end-to-end for a local-DB vault.

**Context:** the whole `scripts/` tree + a scratch vault under `samples/` (gitignored).

**Steps:**
1. `pytest tests/ -q` green (≥ 1056 + the new tests); `mypy --strict scripts/` clean.
2. Grep-guards: `user_version` still 5 (zero DDL — no schema file touched); no new runtime dep; no
   `import anthropic`.
3. **Dogfood** on a fresh `samples/<v>/`: `wiki-init --register-existing --vault <abs> --local`
   (no `--db-path`) → run `wiki-reindex --full`, `wiki-search "q" --vaults <id>` (plural — M-1),
   `wiki-sync scan` each with NO `--db-path`; assert every op hits `<root>/.wiki/index.db` and the
   platform global DB has **no `vaults` row** for this vault (robust form — drop the WAL-fragile mtime
   check, m-2; isolate "global" via a `--db-path`-pinned scratch global). Then `--db-path <other>`
   still overrides (precedence). Confirm an iCloud-pathed `index_db` is rejected with the relocation
   hint (OQ-5 backstop).

**Verification:** the full suite + the scripted dogfood assertions all pass; capture the run in the
TASK.md "Review outcome" before commit.
