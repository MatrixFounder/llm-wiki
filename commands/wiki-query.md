---
description: RAG over FTS5 + entity graph — retrieve, synthesise a cited answer, file it as _queries/<slug>.md
---

`/wiki-query` is a **two-pass** skill (Decision-17): the orchestrator runs
`prepare` (deterministic retrieval), synthesises a cited answer in its own
context via the `wiki-query-synthesis` skill, then runs `apply` (grounding-
checked write-back + self-index). Do **not** call `apply` without first running
`prepare` and synthesising — follow the recipe.

Execute the workflow at [`workflows/wiki-query.md`](../workflows/wiki-query.md).

Quick reference (wrappers at `bin/wiki-query` handle cd + venv):

```bash
# 1. retrieve
wiki-query prepare "<question>" --vault <id> --vault-root <path>
# 2. (orchestrator) Skill({skill: "wiki-query-synthesis"}) → answer + citations JSON
# 3. file
echo "$ANSWER" | wiki-query apply --vault <id> --vault-root <path> \
    --query-slug <slug> --question "<question>" --question-hash <hash> \
    --answer-stdin --citations-file <cites.json>
```

See `skills/wiki-query/SKILL.md` for the full flag + exit-code reference.
