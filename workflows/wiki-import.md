---
description: Unified construct path — fetch+convert an external source, detect its content-type, REASON it (the universal summarizing-meetings harness, fed the vault's known-concepts), and file the note + concept pages per the vault's layout into the obsidian-llm-wiki SQLite index. Any layout (Karpathy or PARA).
---

# Workflow: wiki-import

The **unified construct path**. End-to-end: external source → `_raw/` original →
translated/summarized note → its `_concepts/` entity pages → indexed rows. Two **orthogonal**
axes: **content-type** (`--kind`, auto-detected) sets the note type + what the REASON harness
emphasizes; **layout (config)** decides where it files — Karpathy (`_sources/` + root
`_concepts/`) vs PARA (topic folder + sibling `_concepts/`), via `resolve_layout_config`.
Composes the external `html2md`/`pdf` skills (fetch) with this framework's
`wiki-extract-concepts` + `wiki-index-upsert` (file/index).

**Decision-17:** the CLI is deterministic plumbing; the ONE reasoning step (the
content harness) is yours, the orchestrator. **No `import anthropic`.**

## Prerequisites
- Vault registered (`/wiki-init --register-existing`). **Any layout** — the filing target is
  read from config; you do not choose Karpathy-vs-PARA here. (Legacy Karpathy-raw `wiki-enrich`
  still exists but `wiki-import` is the config-driven successor.)
- `html2md` + `pdf` skills installed (`~/.claude/skills/{html2md,pdf}/scripts/…`); override
  with `--html2md-bin` / `--pdf-extract-bin`.

## Single-source steps

1. **prepare** — `wiki-import prepare --vault <id> --vault-root <abs>
   --source <URL|file> --folder "<topic folder>" --kind auto --mode full|summary|thread`.
   - `--folder` = an EXISTING vault folder (PARA topic, or `_sources` for karpathy). No new top-levels.
   - `--kind auto` detects content-type (meeting / article / paper / thread / summary) and reports
     `kind` + `reason_harness` + `kind_confidence` in the envelope; pass `--kind <X>` to override.
   - On `FETCH_FAILED` (exit 10): source unreachable/empty (e.g. SSRN paywall) → file a
     `needs-manual` stub by hand and stop for this source.
2. **REASON (you)** — run the harness `prepare` reported (`reason_harness` =
   **`summarizing-meetings`** for all content-types; `none` for a finished `summary`). Read
   `prepare`'s `raw_path` and produce the note JSON (`title_ru, tldr, summary_bullets, ru_body?, entities[]`).
   - 🔴 **Inject `prepare.known_concepts`**: reuse an existing concept's `name` when an entity
     matches — never mint a variant. The load-bearing discipline (R-6).
   - Each `entities[].quote` MUST be copied verbatim from the text you write.
3. **apply** — pipe the note JSON to `wiki-import apply … --kind <prepare.kind> --note-stdin
   --raw-rel <prepare.raw_path> --source-url <URL> --source-lang en|ru
   --existing-page-slugs '<prepare.existing_page_slugs JSON>'`.
   - It files the note **per the resolved layout** + sets the note `type:` from `--kind`
     (layout-safe), sanitizes names, guarantees verbatim quotes, runs the collision guard, files
     concept pages (`wiki-extract-concepts apply` with a FRESH hash of the written note + the
     note's rel path as `--source-page`), and indexes the note.
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
