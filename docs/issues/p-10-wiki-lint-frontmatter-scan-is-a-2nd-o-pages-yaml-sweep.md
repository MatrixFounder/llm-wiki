---
id: P-10
type: known-issue
status: fixed
opened_at: 2026-05-29
category: performance
slug: p-10-wiki-lint-frontmatter-scan-is-a-2nd-o-pages-yaml-sweep
---

# wiki-lint frontmatter scan is a 2nd O(pages) YAML sweep

- **Symptom**: `lint._scan_frontmatter_alias_collisions` calls `frontmatter.load()` (file read + PyYAML `safe_load`) on **every** `_concepts`/`_entities` page on every `wiki-lint` run — *in addition to* `check_drift` (P-3), which already reads + hashes + `safe_load`s every page. At 10k entity pages a single lint does the disk+YAML sweep twice (~seconds against the 30s SLO P-3 already flags as at-risk).
- **Root cause**: R-5.6(e) Class A frontmatter scan implemented as an eager per-file YAML parse, independent of `check_drift`'s sweep.
- **Affected components**: `scripts/wiki_index/lint.py:_scan_frontmatter_alias_collisions` + `run_all_checks`.
- **Fix plan**: (a) detect frontmatter alias collisions from `pages.frontmatter_json` via SQL `json_each(...,'$.aliases')` GROUP BY (zero file I/O — the aliases are already mirrored), OR (b) share the single file-read pass with `check_drift` + use the P-3 regex fast-path instead of full PyYAML. Pass at N=100 today; wire only when a real vault crosses ~1k entity pages.
