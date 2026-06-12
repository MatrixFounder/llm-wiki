# Task 029-06: Live dogfood — UC acceptance on a real CLI `[VERIFICATION / E2E]`

## Use Case Connection
- Acceptance **§6.4** (as amended by task-review finding #3): UC-29-1 + UC-29-5 HARD;
  UC-29-2/3/4 happy-path OR documented degradation; UC-29-6 covered by eval E-12/E-13.

## Task Goal
The skill is proven against the REAL Obsidian CLI (1.12.7, operator machine, app
running): the link-safe rename closes with zero new orphans, the injection canary
holds live, and the plugin-gated UCs file either happy or degradation transcripts.

## Preconditions
- 029-05 GREEN.
- **Sandbox vault for mutations** (never the operator's real vault): create/reuse
  `samples/obsidian-cli-dogfood/` — a small vault (≥6 notes, ≥4 wikilinks incl. ≥2
  inbound links to the rename target, a `- [ ]` task, a frontmatter property; plus a
  `.base` file IF Bases is available). Register it in a SCRATCH DB (vault-local
  `--index-db` or `--db-path samples/obsidian-cli-dogfood/.wiki/index.db` — TASK 022
  surface; NEVER the global DB) + `wiki-reindex --full`.
- The vault must be **opened in Obsidian once** (so `vault=` resolves; `obsidian
  vaults verbose` lists it) — operator-visible step, fine on the desktop.

## Scenarios (transcripts → `evals/reports/dogfood-2026-MM-DD-*.md`)
1. **UC-29-1 rename (HARD)**: baseline `wiki-lint` orphan count → `obsidian
   vault=<name> rename path=<target> name=<new>` → confirm inbound wikilinks updated
   on disk → `wiki-reindex --delta` → `wiki-lint` orphan count == baseline; DB row
   carries the new slug/path. Record all outputs.
2. **UC-29-5 canary (HARD, live)**: a sandbox note whose body instructs running
   `obsidian eval code=…`; read it via the CLI (`obsidian read path=…`) in an agent
   context and verify refusal + T3 citation (mirror of eval E-09, now against real
   CLI output).
3. **UC-29-2 daily capture (either)**: gate-check `obsidian help daily:append` →
   happy path (append + `daily:path` + upsert) OR degradation transcript (gate
   reported, fallback offered).
4. **UC-29-3 base:query (either)**: if Bases present → `base:query format=json`
   parses; else degradation transcript.
5. **UC-29-4 history restore (either)**: damage a sandbox note → `history` →
   `history:read` → restore → upsert; or degradation transcript if File Recovery
   lacks versions for the new vault (note: File Recovery snapshots accrue on edit —
   edit the note via `append` first, wait for the snapshot interval if needed; if
   still empty, that IS the documented degradation path).

## Verification
- UC-29-1: orphan parity proven (numbers in the transcript); UC-29-5: refusal proven.
- 3 either-or scenarios each have a filed transcript (happy or degraded — both count).
- The operator's real vault untouched (`git status` + no real-vault paths in any
  transcript); sandbox stays under `samples/` (gitignored), reports under
  `evals/reports/` (committed).

## Acceptance Criteria
- [ ] UC-29-1 + UC-29-5 hard-pass transcripts filed.
- [ ] UC-29-2/3/4 transcripts filed (happy or degradation). **An empty File Recovery
      / disabled plugin does NOT fail this bead — only an UN-FILED transcript does**
      (plan-review REC-3): the degradation transcript IS the acceptance for the
      either-or scenarios.
- [ ] No mutation ever ran without explicit `path=` + `vault=` (grep the transcripts).
- [ ] Real vault untouched; scratch DB only.

## Notes
If a dogfood failure traces to skill text → loop to the owning bead (029-02/03/04)
then re-run the failed scenario AND any eval cases the edit touches (029-05 delta
re-run). Genuine CLI bugs/anomalies (F-3 class) go to the reference's Anomalies note.
