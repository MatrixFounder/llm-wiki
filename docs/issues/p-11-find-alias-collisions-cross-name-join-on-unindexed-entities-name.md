---
id: P-11
type: known-issue
status: open
opened_at: 2026-05-29
category: performance
severity: SEV-3
slug: p-11-find-alias-collisions-cross-name-join-on-unindexed-entities-name
---

# find_alias_collisions cross-name join on unindexed entities.name

- **Symptom**: `find_alias_collisions` cross-name branch `JOIN entities e ON e.name = a.alias` has no index on `entities.name` (schema indexes type/project/email/telegram/is_candidate/last_updated + PK, not `name`). Worst-case nested-loop ≈ O(aliases × entities); at 10k×10k a lint run could blow up. The cross-*slug* branch (`e.slug = a.alias`) is PK-covered and fine.
- **Root cause**: No `entities.name` index (deliberately — adding one taxes every write for a rare lint query, cf. the P-5 dead-index anti-pattern).
- **Affected components**: `scripts/wiki_index/sqlite_repository.py::find_alias_collisions`.
- **Fix plan**: `EXPLAIN QUERY PLAN` to confirm it's a single scan (likely) not a per-alias probe; if it regresses at scale, add a covering index or rewrite as a self-join keyed on the indexed columns. Lint-path only, once per vault. Defer until a real vault shows the regression.
