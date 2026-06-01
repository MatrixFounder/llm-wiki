---
id: D-1
type: known-issue
status: documented
opened_at: 2026-05-26
category: security
slug: d-1-assert-no-symlink-escape-limited-on-unix
---

# assert_no_symlink_escape limited on Unix

- **Symptom**: Function walks `Path.parent` lexically and checks `target.is_relative_to(p.anchor)`. On Unix `anchor = "/"` so the escape check can never trigger; loop detection unreachable (parent chain never revisits).
- **Root cause**: Defensive primitive whose strong form would need an FD-based, kernel-mediated walk.
- **Affected components**: `scripts/wiki_index/security.py`.
- **Fix plan**: Documented as a sanity rail (called from `reindex_delta`); primary R-26 protection is `validate_inside_vault` in `manual.fetch`. No code change beyond docstring honesty.
