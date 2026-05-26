# wiki-ingest v1.1 Integration Contract

> **Audience**: developer of the global `wiki-ingest` skill.
> **Purpose**: Specify the minimum surface `wiki-ingest` v1.1 must expose so MVP (this repo) can vendor it as a git-submodule and integrate via Option I (see [ADR-001](./adr/ADR-001-wiki-ingest-integration.md)).
> **Status**: DRAFT — pending v1.0 capability audit.

This document is the **contract**. v1.1 must satisfy every REQUIRED item below. Optional items are nice-to-have for future Epics.

---

## 1. Machine-Readable Output

### REQUIRED — `ingest` mode JSON manifest (with `vault_id` partitioning per ADR-002)

After successful ingest, the skill must emit a JSON object to stdout (in addition to or instead of the human report) describing all file mutations:

```json
{
  "status": "ok",
  "vault_id": "trade-agents",                               // REQUIRED — ADR-002 §D1.1 (explicit, no fallback)
  "vault_root": "/Users/sergey/dev-projects/trade-agents",
  "course": "ZeroOne Systems",                              // null если single-tier vault
  "source": {
    "path": "/abs/path/to/transcript.txt",
    "slug": "self-improving-trading-agent-on-hermes",
    "hash": "<sha256 of source bytes>"
  },
  "written": [
    {"path": "_sources/self-improving-trading-agent-on-hermes.md", "action": "created", "kind": "source", "scope": "course"},
    {"path": "_concepts/sharpe-score.md", "action": "created", "kind": "concept", "scope": "course"},
    {"path": "_concepts/wacko-alpha.md", "action": "updated", "kind": "concept", "scope": "course", "facts_added": 1},
    {"path": "_entities/hermes-agent.md", "action": "created", "kind": "entity", "scope": "course"},
    {"path": "index.md", "action": "updated"},
    {"path": "log.md", "action": "appended"}
  ],
  "created": ["_concepts/sharpe-score.md", "_concepts/wacko-alpha.md", "_entities/hermes-agent.md"],
  "touched": ["_concepts/wacko-alpha.md"],
  "contradictions": 0,
  "summary_path": "_sources/self-improving-trading-agent-on-hermes.md",
  "log_event": {                                            // ADR-002 R-28 — structured event для log_events table
    "event_ts": "2026-05-26T14:32:11+03:00",
    "event_type": "ingest",
    "subject": "AI Trading Agent Holy Grail: Self-Improving Agent with Hermes",
    "log_md_byte_offset": 4827                              // pointer в log.md для round-trip
  },
  "llm_tokens_used": {"input": 42301, "output": 14502, "model": "claude-sonnet-4-6"}
}
```

**`vault_id` semantics**: read from root `WIKI_SCHEMA.md::vault_id` field (REQUIRED, no fallback — см. §5 ниже). Fail-fast если отсутствует.

**`written[].scope` field**:
- `"course"` — file lives under `<vault>/Lessons/<Course>/_concepts/` (course-local; promotion-spec tier 1)
- `"vault"` — file lives under `<vault>/_concepts/` (shared vault-root; promotion-spec tier 2)

Maps to MVP's `project` column: `scope="course"` → `project="<course-slug>"`; `scope="vault"` → `project="_vault_"`.

**`log_event` object** — structured mirror события из log.md. Используется MVP indexer для INSERT в `log_events` table (ADR-002 §D2). `log_md_byte_offset` позволяет round-trip между Markdown и DB row.

Why: MVP iterates `written[]` to upsert each file into SQLite. Without this manifest MVP would have to filesystem-walk after every ingest (race-prone, slow).

Flag to opt into: `--output-format json` (default human-readable, JSON on opt-in to preserve backward compatibility).

### REQUIRED — `lint` mode JSON report

```json
{
  "status": "ok",
  "issues": [
    {"category": "orphan", "page": "_concepts/foo.md", "details": "no inbound wiki-links"},
    {"category": "dangling", "source_page": "_sources/bar.md", "target": "[[NonExistent]]"},
    {"category": "missing-page", "concept": "Sharpe Score", "mentioned_in": 3, "no_dedicated_page": true},
    {"category": "open-contradiction", "page": "_concepts/baz.md", "line": 42}
  ],
  "counts": {"orphan": 1, "dangling": 1, "missing-page": 1, "open-contradiction": 1}
}
```

Why: MVP's `wiki-lint` is two-layer — file-level issues come from `wiki-ingest lint --output-format json`, SQL-level issues (FTS drift, taxonomy violations, backlinks via JOIN) come from MVP. Combined report merges both.

### REQUIRED — `reindex` mode JSON manifest

```json
{
  "status": "ok",
  "index_path": "index.md",
  "rebuilt": true,
  "rows_added": 12,
  "rows_removed": 2,
  "preserved_sections": ["Notes"]
}
```

