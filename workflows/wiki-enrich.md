---
description: Ingest a raw source via wiki-ingest, then index the resulting files into the obsidian-llm-wiki SQLite database
---

# Workflow: wiki-enrich

End-to-end pipeline from raw source → markdown pages on disk → indexed rows
in SQLite. Composes the external `wiki-ingest` skill (file layer) with this
framework's `wiki-index-upsert` + `wiki-append-log` (index layer).

## Prerequisites

- `wiki-ingest` v1.1+ on PATH (verify via `wiki-ingest --version`).
- Vault already registered: `/wiki-init --register-existing --vault <path>`
  has been run; `vaults` table has the row.
- The raw source file is readable and lives anywhere (does not need to be
  inside the vault — wiki-ingest will copy/transform it into `_sources/`).

## Steps

1. **Pre-flight**
   - Parse `--vault`, `--vault-root`, `--source` from invocation. All three
     required.
   - Resolve absolute paths via `Path.resolve(strict=True)`.
   - Verify `wiki-ingest --version >= 1.1`; abort with `WIKI_INGEST_FAILED`
     envelope (exit 6) on missing binary or older version.

2. **Run wiki-ingest**
   - Invoke `wiki-ingest ingest --source <abs> --vault <vault-root>
     --output-format json` (plus any pass-through `--ingest-arg` values).
   - Subprocess timeout: 600s default, configurable via `--timeout-seconds`.
   - Non-zero exit → `WIKI_INGEST_FAILED` (exit 6) with stderr captured.

3. **Validate manifest** (per `docs/WIKI-INGEST-V1.1-CONTRACT.md §1`)
   - `status == "ok"`
   - `vault_id == --vault` (no mismatch per ADR-002 §D1.1)
   - `written` is a list; each entry has `path`
   - Every `written[].path` resolves inside `vault_root`
     (R-26 / `validate_inside_vault`)

4. **Index each written file**
   - For each `entry in manifest.written`:
     - `python -m scripts.wiki_skills.wiki_index_upsert
       --vault <vault_id> --vault-root <root> --source <vault_root>/<path>`
     - Capture stdout JSON envelope; treat exit-non-zero or `"error"` key
       as failure.
   - Collect successes and failures separately.

5. **Mirror log_event into log_events**
   - If `manifest.log_event` is present AND no upsert failures: insert a
     `LogEvent` row with the manifest's event_ts / event_type / subject and
     the `log_md_byte_offset` for round-trip with log.md.
   - If any upsert failed: skip log_event insertion (operator must
     recover-and-retry; partial-failure envelope contains the manifest).

6. **Emit summary**
   - On full success: `{"action": "enriched", "vault_id": ..., "ingest":
     <manifest>, "index": {"upserted": [...], "log_event_id": N}}` (exit 0).
   - On partial: `{"action": "partial", "error": "PARTIAL_INDEX_FAILURE",
     "ingest": <manifest>, "index": {"failed": [...], "upserted": [...]}}`
     (exit 6).

## Fallback (sequential, non-Claude-Code vendors)

Same flow, just run the steps manually:

```bash
wiki-ingest ingest --source $SRC --vault $VAULT --output-format json > /tmp/m.json
jq '.written[].path' /tmp/m.json | while read rel; do
  python -m scripts.wiki_skills.wiki_index_upsert \
      --vault $VID --vault-root $VAULT --source "$VAULT/$rel"
done
python -m scripts.wiki_skills.wiki_append_log --vault $VID \
    --event-type ingest --subject "$(jq -r '.log_event.subject' /tmp/m.json)"
```

The Python implementation in `scripts/wiki_skills/wiki_enrich.py` packages
this whole flow as a single CLI.

## Integration

Called from:
- `/wiki-enrich` (operator-facing slash command)
- Future bulk-ingest pipelines (loop over a folder of raw sources)
- VDD developer agents when they finish a transcript / spec and need it in
  the vault before the next phase
