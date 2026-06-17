<!-- Sync with scripts/wiki_skills/wiki_extract_concepts/__init__.py argparse (_build_parser_v3) on every change. TASK 016: this module is now a package (facade __init__ + _validation/_sourcing/_db/_pages/_errors leaves). -->
---
name: wiki-extract-concepts
description: >-
  Deterministic concept-extraction skill (v3.1). Two subcommands —
  `prepare` (recon + idempotency check) and `apply` (consume operator-
  synthesised candidates JSON; write _concepts/<slug>.md pages, upsert
  entity rows, emit a wiki-ingest v1.1 manifest, optionally dispatch
  in-process via --ingest). The orchestrator owns the synthesis step
  (Decision-17): there is no `import anthropic` in this skill.
  Triggers: "extract concepts from", "populate entity layer for".
tier: 2
version: 3.1
---

# wiki-extract-concepts (v3.1)

> ⚠️ **BREAKING CHANGE (v2 → v3.1) — operator-facing CLI surface**
>
> - v2: `wiki-extract-concepts --vault X --vault-root P --source-page Y [--ingest]`
> - v3.1: `wiki-extract-concepts prepare ...` **AND** `wiki-extract-concepts apply ...`
>
> The legacy single-command invocation (no subcommand) now errors out at
> argparse with help text pointing at the new surface. Every existing
> script, shell alias, agent prompt, or muscle-memory invocation using
> the v2 form will break. **Migration**: run `prepare` to get a source
> hash, synthesise candidates in your orchestrator context, then run
> `apply --source-hash <hash> --candidates-stdin`. No shim is provided
> — the CLI surface change is intentional (TASK 003 v3.1 / Decision-17).

**Purpose**: Activate the entity layer (Epic 7 R-3 entry-point) on a
specific source page that's already in the vault. The skill is the
deterministic plumbing for the v3.1 two-pass workflow:

1. `prepare` — read the source body, compute its sha256, query
   `source_state` for `is_unchanged`, load the vault's known concepts,
   sweep for disk/DB drift, emit a JSON envelope.
2. (orchestrator) — synthesise candidates JSON per the
   `concept-extraction` skill's contract.
3. `apply` — re-read the source, hash-check against the supplied
   `--source-hash`, validate the candidates payload, write
   `_concepts/<slug>.md` pages, upsert entity rows + refs, emit the
   manifest, optionally dispatch via `--ingest`.

End-to-end workflow lives at [`workflows/wiki-extract-concepts.md`](../../workflows/wiki-extract-concepts.md).
The prompt + JSON contract for the synthesis step lives in the
[`concept-extraction`](../../.agent/skills/concept-extraction/SKILL.md)
skill.

### Layout-awareness (TASK 037)

The skill is **layout-aware** — it works on Karpathy AND PARA (`obsidian-personal`)
vaults, resolving the source page and the `_concepts/` output dir per the vault's layout
(same precedent as `wiki-index-upsert`, TASK 024):

- **Karpathy** — the source is a `_sources/<slug>.md` page (slug = stem); concept pages
  land in the sibling `_concepts/` (`<…>/_sources/x.md` → `<…>/_concepts/`). Byte-identical
  to pre-037.
- **PARA / `obsidian-personal`** — pass `--source-page` as the note's **vault-relative
  path** (a content note in its own folder, NOT under `_sources/`). Its slug is derived
  via the layout slug_strategy (preserve-unicode → matches `pages.slug`, so the entity
  refs FK and inbound `[[Wikilink]]` targets resolve), and concept pages land in a
  `_concepts/` **sibling of that note** (`05 - Материалы/<area>/_concepts/<slug>.md`).
  Slugs may be Unicode (Cyrillic/CJK). The target layout must map `type: concept`
  (obsidian-personal does as of TASK 037).
- **Anti-loop (H-1)**: a source resolving inside a generated dir
  (`_concepts/_entities/_queries/_verifications/`, case-insensitively) is refused with
  `INVALID_SOURCE_PATH` — extraction never runs on its own output.

`entities.file_path` and the manifest `written[].path` carry the **real** vault-relative
concepts path (vault-tier `_concepts/<slug>.md` stays byte-identical; course-tier / PARA
get their nested path).

## `prepare` subcommand

```bash
wiki-extract-concepts prepare \
    --vault <vault-id> \
    --vault-root <path> \
    (--source-page <slug-or-relative-path> | --batch <slugs.json>) \
    [--known-concepts-format {full,slugs-only}] \
    [--db-path <override>]
```

