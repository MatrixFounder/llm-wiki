---
description: Typed-knowledge extraction (RFC-004) — prepare (recon + the ontology contract) → orchestrator synthesises candidates → apply (validates against the ontology, then writes typed pages + edges). See `workflows/wiki-extract-decisions.md` for the full recipe.
---

Two-pass orchestrator workflow (TASK 063 / RFC-004, Decision-17).
**Workflow location (works from any CWD, incl. a vault):** the workflow file lives in the
obsidian-llm-wiki REPO, not in the current directory — resolve it through this command's own
symlink:

```bash
WF="$(dirname "$(dirname "$(readlink -f ~/.claude/commands/wiki-extract-decisions.md)")")/workflows/wiki-extract-decisions.md"
```

Read `$WF` and follow its steps. (Symlink absent → ask the user for the repo path and use
`<repo>/workflows/wiki-extract-decisions.md` — do NOT improvise the procedure from memory.).

The CLI is deterministic and **never calls an LLM** — the orchestrator owns
the REASON step. The prompt/contract lives in
`.agent/skills/decision-extraction/SKILL.md` (loaded via `Skill({skill:
"decision-extraction"})` at workflow Step 4, gated by the H-5 integrity check).

Bash entry points:

```bash
wiki-extract-decisions prepare --vault X --vault-root Y --source-page Z

# → the orchestrator reads the source body + the emitted ONTOLOGY CONTRACT
#   (class roster, edge domain/range, per-class status enums), synthesises
#   candidates JSON, then:

wiki-extract-decisions apply --vault X --vault-root Y --source-page Z \
                             --source-hash <the hash prepare emitted> \
                             --candidates-stdin [--ingest]
```

Key invariants (see the workflow for the full recipe + exit-code table):

- **`prepare` REFUSES EARLY (G4).** A layout that maps no typed classes — or a
  configured folder invisible to the layout's read globs — is refused before any
  reasoning, because a glob-invisible page is written, never indexed, and raises
  no lint issue.
- **`apply` is atomic.** Any contract violation ⇒ **exit 4 and ZERO files
  written** — a partial typed batch would assert edges to pages that do not exist.
- **An empty result is a SUCCESS** (`action: no_candidates`, exit 0). A note with
  no decisions is a normal note.

See `skills/wiki-extract-decisions/SKILL.md` (if present) or the workflow for the
full subcommand reference, exit codes, and manifest contract.
