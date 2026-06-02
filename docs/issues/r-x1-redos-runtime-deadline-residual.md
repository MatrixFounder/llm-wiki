---
id: R-X1-REDOS-RT
type: known-issue
status: fixed
opened_at: 2026-06-01
category: security
severity: SEV-2
slug: r-x1-redos-runtime-deadline-residual
---

# ReDoS load-gate residual — no per-file runtime regex deadline

- **Symptom**: The PW-D ReDoS gate (`layout_config._redos_budget_check`) validates operator-supplied `ref_extraction[].regex` + `paths[].project_pattern` against a battery of short adversarial payloads at config-load. A pattern that is linear on those short payloads but catastrophic only on **long real file content** (e.g. a 100 KB single-line body) is NOT caught — stdlib `re` has no timeout, so `extract_refs`/`_derive_project` could hang `wiki-reindex` on a crafted page.
- **Root cause**: A load-time synthetic gate cannot be complete; the only sound mitigation is a runtime deadline at the consumer.
- **Affected components**: `scripts/wiki_index/layout_config.py` (`_redos_budget_check`, `_derive_project`), `scripts/wiki_source/parsing.py` (`extract_refs`).
- **Fix plan**: Add a per-file wall-clock deadline (signal.alarm on the main thread, or a worker with a deadline) so a slipped-through pattern degrades to "skip this file with a WARN" instead of hanging the reindex. Or adopt a linear-time engine (`regex`/RE2) for operator patterns. Deferred: built-in layout patterns are pre-vetted; the threat is operator-custom configs.
- **Prevention**: diversified load-time payload battery (shipped) catches the common pattern *shapes*; this residual is the content-length-dependent tail.
