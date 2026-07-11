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
auto-detected (pass `--vault-root .` only if a command asks). iCloud vaults: the index
DB lives off the synced drive at an absolute path under the OS app-data dir (e.g.
`~/Library/Application Support/…`), which is **trusted automatically — no env var needed**.
(An absolute DB *outside* app-data still needs `export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`.)

> **⚠️ Permissions: do NOT inline the env var or call a CLI by absolute path.**
> The `.claude/settings.json` allowlist matches the command's **leading token** — `Bash(wiki-search *)`
> fires only if the command begins with exactly `wiki-search`. An inline prefix
> (`WIKI_ALLOW_ABSOLUTE_INDEX_DB=1 wiki-search …`), an absolute path (`/Users/…/bin/wiki-search …`),
> or the `python -m scripts.wiki_skills.wiki_search …` form all **shift** that token → the rule
> misses → Claude prompts and appends the exact literal to `settings.local.json` (cruft accretes).
> **Run the bare command:** `wiki-search "query" --vaults personal`. If you genuinely need the var,
> set it in the **`env` block** of `.claude/settings.json` (the iCloud vault already does) or
> `export WIKI_ALLOW_ABSOLUTE_INDEX_DB=1` once as a **separate** command — then the `wiki-*` command
> stays bare and matches the rule.