### REQUIRED — `query` mode JSON output

```json
{
  "status": "ok",
  "query": "hermes",
  "hits": [
    {"path": "_concepts/hermes-agent.md", "snippet": "...", "score": 4.21}
  ],
  "answer": "...",
  "filed_back_as": null  // or "_queries/<slug>.md" if compounding pattern triggered
}
```

### REQUIRED — `scan` mode (v1.0 already has this — DOCUMENT and STABILIZE)

```json
{
  "vault_root": "/abs/path",
  "schema_present": true,
  "concepts": [{"slug": "sharpe-score", "name": "Sharpe Score", "path": "_concepts/sharpe-score.md"}],
  "entities": [{"slug": "hermes-agent", "name": "Hermes Agent", "path": "_entities/hermes-agent.md"}],
  "sources": [{"slug": "...", "path": "_sources/...md", "date": "YYYY-MM-DD"}],
  "last_ingest": "self-improving-trading-agent-on-hermes",
  "proposed_slug": "<inferred for next ingest if --hint-title passed>"
}
```

---

## 2. Known-Concepts Injection

### REQUIRED — accept external known-concepts list

MVP queries `SELECT slug, name FROM entities WHERE ...` and passes to `wiki-ingest ingest` to prevent dangling-link generation (e.g., summarizing-meetings inventing `[[Hermes]]` when vault has `[[Hermes Agent]]`).

Flag:

```bash
wiki-ingest ingest --source X --vault $V --known-concepts-file /tmp/known.json
```

Where `/tmp/known.json` is:

```json
[
  {"slug": "hermes-agent", "name": "Hermes Agent", "aliases": ["Hermes", "Hermes Framework"]},
  {"slug": "sharpe-score", "name": "Sharpe Score", "aliases": ["sharpe ratio"]}
]
```

Behavior: wiki-ingest reads the file, augments the `scan`-derived list, and passes the merged list to `summarizing-meetings` with the existing instruction ("use EXACT names from this list").

Alternative inline form: `--known-concepts-stdin` reading the same JSON from stdin. (Required because file paths can be racy if multiple ingests run concurrently.)

---

## 3. Atomic Transactions

### REQUIRED — manifest emitted ONLY on full success

If wiki-ingest crashes mid-way (after writing 3 of 5 files), it MUST NOT emit a success manifest. Either:

- (a) emit `{"status": "error", "phase": "<phase>", "written_so_far": [...], "cleanup_advice": "..."}` and exit non-zero, OR
- (b) buffer all writes in-memory, flush atomically at end, OR
- (c) write to a tempdir, rename to vault on success

