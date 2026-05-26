---
name: wiki-enrich
description: >-
  Bridge skill — invoke wiki-ingest (file-layer LLM synthesis) on a raw
  source, then mirror the resulting manifest into the SQLite index of this
  obsidian-llm-wiki framework. Use when you have a new source file and want
  it to land in both layers in one shot. Triggers: "enrich the wiki with",
  "ingest and index", "wiki-enrich".
tier: 2
version: 1.0
---

# wiki-enrich

**Purpose**: Single-call bridge from a raw source file all the way to a
queryable row in the SQLite index. Composes two layers:

1. **File layer** — `wiki-ingest` (external skill): performs LLM-driven
   summarization, additive merge of concept/entity pages, append to log.md.
2. **Index layer** — this framework's SQLite repository: indexes every file
   the manifest reports as written, mirrors the structured `log_event` into
   `log_events`.

ADR-001 Option I architecture: wiki-ingest owns the file layer; this skill
indexes the result. ADR-002 §D8 rebuildability holds — the index is
reconstructable from the files via `wiki-reindex --full`.

## When to use

- Operator or sub-agent has a new raw source (markdown / transcript / article
  / paper) and wants it ingested into a registered vault.
- The vault must already be registered (`/wiki-init --register-existing`).
- `wiki-ingest` v1.1+ must be installed on PATH (see
  `docs/WIKI-INGEST-V1.1-CONTRACT.md` for the contract).

## When NOT to use

- File is already inside `_sources/` and you only want to (re)index it →
  use `/wiki-index-upsert` directly.
- You want to register a vault for the first time → use `/wiki-init`.
- You want to rebuild the whole DB → use `/wiki-reindex --full`.

## Invocation

```bash
python -m scripts.wiki_skills.wiki_enrich \
    --vault <vault_id> \
    --vault-root <abs-path-to-vault> \
    --source <abs-path-to-raw-file> \
    [--wiki-ingest-bin wiki-ingest] \
    [--timeout-seconds 600] \
    [--ingest-arg=--course=ZeroOne] \
    [--db-path <override>]
```

Or via the slash command: `/wiki-enrich <args>`.

## Contract

- Verifies `wiki-ingest --version >= 1.1` before running (fail-fast).
- Forwards `--ingest-arg` values verbatim to `wiki-ingest` (for course
  tier, source-kind hints, known-concepts paths, etc.).
- Manifest from `wiki-ingest ingest --output-format json` must satisfy
  `WIKI-INGEST-V1.1-CONTRACT §1`: `status: ok`, `vault_id`, `written[]`,
  `log_event`. Any deviation → `WIKI_INGEST_FAILED` exit 6.
- Every `written[].path` is resolved relative to `vault_root` and gated
  through `validate_inside_vault` (R-26).
- On any per-file upsert failure → `PARTIAL_INDEX_FAILURE` exit 6 with the
  full manifest + index summary preserved for the operator to recover.

## Exit codes & envelopes

| Code | Envelope | Meaning |
|---|---|---|
| `0` | `{"action": "enriched", "ingest": ..., "index": ...}` | Full success: every file upserted + log_event row created |
| `6` | `{"error": "WIKI_INGEST_FAILED", "message": ...}` | wiki-ingest missing / too old / failed / bad manifest / path-traversal |
| `6` | `{"action": "partial", "error": "PARTIAL_INDEX_FAILURE", ...}` | wiki-ingest succeeded but one or more upserts failed |
| `1` | argparse usage error | Missing required flag |

## Related

- [`docs/adr/ADR-001-wiki-ingest-integration.md`](../../docs/adr/ADR-001-wiki-ingest-integration.md)
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../docs/WIKI-INGEST-V1.1-CONTRACT.md)
- [`workflows/wiki-enrich.md`](../../workflows/wiki-enrich.md) — step-by-step
- `wiki-index-upsert` — the underlying per-file upsert called in a loop
- `wiki-append-log` — the path used to mirror `log_event`
