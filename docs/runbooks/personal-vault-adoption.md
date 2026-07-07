# Runbook — Adopting obsidian-llm-wiki on the real personal Obsidian vault

**Status:** validated on a real-vault copy 2026-06-09 · ready for live cutover ·
**Audience:** the vault owner (operator)

This is an **operational rollout** runbook, not a framework change. All framework
blockers found during the dogfood on `samples/personal-vault-dogfood` + the live
copy are **closed and committed** — TASK 022 (vault-local / absolute `index_db`),
TASK 023 (PARA summary `type_mapping` + structured `sources:` provenance +
`transcript_dedup`), TASK 024 R-1..R-4 (`wiki-index-upsert` layout-awareness, FTS
full-body, PARA enrich guidance, NFC/NFD provenance).

**Validated 2026-06-09 on a full local copy of the live vault**
(`Downloads/TestVault/ObsidianNotes`, obsidian-personal PARA, 2667 .md):
reindex 2486 pages / 2.9 s / exclusions all 0 / FTS full-body on Cyrillic; every
zone scanned with **0 unexpected ingest/convert**; the only enrichable zone
(`03 - Learning` courses) is already summarised → idempotent. The config templates
below are the **exact validated configs** from that copy.

## Operator decisions (locked 2026-06-09)

| Decision | Choice | Consequence |
|---|---|---|
| Vault location | **iCloud Drive** | Index DB MUST live on a non-synced absolute path (see Risk 1). |
| First run | **On a local copy/snapshot first** | Materializes `.icloud` stubs; protects irreplaceable data from the write phases. **DONE** — copy at `Downloads/TestVault/ObsidianNotes`. |
| Rollout scope | **Zone by zone** | Started with `03 - Learning`; all zones validated on the copy. |
| Provenance match | **`basename`** | The existing summaries cite `file:` by basename; basename mode basenames BOTH sides (see Provenance note). |

---

## Risk 1 — iCloud + SQLite (the one thing to get right up front)

The vault lives in `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>/`.
**The SQLite index DB must NOT live inside the vault** — iCloud would sync the
WAL/SHM sidecar files mid-write and corrupt the DB.

Resolution (TASK 022):
- Declare `index_db:` in `WIKI_SCHEMA.md` pointing to an **absolute path outside
  iCloud**, e.g. `/Users/<you>/Library/Application Support/obsidian-llm-wiki/personal.db`
  (use an explicit absolute path; `~` may not be expanded by the resolver).
- **TASK 042:** an absolute `index_db` that resolves UNDER the OS app-data dir
  (`~/Library/Application Support`, etc. — exactly the recommended location above) is now
  **trusted automatically — no env var, no inline prefix**. So for this vault you can run
  plain `wiki-*` commands. `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` is only needed for an absolute
  path *outside* app-data; the partial-write footgun (schema written then validation fails)
  is also closed by the pre-write guard (TASK 025) — validation happens before any write.
- The DB is **Class-B rebuildable** (ADR-002 §D8): if it ever breaks, delete it
  and re-run `wiki-reindex --full`. Nothing irreplaceable lives there.
- On the **local copy** (non-synced) a vault-local `index_db: ".wiki/index.db"` is
  simplest and needs no env var — that is what the validation used.

## Risk 2 — iCloud `.icloud` placeholder stubs

iCloud evicts file *contents* to save disk, leaving 0-byte `.<name>.icloud`
placeholders. A filesystem walk would index empty stubs. **The copy-first decision
solves this** — copying forces materialization. Before snapshotting (or before a
live run), force-download at least the markdown:

```bash
ICLOUD_VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>"
find "$ICLOUD_VAULT" -name '*.md' -print0 | xargs -0 cat >/dev/null   # materialize markdown
find "$ICLOUD_VAULT" -name '*.icloud' | head                          # detect remaining stubs (expect none)
```

## Risk 3 — NFD filenames — ALREADY CLOSED

macOS stores filenames NFD; frontmatter `sources:` is NFC. Closed by TASK 024 R-4
(`_resummarize.summary_exists` NFC-normalizes both sides at the D2a boundary). No
action required.

---

## Config files (exact validated configs from the copy — adjust only paths/zones)

