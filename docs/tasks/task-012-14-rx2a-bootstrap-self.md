# Task 012-14: R-X2.2 (Phase A) — bootstrap obsidian-llm-wiki as the first dev-vault

## Use Case Connection
- UC-31: this repo's own `docs/` becomes searchable; `wiki-search "ADR-002" --vaults obsidian-llm-wiki`.

## Task Goal
Bootstrap THIS repo as a `dev-project` dev-vault and confirm cross-doc search works on real
content (TASKs, ADRs, proposals, the migrated `docs/issues/*.md`). First real end-to-end proof
of R-X1 + R-X2 on production data.

## Changes Description

### Operator-run bootstrap (produces a committed `docs/WIKI_SCHEMA.md`)
1. `wiki-init --register-existing --layout dev-project --vault . --vault-id obsidian-llm-wiki`
   (or `--scaffold-new` guarded per 012-13) → writes/uses `docs/WIKI_SCHEMA.md`:
   ```yaml
   ---
   vault_id: obsidian-llm-wiki
   schema_version: "2.0"
   language: en
   layout: dev-project
   ---
   ```
   Registers the vault in the global SQLite.
   - **Repo-is-not-a-vault invariant:** the dev-vault content is `docs/`, not the repo root;
     the `dev-project.yaml` `paths[]` are `docs/...`-scoped. The DB lives at the standard
     global location (NOT in-repo); `*.db*` + vault artifacts stay gitignored (CLAUDE.md).
2. `wiki-reindex --full --vault obsidian-llm-wiki` → indexes `docs/`.

### Changes in Test Files
#### File: `tests/test_dev_vault_bootstrap.py` (NEW)
- Using a `dev-project` fixture (or a copied subset of this repo's `docs/`): register +
  `reindex_full` → `search_pages("ADR-002")` returns the ADR with a snippet; an `adr`-tagged
  page is retrievable via the tag filter.
- The migrated `docs/issues/*.md` (012-12) index as `known-issue`-tagged; the rendered
  `docs/KNOWN_ISSUES.md` (Class B) is NOT re-ingested as a page (SYSTEM_FILES/auto-output
  implicit-ignore — architecture-review m1).

## Acceptance Criteria
- ✅ `wiki-search "ADR-002" --vaults obsidian-llm-wiki` returns ranked hits with snippets.
- ✅ `docs/issues/*.md` indexed as `known-issue`; the generated ledger not double-indexed.
- ✅ Repo-is-not-a-vault invariant holds (DB + artifacts gitignored; content scoped to `docs/`).
- ✅ `mypy --strict` clean; suite green.

## Stub-First
Integration/dogfood bead. The test runs on a fixture/copied `docs/` subset; the real
`docs/WIKI_SCHEMA.md` registration is the committed deliverable.
