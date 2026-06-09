# Runbook — Adopting obsidian-llm-wiki on the real personal Obsidian vault

**Status:** ready to execute · **Authored:** 2026-06-09 · **Audience:** the vault owner (operator)

This is an **operational rollout** runbook, not a framework change. All framework
blockers found during the 3-round dogfood on `samples/personal-vault-dogfood`
(the clone modelled on this vault) are **closed and committed** — TASK 022
(vault-local / absolute `index_db`), TASK 023 (PARA summary `type_mapping` +
structured `sources:` provenance + `transcript_dedup`), TASK 024 R-1..R-4
(`wiki-index-upsert` layout-awareness, FTS full-body, PARA enrich guidance,
NFC/NFD provenance). The remaining work is *adopting* the framework on the live
vault, which differs from the clone in **scale** (~6000 attachments, far more
notes), **real folder names/conventions**, and **iCloud sync**.

## Operator decisions (locked 2026-06-09)

| Decision | Choice | Consequence |
|---|---|---|
| Vault location | **iCloud Drive** | Index DB MUST live on a non-synced absolute path (see Risk 1). |
| First run | **On a local copy/snapshot first** | Materializes `.icloud` stubs; protects irreplaceable data from the write phases. |
| Rollout scope | **Zone by zone** | Start with the highest-value zone (`03 - Learning/Courses`), expand one zone at a time. |

---

## Risk 1 — iCloud + SQLite (the one thing to get right up front)

The vault lives in `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>/`.
**The SQLite index DB must NOT live inside the vault** — iCloud would sync the
WAL/SHM sidecar files mid-write and corrupt the DB.

Resolution (TASK 022):
- Declare `index_db:` in `WIKI_SCHEMA.md` pointing to an **absolute path outside
  iCloud**, e.g. `~/Library/Application Support/obsidian-llm-wiki/personal.db`.
- An absolute `index_db` is gated by **`WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`** (the
  HIGH-S2 safety fix). Export it for every `wiki-*` invocation against this vault
  (add to `~/.zshrc`, or wrap the CLIs).
- The DB is **Class-B rebuildable** (ADR-002 §D8): if it ever breaks, delete it
  and re-run `wiki-reindex --full`. Nothing irreplaceable lives there.

## Risk 2 — iCloud `.icloud` placeholder stubs

iCloud evicts file *contents* to save disk, leaving 0-byte `.<name>.icloud`
placeholders. A filesystem walk would index empty stubs. **The copy-first decision
solves this** — copying forces materialization. Before snapshotting, force-download
at least the markdown:

```bash
ICLOUD_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>"
find "$ICLOUD_VAULT" -name '*.md' -print0 | xargs -0 cat >/dev/null   # materialize markdown
# optional: detect remaining stubs
find "$ICLOUD_VAULT" -name '*.icloud' | head
```

## Risk 3 — NFD filenames — ALREADY CLOSED

macOS stores filenames NFD; frontmatter `sources:` is NFC. Closed by TASK 024 R-4
(`_resummarize.summary_exists` NFC-normalizes both sides at the D2a boundary). No
action required.

---

## Config files (port 1:1 from the proven dogfood, adjust only zone lists)

### `WIKI_SCHEMA.md` (identity layer — vault root)
```yaml
---
name: WIKI_SCHEMA
vault_id: personal
schema_version: "2.0"
language: ru
layout: obsidian-personal
index_db: "~/Library/Application Support/obsidian-llm-wiki/personal.db"
description: "Personal PARA vault"
---
```
> `vault_id` must be 3–32 chars (CHECK constraint). `index_db` is absolute → set
> `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`.

### `.wiki/layout.yaml` (grammar layer — what to index)
```yaml
ignore:
  - ".obsidian/**"
  - ".trash/**"
  - "_templates/**"
  - "**/*.base"
  - "**/.DS_Store"
  - "_inbox/**"
  - "_daily/**"
  - "Attachments/**"
  - "_attachments/**"
  - "02 - Personal home/Квартиры/**"
  - "02 - Personal home/Household/**"
  - "02 - Personal home/Purchases/**"
  # Z10: generated-view index sidecars ("01 - Inbox.md", "02 - Personal Home.md")
  # are Base/Dataview TOCs, not knowledge. Root-level "NN - *.md" only.
  - "[0-9][0-9] - *.md"
```
> `ignore` on a `.wiki/layout.yaml` override **UNIONs** the base obsidian-personal
> ignores (TASK 021 fix), so this list extends, not replaces.