### `WIKI_SCHEMA.md` (identity layer — vault root)
```yaml
---
name: WIKI_SCHEMA
vault_id: personal
schema_version: "2.0"
language: ru
layout: obsidian-personal
index_db: "/Users/<you>/Library/Application Support/obsidian-llm-wiki/personal.db"
description: "Personal PARA vault"
---
```
> `vault_id` must be 3–32 chars (CHECK constraint). `index_db` absolute UNDER the app-data
> dir → trusted automatically (TASK 042); absolute ELSEWHERE → set
> `WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`. On the copy this was `".wiki/index.db"` (relative,
> no env needed).

### `.wiki/layout.yaml` (grammar layer — what to index)
```yaml
# `ignore` UNIONs the built-in obsidian-personal ignores (TASK 021) — the base
# already covers .obsidian/.trash/_templates/**/*.base/.DS_Store, so list only extras.
ignore:
  - "_inbox/**"
  - "_daily/**"
  - "Attachments/**"
  - "_attachments/**"
  - "02 - Personal Home/Квартиры/**"      # note the CAPITAL "Home" — match your real casing
  - "02 - Personal Home/Household/**"
  - "02 - Personal Home/Purchases/**"
  - "02 - Personal Home/icloud accounts.md"   # sensitive — keep out of the index
  - "[0-9][0-9] - *.md"                    # Z10: root NN- view sidecars ("01 - Inbox.md")
  - "Test.md"                              # loose root test artifact

# type_mapping DEEP-MERGES over the base. Add any custom summary subtype your notes
# carry that the built-in obsidian-personal map lacks, else it UnmappedTypeError-skips.
# (TASK 025 baked the common *-summary family — tutorial/article/book/video/podcast/
# course — into the built-in, so this block is only needed for subtypes beyond those.)
type_mapping:
  tutorial-summary: {db_type: summary, tag: tutorial}

# OPTIONAL — deepen project granularity for the Learning area so course modules that
# reuse filenames ("07 - Домашнее задание" in Модуль 4 vs Модуль 6) get DISTINCT
# projects (otherwise they collide on (slug, project) — detected + WARNed since
# TASK 020/021, but one note drops from the index).
# ⚠ Supplying `paths` REPLACES the entire built-in grammar (it does NOT merge, unlike
# ignore/type_mapping). You MUST re-declare the base rules verbatim + your deeper rule.
# Scoped to Learning here → other areas keep the 2-level area/sub granularity.
# ⚠ DF-049-1: that re-declaration MUST include the `_queries/**` + `_verifications/**`
# rules below — they are how a filed `wiki-query`/`wiki-verify-multi` answer survives
# reindex. Dropping them silently prunes every filed RAG answer on the next
# `wiki-reindex` (the row goes; the Class-A file stays; `is_unchanged` breaks).
paths:
  - {glob: "_daily/**/*.md",     type: daily-note, project: "_daily",     default_tags: [daily]}
  - {glob: "_clippings/**/*.md", type: clipping,   project: "_clippings", default_tags: [clipping]}
  - {glob: "_inbox/**/*.md",     type: note,       project: "_inbox",     default_tags: [inbox, draft]}
  - {glob: "_queries/**/*.md",       project: "_vault_"}   # DF-049-1: filed RAG answers
  - {glob: "_verifications/**/*.md", project: "_vault_"}   # DF-049-1: filed verdicts
  - glob: "[0-9][0-9] - Learning/*/*/*/**/*.md"     # Learning 4-level
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*Learning/(?P<sub>[^/]+)/(?P<subsub>[^/]+)/(?P<mod>[^/]+)/'
    project_template: 'Learning/${sub}/${subsub}/${mod}'
  - glob: "[0-9][0-9] - Learning/*/*/**/*.md"       # Learning 3-level
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*Learning/(?P<sub>[^/]+)/(?P<subsub>[^/]+)/'
    project_template: 'Learning/${sub}/${subsub}'
  - glob: "[0-9][0-9] - */*/**/*.md"                 # generic Area/Sub (base)
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/(?P<sub>[^/]+)/'
    project_template: '${area}/${sub}'
  - glob: "[0-9][0-9] - */*.md"                      # Area (base)
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^/]+)/'
    project_template: '${area}'
  - glob: "[0-9][0-9] - *.md"                        # Area MOC (base)
    type: note
    project_pattern: '^(?P<num>\d+)\s*-\s*(?P<area>[^.]+)\.md$'
    project_template: '${area}'
    extra_tags: [moc]
  - {glob: "*.md", type: note, project: "_root_"}    # root notes (base)