> **Which `--vault <id>` value? (two different "vault" names — don't mix them up)**
> - `wiki-* --vault`/`--vaults <id>` take the **wiki `vault_id`** — declared in
>   `WIKI_SCHEMA.md` (`vault_id:`), e.g. `personal`. **You** choose it.
> - `obsidian …` and `obsidian-active-note --vault <NAME>` take the **Obsidian vault NAME**
>   (the folder name in the app, e.g. `ObsidianNotes`; see `obsidian vaults verbose`).
> - They **can differ** (e.g. `personal` vs `ObsidianNotes`). Find your `vault_id`:
>   ```bash
>   grep '^vault_id:' WIKI_SCHEMA.md                                   # from inside the vault (source of truth)
>   sqlite3 "<index_db>" "SELECT vault_id, root_path FROM vaults;"     # list every registered vault
>   #   <index_db> = the `index_db:` from WIKI_SCHEMA.md, or the global default
>   #   ~/Library/Application Support/wiki-index/global.db
>   ```
>   Every `wiki-search`/`wiki-reindex` JSON line also echoes `"vault_id"`. (There is no
>   dedicated `wiki-* --list-vaults`; the `sqlite3` query above is the list.)

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
wiki-search --vaults personal --tag decision                              # list by a tags[] MEMBER (TASK 033; == --where 'tags=decision')
wiki-search --vaults cybos --tag decision --as-of 2026-04-20               # TEMPORAL: decisions ACTIVE on a date (TASK 034; superseded/invalidated by then are excluded — no LLM, no valid_to authoring)
wiki-search "smart money" --vaults personal --types summary               # restrict to a db type
wiki-search "агент" --vaults personal --exact                            # literal: no stemming (ё/е still folded)
```

> Default search is **inflection-tolerant**: bare terms are auto stemmed + prefixed
> (`сценарии`→`сценар*`, `agents`→`agent*`) and **ё/е-folded**, so one typed form finds
> its siblings and `ещё`/`еще` are one token. `--exact` (`--no-stem`) turns stemming OFF
> for precise literal terms. The body ё/е fold needs a one-time `wiki-reindex --full`;
> stemming + the query ё-fold work immediately.

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
# Freshness (TASK 051): set resummarize.mode:if-changed in .wiki/sync.yaml → re-summarise a source ONLY when its content changed; --force redoes anyway
# Executing the plan (summarising etc.) is orchestrator/LLM work → use Claude CLI (§B).
```

**Health check** (dangling `[[links]]`, hash mismatch, cross-vault dups + lifecycle-drift + ontology-violation)
```bash
wiki-lint --vault personal                   # SQL health + lifecycle-drift + ontology-violation (status/edge vs graph/contract)
wiki-lint --vault personal --strict           # exit non-zero if any issue (CI gate — incl. both contradictions)
```

**Derived knowledge health** (typed-class vaults, e.g. `cybos`) — what's MISSING or CONTRADICTORY (always exit 0)
```bash
wiki-health coverage --vault cybos                       # pages with no expected edge/field
wiki-health coverage --vault cybos --class requirement   # e.g. requirements nothing implements
wiki-health ontology --vault cybos                       # pages breaking the type/edge/property contract (R-19)
wiki-health ontology --vault cybos --class decision      # e.g. a decision implementing the wrong type / bad status
```

**Ask a question and get a cited synthesis (RAG)** — a two-step `prepare`/`apply`:
```bash
wiki-query prepare "compare X and Y" --vault personal     # retrieves context (LLM cites it)
# (the answer is composed, then) wiki-query apply …        # files a compounding _queries/<slug>.md
```

**Retrieval-scope controls (ADR-009) — classification, provenance, read-audit; all default-OFF**
```bash
# --- Retrieval-scope controls (ADR-009 / TASK 049–050) — all default-OFF ---
# Provenance floor: prepare hits carry a derived trust tier
#   external (http(s) source:/url:/URL: or _raw/) < internal < verified (inbound `verifies` edge); origin taints.
wiki-query prepare "..." --vault personal --vault-root . --min-trust internal   # ground RAG on trusted pages, drop clippings
# Classification scope: declare `policy: {levels, default_level}` in WIKI_SCHEMA.md, mark pages
# `classification: <level>`; a page ABOVE the audience never enters context (fail-closed):
wiki-search "..." --vaults personal --audience internal        # also on wiki-query / wiki-verify-multi
# apply MUST repeat prepare's --audience/--min-trust (they fold into question_hash → QUESTION_CHANGED on mismatch).
# Read-audit (opt-in): attribute multi-agent writes/reads (solo use rarely needs it):
WIKI_ACTOR_ID=critic-a wiki-query apply ...                    # stamps details.actor on the log_events row
wiki-search "..." --vaults personal --log-access               # log the read (DB-only Class-C event; access_logged echo)
```

> Lint: `invalid-classification` (out-of-ladder label; a warning) and `classification-leak` (a lower
> page citing a higher one; an error under `--strict`). A bad `--audience`/`policy:` block exits 2.

**Other handy ones**
```bash
# import an external URL/PDF/thread/transcript — OR a local raw file (--source ./raw.md);
# wiki-import distils it, files the note + _concepts/ pages, and indexes (any layout;
# the REASON step between is the orchestrator's).
# prepare emits `language` (the vault's WIKI_SCHEMA language, en fallback) → summarise IN that language:
wiki-import prepare --vault personal --vault-root . --kind auto \
    --source "https://example.com/article" --folder "05 - Материалы/Криптовалюты" --mode full
#   TASK 051: an unchanged re-poll emits {action:unchanged, is_unchanged:true} → STOP (no REASON pass); --force rewrites anyway
#   …translate/summarise IN prepare.language, reusing the emitted known_concepts; note JSON uses
#   neutral {title, body, summary_bullets, entities[]} (legacy title_ru/ru_body still accepted). Then:
wiki-import apply --vault personal --vault-root . --folder "05 - Материалы/Криптовалюты" --kind "<prepare.kind>" \
    --mode full --raw-rel "<prepare.raw_path>" --source-url "<URL>" \
    --existing-page-slugs '<prepare.existing_page_slugs>' --note-stdin
wiki-config show --vault-root .                                    # which settings does THIS folder inherit? (no arg → the active note's folder)
wiki-config report --open --vault-root .                           # one self-contained HTML inheritance report (whole cascade)
wiki-config serve --open --vault-root .                            # local web editor for .wiki/sync.yaml — form + hints + templates + restore
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
`/wiki-sync`, `/wiki-reindex`, `/wiki-lint`, `/wiki-health`, `/wiki-import` (unified
external-source on-ramp and per-source engine — URL/PDF/thread/transcript or a local raw
file, any layout). The agent keeps you in
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
| **Periodic health** | `wiki-lint --vault personal` (orphan-links backlog is expected; drains over time); `--strict` to gate on lifecycle-drift + ontology-violation |
| **Coverage gaps (typed vaults)** | `wiki-health coverage --vault cybos` — requirements w/o implementer, facts w/o source; a gap is *data*, exits 0 |
| **Ontology violations (typed vaults)** | `wiki-health ontology --vault cybos` — a mis-typed edge (wrong source/target class) or a `status` outside its enum; a report, exits 0 (the `--strict` rail is `wiki-lint`) |
| **Which settings does a folder get / broken sync.yaml** | `wiki-config show <folder>` (inheritance provenance) · `validate` · `doctor` → `fix --yes` · `report --open` · `serve` (web editor); works even with a broken index |
| **Index looks wrong / after a big move** | `wiki-reindex --full --vault personal` (safe — rebuilds from markdown) |

**Tuning** lives in two per-vault files (see the runbook): `<vault>/.wiki/layout.yaml`
(what to index — `ignore`, `type_mapping`; e.g. adopt the TASK 031 typed knowledge
classes — `decision`/`requirement`/`risk`/`incident`/`hypothesis`/`fact`/`event` — by
adding them under `type_mapping` here, which UNIONs into the built-in layout) and
`<vault>/.wiki/sync.yaml` (how `wiki-sync` routes a zone — `zones`, `transcript_dedup`,
`resummarize`). New whole-vault shapes are config too: drop a `layouts/<name>.yaml`
(e.g. the built-in `cybos`) — `wiki-init --layout <name>` picks it up, zero code.
