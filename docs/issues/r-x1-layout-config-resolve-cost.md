---
id: R-X1-CFG-COST
type: known-issue
status: open
opened_at: 2026-06-01
category: performance
severity: SEV-3
slug: r-x1-layout-config-resolve-cost
---

# Per-command layout-config resolve cost (no cache; per-file regex recompile)

- **Symptom**: `resolve_layout_config` re-reads + re-parses the layout YAML on every callsite (reindex_full/delta, check_drift, find_pages_missing, lint, render). The static JSON-schema *meta*-validation was hoisted to a module singleton (fixed), but the YAML re-reads + the ReDoS gate still run per resolve (O(callsites) across a maintenance run, not O(pages)). Separately, `_derive_project`/`extract_refs` `re.compile` already-validated patterns per file/page (mitigated by the stdlib `re` cache → microseconds).
- **Root cause**: No per-vault `LayoutConfig` cache; patterns stored as strings, not compiled `re.Pattern` on the frozen config.
- **Affected components**: `scripts/wiki_index/layout_config.py` (`resolve_layout_config`, `_derive_project`, `iter_pages`), `scripts/wiki_source/parsing.py` (`extract_refs`).
- **Fix plan**: memoize `resolve_layout_config` per resolved `vault_root` (CLIs are one-shot → no staleness); compile `project_pattern`/`ref_extraction.regex` once into the `LayoutConfig` in `_build`. Deferred: O(1) per command, microsecond per-file cost; not a correctness issue.
- **Prevention**: module-level schema-validator singleton already removes the per-call meta-validation.