```

### `.wiki/sync.yaml` (executor routing — what to summarize/dedup)
```yaml
zones:
  - "03 - Learning/**"
exclude:
  - "_inbox/**"
  - "_daily/**"
  - "Attachments/**"
  - "02 - Personal Home/Квартиры/**"
  - "02 - Personal Home/Household/**"
  - "02 - Personal Home/Purchases/**"
  - "**/_summary/*.xlsx"          # worksheet/exercise spreadsheets beside summaries — not knowledge
tag_namespace: wiki

# TASK 023: one recording lands as several caption formats (ID.ru.txt + ID.ru.vtt
# + ID.ru-orig.vtt + ID.en.vtt). Ingest only the preferred one; `before-first-dot`
# groups by the YouTube-id prefix. A LONE caption is kept (still ingested).
transcript_dedup:
  enabled: true
  identity: before-first-dot
  prefer_ext: [".txt", ".vtt", ".srt"]

# TASK 019: a raw transcript is auto-summarised ONLY if no summary exists.
# provenance_ref match: BASENAME — the gate basenames BOTH the cited file: AND the
# raw target, so it matches summaries that cite file: by basename (the existing
# corpus, e.g. "059RZHWA5Qg.ru.txt") AND any future summaries that cite a full
# vault-rel path. Safe because the transcripts are YouTube-id-named → basenames are
# globally unique. (vault-rel-path would MISS the basename-cited corpus → 16 false
# "ingest" → 16 DUPLICATE summaries on a live run.) mirror OFF.
resummarize:
  mode: if-missing
  detect:
    source_state: true
    provenance_ref:
      enabled: true
      fields: [source, sources]
      match: basename
    mirror:
      enabled: false
