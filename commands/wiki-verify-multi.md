---
description: Off-by-default multi-critic verification of a filed wiki-query answer against its cited sources
---

`/wiki-verify-multi` is an **off-by-default**, **two-pass** skill (Decision-17)
for *high-stakes* answers: the orchestrator runs `prepare` (assemble the answer
+ cited source bodies), runs the four critics in its own context via the
`wiki-verify` skill, then runs `apply` (grounding-checked verdict write-back +
self-index). It is layered **after** a `wiki-query apply`; `wiki-query` never
calls it. Do **not** call `apply` without first running `prepare` and the critics.

**Workflow location (works from any CWD, incl. a vault):** the workflow file lives in the
obsidian-llm-wiki REPO, not in the current directory — resolve it through this command's own
symlink:

1. Run (plain command — pre-allowed, no shell constructs, so no permission prompt):

   ```bash
   readlink -f ~/.claude/commands/wiki-verify-multi.md
   ```

2. The output is `<repo>/commands/wiki-verify-multi.md`. Derive the workflow path YOURSELF (no shell):
   replace `commands/wiki-verify-multi.md` with `workflows/wiki-verify-multi.md`.
3. Open that file with the **Read tool** (not cat) and follow its steps.

Follow the workflow's steps. (Symlink absent → ask the user for the repo path and use
`<repo>/workflows/wiki-verify-multi.md` — do NOT improvise the procedure from memory.)

Quick reference (wrappers at `bin/wiki-verify-multi` handle cd + venv):

```bash
# 1. assemble the verification envelope (answer + cited sources, via pages.file_path)
wiki-verify-multi prepare <query-slug> --vault <id> --vault-root <path>
# 2. (orchestrator) Skill({skill: "wiki-verify"}) → run 4 critics → verdict JSON
# 3. file the verdict (exit 6 on FAIL; the answer is NEVER mutated)
wiki-verify-multi apply --vault <id> --vault-root <path> \
    --verification-slug <slug-from-prepare> --query-slug <query-slug> \
    --answer-hash <hash-from-prepare> --verdict-file <verdict.json>
```

**Exit-code caveat — exit 6 is AMBIGUOUS:** a FAIL verdict returns **exit 6** but the
verdict page IS filed — a SUCCESS envelope (no `error` key), a deliberate divergence
from the family's `6 = error` convention. **The same code 6 also carries
`INVALID_INDEX_DB`** (an *error* envelope, inherited from `build_repo_config`, raised by
both subcommands before any work — nothing examined, nothing filed). So branch on the
presence of an `error` key in the stdout envelope, **never** on `$? == 6`.
`--fail-on=none` removes the *verdict* path to 6 — it does **not** guarantee exit 0.

See `skills/wiki-verify-multi/SKILL.md` for the full flag + exit-code reference.
