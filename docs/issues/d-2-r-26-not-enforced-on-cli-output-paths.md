---
id: D-2
type: known-issue
status: open
opened_at: 2026-05-26
category: security
slug: d-2-r-26-not-enforced-on-cli-output-paths
---

# R-26 not enforced on CLI output paths

- **Symptom**: `wiki-lint --report` / `--json-sidecar`, `wiki-index-render --output` accept arbitrary destination paths. An operator can write report files outside the vault root.
- **Root cause**: Outputs were considered operator-trusted; not gated by `validate_inside_vault`.
- **Affected components**: `scripts/wiki_skills/wiki_lint.py`, `scripts/wiki_skills/wiki_index_render.py`.
- **Fix plan**: Decide policy — either gate via `validate_inside_vault(arg, vault.root_path)` for R-26 compliance, or document explicit operator-trust scope in CLI `--help` text. Deferred pending Phase 3b threat-model review.

---