| Flag | Required | Notes |
|---|---|---|
| `--vault` | yes | vault_id; must be registered in `vaults` |
| `--vault-root` | yes | absolute path; resolved with `strict=True` |
| `--source-page` | mutex | kebab slug OR vault-relative path (XOR `--batch`) |
| `--batch SLUGS_JSON` | mutex | **TASK 015 / R-015-4**: path to a JSON array of slugs; one invocation, `known_concepts` + concept-drift swept ONCE and shared. Per-entry errors are non-fatal. Output: `{"known_concepts": […], "missing_concept_files": […], "batch": [{source_slug, source_path, source_hash, is_unchanged} \| {source_slug, error, …}, …]}` — `known_concepts`/`missing_concept_files` are emitted ONCE at the top level (not per entry, P-6) |
| `--known-concepts-format` | no | **TASK 015 / R-015-3**: `full` (default) = `[{slug,name,type,aliases},…]`; `slugs-only` = `[slug,…]` (smaller payload at scale) |
| `--db-path` | no | override XDG global DB location |

**No** `--model`, `--max-tokens`, `--ingest` (those belong to v2 / apply).

Output JSON envelope (success, exit 0):

```json
{
  "vault_id": "...",
  "source_slug": "...",
  "source_path": "/absolute/path/.md",
  "source_hash": "<sha256-hex>",
  "is_unchanged": false,
  "known_concepts": [{"slug":"...","name":"...","type":"...","aliases":[...]}],
  "missing_concept_files": ["..."]
}
```

## `apply` subcommand

```bash
wiki-extract-concepts apply \
    --vault <vault-id> \
    --vault-root <path> \
    --source-page <slug> \
    --source-hash <hex-from-prepare> \
    (--candidates-stdin | --candidates-file <path> | --batch-candidates <combined.json>) \
    [--db-path <override>] \
    [--orchestrator-id <id>] \
    [--ingest]
```

| Flag | Required | Notes |
|---|---|---|
| `--vault` / `--vault-root` / `--source-page` / `--db-path` | as `prepare` | same semantics |
| `--source-hash HEX` | single-page | sha256 emitted by `prepare`; mismatch → exit 2 `SOURCE_CHANGED_DURING_EXTRACTION` (H-1, Q5). Required for single-page; omit with `--batch-candidates` (per-entry hash) |
| `--candidates-stdin` | mutex | reads JSON array from stdin (cap 1 MiB) |
| `--candidates-file PATH` | mutex | reads JSON from path (must resolve inside vault; stat-cap 1 MiB) |
| `--batch-candidates COMBINED_JSON` | mutex | **TASK 015 / R-015-5**: path to `[{source_slug, source_hash, candidates:[…]}, …]`. ONE repo reused across all entries; per-entry isolation; with `--ingest`, `index_from_manifest` dispatched once per entry on the shared repo. Output: `{"batch": [{source_slug, action, manifest} \| {source_slug, error, message}, …]}`. `--source-page`/`--source-hash` are omitted (per-entry) |
| `--orchestrator-id ID` | no | regex `^[a-z0-9._:@-]{1,64}$`; defaults to literal `"orchestrator"` (Q9-v3.1) |
| `--ingest` | no | dispatch manifest in-process to `index_from_manifest` (Decision-15 preserved) |

## Exit codes (R-42 v3.1)