Option (c) is cleanest but has FS-rename limitations (can't cross fs boundaries). Option (a) is simplest and lets MVP decide whether to partial-index or rollback.

### REQUIRED — explicit exit codes

- `0` — success
- `1` — usage/arg error (existing convention from v1.0)
- `2` — schema missing, run `init` first (existing convention from v1.0)
- `3` — partial success (some files written, manifest reflects state for recovery)
- `4` — subprocess to summarizing-meetings failed (passthrough)
- `5` — LLM API unavailable / auth failed

---

## 4. Schema Compatibility

### REQUIRED — bundled default schema must match MVP's vault layout

Current `wiki-ingest` `_sources/`, `_concepts/`, `_entities/` directories. MVP's UC-01 step 10 creates `00-Vault-Index/`, `Summaries/`, `Sources/{email,...}/`, `_raw/`.

**Required alignment**:
- MVP UC-01 calls `wiki-ingest init --vault $VAULT` for scaffolding. wiki-ingest creates `_sources/`, `_concepts/`, `_entities/`, `index.md`, `log.md`, `WIKI_SCHEMA.md`.
- MVP additionally creates `00-Vault-Index/log/` (for monthly log rotation R-09.1 — MVP wants monthly files, not single `log.md`), `_raw/`, `_raw/.locks/`, `_raw/failed/`.

Two options for `log.md`:
- (a) wiki-ingest appends to monthly file `log/{YYYY-MM}.md` (preferred — MVP-compatible), OR
- (b) wiki-ingest keeps single `log.md`, MVP rotates daily/monthly as separate step.

**Decision request**: option (a) is cleaner; please add `--log-path` flag accepting either single file or monthly-rotation pattern.

### REQUIRED — `WIKI_SCHEMA.md` declares MVP-required frontmatter fields

MVP's `wiki.lint.required_frontmatter: [type, title, date, tags]` (flat layout) or `[..., project]` (per-project). wiki-ingest's bundled schema must declare these as required, so its own lint catches missing fields before MVP indexes them.

---

## 5. Configuration Surface

### REQUIRED — accept `--config <path>` for runtime overrides

So MVP can inject `wiki.transcript.model='claude-sonnet-4-6'`, `wiki.transcript.timeout_seconds=600`, etc. wiki-ingest reads this and propagates to summarizing-meetings.

Format: same YAML as MVP's CLAUDE.md `wiki:` block (just the relevant subset).

### REQUIRED — respect `WIKI_INGEST_DRY_RUN=1` env var

Equivalent to `--dry-run` flag on all mutating commands. Useful for MVP's lint `--fix` mode preview.

### REQUIRED — `vault_id` field MUST exist in root `WIKI_SCHEMA.md` (per ADR-002 §D1.1, fail-fast)

**Decision (2026-05-26)**: `vault_id` — REQUIRED explicit field в `WIKI_SCHEMA.md` frontmatter. **No hash fallback.** Hash-derivation отвергнут — приводит к silent drift при folder rename.

**Format constraint**: `^[a-z][a-z0-9-]{2,31}$` (kebab-case, letter-start, length 3-32).

**`init` command behaviour**:
- При scaffolding нового vault'а → interactive prompt `vault_id` (default suggestion = `kebab(folder_basename)`). Записывает в `WIKI_SCHEMA.md` frontmatter автоматически. `--vault-id <slug>` flag отключает prompt.
- При detection существующего `WIKI_SCHEMA.md` без `vault_id` field → **fail-fast** `MISSING_VAULT_ID` с `suggested_vault_id: <kebab(folder_basename)>` в error JSON. НЕ автогенерит — operator должен сам добавить (one-line edit).
- При invalid format → fail-fast `INVALID_VAULT_ID` с указанием pattern.

**`--vault-id <slug>` flag (optional validation guard)**:
- Если задан → must match `WIKI_SCHEMA.md::vault_id` exactly; mismatch → fail-fast `VAULT_ID_FLAG_MISMATCH`. Назначение: CI / multi-invocation pipelines где operator хочет explicit assertion на vault identity.
- Если НЕ задан → wiki-ingest читает из `WIKI_SCHEMA.md::vault_id` (REQUIRED, fail-fast если отсутствует — см. выше).

**Exit codes** (extend §3):
- `6` — `MISSING_VAULT_ID`
- `7` — `INVALID_VAULT_ID`
- `8` — `VAULT_ID_FLAG_MISMATCH`

**Error JSON template** (MISSING_VAULT_ID):

```json
{
  "status": "error",
  "code": "MISSING_VAULT_ID",
  "message": "WIKI_SCHEMA.md must declare 'vault_id' in frontmatter (no hash fallback per ADR-002).",
  "wiki_schema_path": "/Users/sergey/dev-projects/trade-agents/WIKI_SCHEMA.md",
  "suggested_vault_id": "trade-agents",
  "fix": "Add 'vault_id: trade-agents' to the frontmatter block of WIKI_SCHEMA.md (after 'schema_version:'), then re-run."
}
```

**Migration for existing vaults** (e.g., `trade-agents/` which has `schema_version: 2.0` но без `vault_id`):
1. Operator manually adds `vault_id: <slug>` в frontmatter — one-line edit.
2. First post-edit `wiki-ingest ingest` (или explicit `wiki-init --register-existing`) — registers `(vault_id, root_path, schema_version, ingest_count из existing log.md)` в MVP's `vaults` table.
3. Backfill sweep — все historic `_sources/`/`_concepts/`/`_entities/` indexed с этим `vault_id`.

---

## 6. Idempotency

### REQUIRED — `--source-hash <hex>` external override

MVP may have already computed `sha256(source_bytes)` and stored it in `source_state` table. To avoid re-reading the file:

```bash
wiki-ingest ingest --source X --vault $V --source-hash <hex>
```

wiki-ingest checks: if its own internal idempotency tracking (e.g., footer of `_sources/<slug>.md` containing `source_hash:`) matches → returns `{"status": "ok", "action": "unchanged", "manifest": <empty>}` without re-running LLM. Exit code `0`, manifest reflects no changes.

### REQUIRED — same source slug + different hash → re-ingest gracefully

If user edits a transcript file (corrected typos), wiki-ingest should detect hash change and run a full ingest, additive-merging new facts into existing concept pages. This is the **additive-merge contract** — file rewrites are not just acceptable but required behavior.

---

## 7. CLI Stability

### REQUIRED — frozen CLI signature for v1.1+

After v1.1 release, no breaking changes to:
- Subcommand names (`ingest|query|lint|reindex|init|scan`)
- Required argument names
- JSON manifest schema (additive changes OK; field removals/renames are MAJOR version)

Use semver: v1.1.x = backward-compatible additions, v1.2.0+ = potentially breaking but documented in CHANGELOG.

### REQUIRED — `--version` flag

```bash
wiki-ingest --version
# → wiki-ingest 1.1.0
```

MVP `wiki-init` calls this to verify minimum compatible version (≥ 1.1.0 for Option I integration). Fail-fast if older.

---

## 8. Subprocess-Friendly Behavior

### REQUIRED — quiet by default when not a TTY

When stdout is piped (subprocess), suppress decorative output, banners, progress bars. Emit only structured JSON or unstructured logs to stderr.

Mechanism: `os.isatty(1)` check, or explicit `--quiet` flag.

### REQUIRED — `--timeout-seconds <N>` flag

Bound the total ingest time. If exceeded, kill internal LLM call cleanly and exit with code `4` + partial manifest.

MVP I-3.3 already passes `timeout=600` to its own subprocess; wiki-ingest receiving the same timeout via flag (or env var `WIKI_INGEST_TIMEOUT`) lets it gracefully clean up rather than being SIGKILL'd by parent.

---

## 9. Optional (Future-Friendly)

### OPTIONAL — `--hooks <path>` for post-write callbacks

For Epic 7+ when MVP wants `wiki-ingest` to call back into MVP for entity canonicalization mid-ingest. v1.1 doesn't need this; v1.2+ might.

### OPTIONAL — `compose` mode

A pipeline that chains `summarizing-meetings → wiki-ingest ingest → wiki-index-upsert (MVP)` in one call. Nice ergonomics but adds coupling. v1.2+.

### OPTIONAL — `--source-kind {transcript|article|paper|...}` discriminator

Today wiki-ingest treats all sources uniformly. MVP has distinct adapters (manual/transcript/light) — passing through the kind lets wiki-ingest tune known-concepts prompt per kind. Nice-to-have, not required.

---

## 10. Acceptance Checklist (for v1.1 release)

### Core (Phase 2 — ADR-001)

- [ ] `--output-format json` on `ingest|lint|reindex|query` with stable schemas (see §1)
- [ ] `--known-concepts-file` / `--known-concepts-stdin` accepts injection list (§2)
- [ ] Atomic manifest emission on success only; exit codes documented (§3)
- [ ] `init` scaffolds layout compatible with MVP UC-01 (`_sources/`, `_concepts/`, `_entities/`) (§4)
- [ ] Monthly-rotation `--log-path` flag or single-file fallback (§4)
- [ ] `--config` accepts MVP YAML subset (§5)
- [ ] `--source-hash` external override for idempotency (§6)
- [ ] Frozen CLI signature; `--version` flag (§7)
- [ ] Quiet mode when stdout is piped; `--timeout-seconds` (§8)
- [ ] CHANGELOG.md documenting v1.0 → v1.1 deltas
- [ ] At least one e2e test: ingest → MVP indexes via manifest → `wiki-search` finds the result

### Multi-vault (Phase 2.5 — ADR-002)

- [ ] `vault_id` field в JSON manifest всех modes (REQUIRED, §1)
- [ ] `course` field в manifest для two-tier promotion-spec vaults (§1)
- [ ] `written[].scope` field (`"course"` / `"vault"`) для tier discrimination (§1)
- [ ] `log_event` структурированный объект в manifest (§1) — соответствует `log_events` table schema
- [ ] `init` requires `vault_id` interactive (или `--vault-id <slug>` flag), записывает в `WIKI_SCHEMA.md` (§5)
- [ ] Fail-fast `MISSING_VAULT_ID` (exit 6) на existing vault без `vault_id` field (§5)
- [ ] Fail-fast `INVALID_VAULT_ID` (exit 7) на pattern violation (§5)
- [ ] `--vault-id <slug>` validation guard (mismatch → exit 8) (§5)
- [ ] `--known-concepts-stdin` accepts DB-piped JSON (resolves bottleneck B2 из ADR-002, §2/§5)
- [ ] e2e migration test: existing `trade-agents/` vault без `vault_id` → fail-fast → operator-edit → re-run → register в MVP `vaults` table → backfill indexed
- [ ] Two-tier promotion-spec support (`promote`/`demote` commands) — отдельный roadmap, отслеживается в `trade-agents/docs/wiki-ingest-promotion-spec.md`

When ALL items (Core + Multi-vault) green, MVP может начать Phase 3 (TASK.md coordinated rework + vendoring).

---

## References

- [docs/adr/ADR-001-wiki-ingest-integration.md](./adr/ADR-001-wiki-ingest-integration.md) — Option I architecture pivot
- [docs/adr/ADR-002-multi-vault-bottleneck-corrections.md](./adr/ADR-002-multi-vault-bottleneck-corrections.md) — multi-vault + bottleneck corrections (vault_id REQUIRED)
- `~/.claude/skills/wiki-ingest/SKILL.md` — v1.0 surface (baseline)
- [trade-agents/docs/wiki-ingest-promotion-spec.md](../../trade-agents/docs/wiki-ingest-promotion-spec.md) — two-tier promotion roadmap
- [docs/TASK.md](./TASK.md) — MVP spec (will be reworked в Phase 3)