```

> **Provenance match modes.** `basename` basenames both sides (cited `file:` value
> AND the walked raw path) → matches basename- OR path-cited summaries; choose it
> when source basenames are globally unique (YouTube-id transcripts) or your existing
> summaries cite by basename. `vault-rel-path` is stricter (exact full-path equality)
> → only matches full-path citations; risk-free against cross-folder basename
> collisions but misses basename-only citations. This vault uses **basename**.

> Per-folder overrides (`<folder>/.wiki/sync.yaml`, deepest-wins deep-merge) are
> available if a specific course needs different `resummarize`/`mirror` keying.

### `.claude/settings.json` (stop Claude CLI re-confirming every command)

When you run Claude CLI inside the vault, it otherwise prompts for every Bash command
(both safe reads and the `wiki-*` CLIs). Drop in the shipped permissions template so
the known-good set auto-runs while dangerous ops stay gated:

```bash
mkdir -p "<vault>/.claude"
cp /path/to/obsidian-llm-wiki/templates/vault.claude-settings.json "<vault>/.claude/settings.json"
```

What it does (verified against the Claude Code permissions schema):
- **`defaultMode: "acceptEdits"`** — Claude can write/edit notes (file summaries) and run
  `mkdir`/`mv`/`cp` **without prompting**; it still prompts for other Bash.
- **`allow`** — every `wiki-*` CLI + safe read-only shell (`ls`/`cat`/`grep`/`find`/…) +
  the pipe targets `jq` and `python3 -m json.tool` (pipes need EACH leg allow-listed) +
  read-only `git`. These never prompt.
- **`deny`** (hard block, overrides allow) — `rm -rf`, `sudo`, `git reset --hard`,
  `git clean`, egress (`curl`/`wget`/`nc` — the H-6 untrusted-data posture), and writes to
  `.claude/**` (so an injected instruction can't widen its own permissions). Anything not
  listed still **prompts** (the safe default).

Edits auto-reload (no restart). Per-machine tweaks go in `.claude/settings.local.json`
(gitignored) — e.g. add `"Bash(sqlite3 *)"` to `allow` if you query the index directly,
or remove the `curl`/`wget` deny if your flow needs egress.

> **For the `wiki-*` allow rules to actually fire, the wrappers must be on `PATH`.**
> Verify in the vault terminal: `which wiki-search`. If it's missing, Claude falls back
> to `python -m scripts.wiki_skills.…` or absolute paths (`/usr/bin/…`) — which the
> bare-name rules do NOT match (Claude Code does not normalise absolute paths), so it
> keeps prompting. Fix the `PATH` (add the dir holding the `wiki-*` wrappers, e.g.
> `~/.local/bin`, to your shell profile) rather than allow-listing `python`/`bash`.

> **Do NOT carry over broad `Bash(bash *)` / `Bash(/bin/bash *)` / `Bash(python3 -c *)`
> rules** that "Yes, don't ask again" accumulates in `settings.local.json` — each is
> arbitrary code execution and re-opens the whole gate. If a wrapped command keeps
> prompting, allow the SPECIFIC inner command, not the shell. Periodically prune
> `settings.local.json` of such over-broad entries.

---

## Phased rollout

### Phase 0 — pre-flight (on the copy) — ✅ DONE 2026-06-09
1. Materialize markdown (Risk 2), then snapshot to a **local non-synced** dir:
   `rsync -a "$ICLOUD_VAULT/" "$HOME/vault-snapshot/"`.
2. Drop `WIKI_SCHEMA.md` + `.wiki/{layout,sync}.yaml` into the copy.
3. **Register the vault** (reads the declared `index_db`):
   ```bash
   wiki-init --register-existing --vault "$HOME/vault-snapshot"
   ```
   Use `--register-existing` (reads the hand-authored `index_db`), NOT `--local`
   (which WRITES `index_db`). An absolute `index_db` under the app-data dir is trusted
   automatically (TASK 042); only an absolute path elsewhere needs `export
   WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` first.
4. `wiki-reindex --full --vault personal --vault-root "$HOME/vault-snapshot"`
   - **Verified:** 2486 pages, exclusions all 0, FTS full-body works. Findings:
     1 malformed-frontmatter skip + slug-collisions (see Data fixes).

### Phase 1 — first zone (`03 - Learning`) — ✅ DONE
1. `wiki-sync scan "03 - Learning" --vault personal --vault-root "$HOME/vault-snapshot"`
   → review the plan: `ingest` / `convert+ingest` / `upsert` / `skip:*`.
   - **Verified:** 869 upsert + **16 skip:summary-exists** + 39 skip:transcript-variant
     + 4 skip:empty-source; **0 ingest / 0 convert** — the course is already
     summarised and the gate (match: basename) correctly recognises it.
2. Executor (only when there ARE raw sources to summarise) per `workflows/wiki-sync.md`:
   de-timestamp (`.vtt`/`.srt`) → delegate each raw source to `wiki-import`
   (convert → REASON via `summarizing-meetings` behind the H-6 fence → file note +
   `_concepts/` → index) → ready `.md` via `wiki-index-upsert` → `wiki-sync record`.
3. Smoke-test: `wiki-search "<known term>" --vaults personal --vault-root <V>`,
   `wiki-lint`, idempotency re-scan (every done raw → `skip:source_state`/`:provenance`).

### Phase 2 — remaining zones — ✅ ALL VALIDATED (search-only, 0 ingest)
`04 - Work projects` (755 upsert / 2 skip:view), `05 - Материалы` (816 upsert /
1 view), `02 - Personal Home` (116 skip:excluded-zone / 21 upsert), `07 - Crypto`
(3 upsert), `_clippings` (empty). The whole vault is **search-only except the
Learning courses**, which are done. view-detection + excluded-zones work everywhere.

### Phase 3 — cut over to the live iCloud vault
The copy proved the configs. To go live:
1. **Materialize** the live vault's markdown (Risk 2) — `find "$ICLOUD_VAULT" -name
   '*.md' -print0 | xargs -0 cat >/dev/null`.
2. **Author** `WIKI_SCHEMA.md` (absolute `index_db`, Risk 1) + `.wiki/{layout,sync}.yaml`
   (the validated templates above) into the LIVE vault root.
3. **TASK 042:** the app-data `index_db` is trusted automatically — `export
   WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` is NO LONGER required for this vault (plain `wiki-*`
   calls work). Only set it if you point `index_db` at an absolute path *outside* app-data.
4. **Register + index:**
   ```bash
   wiki-init --register-existing --vault "$ICLOUD_VAULT"
   wiki-reindex --full --vault personal --vault-root "$ICLOUD_VAULT"
   ```
   (the live DB is a separate island from the copy's DB — TASK 022 island model).
5. **Fix the 3 data items in the LIVE vault** (see Data fixes) — or accept them.
6. **Per-zone scan** (`wiki-sync scan "<zone>" --vault personal --vault-root
   "$ICLOUD_VAULT"`); execute only zones with genuine raw sources. Learning is
   already summarised → no-op until you add new transcripts.
7. **Verify:** idempotency re-scan all-skip · `wiki-search` returns content ·
   `wiki-lint` clean.
8. Going forward: add new course transcripts → `wiki-sync scan` flags them `ingest`
   → run the executor → they're summarised once and skip thereafter.

---

## Data fixes the owner must do in the live vault (your data, not framework bugs)
All detected correctly on the copy — zero silent loss. ~4 notes / 0.16%.
1. **1 malformed frontmatter** — `04 - Work projects/Telegram agents/Promo code
   advisor.md` has an empty `---` fence (no close) → skipped at reindex/upsert. Clean
   the frontmatter (remove the stray fence / add a proper close).
2. **2 same-directory duplicate-version files** (collide on slug, distinct content —
   one drops from the index): `03 - Learning/Управление проектами/План оценки…`
   (double- vs single-space variant), `05 - Материалы/AI-tools/Техники для Chat GPT…`
   (parens vs no-parens variant). Rename to disambiguate, or delete the stale copy.
   (The course-module collision is already fixed by the Learning `paths` deepening.)

## Known borderline items (operator's call, non-blocking)
- `_clippings` (empty in the copy) and `Travel notes` are currently **indexed**.
  Add to `ignore` if undesired.
- `_raw` / `.staging` scratch dirs are kept out of the search index by the built-in
  obsidian-personal `ignore` (TASK 025 — `**/_raw/**` + `**/.staging/**`, any depth),
  so raw markdown does not land in search. They are reserved scratch names under this
  layout; rename a colliding folder rather than trying to un-ignore it.
- Cosmetic: with the Learning `paths` deepening, `_summary`/`_transcripts` become
  project leaves (e.g. `Learning/Courses/Руководитель 2026/_summary`). Harmless;
  collapse with a finer rule if you dislike it.
- Orphan-links backlog is expected (compounding) — run `wiki-extract-concepts`.
- `--vault all` spans only the connected DB (island model). One DB per vault.

## Acceptance per zone
- reindex: 0 unexpected skips, 0 unexplained slug_collisions, exclusions all 0.
- scan: dedup + provenance skips match expectation; no unexpected `skip:unmappable-type`
  (if you hit one, add the `type:` to `.wiki/layout.yaml` `type_mapping`).
- post-execute: idempotency re-scan all-skip; `wiki-search` returns new summaries;
  `wiki-lint` clean.

## Related framework follow-ups — CLOSED in TASK 025 (2026-06-09)
Surfaced by the adoption audit and shipped via the full VDD pipeline: installer
absolute-`--index-db` **pre-write guard** (no partial Class-A mutation on failure) +
`INVALID_INDEX_DB` exit-code/field unification (exit 6 / `index_db`); the common
`*-summary` subtypes + `_raw`/`.staging` ignore **baked into the built-in
obsidian-personal layout** (so a fresh adopter needs neither the per-vault
`type_mapping` extension for `tutorial-summary` nor the `_raw` ignore shown above —
they ship by default now); a **layout-aware `CLAUDE.md`** template for
dev-project/obsidian-personal (the Karpathy `rm …/global.db` hardcode removed); and
the `basename` provenance mode + `paths`=REPLACE sharp edge **documented** in the
manual/schema/workflow. The per-vault overrides above remain valid (and harmless) —
the built-ins now simply cover the common cases out of the box.
