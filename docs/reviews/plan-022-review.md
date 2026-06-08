# Plan Review — TASK 022 `vault-local-db-resolution`

- **Date:** 2026-06-08 · **Reviewer:** Plan Reviewer (07) — Planning→Execution gate
- **Targets:** `docs/PLAN.md` + `docs/tasks/task-022-01..09-*.md` vs `docs/TASK.md` + `docs/ARCHITECTURE.md` §Q-022
- **Status:** 🟡 **APPROVED WITH COMMENTS** (no 🔴 BLOCKING; both gate criteria PASS; 3 🟡 MAJOR + 4 🟢 MINOR)

## Gate criteria
- **RTM coverage — PASS.** R-022-1→{02-01,02-03}; R-022-2→{02-02,02-06}; R-022-3→02-07; R-022-4→{02-04,02-05}; R-022-5→02-08; R-022-6→02-09 (+ guarded throughout). Every PLAN item starts `[R-022-N]`; UC-1/2/3 trace; no orphans.
- **Stub-First — PASS.** 02-01/02-02 each name a concrete stub→RED→GREEN; 02-03 pure-config accept/reject; byte-identity invariant (R-022-6) checked at every wiring bead (02-02/04/05), not deferred.
- **Atomicity — PASS.** 02-05 (7 CLIs) is wide-but-shallow homogeneous → keep as one bead; 02-04 (5 CLIs/2 classes) atomic (class-ii all already have `--vault-root`). Dependency order valid. ARCHITECTURE fidelity confirmed (raw frontmatter, lazy import, no sig change, `allOf` ban form).

## 🟡 MAJOR
- **M-1 — `wiki-search` uses `--vaults` (plural), not `--vault`** (`wiki_search.py:44,117`). 02-05 step 3 / its verify / UC-2 / 02-09 all use `--vault X` for search → invalid attr + un-runnable test. Fix: special-case search — `vault_id = vaults_list[0] if vaults_list and vaults_list[0] != "all" else GLOBAL_VAULT_SENTINEL`; correct `--vault X`→`--vaults X` for search everywhere. Other 6 CLIs fine; no split.
- **M-2 — island-for-search note (02-08).** State that `build_repo_config` resolves off `vault_root` independent of the (possibly-sentinel) `vault_id`, so `--vaults all --vault-root <root>` reaches the local DB and the island AC holds for search.
- **M-3 — class-(ii) test thinness (02-04).** Only `test_sync_local` covers the 3 inverted CLIs. Add a `wiki-query` (or verify-multi) local-DB assertion, or state the parametrized fixture covers all three.

## 🟢 MINOR
- **m-1 (02-05):** name the source of the emitted `VAULT_ROOT_NOT_FOUND` code string (lift to `_common` or per-CLI literal) — the 7 CLIs have neither code today; `config_loader` raises `VaultRootNotFoundError` (not the string).
- **m-2 (02-09):** drop the WAL-fragile `global.db` **mtime** assertion; keep the robust "no new `vaults` row in global AND row in local" form (matches task-review m-5).
- **m-3 (02-04):** resolve the `wiki_index_render` conditional ("fold in if inline") to a definite include/exclude.
- **m-4 (02-07):** the verify line `--db-path <ignored?> … run WITHOUT --db-path` is self-contradictory; test only the `--local`-without-`--db-path` path (precedence already covered by 02-02 + 02-09).

## Decision
APPROVED WITH COMMENTS — route M-1/M-2/M-3 + the 4 minors to `planner` before execution. No methodology block.

```json
{"plan_file":"docs/PLAN.md","has_critical_issues":false}
```
