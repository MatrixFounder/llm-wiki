# Architecture Review — TASK 022 (vault-local-db-resolution)

- **Date:** 2026-06-08 · **Reviewer:** Architecture Reviewer (05) — Architecture→Planning gate
- **Surface:** `docs/ARCHITECTURE.md` §11a Q-022-1/2/3 vs `docs/TASK.md` (TASK 022) + live code
- **Verdict:** 🟡 **APPROVED WITH COMMENTS** (no 🔴 BLOCKING; 3 🟡 MAJOR spec-precision + 4 🟢 MINOR)

## Verified-sound (claims that hold)
`make_repo` UNTOUCHED is correct (existing `db_path_override`→iCloud→schema→global fallback); no
import cycle from the make_repo side; ordering-inversion is real+necessary (`reindex`/`wiki_sync`/
`wiki_search`/`wiki_lint` open DB first; `wiki_index_upsert` is a valid template); zero-DDL true
(`vaults` = partition-of-one, ADR-002 §D1); `index_db` won't trip the `wiki-lint` drift guard
(`WIKI_SCHEMA.md` ∈ `SYSTEM_FILES`, never indexed); nested-vault walk-up is by-design (nearest
`WIKI_SCHEMA.md`); island/federation YAGNI is structurally enforced (`list_vaults()` spans only the
connected DB); `wiki-init` local-DB registration is feasible with no DAL change.

## 🟡 MAJOR (text amendments — applied to Q-022)
- **M-1 — relative-`index_db` containment must resolve-THEN-check (symlink escape).** A relative
  `.wiki/index.db` where `<vault>/.wiki/` is a symlink out of the vault passes a lexical check but
  resolves outside (prior findings: TASK 018 SEC-A3). Check
  `(vault_root/rel).parent.resolve(strict=False).is_relative_to(vault_root.resolve())`; string-level
  `..`/abs/NUL rejection alone is insufficient. (Absolute form = documented escape, still iCloud-gated.)
- **M-2 — internal-site threading (split-brain risk).** `_manifest_consumer.index_from_manifest`
  calls `make_repo` with `db_path` only; `wiki_enrich` passes `db_path=args.db_path`. If the helper
  is applied at CLI layer but not here, `wiki-enrich` writes GLOBAL while the rest is local —
  split-brain. Fix: `wiki_enrich.main` runs `build_repo_config` and passes resolved `config['db_path']`
  down the existing `db_path=` kwarg (no signature change).
- **M-3 — helper placement + name.** `_common` is acyclic (defensible home) BUT `build_repo_config`
  must **lazily import `config_loader` inside the function** (matching `_common.resolve_entity_file`'s
  lazy `security` import) — not a top-level `_common→wiki_index` edge that `rendering` transitively
  pulls. Also reconcile the name: TASK said `resolve_repo_config`, ARCHITECTURE said
  `build_repo_config` → standardize on **`build_repo_config`**.

## 🟢 MINOR
- **MN-1 — schema ban form:** ban BOTH keys via `allOf:[{not:{required:[vault_id]}},{not:{required:[index_db]}}]`
  (a single `not: required:[vault_id, index_db]` only rejects having BOTH — wrong). DiD only —
  `resolve_index_db_path` reads raw frontmatter, never the merged override.
- **MN-2 — `WikiRootConfig`:** `index_db: {type: string, minLength: 1}`; path semantics validated in
  code, not a schema pattern.
- **MN-3 — error code:** prefer reusing the existing `VAULT_ROOT_NOT_FOUND` (`wiki_index_upsert`) /
  `INVALID_VAULT_ROOT` (`wiki_sync`) rather than minting a third near-duplicate; whichever is chosen,
  no path-content echo (CWE-209/117).
- **MN-4 — document the nested-vault island consequence** (a sub-vault with its own `index_db` routes
  to a different DB) in the island contract / README.

## Routing
3 MAJOR + 4 MINOR returned to `architect` as small text amendments to the Q-022 blocks before
Planning. None are redesigns. No blocking defect.

```json
{"architecture_file":"docs/ARCHITECTURE.md","has_critical_issues":false}
```
