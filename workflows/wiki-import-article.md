---
description: PARA construct path — fetch+convert an external source, translate/summarize it (fed the vault's known-concepts), and file the note + concept pages into the obsidian-llm-wiki SQLite index
---

# Workflow: wiki-import-article

The PARA analog of `wiki-enrich`. End-to-end: external source → `_raw/` original →
translated/summarized `article-summary` note in its PARA topic folder → sibling
`_concepts/` entity pages → indexed rows. Composes the external `html2md`/`pdf` skills
(fetch) with this framework's `wiki-extract-concepts` + `wiki-index-upsert` (file/index).

**Decision-17:** the CLI is deterministic plumbing; the ONE reasoning step
(translation / summary) is yours, the orchestrator. **No `import anthropic`.**

## Prerequisites
- Vault registered (`/wiki-init --register-existing`), PARA layout (`obsidian-personal`).
  For Karpathy vaults use `/wiki-enrich`.
- `html2md` + `pdf` skills installed (`~/.claude/skills/{html2md,pdf}/scripts/…`); override
  with `--html2md-bin` / `--pdf-extract-bin`.

## Single-article steps

1. **prepare** — `wiki-import-article prepare --vault <id> --vault-root <abs>
   --source <URL|file> --folder "05 - Материалы/<Topic>" --mode full|summary|thread`.
   - Pick `--folder` by meaning into an EXISTING sibling (no new top-level folders).
   - Mode: digestible web article → `full`; dense paper/long PDF → `summary`; X-thread → `thread`.
   - On `FETCH_FAILED` (exit 10): the source is unreachable/empty (e.g. SSRN paywall) —
     file a `needs-manual` stub by hand and stop for this source.
2. **REASON (you)** — Read `prepare`'s `raw_path` and produce the note JSON
   (`title_ru, tldr, summary_bullets, ru_body?, entities[]`).
   - 🔴 **Inject `prepare.known_concepts`**: reuse an existing concept's `name` when an
     entity matches — never mint a variant. This is the load-bearing discipline (R-6).
   - Each `entities[].quote` MUST be copied verbatim from the Russian text you write.
3. **apply** — pipe the note JSON to `wiki-import-article apply … --note-stdin
   --raw-rel <prepare.raw_path> --source-url <URL> --source-lang en|ru
   --existing-page-slugs '<prepare.existing_page_slugs JSON>'`.
   - It assembles the per-mode note, sanitizes names, guarantees verbatim quotes, runs the
     collision guard, files concept pages (`wiki-extract-concepts apply` with a FRESH hash
     of the written note + the note's own slug as `--source-page`), and indexes the note.
   - Review the manifest's `skipped[]` (collision-guarded candidates) — expected, not an error.
4. **verify** — `wiki-reindex --full` (collisions must stay 0); `wiki-lint` (orphan-link delta
   for this note ≈ 0 — wikilinks resolve because known-concepts were injected).

## Batch path (the DAO/#01 pattern — Workflow tool)

The CLI stays per-article. For a list, drive it with the **Workflow tool**:

1. **Scout-fetch** each source (run `prepare` per source up front; collect the envelopes;
   drop `FETCH_FAILED` ones to a needs-manual list).
2. **Parallel REASON** — one Workflow `agent()` per source under a shared `NOTE_SCHEMA`,
   **each fed its `known_concepts`**. Pure reasoning → no DB writes → safe to parallelize.
3. **Serialized apply** — run `apply` **one source at a time** (a pipeline/loop, NOT
   `parallel`) to avoid SQLite WAL write contention; then ONE `wiki-reindex --full` + `wiki-lint`.

```
// sketch
const envs = sources.map(s => prepareSync(s)).filter(e => e.action === 'prepared')
const notes = await parallel(envs.map(e => () =>
  agent(translatePrompt(e /* incl. e.known_concepts */), {schema: NOTE_SCHEMA})))
for (const [e, note] of zip(envs, notes)) await applySync(e, note)   // serial DB writes
```

## Failure semantics
- `FETCH_FAILED` (10): no `_raw/` written; stub by hand.
- dependency missing / partial (6): a bin is absent, or index/concept-filing failed
  (manifest preserved). Fix the cause and re-run `apply` (idempotent on an unchanged source).
