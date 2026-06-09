# obsidian-llm-wiki — CLI quick reference

> 🇷🇺 Russian mirror: [`cli-quick-reference.ru.md`](cli-quick-reference.ru.md).

A one-page cheat-sheet for day-to-day use **from a terminal opened in your vault
folder** (the same folder Obsidian opens) and **via Claude CLI** launched there. For
the full reference see [obsidian-llm-wiki_manual.md](obsidian-llm-wiki_manual.md);
for first-time setup on a real vault see
[../runbooks/personal-vault-adoption.md](../runbooks/personal-vault-adoption.md).

**Mental model.** You write markdown in Obsidian; the SQLite index is a *rebuildable
cache* (ADR-002 §D8). The CLIs keep the search/knowledge layer current — they read
the markdown, never lock you out of it. `vault_id` (e.g. `personal`) is declared in
`WIKI_SCHEMA.md`. Run commands **from inside the vault**: the vault root is
auto-detected (pass `--vault-root .` only if a command asks). iCloud vaults: keep
`export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` in your shell (the index DB lives off the
synced drive).

---

## A. Manual — type the commands yourself

```bash
cd "/path/to/your/Obsidian/Vault"     # the vault root (has WIKI_SCHEMA.md)
```

**Search (the thing you do most) — FTS5, <100 ms**
```bash
wiki-search "дофамин"                       --vaults personal
wiki-search "lasso regularization"          --vaults personal --limit 5
wiki-search "переговоры" --vaults personal --project "Learning/Переговоры"
wiki-search --vaults personal --where "type=lesson-summary" --limit 10   # list by frontmatter field (no FTS query)
wiki-search "smart money" --vaults personal --types summary               # restrict to a db type
```

**Keep the index current after you edit/add notes in Obsidian**
```bash
wiki-reindex --delta --vault personal       # fast: only changed files (mtime/hash)
wiki-reindex --full  --vault personal        # wipe + rebuild from markdown (rare; authoritative)
```

**Index one ready note immediately** (layout-aware: correct project/type/refs)
```bash
wiki-index-upsert --vault personal --source "./03 - Learning/Courses/X/note.md"
```

**Auto-route a mixed zone** (transcripts to summarise, docs to convert, notes to
index, view-sidecars to skip). `scan` only PLANS — it writes nothing:
```bash
wiki-sync scan "03 - Learning" --vault personal              # JSON plan
wiki-sync scan "03 - Learning" --vault personal --dry-run     # human-readable plan
# Executing the plan (summarising etc.) is orchestrator/LLM work → use Claude CLI (§B).
```

**Health check** (drift, dangling `[[links]]`, hash mismatch, cross-vault dups)
```bash
wiki-lint --vault personal
```

**Ask a question and get a cited synthesis (RAG)** — a two-step `prepare`/`apply`:
```bash
wiki-query prepare "compare X and Y" --vault personal     # retrieves context (LLM cites it)
# (the answer is composed, then) wiki-query apply …        # files a compounding _queries/<slug>.md
```

**Other handy ones**
```bash
wiki-enrich --vault personal --vault-root . --source "./raw.md"   # ingest+index a raw source
wiki-index-render --vault personal --auto-indexes                  # (re)generate index/ledger pages
wiki-init --register-existing --vault .                            # one-time: register this vault
```

> Tip: every command prints a JSON envelope — pipe to `python3 -m json.tool` to read
> it, or to `jq` if installed.

---

## B. With Claude CLI — let the agent drive

Launch Claude in the vault root; it reads the vault's `CLAUDE.md` and runs the CLIs
for you. Just ask in plain language — you don't memorise flags:

```bash
cd "/path/to/your/Obsidian/Vault"
claude        # or your Claude Code launcher
```

> **Stop the constant command prompts.** Copy the shipped permissions template into the
> vault once: `mkdir -p .claude && cp <repo>/templates/vault.claude-settings.json
> .claude/settings.json`. It auto-runs the `wiki-*` CLIs + safe read commands and
> auto-accepts file edits, while still gating dangerous ops (`rm -rf`, `sudo`, egress).
> See the runbook's `.claude/settings.json` section.

Then, for example:
- *"Search my wiki for what I noted about dopamine and summarise it."*
- *"I dropped new transcripts in `03 - Learning/Courses/<Course>/_transcripts/` —
  scan the zone, summarise the new ones, file them, and reindex."* (the agent runs
  `wiki-sync scan`, then the executor in `workflows/wiki-sync.md`: de-timestamp →
  summarise → `wiki-index-upsert` → `wiki-sync record`, idempotently.)
- *"What does my vault say about X and Y? Give a cited answer."* (runs `wiki-query`.)
- *"I edited a bunch of notes — bring the index up to date and lint it."*
- *"File this meeting summary as a note in `04 - Work projects/<Client>/` and index it."*

Slash commands also exist for the common verbs: `/wiki-search`, `/wiki-query`,
`/wiki-sync`, `/wiki-reindex`, `/wiki-lint`, `/wiki-enrich`. The agent keeps you in
the loop on anything that writes (summaries, new notes) and is safe to re-run
(per-file idempotency).

---

## C. Typical loops

| When | Do |
|------|----|
| **After editing notes in Obsidian** | `wiki-reindex --delta --vault personal` → `wiki-search …` |
| **New transcript / raw doc in a course zone** | Claude CLI: "scan & summarise `<zone>`" → it plans (`wiki-sync scan`) then executes; re-running is a no-op (already-summarised raws skip) |
| **Look something up** | `wiki-search "…" --vaults personal` (or ask Claude) |
| **Need a synthesised, cited answer** | `wiki-query prepare/apply` (or ask Claude) |
| **Periodic health** | `wiki-lint --vault personal` (orphan-links backlog is expected; drains over time) |
| **Index looks wrong / after a big move** | `wiki-reindex --full --vault personal` (safe — rebuilds from markdown) |

**Tuning** lives in two per-vault files (see the runbook): `<vault>/.wiki/layout.yaml`
(what to index — `ignore`, `type_mapping`) and `<vault>/.wiki/sync.yaml` (how
`wiki-sync` routes a zone — `zones`, `transcript_dedup`, `resummarize`).
