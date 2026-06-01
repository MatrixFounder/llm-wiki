---
id: H-PERF-3
type: known-issue
status: open
opened_at: 2026-05-28
category: security
severity: SEV-2
slug: h-perf-3-index-from-manifest-argparse-in-loop
---

# index_from_manifest argparse-in-loop

- **Symptom**: For each of up to 25 written concept pages per source, `_manifest_consumer.index_from_manifest` calls `wiki_index_upsert.main(argv)` which **re-parses argparse**, opens fresh `make_repo`, runs PRAGMA sweep, parses frontmatter, writes, closes — all per row. At 25 candidates × 1000 source pages = 25,000 argparse calls + connection cycles.
- **Root cause**: Subprocess-style invocation pattern reused in-process for "compatibility"; the supposedly-fast in-process path still does subprocess-shaped per-row work.
- **Affected components**: `scripts/wiki_skills/_manifest_consumer.py:91-139`, `scripts/wiki_skills/wiki_index_upsert.py` (only exposes `main(argv)`).
- **Fix plan**: Expose `wiki_index_upsert._upsert_one(parsed_args, repo)` as the programmatic entry point. Loop calls that, not `main(argv)`. Eliminates ~30-60s wall-clock per 1000 pages.
