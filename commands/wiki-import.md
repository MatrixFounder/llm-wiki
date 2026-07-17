---
description: Import an external source (article / paper / X-thread / meeting transcript / finished summary) into the vault — fetch+convert, detect content-type, REASON (summarizing-meetings), file the note + concept pages per the vault's layout, index. Works for any layout (Karpathy or PARA).
---

**Workflow location (works from any CWD, incl. a vault):** the workflow file lives in the
obsidian-llm-wiki REPO, not in the current directory — resolve it through this command's own
symlink:

1. Run (plain command — pre-allowed, no shell constructs, so no permission prompt):

   ```bash
   readlink -f ~/.claude/commands/wiki-import.md
   ```

2. The output is `<repo>/commands/wiki-import.md`. Derive the workflow path YOURSELF (no shell):
   replace `commands/wiki-import.md` with `workflows/wiki-import.md`.
3. Open that file with the **Read tool** (not cat) and follow its steps.

Follow the workflow's steps. (Symlink absent → ask the user for the repo path and use
`<repo>/workflows/wiki-import.md` — do NOT improvise the procedure from memory.)

Follow all steps sequentially. Apply all Global Protocols
(skill-archive-task, skill-session-state) where relevant.

User's task context:
$ARGUMENTS

## The typed-knowledge dispatch marker (TASK 063)

When the folder's `.wiki/sync.yaml` enables it, the `apply` envelope carries:

```jsonc
"extract_decisions": {
  "tool": "wiki-extract-decisions",
  "source": "06 - BD/Acme/protokol.md",
  "dirs": {"decision": "Решения", "requirement": "requirements", "risk": "Риски"}
}
```

**If that key is present, run the rail as a SECOND STEP** — `wiki-import` never does:

```bash
wiki-extract-decisions prepare --vault X --vault-root Y --source-page <source>
# → load the `decision-extraction` skill, read the note, synthesise candidates
wiki-extract-decisions apply   --vault X --vault-root Y --source-page <source> \
                               --source-hash <hash> --candidates-stdin --ingest
```

The key is **ABSENT** — not `false` — when the rail is not enabled. Nothing to do then.

This is the same shape as `wiki-sync` delegating to `wiki-import`: the CLI is
deterministic plumbing, the orchestrator owns the reasoning step (Decision-17).
