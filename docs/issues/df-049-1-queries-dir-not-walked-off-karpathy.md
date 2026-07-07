---
id: DF-049-1
type: known-issue
status: open
opened_at: 2026-07-07
category: correctness
severity: SEV-2
slug: df-049-1-queries-dir-not-walked-off-karpathy
---

# filed `_queries/`/`_verifications/` pages don't survive reindex on non-karpathy layouts

- **Symptom**: On an `obsidian-personal` (and `dev-project`/`cybos`) vault, `wiki-query
  apply` files `_queries/<slug>.md` and self-indexes it (`page_indexed: true`), but the
  next `wiki-reindex --delta` **deletes the row** (`deleted: 1`) while the Class-A file
  stays on disk: the layout's `paths:` grammar has no `_queries/**` (nor
  `_verifications/**`) glob, so the walk never sees the file and the pruning pass treats
  the DB row as missing-on-disk. Consequences: `is_unchanged` idempotency breaks (the
  recorded `source_state` hash survives but the page row is gone), the filed answer stops
  being retrievable/citable, the R-6.5e `cited`-backlink read-side never fires, and a
  `classification-leak` lint finding over the filed answer (TASK 049) disappears with the
  row. Same class applies to `wiki-verify-multi`'s `_verifications/` verdict pages.
- **Reproduced**: TASK 049 dogfood on the `personal` Phase-0 test copy
  (`Downloads/TestVault/ObsidianNotes-Test`, layout `obsidian-personal` + `.wiki/layout.yaml`
  paths-override): apply → row + `cited` ref present, lint `classification-leak: 1`;
  `wiki-reindex --delta` → `deleted: 1`, row gone, leak finding gone.
- **Root cause**: `wiki-query`/`wiki-verify-multi` file to the karpathy constants
  `QUERIES_SUBDIR`/`VERIFICATIONS_SUBDIR` unconditionally, but only `karpathy.yaml` walks
  those subdirs. The §D8 durability contract (apply-written rows byte-identical to a
  `--full` rebuild) implicitly assumes the layout indexes the filing location — true only
  for karpathy. A vault-local `paths:` override compounds it (REPLACE semantics, Q-012-f)
  but the built-ins are the primary gap.
- **Affected components**: `scripts/wiki_index/layouts/{obsidian-personal,dev-project,cybos}.yaml`,
  `wiki_query.apply` self-index durability (R-6.4/R-6.5e), `wiki_verify_multi.apply` (R-8.4),
  TASK 049 `classification-leak` lint coverage on those layouts.
- **Fix plan**: (a) add `_queries/**` + `_verifications/**` path rules (type `query` /
  `verification`, project `_vault_`) to the three non-karpathy built-in layouts — additive
  YAML, zero Python, preserves karpathy byte-identity; (b) adoption-runbook note: a vault
  `paths:` override must re-declare them (REPLACE semantics); (c) optionally a `wiki-lint`
  guard: a `type=query|verification` DB row whose `file_path` is outside every layout glob
  → warn "filed page will not survive reindex".
- **Workaround**: karpathy vaults unaffected; on other layouts add the two globs to the
  vault's `.wiki/layout.yaml` `paths:` override.
