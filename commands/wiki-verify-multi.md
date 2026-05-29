---
description: Off-by-default multi-critic verification of a filed wiki-query answer against its cited sources
---

`/wiki-verify-multi` is an **off-by-default**, **two-pass** skill (Decision-17)
for *high-stakes* answers: the orchestrator runs `prepare` (assemble the answer
+ cited source bodies), runs the four critics in its own context via the
`wiki-verify` skill, then runs `apply` (grounding-checked verdict write-back +
self-index). It is layered **after** a `wiki-query apply`; `wiki-query` never
calls it. Do **not** call `apply` without first running `prepare` and the critics.

Execute the workflow at [`workflows/wiki-verify-multi.md`](../workflows/wiki-verify-multi.md).

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

**Exit-code caveat:** a FAIL verdict returns **exit 6** but the verdict page IS
filed — this is a SUCCESS envelope (no `error` key), a deliberate divergence
from the family's `6 = error` convention. Branch on the stdout `verdict` field,
not on `$?`. `--fail-on=none` → always exit 0.

See `skills/wiki-verify-multi/SKILL.md` for the full flag + exit-code reference.
