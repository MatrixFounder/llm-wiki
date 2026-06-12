# Task 029-04: Recipes — composed playbooks `[LOGIC IMPLEMENTATION]`

## Use Case Connection
- RTM **R-029-6** (a/b/c); UC-29-1/2/3/4 main scenarios in recipe form; coherence invariant.

## Task Goal
`references/recipes.md` carries ≥8 end-to-end playbooks, each immediately executable
by any LLM agent: preconditions → exact commands → coherence step → failure handling.

## Changes Description

### File: `skills/obsidian-cli/references/recipes.md` (replace TODO)
The 8 recipes (headers were scaffolded in 029-00):
1. **Link-safe rename/move** — verify vault identity → `rename`/`move` with explicit
   `path=`+`vault=` → `wiki-reindex --delta` → `wiki-lint` orphan parity spot-check.
   Failure: name collision → report verbatim, never force (UC-29-1 A3); precondition:
   "Automatically update internal links" ON (TASK A-3 — verify once per vault).
2. **Capture to daily note** — gate-check `obsidian help daily:append` →
   `daily:append content=…` → resolve via `daily:path` → upsert. Fallback: plugin
   off → `append path=<computed>` or report (UC-29-2 A1).
3. **Task sweep** — `tasks todo format=json` (bounded `path=`/`file=` scope) →
   `task ref=<path:line> done` per item → upsert touched files.
4. **Base → JSON analysis** — `bases` → `base:views path=…` → `base:query view=…
   format=json` → analyse in-context; no mutation ⇒ no coherence step (UC-29-3).
5. **Property migration** — `properties counts` survey → `property:set name=… value=…
   type=…` per file (explicit `path=`) → upsert each.
6. **History recovery** — `history path=…` → `history:read version=N` → SHOW the
   operator / diff → confirm → `history:restore version=N` → upsert (UC-29-4;
   autonomous runs STOP before restore).
7. **Vault audit** — `orphans total` + `deadends total` + `unresolved counts` vs
   `wiki-lint` orphan/dangling output; reconcile discrepancies (app counts links
   live; wiki-lint counts the indexed view).
8. **Workspace/session setup** — `workspace`, `tabs`, `tab:open`, `open path=…
   newtab` (T1-UX; no coherence step).

Formatting rules (binding):
- Every mutating command line carries explicit `path=` AND `vault=` (R-029-6c).
- Every recipe ends with either a "Coherence" block (registered vault) or an explicit
  "No mutation — no coherence step" line.
- Machine-readable outputs request `format=json` ONLY where the reference (029-03)
  says the command supports it; otherwise the documented default + a parse note (R-029-5e).

## Verification
- Recipe checklist: 8/8 present, each with the 4 blocks (preconditions / commands /
  coherence-or-none / failure handling).
- Grep guards (record commands + zero-hit proof):
  - no mutating example without `path=` — e.g.
    `grep -nE 'obsidian .*(rename|move|append|prepend|create|delete|property:set|task )' references/recipes.md | grep -v 'path='` → empty (adapt the mutating-verb list to the final text; the acceptance is the property, record the actual command).
  - `grep -n 'format=json' recipes.md` rows cross-checked against 029-03 format columns.
- `grep -c 'TODO 029-04'` == 0.

## Acceptance Criteria
- [ ] ≥8 recipes, 4 blocks each.
- [ ] Explicit-target grep guard passes; coherence block present or explicitly waived per recipe.
- [ ] `format=` usage agrees with the 029-03 reference.

## Notes
Recipes 1/2/4/6 are the dogfood scripts for 029-06 — keep their command sequences
copy-paste runnable against a sandbox vault.
