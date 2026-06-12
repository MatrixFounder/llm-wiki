# Full dogfood — ObsidianNotes-Test (real obsidian-personal PARA vault)

**Date:** 2026-06-12 · **Vault:** `~/Downloads/TestVault/ObsidianNotes-Test` (vault_id
`personal`, layout `obsidian-personal`, vault-local `.wiki/index.db`, language ru, 2484
indexed pages). Obsidian 1.12.7 running. **Result: PASS** — framework + the new
`obsidian-cli` skill validated end-to-end on real content; 3 real-content findings
surfaced (operator-actionable, not framework bugs). Mutations contained to a self-created
`_cli-dogfood/` subfolder (deleted at end); the real index was rebuilt (Class-B,
rebuildable) — markdown untouched.

## Phase A — config regeneration (real vault)
`wiki-init --register-existing --vault <TV> --force` → **CLAUDE.md + .claude/settings.json
regenerated** from the updated templates:
- CLAUDE.md now renders from **`CLAUDE.layout.md.tmpl`** (correct for obsidian-personal:
  existing-tree, no `_sources` scaffold) and carries the new **obsidian-cli pointer**.
- settings.json now carries the **obsidian-cli-aligned permissions** (allow: obsidian T1
  reads + `touch`/`mkdir`; deny: obsidian T3 `eval`/`dev:*`/`plugin:*`/`sync on|off`/…).
- DB resolved to the vault-local `.wiki/index.db` (TASK 022).

## Phase B — index layer (real content)
`wiki-reindex --full` → **2486 files processed, 2484 rows in 3.2 s.** `wiki-search "оценка
людей"` → 20 hits (TASK 028 stemming: query `оценка` matched `оценки-…` pages). `wiki-lint`
→ 6540 orphan-link (the vault's own dense wikilink graph — operator content hygiene, not a
framework defect) + 1 missing-in-db + 2 hash-mismatch.

**Real-content findings (operator-actionable):**
1. **2 slug collisions** (TASK 020 detection working — `slug_collisions` envelope + WARN):
   two file pairs differ only by a double-space / `(parens)` in the filename and slugify
   identically → the later overwrote the earlier (2 rows lost). Disambiguate via a
   per-folder `project`/`project_pattern` in `.wiki/layout.yaml`, or rename one of each pair.
2. **1 malformed-YAML note skipped** (report-and-skip, no crash): `04 - Work projects/
   Telegram agents/Promo code advisor.md` — invalid YAML frontmatter at line 4 (an unquoted
   value YAML reads as an alias). Fix the note's frontmatter to index it.

## Phase C — obsidian-cli T1 reads (real content)
All live and correct: `vaults verbose` (the Obsidian name **`ObsidianNotes-Test`** ≠ the
wiki vault_id **`personal`** — the documented mismatch the skill handles), `search "оценка"`
(3 hits), `orphans total` = **2798** (live graph, per-target) vs wiki-lint's 6540 (indexed
view, per-ref) — the documented recipe-7 discrepancy, **base:query format=json** on a real
`.base` (parsed JSON rows), `tasks todo total` = 44.

## Phase D — obsidian-cli T2 mutations (contained `_cli-dogfood/`, scratch /tmp index)
- **Link-safe rename** (`obsidian rename`) live: `df-target.md` → `df-renamed.md`; the app
  rewrote the inbound `[[df-target]]` → `[[df-renamed]]`. **Coherence `wiki-reindex --full`
  → 0 orphans** (DF-029-1 `--full`-for-rename rule confirmed live; a plain `--delta` would
  have missed the mtime-preserved rename).
- **`property:set`** live (`status: reviewed`) + `property:read` round-trip + `wiki-index-
  upsert --source` coherence.
- **App-index lag re-confirmed** (029-06 finding): a *just-created* file is not visible to
  the obsidian CLI until the app's file-watch re-scans (~seconds) — `rename`/`read` returned
  "not found" on the first attempt, succeeded after the app indexed. Operational, not a bug.

## Phase E — security
- **Injection canary (E-09) live:** a note body instructing `obsidian eval code=…` is, when
  read via `obsidian read`, untrusted DATA — T3 `eval` is banned, NEVER from note content →
  not executed, flagged.
- **Templater feature-detect (E-15):** `community-plugins.json` has **no Templater/QuickAdd**
  → `template:insert`/`create template=` stay plain T2 here (the T3-when-scripting gate
  correctly does NOT trigger; feature-detect negative). The Templates core command exists, so
  the gate is reachable if a scripting plugin is added.
- **Real-vault validation of the 029-07 `command id=`→T3 fix:** the vault HAS a **`terminal`**
  community plugin (shell-running palette commands) + `dataview` (DataviewJS). A
  `command id=terminal:…` is genuinely code-running — concretely validating why `command id=`
  must default to **T3** when the dispatched effect can't be proven from a friendly palette
  title.

## Containment / cleanup
Only the self-created `_cli-dogfood/` files were mutated (deleted at end); all wiki-side
mutation tests used a `/tmp` scratch index (the real `personal` `.wiki/index.db` was only
rebuilt by the legitimate Phase-B `--full`, which is Class-B/rebuildable — markdown is the
source of truth and was never edited). Scratch DB removed.
