---
description: RAG over FTS5 + entity graph — retrieve, synthesise a cited answer, file it as _queries/<slug>.md
---

`/wiki-query` is a **two-pass** skill (Decision-17): the orchestrator runs
`prepare` (deterministic retrieval), synthesises a cited answer in its own
context via the `wiki-query-synthesis` skill, then runs `apply` (grounding-
checked write-back + self-index). Do **not** call `apply` without first running
`prepare` and synthesising — follow the recipe.

**Workflow location (works from any CWD, incl. a vault):** the workflow file lives in the
obsidian-llm-wiki REPO, not in the current directory — resolve it through this command's own
symlink:

```bash
WF="$(dirname "$(dirname "$(readlink -f ~/.claude/commands/wiki-query.md)")")/workflows/wiki-query.md"
```

Read `$WF` and follow its steps. (Symlink absent → ask the user for the repo path and use
`<repo>/workflows/wiki-query.md` — do NOT improvise the procedure from memory.)

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