### `.wiki/sync.yaml` (executor routing — what to summarize/dedup)
```yaml
zones:
  - "03 - Learning/**"
exclude:
  - "_inbox/**"
  - "_daily/**"
  - "Attachments/**"
  - "02 - Personal home/Квартиры/**"
  - "02 - Personal home/Household/**"
  - "02 - Personal home/Purchases/**"
  - "03 - Learning/Courses/Руководитель 2026/_summary/*.xlsx"
tag_namespace: wiki

# TASK 023: same recording lands as several caption formats (ID.ru.txt + ID.ru.vtt
# + ID.ru-orig.vtt + ID.en.vtt). Ingest only the preferred one; `before-first-dot`
# groups by the YouTube-id prefix. A LONE caption is kept (still ingested).
transcript_dedup:
  enabled: true
  identity: before-first-dot
  prefer_ext: [".txt", ".vtt", ".srt"]

# TASK 019: a raw transcript is auto-summarised ONLY if no summary exists.
# provenance_ref (match: vault-rel-path): a summary whose sources:/source: cites
# the raw by VAULT-RELATIVE path. The summarizer writes this back. mirror OFF —
# no course keys transcripts↔summaries by a shared number/date here.
resummarize:
  mode: if-missing
  detect:
    source_state: true
    provenance_ref:
      enabled: true
      fields: [source, sources]
      match: vault-rel-path
    mirror:
      enabled: false
```

> Per-folder overrides (`<folder>/.wiki/sync.yaml`, deepest-wins deep-merge) are
> available if a specific course needs different `resummarize`/`mirror` keying.

---

## Phased rollout

### Phase 0 — pre-flight (on the copy)
1. Materialize markdown (Risk 2), then snapshot to a **local non-synced** dir:
   ```bash
   rsync -a "$ICLOUD_VAULT/" "$HOME/vault-snapshot/"
   ```
2. Drop `WIKI_SCHEMA.md` + `.wiki/{layout,sync}.yaml` into the copy. (For the copy
   itself — local, non-synced — a vault-local `index_db` is also fine; the absolute
   path matters on the live iCloud vault.)
3. `export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` (if using the absolute DB path).
4. `wiki-reindex --full --vault-root "$HOME/vault-snapshot"`
   - **Verify:** pages indexed > 0, **0 skipped, 0 slug_collisions**, exclusions
     all 0 (Attachments/inbox/daily not indexed). Investigate any non-zero.

### Phase 1 — first zone (`03 - Learning/Courses`, highest compounding value)
1. `wiki-sync scan "03 - Learning" --dry-run` → review the plan JSON: counts for
   `ingest` / `convert+ingest` / `upsert` / `skip:*`. Confirm transcript-dedup and
   `skip:summary-exists:provenance` count as expected.
2. Run the executor per `workflows/wiki-sync.md`: de-timestamp (`.vtt`/`.srt`) →
   `summarizing-meetings` (behind the H-6 fence) → `wiki-enrich` /
   `wiki-extract-concepts` → `wiki-index-upsert` → `wiki-sync record`.
3. Smoke-test: `wiki-search personal "<known term>"`, `wiki-lint`, and an
   **idempotency re-scan** (every done raw → `skip:source_state` / `:provenance`).

### Phase 2 — expand one zone at a time
`04 - Work projects` → `02 - Personal home` → `05 - Материалы` → `_clippings` /
remaining. Same Phase 1 loop per zone. Each zone localizes any real-vault surprises
(non-standard frontmatter, unusual folder names, large attachments).

### Phase 3 — cut over to the live vault
Once the loop is clean on the copy:
1. Point the config at the live iCloud vault path; keep `index_db` on the absolute
   non-synced path.
2. Run the **write** phases (summary generation) directly on the live vault — that
   is where the summaries belong. The DB can be rebuilt from scratch (Class-B).
3. Re-run reindex + per-zone scan + idempotency check on live.

---

## Known borderline items (operator's call, non-blocking)
- `_clippings` and `Travel Notes` are currently **indexed** (not in `ignore`).
  Earlier decision: leave as-is. Add to `ignore` if undesired.
- Orphan-links backlog is expected (compounding) — run `wiki-extract-concepts` to
  drain it over time.
- `--vault all` spans only the connected DB (TASK 022 island model — no cross-DB
  federation). One DB per vault.

## Acceptance per zone
- reindex: 0 skipped, 0 slug_collisions, exclusions all 0.
- scan: dedup + provenance skips match expectation; no unexpected `skip:unmappable-type`.
- post-execute: idempotency re-scan is all-skip; `wiki-search` returns the new
  summaries; `wiki-lint` clean.
