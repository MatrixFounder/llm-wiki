<!-- Sync with scripts/wiki_skills/wiki_extract_concepts.py argparse on every change. -->
---
name: wiki-extract-concepts
description: >-
  LLM-driven concept extraction from an already-indexed source summary page.
  Reads the page body, calls Claude Sonnet 4.6 to identify candidate
  concepts, de-duplicates against existing entities, writes
  `_concepts/<slug>.md` pages, and emits a wiki-ingest v1.1-compatible
  manifest. Optionally indexes the manifest in-process via `--ingest`.
  Triggers: "extract concepts from", "populate entity layer for".
tier: 2
version: 1.0
---

# wiki-extract-concepts

**Purpose**: Activate the entity layer (Epic 7 R-3 entry-point) on a
specific source page that's already in the vault. The skill is the
"synthesis step" for the concept layer — it does NOT call `wiki-ingest`
(that's `/wiki-enrich`'s job for raw-source synthesis). Concept-page
derivation from already-summarised pages is this skill's responsibility
(Decision-8).

## When to use

- A source page (type=`summary`/`lesson-summary`/`meeting-summary`) is
  already indexed in the vault via `/wiki-enrich` or `/wiki-index-upsert`.
- You want LLM-extracted concept entities written to `_concepts/<slug>.md`
  and recorded in the `entities` table with `is_candidate=1`.
- `ANTHROPIC_API_KEY` is set in the environment.

## When NOT to use

- Source page is not yet indexed → run `/wiki-enrich --source ...` first.
- You want to register a vault → use `/wiki-init`.
- You want to promote a candidate to confirmed (`is_candidate=0`) → that's
  the future R-4 `wiki-confirm` CLI (deferred per Decision-7).
- You need batch extraction across many sources → script it externally
  (loop the slash command per source).

## Invocation

Two modes — inspection (manifest only) and auto-dispatch (in-process index):

```bash
# Inspection mode — manifest to stdout, no DB index mirror
python -m scripts.wiki_skills.wiki_extract_concepts \
    --vault <vault_id> \
    --vault-root <abs-path-to-vault> \
    --source-page <slug-or-rel-path> \
    [--model claude-sonnet-4-6] \
    [--max-tokens 4096] \
    [--db-path <override>]

# Auto-dispatch mode — manifest emitted + in-process index_from_manifest
python -m scripts.wiki_skills.wiki_extract_concepts \
    --vault <vault_id> \
    --vault-root <abs-path-to-vault> \
    --source-page <slug> \
    --ingest
```

Or via the slash command: `/wiki-extract-concepts <args>`.

## Contract

- Reads `entities LEFT JOIN entity_aliases WHERE vault_id=?` before any LLM
  call (R-32). Passes canonical names as known-concepts to the LLM so it
  de-duplicates server-side.
- Calls Claude Sonnet 4.6 at `temperature=0` for reproducibility (R-33).
- Writes `_concepts/<slug>.md` atomically (tempfile + rename) with
  frontmatter declaring `is_candidate: true`, `trust_level: medium`,
  `vault_id`, `source_page` (R-36).
- All new `entities` rows land with `is_candidate=1`; existing confirmed
  entities (`is_candidate=0`) are never downgraded (R-37).
- All `page_entity_refs` rows carry `trust_level='medium'`, `source_quote`
  (10-50 words from the body), and `line_start`/`line_end` parsed from the
  LLM's `"Lstart-Lend"` source-span format (R-38, Decision-10).
- Idempotent: re-running with unchanged source body returns
  `{"status": "ok", "action": "unchanged", "manifest": null}` and makes
  zero LLM calls (R-39, hash compared against `source_state` row).
- Multi-vault: every DB query carries `vault_id=?`; concept pages are
  written under the caller's `--vault-root` only (R-40, ADR-002 §D1.1).

## Architecture note (Decision-15 + Decision-16)

The `--ingest` auto-dispatch path is **in-process** — it imports
`validate_manifest`, `index_from_manifest`, and `WikiIngestError` from the
neutral module `scripts.wiki_skills._manifest_consumer` and calls them
directly. No subprocess. No CLI-flag dispatch on `wiki-enrich` (that path
was retracted by Decision-15; the v1 R-44 / I-7.15 flags are dropped).
The neutral module exists so this skill does not depend on `wiki_enrich`
(which would have been a skill-to-skill coupling smell).

## Exit codes & envelopes

| Code | Envelope | Meaning |
|---|---|---|
| `0` | manifest JSON (no `--ingest`) or `{"extraction": ..., "index": ...}` (with `--ingest`) | Full success |
| `0` | `{"status": "ok", "action": "unchanged", "manifest": null}` | Idempotency short-circuit — source hash unchanged |
| `1` | argparse usage error | Missing required flag |
| `2` | `{"error": "SOURCE_NOT_FOUND", ...}` | `--source-page` does not resolve inside `--vault-root` |
| `3` | `{"error": "LLM_API_UNAVAILABLE", ...}` | Anthropic SDK unreachable or auth failed (after 1 retry) |
| `4` | `{"error": "EXTRACTION_PARSE_ERROR", "details": {"raw_response": ...}}` | LLM returned malformed JSON |
| `5` | `{"action": "partial", "error": "PARTIAL_INDEX_FAILURE", "extraction": ..., "index": ...}` | `--ingest` set; some concept pages written but indexer failed for some (operator can roll back files listed in `summary.failed[]`) |
| `6` | `{"error": "MANIFEST_INVALID", ...}` | `validate_manifest` rejected the manifest (path-traversal, vault_id mismatch, missing field) |

## Related

- [`docs/TASK.md`](../../docs/TASK.md) — TASK 003 v2 spec
- [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §2.1 Concept Extractor component, §3.4 UC-08 sequence
- [`docs/adr/ADR-001-wiki-ingest-integration.md`](../../docs/adr/ADR-001-wiki-ingest-integration.md) — Option I (clarified by Decision-8)
- [`docs/adr/ADR-002-multi-vault-bottleneck-corrections.md`](../../docs/adr/ADR-002-multi-vault-bottleneck-corrections.md) — Class A/B/C layering
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../docs/WIKI-INGEST-V1.1-CONTRACT.md) — manifest schema this skill emits
- `wiki-enrich` — the bridge skill for raw-source ingestion (different layer)
- `wiki-search` — query the resulting entity layer via FTS5
