---
id: Q-007-3
type: known-issue
status: documented
opened_at: 2026-05-29
category: quality
slug: q-007-3-apply-question-changed-if-a-retrieval-scope-flag-is-omitted
---

# `apply` QUESTION_CHANGED if a retrieval-scope flag is omitted

- **Symptom**: `apply` must be passed the **same** `--vaults`/`--types`/
  `--project`/`--limit`/`--no-expand-aliases` the operator passed to `prepare`,
  or it reproduces a different retrieval and the hash mismatches → a (correct
  but surprising) `QUESTION_CHANGED`.
- **Root cause**: inherent to the re-retrieval TOCTOU mechanism (Q-007-1).
- **Affected**: `scripts/wiki_skills/wiki_query.py::apply`.
- **Mitigation**: the workflow recipe (`workflows/wiki-query.md` Step 7) +
  `skills/wiki-query/SKILL.md` instruct passing the identical scope flags;
  the orchestrator drives both passes so it controls the flags. A future polish
  could have `prepare` emit the scope and `apply` accept a single
  `--from-prepare <json>` to eliminate the footgun.
