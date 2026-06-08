# Task Review — TASK 022 `vault-local-db-resolution`

- **Date:** 2026-06-08 · **Reviewer:** Task Reviewer (03) — VDD Analysis→Architecture gate
- **Target:** `docs/TASK.md` (TASK 022)
- **Status:** 🟡 **APPROVED WITH COMMENTS** (no 🔴 BLOCKING; 1 borderline-blocking MAJOR + 5 MAJOR + 5 MINOR)

## General Assessment
Well-grounded spec that identifies the real hard part (bootstrap circularity), places `index_db`
in the right layer (identity / `WIKI_SCHEMA.md`), preserves the global default byte-identically,
and asserts zero DDL. All ground-truth code facts verified. One naming correction:
`config_loader.find_vault_root` is **public** (not `_find_vault_root`).

## 🔴 Critical (BLOCKING)
None.

## 🟡 Major
- **M-1 (borderline-blocking → OQ-5): iCloud guard defeats the goal for an iCloud-synced Obsidian
  vault.** Obsidian-on-iCloud lives under `~/Library/Mobile Documents/iCloud~md~obsidian/…`;
  `validate_db_path` **raises `ICloudRejectionError`** for a DB resolved there (WAL/shm corruption
  across devices — the reason the guard exists). So `index_db: .wiki/index.db` inside such a vault
  raises and points back at `--db-path`. Reconcile the iCloud guard with the goal (promote to OQ-5).
- **M-2: no registry of local DBs exists.** Every "all vaults" path is `repo.list_vaults()` over the
  single connected DB. `--vault all` is *architecturally* incapable of seeing a local-DB vault from
  global. Reframe OQ-1/B1 from "proposed default" to the architectural fact + the dual-registration
  fork.
- **M-3: ordering inversion (the hidden hole).** The fleet pattern is `make_repo` first, then read
  `root_path` from the opened DB. For a local-DB vault this opens GLOBAL then fails `get_vault`.
  Resolution must run `vault_root` (flag → walk-up) **before** `make_repo`. `wiki-index-upsert` /
  `wiki-extract-concepts prepare` already do this — cite as the template.
- **M-4: "all 15 CLIs" needs a per-CLI inventory (3 classes).** (i) resolve root before make_repo:
  upsert, extract-concepts; (ii) accept `--vault-root` but derive from DB after: query, sync,
  verify-multi; (iii) **no `--vault-root` at all**: search, lint, reindex, index-render, alias,
  confirm, merge, append-log. UC-2 shows `wiki-search --vault-root` which **does not exist today**.
  The shared helper must also reach internal sites (`_manifest_consumer.index_from_manifest`,
  `wiki_index_upsert.upsert_one`).
- **M-5: `validate_inside_vault` can't validate a not-yet-created DB** (`resolve(strict=True)` →
  `FileNotFoundError`). Validate the parent dir / reject the relative-string (`..`/abs/NUL)
  pre-filesystem instead.
- **M-6: `wiki-init --reconcile` uncovered** by A3/R-022-3 — the "moved the portable vault" path.
  Cover all three init subcommands or scope `reconcile` out with a rationale.

## 🟢 Minor
- **m-1:** terminology — canonical framing is **two config systems** (identity vs grammar) + sync
  dispatcher state, not "3-config-layer split". The decision (identity) is correct.
- **m-2:** schema — `WikiRootConfig` is `additionalProperties:true` (must *add* `index_db`
  validation); mirror the `WikiProjectOverride` `vault_id` ban for `index_db` (identity can't be
  redirected by a project override).
- **m-3:** `load_root_config` overlays `CLAUDE.md::wiki:` — decide if `index_db` is readable there
  (second redirect surface) or raw frontmatter only (likely the latter). Add as OQ-2 sub-point.
- **m-4:** three `find_vault_root` walk-ups exist; consolidate, don't add a fourth.
- **m-5:** AC precision — "global.db mtime unchanged" is WAL-fragile → assert "no new `vaults` row
  in global AND row present in local"; name `VAULT_ROOT_UNRESOLVED` in the RTM; no path echo
  (CWE-209/117).

## ADR-002 §D1 check
No contradiction — implements the named "per-vault opt-out" hook; global path byte-identical when
`index_db` absent.

## Final Recommendation
**APPROVED WITH COMMENTS — proceed to Architecture** carrying the comments as the agenda. Promote
OQ-5 (iCloud), reframe OQ-1 (registry fact), pin the ordering inversion + per-CLI inventory, fix the
containment mechanism + schema bans, cover/scope-out `reconcile`. Two comments need **operator
input** before Architecture: OQ-5 (is the real vault iCloud/cloud-synced?) and OQ-1 (island vs
cross-vault).

```json
{"review_file": "docs/reviews/task-022-review.md", "has_critical_issues": false}
```
