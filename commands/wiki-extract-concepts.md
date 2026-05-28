---
description: Two-pass concept extraction — prepare (recon) → orchestrator synthesises candidates → apply (writes pages + entities + manifest). See `workflows/wiki-extract-concepts.md` for the full 7-step recipe.
---

Two-pass orchestrator workflow (TASK 003 v3.1, Decision-17).
Read and execute the workflow defined in
`workflows/wiki-extract-concepts.md`.

The skill is now deterministic: the orchestrator owns the synthesis step.
The Python skill provides two subcommands (`prepare` + `apply`) and the
matching prompt/contract lives in
`.agent/skills/concept-extraction/SKILL.md` (loaded via `Skill({skill:
"concept-extraction"})` at workflow Step 4).

> ⚠️ **BREAKING CHANGE vs v2**: the single-command invocation
> `wiki-extract-concepts --vault X --source-page Y` is no longer
> accepted. Run `wiki-extract-concepts prepare --help` /
> `wiki-extract-concepts apply --help` for the new surface, or follow
> the workflow above.

Bash entry points:

```bash
wiki-extract-concepts prepare --vault X --vault-root Y --source-page Z
wiki-extract-concepts apply   --vault X --vault-root Y --source-page Z \
                              --source-hash <prepare-hash> --candidates-stdin \
                              [--orchestrator-id ID] [--ingest]
```

`bin/wiki-extract-concepts` cd's into the repo and activates its venv, so
this works from any CWD as long as the repo's `bin/` is on `PATH`
(see `bin/install-globally.sh`). See `skills/wiki-extract-concepts/SKILL.md`
for the full subcommand reference, exit codes, and manifest contract.