| Code | Meaning | Sub-envelopes |
|---|---|---|
| 0 | Success (manifest or `{extraction, index}`) or `is_unchanged=true` | — |
| 1 | argparse / usage error | — |
| 2 | Input-validation failure | `SOURCE_NOT_FOUND`, `INVALID_SOURCE_PATH`, `INVALID_SOURCE_SLUG`, `SOURCE_TOO_LARGE`, `SOURCE_CHANGED_DURING_EXTRACTION`, `INVALID_CANDIDATES_PATH` |
| 4 | Candidates payload error | `EXTRACTION_PARSE_ERROR`, `CANDIDATES_TOO_LARGE`, `CANDIDATE_COUNT_OUT_OF_BOUNDS`, `FIELD_TOO_LONG`, `UNKNOWN_FIELD`, `FIELD_QUOTE_NOT_IN_BODY`, `INVALID_NAME_FORMAT`, `INVALID_SOURCE_SPAN` |
| 5 | Partial / retry-safe failure | `PARTIAL_INDEX_FAILURE` (`--ingest`), `IDEMPOTENCY_UPDATE_FAILED`, `DB_WRITE_FAILED` (a `sqlite3.Error` — e.g. a FOREIGN KEY failure when the source page isn't indexed yet; **run `wiki-reindex` first**) — all leave `source_state` NOT updated (C-1 invariant); safe to retry |
| 6 | Manifest invalid (`--ingest`) | `MANIFEST_INVALID` |

> Exit code **3** (the v2 `LLM_API_UNAVAILABLE` envelope) is **RETIRED**
> in v3.1 — the Python skill makes no LLM calls. (Note: the legacy v2
> code path retains the exit-3 mapping until `task-003-v3-06` deletes
> it; this is invisible to v3.1 operators.)

**CWE-117 / CWE-209 invariant**: error envelopes carry `{error, field?,
reason}` only — they NEVER echo the offending payload value (the
`field` key names the field; the `reason` describes the violation in
length / type / shape terms).

## Example: end-to-end orchestrator script

```bash
# Step 1: prepare
PREPARE=$(wiki-extract-concepts prepare \
    --vault myvault \
    --vault-root /vaults/myvault \
    --source-page some-summary)
HASH=$(echo "$PREPARE" | jq -r .source_hash)
UNCHANGED=$(echo "$PREPARE" | jq -r .is_unchanged)
[ "$UNCHANGED" = "true" ] && exit 0

# Step 2: orchestrator synthesises candidates JSON
# (per the concept-extraction skill's strict schema)
CANDIDATES='[{"slug":"sharpe-ratio","name":"Sharpe Ratio", "...":"..."}]'

# Step 3: apply
echo "$CANDIDATES" | wiki-extract-concepts apply \
    --vault myvault \
    --vault-root /vaults/myvault \
    --source-page some-summary \
    --source-hash "$HASH" \
    --candidates-stdin \
    --orchestrator-id "claude-opus-4-7" \
    --ingest
```

## Architecture note (Decision-15 + Decision-16 + Decision-17)

- **Decision-15** (preserved): the `--ingest` auto-dispatch path is
  **in-process** — `apply` imports `validate_manifest`,
  `index_from_manifest`, and `WikiIngestError` from the neutral module
  `scripts.wiki_skills._manifest_consumer` and calls them directly.
  No subprocess.
- **Decision-16** (preserved): the neutral module exists so this skill
  does not depend on `wiki_enrich` (which would have been a
  skill-to-skill coupling smell).
- **Decision-17** (NEW in v3.1): the synthesis step lives outside the
  Python skill. The orchestrator runs `prepare`, loads the
  `concept-extraction` skill into its own context, reads the source
  body, generates candidates JSON, and pipes them into `apply`. The
  skill no longer imports `anthropic` and has no `--model` /
  `--max-tokens` flags.

## Migration from v2

If you had a v2 shell script:

```bash
# v2 (NO LONGER WORKS):
wiki-extract-concepts --vault X --vault-root Y --source-page Z --ingest
```

Rewrite it as:

```bash
# v3.1:
out=$(wiki-extract-concepts prepare --vault X --vault-root Y --source-page Z)
hash=$(echo "$out" | jq -r .source_hash)
# (orchestrator synthesises $candidates JSON)
echo "$candidates" | wiki-extract-concepts apply \
    --vault X --vault-root Y --source-page Z \
    --source-hash "$hash" --candidates-stdin --ingest
```

The synthesis step (which v2 ran inside the Python process) is now the
orchestrator's responsibility. There is no Python-side shim because
embedding an LLM call in the skill was the architectural mistake
Decision-17 reversed.

## Related

- [`workflows/wiki-extract-concepts.md`](../../workflows/wiki-extract-concepts.md) — 7-step orchestrator recipe (UC-08 v3.1)
- [`concept-extraction` skill](../../.agent/skills/concept-extraction/SKILL.md) — extraction prompt + strict JSON contract
- [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §2.1 Concept Extractor + §3.4 UC-08 sequence
- [`docs/adr/ADR-001-wiki-ingest-integration.md`](../../docs/adr/ADR-001-wiki-ingest-integration.md) — Option I (clarified by Decision-8)
- [`docs/adr/ADR-002-multi-vault-bottleneck-corrections.md`](../../docs/adr/ADR-002-multi-vault-bottleneck-corrections.md) — Class A/B/C layering
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../../docs/WIKI-INGEST-V1.1-CONTRACT.md) — manifest schema this skill emits
- `wiki-enrich` — the bridge skill for raw-source ingestion (different layer)
- `wiki-search` — query the resulting entity layer via FTS5
