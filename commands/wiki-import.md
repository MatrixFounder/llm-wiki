---
description: Import an external source (article / paper / X-thread / meeting transcript / finished summary) into the vault — fetch+convert, detect content-type, REASON (summarizing-meetings), file the note + concept pages per the vault's layout, index. Works for any layout (Karpathy or PARA).
---

Read and execute the workflow defined in `workflows/wiki-import.md`.

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
