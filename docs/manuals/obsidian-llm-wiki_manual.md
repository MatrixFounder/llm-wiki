# obsidian-llm-wiki — Manual

> 🇷🇺 Russian mirror: [`obsidian-llm-wiki_manual.ru.md`](obsidian-llm-wiki_manual.ru.md).

> **Who this guide is for.** Engineers meeting this system for the first time. No
> prior knowledge of the project's jargon is assumed — every term (vault, Class A/B/C,
> FTS5, layout, `prepare`/`apply`, …) gets a plain-language gloss the first time it
> appears, and all of them are collected in
> [Appendix A. Glossary](#appendix-a-glossary). The goal is *understanding*: in two
> weeks you will forget the flags, but the operating principles should stay.

> **How to read this guide.**
> - **Bold text** and the "✅ Key takeaways" blocks at the end of each chapter carry
>   the **principles** — the part worth retaining after the details fade.
> - Reference tables (command menus, page/relation types, exit codes) are for
>   *looking things up*, not memorising — skim them on first read.
> - `TASK NNN` / `ADR-NNN` / `R-NN` markers are pointers into the project's design
>   history. You can ignore them entirely on first read; they matter only when you
>   need the rationale behind a behaviour.

> **Sources.** This manual is verified against the real code of this repository at
> the time of writing. When the manual and the code disagree, **the code wins** —
> each command's exact contract lives in its `skills/<name>/SKILL.md`.

> **Companion to [`README.md`](../../README.md).** The README is the *entry point*
> (what the project is, how to install, the command index). **This manual is the
> *methodology*** — why each command exists, how to work with the vault's markdown
> documents (standard and custom layouts), and how to wire the wiki into another
> agent as an external knowledge resource. If you only want to get running, read
> the README. If you want to *operate* the wiki well, read this. For a one-page
> day-to-day cheat-sheet (main commands, manual + Claude CLI), see
> [`cli-quick-reference.md`](cli-quick-reference.md).

---

## Contents

- [TL;DR — in 60 seconds](#tldr--in-60-seconds)
- [Overview](#overview)
- [Why an index layer at all (the methodology)](#why-an-index-layer-at-all-the-methodology)
- [How to run the commands](#how-to-run-the-commands)
- [The command vocabulary, by purpose](#the-command-vocabulary-by-purpose)
  - [Construct knowledge](#1-construct-knowledge)
  - [Search & retrieve](#2-search--retrieve)
  - [Resolve entities](#3-resolve-entities)
  - [Answer & verify (RAG)](#4-answer--verify-rag)
  - [Maintain health](#5-maintain-health)
  - [Vault lifecycle](#6-vault-lifecycle)
- [Working with documents in Obsidian](#working-with-documents-in-obsidian)
  - [Vault configuration files (overview)](#vault-configuration-files-overview)
  - [The standard (karpathy) layout](#the-standard-karpathy-layout)
  - [Page anatomy & the auditability invariants](#page-anatomy--the-auditability-invariants)
  - [The author's contract: markdown is canonical](#the-authors-contract-markdown-is-canonical)
  - [Registering a pre-made summary (not raw)](#registering-a-pre-made-summary-not-raw)
  - [Custom layouts: the layout engine](#custom-layouts-the-layout-engine)
  - [Reference: page types & relation types (the knowledge model)](#reference-page-types--relation-types-the-knowledge-model)
  - [Mixed vault: search-only areas + enrich-able course zones](#mixed-vault-search-only-areas--enrich-able-course-zones)
  - [Automating the mix: `wiki-sync` (per-note routing, conversion, OCR)](#automating-the-mix-wiki-sync-per-note-routing-conversion-ocr)
  - [Configuring folders with `wiki-config` (provenance, repair, templates, web editor)](#configuring-folders-with-wiki-config-provenance-repair-templates-web-editor)
- [Using the wiki as an external resource for other agents](#using-the-wiki-as-an-external-resource-for-other-agents)
  - [The integration model: JSON envelopes + exit codes](#the-integration-model-json-envelopes--exit-codes)
  - [The `prepare` / `apply` contract (Decision-17)](#the-prepare--apply-contract-decision-17)
  - [The wiki as a RAG backend](#the-wiki-as-a-rag-backend)
  - [Untrusted data: the H-6 posture](#untrusted-data-the-h-6-posture)
- [Policy, provenance & read-audit (ADR-009)](#policy-provenance--read-audit-adr-009)
- [Health & maintenance, methodologically](#health--maintenance-methodologically)
- [Anti-patterns (do NOT)](#anti-patterns-do-not)
- [Command reference appendix](#command-reference-appendix)
- [Appendix A. Glossary](#appendix-a-glossary)
- [Related](#related)

---

## TL;DR — in 60 seconds

**The knowledge lives in markdown, not in a database.** Your notes sit in an
Obsidian **vault** (a folder of markdown files) and are the canonical record —
"Class A" in this project's vocabulary. Beside them sits a SQLite full-text index
("Class B"), which is a **100%-rebuildable cache**: you can delete the database at
any moment and `wiki-reindex --full` recreates it from the markdown, losing nothing.

**Three loops run over that pair.** The *construct* loop turns raw material
(articles, PDFs, transcripts) into summary notes plus cross-linked concept pages.
The *search/answer* loop reads the index: fast full-text search, graph traversal,
and RAG (retrieval-augmented generation — an answer synthesised *only* from
retrieved notes, with citations) whose answers are filed back as pages, so good
answers compound. The *maintain* loop (lint, reindex, entity curation) keeps cache
and canon honest with each other.

**Everything is a shell CLI.** The 19 `wiki-*` commands are ordinary terminal
programs, each doubling as a `/wiki-*` slash command inside Claude Code. The
deterministic ones run anywhere; the four LLM-shaped ones (`import`, `query`,
`verify-multi`, `extract-concepts`) split into a deterministic `prepare` call, an
agent-owned reasoning step, and a deterministic `apply` call — so any agent, not
just Claude, can drive them.

**The one discipline that matters:** after you hand-edit markdown, tell the index
(`wiki-index-upsert` for one file, `wiki-reindex --delta` for many). Markdown is
canonical; the reindex is how the cache learns.

```mermaid
flowchart LR
    RAW["raw source"] -->|"construct<br/>(wiki-import / wiki-sync)"| MD["markdown vault<br/>Class A — canonical"]
    MD -->|"reindex"| DB["SQLite index<br/>Class B — rebuildable cache"]
    DB -->|"search / graph / RAG"| ANS["cited answer"]
    ANS -->|"filed back as a page"| MD
    MD -.->|"maintain: lint · resolve · render"| DB
    classDef canon fill:#eef7ee,stroke:#5a5;
    class MD canon;
```

| Task | Command |
|---|---|
| Bring an existing vault under management | `wiki-init --register-existing --vault /path/to/MyVault` |
| Full-text search with ranked snippets | `wiki-search "lasso regularization" --vaults personal --limit 5` |
| Import an external article (agent session; REASON step follows) | `wiki-import prepare --vault personal --vault-root ~/Vault --kind auto --source "https://example.com/article"` |
| Index one ready note — no LLM | `wiki-index-upsert --vault personal --source ~/Vault/_sources/my-article.md` |
| Catch the index up after hand-edits | `wiki-reindex --delta --vault personal` |
| Get a durable, cited RAG answer (agent session) | `wiki-query prepare "compare X and Y" --vault personal --vault-root ~/Vault` |
| Plan a batch ingest of a folder (writes nothing) | `wiki-sync scan "03 - Learning" --vault personal --dry-run` |
| Health-check the vault, gate on contradictions | `wiki-lint --vault personal --strict` |
| List every decision that was live on a date | `wiki-search --tag decision --as-of 2026-04-15 --vaults personal` |
| Trace a supersession lineage | `wiki-graph chain switch-to-kafka --kind supersedes --vault personal` |
| See a folder's effective config and where it comes from | `wiki-config show --vault-root ~/Vault` |

---

## Overview

**obsidian-llm-wiki** is the *index + tooling layer* for an Obsidian-style
[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The
file layer (LLM-driven page synthesis) is owned by `wiki-import`, the in-repo
construct engine; this repo reads that output into a SQLite index and serves
fast, structured queries, an entity graph, cited RAG answers, and a verification
layer.

| Property | Value |
|---|---|
| **Type** | Multi-vault knowledge-base index + CLI toolkit |
| **Canonical source** | Markdown in the Obsidian vault (Class A) |
| **Derived cache** | One global SQLite DB (FTS5 + WAL), partitioned by `vault_id` (Class B/C) |
| **Surface** | 19 CLIs (`wiki-*`), each also a `/wiki-*` slash command inside Claude Code |
| **I/O contract** | stdin/args in → one-line JSON envelope on stdout + exit code |
| **Core invariant** | The DB is 100% rebuildable from markdown (`wiki-reindex --full`) |
| **Schema** | `user_version = 7` (`sql/wiki-index-v2.sql`) |
| **Runtime** | Python 3.14+; deps in `requirements.txt` |

First-use glosses for the table above, in plain language:

- **Vault** — an Obsidian-style folder of markdown notes; the unit this system
  manages. **Layout** — the on-disk grammar of a vault: which folders hold which
  kinds of pages.
- **Class A / B / C** — the data-layering contract (ADR-002 §D8): A = canonical
  markdown you author; B = derived state that is fully rebuildable from A (the DB,
  generated ledgers); C = minimal DB-only operational state (locks, audit rows).
- **FTS5** — SQLite's built-in full-text-search engine; **WAL** — write-ahead
  logging, a SQLite mode that lets readers and a writer coexist safely.
- **RAG** — retrieval-augmented generation: retrieve relevant notes first, then
  have the model answer *only* from them, with citations.
- **Envelope** — the single line of JSON each CLI prints on stdout; the
  machine-readable result an agent parses instead of prose.
- **Frontmatter** — the YAML metadata block (`---` … `---`) at the top of a
  markdown note; the index reads types, tags, and relations from it.

> **✅ Key takeaways.** This repo is the *index and tooling* layer, not the notes
> themselves: markdown in the vault is canonical (Class A), the SQLite DB is a
> disposable cache (Class B/C). Every command is a shell CLI that speaks one JSON
> envelope plus an exit code, so both humans and agents drive the same surface.

---

## Why an index layer at all (the methodology)

The standard RAG pattern is **stateless**: every question re-derives knowledge
from raw documents, and nothing accumulates. Karpathy's llm-wiki inverts that —
the LLM **incrementally builds and maintains a persistent, interlinked wiki** that
sits between you and the raw sources. Knowledge **compounds**: each ingest enriches
the corpus the next query reads.

`wiki-import` does the *file-layer* half of that loop (fetch+convert → REASON —
the LLM summarisation pass, owned by the calling agent rather than by the Python —
→ synthesise the source note + its `_concepts/` pages; concept compounding is a
derived Class-B render, not a body-merge). This repo does the half that makes the
compounding *usable at scale*:

```mermaid
flowchart LR
    SRC["raw source /<br/>external summary"] --> C
    C["CONSTRUCT<br/>import · extract · upsert"] -->|"writes"| MD["MARKDOWN<br/>Class A — canonical"]
    MD -->|"index / reindex"| DB["SQLITE INDEX<br/>Class B/C — rebuildable"]
    DB -->|"rebuild (--full)"| MD
    DB -->|"retrieve"| ANS["ANSWER + VERIFY<br/>cited RAG (wiki-query / wiki-verify-multi)"]
    ANS -->|"filed back as a page"| MD
    MD -.->|"MAINTAIN: lint · resolve · render"| DB
    classDef canon fill:#eef7ee,stroke:#5a5;
    classDef cache fill:#e8f0ff,stroke:#5577cc;
    class MD canon;
    class DB cache;
```

The methodological consequences that every command below serves:

1. **Markdown is canonical; the DB is a cache.** Hand-edits to vault files are
   first-class. The DB never holds knowledge that markdown doesn't —
   it can always be thrown away and rebuilt. (ADR-002 §D8, the Class A/B/C
   contract.)
2. **Every fact is auditable.** Claims trace to their source via footnote
   citations; answers cite only retrieved sources; nothing is "just known".
3. **The system never silently picks a winner.** Contradictions are *flagged*,
   not resolved. A failed verification is *recorded*, not auto-fixed.
4. **Good answers compound.** A cited RAG answer is filed back as a first-class
   page, so the next query can find it.

> **✅ Key takeaways.** Standard RAG is stateless; this system inverts it — every
> ingest and every good answer enriches the corpus the next query reads. Four
> consequences follow: markdown is canonical and the DB disposable; every fact
> is auditable to a source; contradictions are surfaced, never auto-resolved; and
> answers are filed back so knowledge compounds instead of evaporating.

---

## How to run the commands

The `wiki-*` commands are ordinary **shell CLIs** that operate on the vault's
markdown files. Obsidian itself does not *execute* them — Obsidian's role is the
editor/viewer of the Class-A markdown — but you can run them right inside the
Obsidian window with the `Terminal` community plugin (an embedded real shell; see
below), so in practice you needn't leave Obsidian at all.

By default the SQLite index lives outside the vault entirely
(`~/Library/Application Support/wiki-index/global.db` on macOS) — one global DB
shared by all vaults, partitioned by `vault_id`. A vault can instead own a
**vault-local** index that travels with it (`index_db: .wiki/index.db` in
`WIKI_SCHEMA.md`); you pick global vs local once, at init — see
[Choosing the index database](#choosing-the-index-database-global-default-vs-vault-local)
under Vault lifecycle.

The working loop is: **edit in Obsidian → run a command → reindex catches the
cache up → search / query reflects it** — and Obsidian picks up the on-disk
changes live.

```mermaid
flowchart LR
    OBS["Edit in Obsidian<br/>Class A markdown (canonical)"] --> RUN["Run a wiki-* command<br/>terminal · Terminal plugin ·<br/>Claude Code · Gemini CLI"]
    RUN --> RIDX["reindex / index-upsert<br/>cache catches up to canon"]
    RIDX --> SRCH["search / query / lint<br/>reflects the change"]
    SRCH -.->|"cited answers filed back as pages"| OBS
    classDef canon fill:#eef7ee,stroke:#5a5;
    classDef act fill:#e8f0ff,stroke:#5577cc;
    class OBS canon;
    class RUN act;
```

### The three invocation surfaces

**1. A plain terminal (the baseline).** After `bin/install-globally.sh`, the
`~/.local/bin/wiki-*` wrappers are on `PATH` and run from any directory — each
wrapper `cd`s into the repo, activates the `.venv`, and execs the CLI, so you need
no manual setup:

```bash
wiki-search "vault bottleneck" --vaults my-vault
wiki-lint --vault my-vault
wiki-reindex --delta --vault my-vault
```

Obsidian need not even be open. This is the right surface for the **deterministic**
commands.

**2. Inside Obsidian, via the `Terminal` community plugin.** The
[Terminal plugin](https://github.com/polyipseity/obsidian-terminal) embeds a
*real* integrated shell inside Obsidian (like VS Code's terminal). Because it's a
genuine shell, the `wiki-*` wrappers resolve through `PATH` and activate the venv
exactly as in any terminal — so you can edit a note and run `wiki-reindex --delta`
in the same window, without alt-tabbing. (A lighter alternative, the
**Shell commands** plugin, binds a fixed `wiki-*` invocation to an Obsidian command
/ hotkey — handy for one-keystroke `wiki-lint`, but only sensible for the
deterministic commands.)

**3. Inside an agent session (Claude Code — recommended for the LLM commands).**
The same commands are `/wiki-*` slash commands; the agent auto-suggests them on the
SKILL.md triggers. For `wiki-query` / `wiki-verify-multi` / `wiki-extract-concepts`
/ `wiki-import` this is effectively the *required* surface, because the middle of
their `prepare`/`apply` contract (two deterministic CLI calls — `prepare` stages
and retrieves, `apply` validates and files) is an LLM reasoning step the
*orchestrator* — the main agent driving the session — owns (see
[the `prepare`/`apply` contract](#the-prepare--apply-contract-decision-17)). You
*can* run their deterministic halves by hand, but then you must do the
synthesis/critique yourself.

Other vendors (Gemini CLI, **pi**, etc.) drive the same vendor-neutral binaries —
each workflow's `## Fallback` section explains the non-Claude-Code path (inline
the contract skill into the system context instead of `Skill({…})`).

> **pi (pi.dev) — first-class (TASK 043).** pi reads `AGENTS.md` (write it with
> `wiki-init --vendor pi`, which also drops `.pi/extensions/permissions.json`). The skills
> are pi-native `SKILL.md`s: `bin/install-globally.sh` links them into `~/.pi/skills/`,
> and with `enableSkillCommands` they surface as `/skill:wiki-search` etc. The on-PATH
> `wiki-*`/`obsidian` binaries work unchanged. pi has no allow-list — its permissions are a
> `mode` (`fullAuto` = auto-approve safe bash, confirm dangerous) + danger/protected patterns
> (a translation of the Claude deny-list). iCloud caveat: pi's host process needs Full Disk
> Access to read/write an iCloud vault (same as Claude/VS Code).

### Which surface for which command

| Command | Plain terminal / Obsidian `Terminal` plugin | Claude Code `/wiki-*` | Gemini / pi / other agents |
|---|---|---|---|
| `init` · `search` · `lint` · `reindex` · `index-upsert` · `index-render` · `confirm` · `alias` · `merge` · `append-log` · `sync scan` · `sync record` | ✅ run directly | ✅ | ✅ |
| `query` · `verify-multi` · `extract-concepts` · `import` · `sync` *(executor)* *(need an LLM step)* | ⚠️ deterministic halves only — you'd supply the LLM reasoning by hand | ✅ **recommended** | ✅ via each workflow's `## Fallback` |

> **The one discipline that matters:** after you hand-edit markdown in Obsidian,
> tell the index — `wiki-index-upsert` for one file, `wiki-reindex --delta` for
> many. Until you do, `wiki-search` returns stale snippets and `wiki-lint` reports
> hash drift. The markdown is canonical; the reindex is how the cache learns.

> **✅ Key takeaways.** Obsidian is the *editor* of the canonical markdown; the
> `wiki-*` commands are ordinary shell CLIs you can run from a terminal, from a
> terminal embedded in Obsidian, or as `/wiki-*` inside an agent session. Use the
> plain terminal for deterministic commands and an agent session for the four
> LLM-shaped ones. Whatever the surface: after a hand-edit, reindex.

---

## The command vocabulary, by purpose

The 19 CLIs are not a flat list — each plays a role in the loop above. Below,
each command is given as *why it exists* and *when to reach for it*, not just its
flags (those live in each [`SKILL.md`](../../skills/)).

### 1. Construct knowledge

These turn raw material into compounding pages.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-sync`** | The **zone-level dispatcher** (the multi-file on-ramp, TASK 046) — a *zone* is a folder subtree you designate for batch ingest; reach for `wiki-sync` instead of hand-routing a folder of heterogeneous drops file-by-file.<br>• `scan <zone>` classifies *every* file by extension + `#wiki/*` tag + content shape and emits a deterministic **plan** (distil / upsert / skip — *distil* = run raw material through the LLM summarisation into a note; *upsert* = index a ready markdown file as-is).<br>• The [`wiki-sync` workflow](#automating-the-mix-wiki-sync-per-note-routing-conversion-ocr) executes the plan idempotently (a re-run redoes nothing): each *distil* source is **delegated to `wiki-import`** (which owns fetch+convert, **scanned-PDF OCR**, `.vtt` de-timestamp, the REASON summary + `_concepts/` filing); ready notes go straight to `wiki-index-upsert`; view-sidecars are skipped.<br>• Deterministic driver, no inline summarise/convert; `wiki-sync record` is the per-file commit-marker. |
| **`wiki-import`** | The **unified construct on-ramp AND per-source engine** (TASK 039/040/046/047; `wiki-import-article` is a back-compat alias).<br>• Hand it **one source** — an external **URL / PDF / office doc / X-thread / meeting transcript / finished summary**, OR a **local raw file** (`--source ./path` — the single-file raw on-ramp that used to be `wiki-enrich`).<br>• It does deterministic fetch+convert → REASON → a summary note **plus** its `_concepts/` pages → indexed, all in one `prepare`/`apply` loop.<br>• Two orthogonal axes: **content-type** (`--kind`, auto-detected) sets the note `type:` + the REASON harness (all content → the ONE universal `summarizing-meetings`; finished `summary` → register), and the vault **LAYOUT (config)** decides where it files (Karpathy `_sources/`+root `_concepts/` vs PARA — Projects/Areas/Resources/Archives, a common personal-vault folder method — topic-folder+sibling `_concepts/`, via `resolve_layout_config` — Karpathy is a layout YAML, not a code fork, ADR-007).<br>• If you *already have a finished summary* and want it verbatim, skip the REASON step and use the [pre-made-summary recipe](#registering-a-pre-made-summary-not-raw) instead.<br>• `prepare` shells out to `html`/`pdf` + emits **`known_concepts`** (reuse them — the discipline that stops dangling `[[wikilinks]]`, Obsidian's double-bracket links between notes, "dangling" when the target page doesn't exist); `apply` files the note + `_concepts/` with the **collision guard** (a generic `defi` never evicts `Defi.md`). (Diagram: `docs/architectures/functional-architecture.md` §2.3.) |
| **`wiki-extract-concepts`** | The *retroactive* on-ramp: given a source page already in the index, it extracts the concepts/entities it mentions but that have no page yet.<br>• Turns implicit knowledge into explicit, linkable pages — each carrying the derived `<!-- BEGIN-AUTO:mentions -->` ledger, regenerated by `wiki-index-render --concept-mentions` (TASK 047).<br>• A two-pass `prepare`/`apply` skill (see [below](#the-prepare--apply-contract-decision-17)).<br>• Use it to *densify* an existing corpus, or after importing many sources at once — **regardless of how the source page got indexed** (imported or hand-registered). |
| **`wiki-extract-decisions`** | The *typed-knowledge* on-ramp (TASK 063 / RFC-004): given a **summarised** source note, it extracts the **decisions / requirements / risks** it records — plus the typed **forward edges** between them (`implements` / `supersedes` / `causes` / …) — as first-class graph pages that `wiki-graph` can traverse and `wiki-health` can audit.<br>• A two-pass `prepare`/`apply` skill. `prepare` emits the **ontology contract** (the class roster, each edge's domain/range, each class's `status` enum) and PREFLIGHTS the layout (G4 — it refuses *early* if the vault maps no typed classes, or the target folder is invisible to the layout's read globs, because a glob-invisible page is written, never indexed, and raises no lint issue); `apply` validates **every** candidate against that contract *before* the first write (any violation ⇒ exit 4, **zero files**).<br>• **Anti-fabrication is a mechanism, not a request:** an empty extraction is a **SUCCESS** (`no_candidates`, exit 0 — a note with no decisions is a normal note), and every `source_quote` must be **verbatim** from the note; there is no escape hatch.<br>• Config-driven via the cascading `extract_decisions:` block in `.wiki/sync.yaml`; `wiki-sync` / `wiki-import` emit a **dispatch marker** (never an inline LLM call). ⚠️ Typed classes are layout-dependent — `cybos` maps them; `obsidian-personal` does **not** (there `prepare` refuses at G4). |
| **`wiki-index-upsert`** | The single-file primitive. Indexes one markdown file idempotently (a file-hash match is a no-op). Use it when you've hand-written, hand-edited, **or dropped in a finished summary from elsewhere** and want the index to reflect it immediately without a full reindex — **no LLM, no raw processing**. |
| **`wiki-append-log`** | Writes a structured event to `log.md` *and* mirrors it to the `log_events` table atomically (flock + fsync, bi-directional M-2 contract). The log is grep-friendly chronological memory for future agent sessions — git diff is for humans, the log is for the next LLM. |

```bash
# plan the zone; writes nothing
wiki-sync scan "03 - Learning" --vault personal --dry-run
# fetch+convert one external source (REASON follows)
wiki-import prepare --vault personal --vault-root ~/Vault --kind auto \
    --source "https://example.com/article" --folder "05 - Материалы" --mode full
# recon pass for concept extraction
wiki-extract-concepts prepare --vault personal --vault-root ~/Vault --source-page my-article
# recon pass for typed-knowledge extraction (decisions/requirements/risks — layout must map them)
wiki-extract-decisions prepare --vault cybos --vault-root ~/CybosVault --source-page protocol-note
# index one ready note (no LLM)
wiki-index-upsert --vault personal --source ~/Vault/_sources/my-article.md
# append a structured log event
wiki-append-log --vault personal --event-type ingest --subject "imported my-article"
```

> **✅ Key takeaways.** One engine, three entry points: `wiki-import` for one
> source (any format, LLM distillation), `wiki-sync` for a whole zone (it plans
> deterministically and delegates each distil to `wiki-import`), and
> `wiki-index-upsert` for a note that is already finished (no LLM ever touches
> it). If you remember only one routing rule: raw material gets distilled,
> finished notes get upserted.

### 2. Search & retrieve

The everyday read path — **search before you grep**.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-search`** | FTS5 BM25 (the standard keyword-relevance ranking formula) full-text search across one or many vaults, ranked with snippets, expanding through entity aliases by default — the fast lookup that replaces re-reading raw files.<br>• **Default search is inflection-tolerant** (TASK 028): bare terms are auto stemmed (matched by word root) + prefixed (per-term by script — Cyrillic→russian, Latin→english) and **ё/е-folded** on both the query and the body corpus, so one typed form finds its siblings and `ещё`/`еще` are one token. `--exact` (`--no-stem`) disables stemming for literal precision (ё/е fold still applies). The body ё/е fold takes effect on the next `wiki-reindex --full`; stemming + the query ё-fold are immediate.<br>• **Metadata filtering**: `--status` / `--severity` / `--where 'field=value'` compile to a `CAST(json_extract(frontmatter_json, …) AS TEXT) = ? OR EXISTS(json_each … = ?)` predicate (not full-text), so hyphenated (`SEV-2`) and numeric (`priority=1`) **scalar** values match by string AND a **list member** matches too (TASK 033) — `--tag decision` (sugar for `--where 'tags=decision'`) lists every typed-class `decision` page in one command; omit the query for a pure metadata *listing* (the `--tag`/`tags=` listing narrows through the existing `pages_fts.tags` index since TASK 035 — identical results, ~4× faster at scale).<br>• **Temporal filtering** (TASK 034): `--as-of YYYY-MM-DD` returns only pages **active on that date** — created on-or-before it AND not yet superseded/invalidated by then, *derived* from `pages.date` + the supersede/invalidate event graph (no LLM, no hand-authored `valid_to`; `valid_from`/`valid_to` are optional overrides). E.g. `--tag decision --as-of 2026-04-15` answers "which decisions were live on 2026-04-15".<br>• Two optional retrieval-scope filters also ride here (default-OFF): `--audience <level>` (a classification gate) and `--log-access` (read-audit) — see [Policy, provenance & read-audit](#policy-provenance--read-audit-adr-009). |
| **`wiki-index-render`** | Regenerates `index.md` — a *read-only projection* of the DB — preserving any operator-authored `<!-- BEGIN-CUSTOM:name -->` blocks. Use it to refresh the human-browsable catalog after imports.<br>• With `--auto-indexes` it also renders Class-B "rebuildable markdown" ledgers (e.g. a `KNOWN_ISSUES.md` rolled up from per-issue source files).<br>• With **`--concept-mentions` (TASK 047)** it regenerates each concept page's `<!-- BEGIN-AUTO:mentions -->## Mentions across sources … <!-- END-AUTO:mentions -->` block — a **derived** "which sources mention this concept" ledger, so concept compounding is a rebuildable render, not a body-merge. |

```bash
# ranked full-text search with snippets
wiki-search "lasso regularization" --vaults personal --limit 5
# regenerate index.md and auto ledgers
wiki-index-render --vault personal --auto-indexes
```

> **✅ Key takeaways.** `wiki-search` is the everyday read path — full-text by
> default, metadata (`--where`/`--tag`) when you want a listing, `--as-of` when
> you want a point-in-time view; search before you grep. `wiki-index-render`
> never authors knowledge: it only *projects* the DB into browsable markdown, and
> anything it writes is Class B — regenerable, not editable.

### 3. Resolve entities

The corpus accumulates *candidate* entities (LLM-guessed) and duplicate spellings.
These commands curate the entity graph — the network of concept/entity pages and
the references between them — so it stays a graph, not a pile.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-confirm`** | Promotes a *candidate* entity (`is_candidate = 1`, LLM-extracted, unvetted) to *confirmed* — your editorial sign-off that this is a real, canonical entity. `--undo` demotes; `--auto --threshold N` bulk-promotes anything mentioned ≥ N times. Confirm-state is Class A (entity-page frontmatter) mirrored to the DB. |
| **`wiki-alias`** | Registers surface-string aliases ("Hermes" → `hermes-agent`). Aliases are **hard-unique per vault** (one surface → exactly one entity) and `wiki-search` expands through them, so a query for any spelling finds the canonical page. Class A frontmatter + DB mirror. |
| **`wiki-merge`** | Folds a duplicate entity into the canonical one (`hermes-framework` → `hermes-agent`): re-points all references, absorbs + registers redirect aliases, and deletes the duplicate page. The alias table *is* the durable redirect — there is no wikilink rewriting to drift out of sync. |

```bash
# promote a candidate entity
wiki-confirm hermes-agent --vault personal
# register an alias surface-string
wiki-alias hermes-agent --add "Hermes" --vault personal
# fold a duplicate entity
wiki-merge hermes-framework hermes-agent --vault personal
```

> **✅ Key takeaways.** Entity curation is editorial work the machine cannot do
> for you: confirm what is real, alias the spellings, merge the duplicates. The
> payoff is that search expands through aliases and the graph stays navigable.
> Confirm-state and aliases live in Class A frontmatter — the DB only mirrors them.

### 4. Answer & verify (RAG)

The compounding payoff: turn the corpus into cited answers, and audit them.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-query`** | Retrieval-augmented answering — "good answers can be filed back into the wiki" made durable.<br>• `prepare` retrieves (FTS5 BM25 + alias/entity-graph expansion); the orchestrator agent synthesises a *cited* answer; `apply` files it as a first-class compounding `_queries/<slug>.md` page (a *slug* is the file-name-safe identifier derived from a title) — indexed, FTS-searchable, with `cited` backlinks that survive a full reindex.<br>• Optional retrieval-scope controls — `--min-trust` (a provenance floor) and `--audience` (classification), both folded into `question_hash` so `apply` must repeat them — are covered in [Policy, provenance & read-audit](#policy-provenance--read-audit-adr-009). |
| **`wiki-verify-multi`** | An **off-by-default** four-critic prose audit (factual-grounding / logic-coherence / security-injection / completeness-faithfulness) of a filed answer *against the sources it cited*.<br>• Files a `_verifications/verify-<slug>.md` verdict page.<br>• A FAIL **records the verdict and exits non-zero — it never edits the answer**.<br>• Reach for it on high-stakes answers where a silent hallucination would be costly. |
| **`wiki-graph`** | Read-only **event-graph** traversal (TASK 032/034 / ADR-004): "what did this decision cause / what supersedes X / the lineage."<br>• Traverses the typed page-to-page edges (`implements`/`supersedes`/`causes`/`relates-to`, plus the TASK-034 `invalidated-by`/`activated-by`/`uses`/`owns`, + auto-derived inverses) authored in frontmatter and indexed on reindex.<br>• Subcommands: `backlinks` (inbound) / `neighbors` (one-hop, in/out/both, by `--kind`) / `chain` (bounded supersession/causation lineage).<br>• Pairs with `wiki-query prepare --follow-edges`, which weaves typed-edge neighbors into a cited answer (default OFF; deterministic). |

```bash
# retrieve context for a cited answer
wiki-query prepare "compare X and Y" --vault personal --vault-root ~/Vault
# audit a filed answer against sources
wiki-verify-multi prepare td-sequential-risks --vault personal --vault-root ~/Vault
# trace a supersession lineage
wiki-graph chain switch-to-kafka --kind supersedes --vault personal
```

> **✅ Key takeaways.** `wiki-query` makes an answer *durable*: retrieved, cited,
> filed back as a page the next query can find. `wiki-verify-multi` audits a filed
> answer against its own citations and records a verdict — it never edits the
> answer. `wiki-graph` reads the typed-edge graph deterministically; no LLM is
> involved in traversal.

### 5. Maintain health

| Command | Why it exists / what it does |
|---|---|
| **`wiki-lint`** | A SQL-level health-check over one vault or all of them. Run it periodically; the findings have a natural action priority (dangling → contradictions → missing → orphans).<br>• Surfaces **orphan links** (pages with no inbound links), **dangling refs** (`[[X]]` with no page X), **missing-on-disk** pages (DB/disk drift), **hash drift** (a file changed but wasn't reindexed), **type mismatches**, and **cross-vault concept duplicates**.<br>• Since **R-15 / TASK 036** it also runs **lifecycle-drift** — a page whose authored `status` *contradicts* the event graph (a `decision` carrying a `superseded-by` edge but still `status: accepted`; one an incident `invalidates` but still live).<br>• Since **R-19 / TASK 054** it runs **ontology-violation** — a page that breaks the declared `ontology:` contract (an edge whose source/target class is out of its `from`/`to`, e.g. a `fact` that `implements` a `risk`; or a `status` outside its class enum).<br>• Both drift and ontology-violation are **advisory by default and gate only `--strict`** (they are true contradictions); `--mtime-skip` trades full-hash integrity for speed. |
| **`wiki-health`** | Read-only **derived knowledge-health** report (R-15 / TASK 036, ADR-006) — the always-exit-0 sibling of `wiki-lint`'s `--strict`-gating contradictions.<br>• **`wiki-health coverage --vault <id> [--class C]`** lists pages **missing an expected relation** — a `requirement` nothing implements, a `capability` no agent provides, a `fact` with no `source:`.<br>• **`wiki-health ontology --vault <id> [--class C]`** (R-19 / TASK 054) lists pages **contradicting the declared `ontology:` contract** — an edge whose source/target class is out of its declared domain/range, or a `status` value outside its class enum.<br>• Both are computed over frontmatter + the event graph (layout-config-driven `coverage_rules` / `ontology`; the `cybos` layout ships them, other layouts → an empty report) and **always exit 0** (a gap/violation from this surface is *data* — the `--strict` gate for the ontology contradiction is `wiki-lint`).<br>• Pure derivation: zero new fields, zero DDL. |
| **`wiki-config`** | (TASK 058) The interface for the **per-folder `.wiki/sync.yaml`** config — answers *"which settings does this folder actually get, and from where?"*.<br>• `show` prints per-key inheritance *provenance* — where each effective value comes from (no folder argument → the **active Obsidian note's** folder, then CWD, then vault root).<br>• `tree` maps every override point vault-wide, incl. the #1 trap — a **root-only key** (`zones`/`exclude`/`extensions`/`transcript_dedup`/`tag_namespace`) sitting in a subfolder file where it is *silently ignored* (only `resummarize:`/`summarize:` cascade).<br>• `validate` lints ALL three config systems (40-code taxonomy, exit 6 on errors); tiered `doctor`/`fix` repair mechanically (comment-preserving, backed up to `.wiki/backups/`, TOCTOU-guarded — protected against time-of-check/time-of-use races — and `restore` undoes).<br>• `set`/`unset` edit one key; `init --template` scaffolds from `templates/sync-profiles/`; `report --open` renders ONE self-contained HTML inheritance report; `serve` starts the local web editor.<br>• Fully schema-driven (`x-wiki-*` annotations) — a NEW config field appears in every surface with zero interface-code changes; needs no DB (works while the index is broken).<br>• **Full copy-paste commands + editor tour: [Configuring folders with `wiki-config`](#configuring-folders-with-wiki-config-provenance-repair-templates-web-editor).** |
| **`wiki-reindex`** | Rebuilds the DB from markdown. `--full` wipes and rebuilds (this is the **rebuildability gate** — if a vault can't survive `--full`, the Class A→B contract is broken); `--delta` does an incremental mtime/hash-based pass after manual edits. The authoritative reconciliation of cache ↔ canon. |

```bash
# SQL health-check; gate on contradictions
wiki-lint --vault personal --strict
# coverage gaps (typed vaults, e.g. cybos)
wiki-health coverage --vault cybos --class requirement
# effective config with per-key provenance
wiki-config show --vault-root ~/Vault
# incremental reindex after edits
wiki-reindex --delta --vault personal
```

> **✅ Key takeaways.** Two kinds of health surface here and they behave
> differently: contradictions (lint's drift/ontology findings) can gate a pipeline
> via `--strict`; gaps (`wiki-health`) are data and always exit 0. `wiki-reindex
> --full` doubles as the rebuildability proof — if a vault cannot survive it, the
> Class A→B contract is broken somewhere. `wiki-config` is the safe way to touch
> the per-folder config tree.

### 6. Vault lifecycle

| Command | Why it exists / what it does |
|---|---|
| **`wiki-init`** | Brings a vault under management — the one-time setup per vault.<br>• `--register-existing` indexes a pre-existing vault; `--scaffold-new --layout <name>` creates a fresh vault skeleton; `--reconcile` renames/re-points a registered vault.<br>• Add `--local` (or `--index-db <path>`) to give the vault its **own** index DB instead of the shared global one — see below. |

```bash
# scaffold a fresh karpathy vault
wiki-init --scaffold-new --vault ~/Vaults/courses --layout karpathy
```

#### Choosing the index database: global (default) vs vault-local

There are two ways to store a vault's index, and you choose **once, at init**:

| | **Global (default)** | **Vault-local** |
|---|---|---|
| Where the DB lives | `~/Library/Application Support/wiki-index/global.db` (macOS) — *outside* every vault | inside the vault, e.g. `<vault>/.wiki/index.db` |
| Declared in `WIKI_SCHEMA.md`? | no (`index_db` absent) | yes (`index_db: .wiki/index.db`) |
| Good when | many vaults you search together; one machine | the vault must be **portable** — clone/move it and the index comes along; or you want one DB per project, gitignored & rebuildable |
| `--vault all` reaches | every vault registered in the global DB | only this vault (it's an **island** — no cross-DB federation) |

Three recipes — the **only** difference is what `wiki-init` writes into `WIKI_SCHEMA.md`:

```bash
# (a) GLOBAL — the default. Nothing extra to declare.
wiki-init --register-existing --vault /path/to/MyVault

# (b) VAULT-LOCAL — DB at <vault>/.wiki/index.db (vault-relative & contained:
#     a symlink or `..` escape out of the vault is refused). --local writes
#     `index_db: .wiki/index.db` into WIKI_SCHEMA.md and registers into THAT DB.
wiki-init --register-existing --vault /path/to/MyVault --local
#     ...or a custom in-vault path:
wiki-init --register-existing --vault /path/to/MyVault --index-db db/index.db

# (c) CLOUD-SYNCED vault (iCloud / Dropbox) — SQLite must NOT sit inside the
#     byte-syncing folder (WAL/shm corruption). Point at an ABSOLUTE path OUTSIDE
#     the sync root. A path under the OS app-data dir (where wiki-init writes, never
#     iCloud) is trusted automatically — no env var. An absolute path ELSEWHERE needs
#     WIKI_ALLOW_ABSOLUTE_INDEX_DB=1 (so a synced/cloned config can't redirect writes):
wiki-init --register-existing --vault /path/to/MyVault \
          --index-db "~/Library/Application Support/obsidian-llm-wiki/myvault.db"
```

`--local` / `--index-db` are pure convenience — equivalently, hand-edit
`WIKI_SCHEMA.md` and add `index_db: .wiki/index.db` to the frontmatter. **Precedence
is always `--db-path` (a per-command override, mainly for tests) > `index_db`
(in `WIKI_SCHEMA.md`) > global.** So a vault is global until the day you add
`index_db`; remove the key and it's global again, byte-for-byte. **iCloud paths are
auto-rejected wherever they appear**, to prevent SQLite WAL/shm corruption.

> **✅ Key takeaways.** `wiki-init` is once-per-vault, and the one decision it
> locks in is where the index lives: global (many vaults, one DB, cross-vault
> search) or vault-local (the index travels with the vault, but it is an island).
> Cloud-synced folders must never contain the SQLite files; the tooling refuses
> iCloud paths for you.

---

## Working with documents in Obsidian

This is the half most operators get wrong: **what do the files look like, what may
I touch by hand, and how do I make the tooling fit a vault that isn't shaped like
Karpathy's?** First, a map of the configuration files; then three parts: the standard
layout, the page contract, and custom layouts.

### Vault configuration files (overview)

Under `<vault>/` live a few configuration surfaces. The key thing: there are **two
SEPARATE systems** — the vault's *identity* (`WIKI_SCHEMA.md`) and the layout *grammar*
(`.wiki/layout.yaml`); they don't overlap and change independently.

| File | Responsibility | Required | How it's overridden |
|---|---|---|---|
| **`WIKI_SCHEMA.md`** (frontmatter) | The vault's **identity**: `vault_id`, `layout`, optional `index_db`, optional `policy:` (ADR-009) | **Yes** | It *is* the vault's declaration — hand-edited, never merged |
| **`.wiki/layout.yaml`** | The **layout grammar**: WHAT and HOW to index — `ignore`, `type_mapping`, `paths`, `ref_extraction`, `drift_rules`/`coverage_rules`, `ontology` (R-19: the declared type/edge/property contract) | No (base = the built-in `layout`) | Per-key: **`ignore` → UNION**, **`type_mapping` → deep-MERGE**, **`paths`/`ref_extraction`/`ontology.edges`/`ontology.properties` → REPLACE** |
| **`.wiki/sync.yaml`** | **`wiki-sync`** config: `zones` (**advisory** — it *documents* the zones; nothing reads it at runtime), `exclude` (**the** walk scope — the only key that prunes), `extensions`, `tag_namespace`, the `resummarize` gate | No | Strict schema; a deeper `<subfolder>/.wiki/sync.yaml` deep-merges over the root one |
| **`.wiki/page-types/*.md`** | Authoring scaffolds — one template per typed class | No | Copied by `wiki-init`; not indexed themselves (they live under `.wiki/`) |

- **Two systems.** `WIKI_SCHEMA.md` answers "WHAT vault is this" (identity —
  `config_loader`); `.wiki/layout.yaml` answers "HOW to index it" (grammar —
  `layout_config`). Distinct layers, edited separately.
- **The override rule that bites.** In `.wiki/layout.yaml`, `paths` and `ref_extraction`
  **REPLACE** the built-in list wholesale — supply `paths:` with one rule and you silently
  lose all the built-in routing; to extend, re-declare the base rules verbatim + yours.
  `ignore` and `type_mapping`, by contrast, ADD to the built-in.
- **Index DB location (`index_db`).** Defaults to one shared global DB; declare `index_db:`
  in `WIKI_SCHEMA.md` to make the DB travel with the vault. Precedence: `--db-path` >
  `index_db` > global.

Details: layout override semantics are in **"Custom layouts: the layout engine"**;
`wiki-sync` in **"Automating the mix: `wiki-sync`"**; the `policy:` block in **"Policy,
provenance & read-audit"**.

> **✅ Key takeaways.** Two separate config systems, never conflated:
> `WIKI_SCHEMA.md` says *what vault this is* (identity), `.wiki/layout.yaml` says
> *how to index it* (grammar). The merge rule that bites: `paths` and
> `ref_extraction` overrides REPLACE the built-in list wholesale, while `ignore`
> unions and `type_mapping` deep-merges.

### The standard (karpathy) layout

`wiki-init --scaffold-new --layout karpathy` creates (and the tooling expects)
this shape. The leading-underscore folders follow the Obsidian system-folder
convention — they sort to the top and signal "meta-content, not user notes":

```
<vault>/
├── WIKI_SCHEMA.md          # this vault's identity + conventions (REQUIRED — holds vault_id)
├── index.md                # read-only catalog projection (## Sources / ## Concepts / ## Entities)
├── log.md                  # chronological append-only journal (mirrors log_events)
├── _sources/               # per-source summary pages         (type=summary)   ← wiki-import
├── _concepts/              # abstract concepts                (entities)        ← wiki-import
├── _entities/              # concrete people/companies/...     (entities)        ← wiki-import
├── _queries/               # filed RAG answers                (type=query)      ← wiki-query
├── _verifications/         # verdict pages                    (type=verification) ← wiki-verify-multi
├── _raw/                   # immutable raw source files (never modified)
│   ├── .locks/             # ingest lock files
│   └── failed/             # quarantined failed ingests
├── 00-Vault-Index/
│   └── log/                # monthly log.md files
└── Lessons/<Course>/       # (optional) course-tier sub-vaults (ADR-002 §D6)
```

Key distinctions:

- **`_sources/` vs `_concepts/`/`_entities/`.** Sources are *immutable summaries
  of one input*; concepts/entities are *additive, cross-referenced abstractions*
  built from many sources. The first is a leaf; the second is the graph.
- **Vault-tier vs course-tier.** A page at the vault root has
  `pages.project = '_vault_'`. A page under `Lessons/<Course>/` carries the
  slugified course name as its `project` — letting one vault hold many course
  sub-corpora without cross-talk.
- **`index.md` and the auto-rendered ledgers are Class B** — *generated*. Don't
  author knowledge there; author it in pages, then `wiki-index-render`. The one
  exception: explicit `<!-- BEGIN-CUSTOM:name --> … <!-- END-CUSTOM:name -->`
  blocks are preserved verbatim across renders.
- **`WIKI_SCHEMA.md` is the vault's identity card.** It is `wiki-init`'s discovery
  marker and holds the **required** `vault_id` (`^[a-z][a-z0-9-]{2,31}$`, no hash
  fallback) plus `layout:` and `language:`.
  - **The `vault_id` is what you pass to `wiki-* --vault`/`--vaults`** — find it with
    `grep '^vault_id:' WIKI_SCHEMA.md`, or list all registered vaults with
    `sqlite3 "<index_db>" "SELECT vault_id, root_path FROM vaults;"` (every `wiki-*` JSON
    line also echoes `"vault_id"`; there is no `wiki-* --list-vaults`).
  - **Do not confuse it with the Obsidian vault *NAME*** (the folder name shown by
    `obsidian vaults verbose`, used by `obsidian …` / `obsidian-active-note --vault`). The
    two namespaces are independent and **may differ** (e.g. wiki `vault_id: personal` vs
    Obsidian name `ObsidianNotes`).

> **✅ Key takeaways.** The underscore folders are the system-managed half of the
> vault: `_sources/` holds immutable per-input summaries (leaves), `_concepts/` and
> `_entities/` hold the additive cross-referenced graph. `index.md` and the ledgers
> are generated projections — never author knowledge in them. And keep the two ID
> namespaces apart: the wiki `vault_id` (what `--vault` takes) is not the Obsidian
> vault name.

### Page anatomy & the auditability invariants

A concept/entity page (produced by the file layer, indexed by this repo) carries
frontmatter + sectioned body + footnote citations. The two invariants you must not
break by hand:

**1. The citation footnote (the auditability invariant).** Every fact traces back
to its source via a Markdown footnote whose key matches the source page slug:

```markdown
## Definition
Risk-adjusted return: `(R_p − R_f) / σ_p`. [^src-hermes-trading-agent]

## Footnotes
[^src-hermes-trading-agent]: [[hermes-trading-agent]] — AI Trading Agent Holy Grail
```

Click the footnote → jump to the source. This is what keeps the wiki auditable at
50 ingests instead of becoming a noise pile.

**2. The contradiction block (the don't-pick-a-winner invariant).** When a new
source disagrees with an existing claim, the tooling inserts a `## Contradictions`
block for operator review rather than silently overwriting:

```markdown
## Contradictions
> ⚠️ **Contradiction flagged** — operator review needed.
> - Existing claim: min Sharpe of 1 recommended
> - New claim from [[conservative-crypto-guide]]: a minimum Sharpe of 0.5 is sufficient.
```

The operator resolves contradictions by editing the page — the machine's job is to
*surface*, not to *decide*.

Frontmatter fields the index reads: `type`, `title`, `date`, `tags`,
`concepts:`/`related:` (link targets), `aliases:`, `is_candidate`, and reference
fields like `cites:` (→ `cited` refs) and `verifies:` (→ `verifies` refs). The
`frontmatter_json` column stores the whole block, which is what powers
`wiki-search --where`.

> **✅ Key takeaways.** Two invariants keep a growing wiki trustworthy: every fact
> carries a footnote back to its source (auditability), and a disagreement between
> sources becomes a visible `## Contradictions` block instead of a silent
> overwrite (the machine surfaces, the operator decides). Break either by hand and
> the corpus degrades into an unauditable pile.

### The author's contract: markdown is canonical

Because the DB is a rebuildable cache, **hand-editing markdown is supported and
expected** — but it has a discipline:

| You did this | Then do this | Why |
|---|---|---|
| Edited one page by hand | `wiki-index-upsert --file <path>` (or `wiki-reindex --delta`) | The index must learn about the change; otherwise `wiki-lint` reports **hash drift**. |
| Edited many pages / restructured | `wiki-reindex --delta` (or `--full`) | Delta catches mtime changes; full is the authoritative rebuild. |
| Added a fact to a concept page | Add the `[^src-…]` footnote | Preserve auditability — an unfootnoted claim is an orphaned assertion. |
| Want to change the on-disk convention | Edit the layout (see below), not individual pages | Conventions are config, not per-file edits. |

> **Safety:** `wiki-index-render` and `wiki-reindex --full` overwrite generated
> markdown (`index.md`, ledgers). Commit to git first. Authored *pages* are never
> overwritten by these — only the projections are.

> **✅ Key takeaways.** Hand-editing is a supported first-class operation, not a
> workaround — the whole design exists so you can. The contract is small: tell the
> index afterwards (upsert or `--delta`), keep new facts footnoted, and change
> conventions in the layout config rather than file by file.

### Registering a pre-made summary (not raw)

A very common case: **you already have a finished article/summary** — produced by
another tool, written by hand, exported from somewhere — and you want it in the
vault as a source page so you can later extract concepts from it. You do **not**
want it run through the raw LLM-summarisation pipeline (it's already a summary).

**Which on-ramp do I use?** This is the single most common confusion, so decide it
explicitly:

```mermaid
flowchart TD
    Q{"What do you have?"}
    Q -->|"a LOCAL raw file<br/>(transcript, notes) — needs summarising"| ENR["wiki-import --source &lt;file&gt;<br/>= REASON summarises → note + _concepts/ → index"]
    Q -->|"an EXTERNAL URL / PDF / X-thread / meeting<br/>(any layout)"| IMP["wiki-import: prepare → REASON → apply<br/>= fetch+convert + --kind detect, summarise (fed known_concepts),<br/>→ note + _concepts/ filed PER LAYOUT (config) → index"]
    Q -->|"a FINISHED summary<br/>(already distilled elsewhere)"| REG["1. place it at _sources/&lt;slug&gt;.md (with frontmatter)<br/>2. wiki-index-upsert --source &lt;abs path&gt;<br/>= indexed verbatim, NO LLM, NOT raw"]
    ENR --> IDX["source page is now indexed (type=summary)"]
    IMP --> IDX
    REG --> IDX
    IDX -->|"optional: densify"| EXT["wiki-extract-concepts prepare/apply<br/>--source-page &lt;slug&gt;<br/>→ concept/entity pages"]
    classDef raw fill:#fdeede,stroke:#e0a050;
    classDef premade fill:#eef7ee,stroke:#5a5;
    classDef para fill:#e8f0fe,stroke:#5a7;
    class ENR raw;
    class REG premade;
    class IMP para;
```

> **One on-ramp, layout from config (TASK 039/040):** `wiki-import` files PER the vault's
> resolved layout — Karpathy `_sources/`+root `_concepts/`, PARA topic-folder+sibling
> `_concepts/` — via `LayoutConfig.write` (no layout-name fork; ADR-007). It feeds the REASON
> step the vault's `known_concepts` so wikilinks resolve. The old Karpathy-raw `wiki-enrich`
> and its vendored `wiki-ingest` synthesis layer were retired (TASK 047); `wiki-import` (hand
> it a local `--source`) is now the single raw on-ramp. Diagram:
> `docs/architectures/functional-architecture.md` §2.3.
>
> **Universal + localized (2026-06 hardening).** The summary is written **in the vault's
> `language`** (`WIKI_SCHEMA`; English fallback) — headings/labels are localized, never
> hardcoded to one locale. The note links to its original via a clickable `[[_raw/<slug>]]`
> wikilink (the `_raw/` capture is kept but never indexed). Concept pages are filed only on a
> concept-capable layout (Karpathy / obsidian-personal / cybos); a structured-doc layout like
> `dev-project` files just the summary note (no concepts) so nothing is left un-rebuildable.
> Works on all four built-in layouts. Bad input fails with a clean JSON envelope
> (`INVALID_FOLDER` / `INVALID_VAULT_ROOT` / `FETCH_FAILED`), never a traceback.

`wiki-import` runs the REASON step (`summarizing-meetings`) to *distil* whatever
you hand it — raw file or external source. For a finished summary you want kept
verbatim, skip that distillation and register the page directly. The full recipe:

**Step 1 — Place the summary in `_sources/` with valid frontmatter.** The karpathy
layout *requires* a `type:` (it does not synthesise one), and the page needs a
`title`. The minimal source-page frontmatter:

```markdown
---
type: summary            # → pages.type=summary (also: lesson-summary, meeting-summary, summary-light)
title: "My Article Title"
date: 2026-06-02         # optional; real-world sources may be undated
tags: [imported, crypto] # optional; powers wiki-search --where
---

# My Article Title

…the summary prose. Any [[wiki-links]] in the body become reference edges
(orphan links until the target pages exist — wiki-extract-concepts can create them).
```

(For a `dev-project` / custom layout the `type:` may be inferred from the path or
synthesised — see [Custom layouts](#custom-layouts-the-layout-engine) — but in
`_sources/` under karpathy, frontmatter `type:` is mandatory or the upsert raises
`UnmappedTypeError`.)

**Step 2 — Index it (no LLM, no raw step):**

```bash
wiki-index-upsert --vault my-vault --source /abs/path/to/MyVault/_sources/my-article.md
# idempotent: re-running on unchanged content is a no-op (file-hash match)
```

The page is now a first-class `type=summary` source, immediately FTS-searchable.

**Step 3 (optional) — Extract concepts from it.** Because the source is now
indexed, `wiki-extract-concepts` works on it exactly as it would on a raw-ingested
page — it does not care how the page arrived:

```bash
wiki-extract-concepts prepare --vault my-vault --vault-root /abs/path/to/MyVault \
    --source-page my-article
# → orchestrator synthesises candidate concepts JSON (concept-extraction contract)
wiki-extract-concepts apply   --vault my-vault --vault-root /abs/path/to/MyVault \
    --source-page my-article --source-hash <hash from prepare> \
    --candidates-stdin --ingest < candidates.json
```

Inside a Claude Code session, just say *"register the summary at `<path>` into
`my-vault` (don't re-summarise it), then extract its concepts"* — the agent runs
the upsert and drives the two-pass `wiki-extract-concepts` flow.

> **Why not just point `wiki-import` at it?** `wiki-import` would treat your summary
> as *raw input* to the REASON step and produce a **summary-of-your-summary** —
> double-distilled, with new slugs. Registering directly keeps your text verbatim
> and canonical. Use `wiki-import` only when the LLM *should* do the distillation.

> **✅ Key takeaways.** Pick the on-ramp by what you hold: raw material →
> `wiki-import` (the LLM distils it); a finished summary → place it in
> `_sources/` with frontmatter and `wiki-index-upsert` it verbatim (no LLM).
> Either way the page ends up equally first-class — `wiki-extract-concepts` does
> not care how a source got indexed.

### Custom layouts: the layout engine

Not every vault is Karpathy-shaped. A software repo's `docs/` tree, a personal
Obsidian vault with numbered folders and Unicode titles — these need a different
"where do pages live / what type are they" grammar. Since TASK 012 that grammar is
**YAML config, not code** (`scripts/wiki_index/layout_config.py`, schema
`config/layout-config.schema.yaml`).

Four layout *grammars* ship built-in (`scripts/wiki_index/layouts/`), exposed as six
`--layout` values (`flat`/`per-project` are aliases of `karpathy`):

| Layout | Shape | Slug strategy |
|---|---|---|
| `karpathy` | The standard layout above. **Byte-identical** to the legacy hardcoded behaviour (golden-anchor-guarded). Aliases: `flat`, `per-project`. | `identity` (verbatim stem) |
| `dev-project` | A repo's `docs/` — `tasks/*.md`, `adr/*.md`, `issues/*.md`, etc. | `transliterate` (ASCII-safe) |
| `obsidian-personal` | Numbered folders + Unicode | `preserve-unicode` |
| `cybos` | **Typed knowledge / "operational-memory" vault** (TASK 031/034): `decisions/ requirements/ risks/ incidents/ hypotheses/ facts/ events/` + the `tasks/ adr/ plans/` engineering spine + the TASK-034 agent-memory classes `agents/ tools/ workflows/ capabilities/ executions/ patterns/`. The home for the typed knowledge classes AND the agent-memory model. | `transliterate` |

Pick one at init: `wiki-init --scaffold-new --vault <path> --layout dev-project`.

**Authoring a custom layout.** A layout YAML maps files → `(type, project)`, maps
those raw types onto the DB's `pages.type` enum, and declares how cross-references
are extracted. Here is the shape, annotated (the real `dev-project.yaml` is the
best worked example):

```yaml
schema_version: '2.0'
layout: my-layout
slug_strategy: transliterate          # identity | preserve-unicode | transliterate | ascii-only
ignore: [".git/**", "**/.DS_Store"]   # globs never indexed
file_extensions: ['.md']

# Globs evaluated in order, first-match-wins (relative to vault_root):
paths:
  - {glob: "tasks/*.md", type: task, project: "_vault_"}
  - {glob: "adr/*.md",   type: adr,  project: "_vault_"}
  # project can also be DERIVED from the path via a (guarded) regex:
  - {glob: "Lessons/*/*.md", type: lesson,
     project_pattern: "Lessons/(?P<name>[^/]+)/", project_template: "${name}",
     project_slug_strategy: course-slug}

# Route your raw types onto the live pages.type CHECK enum + a filterable tag.
# This is how NEW doc types get indexed with ZERO schema change (no DDL):
type_mapping:
  task: {db_type: brief,    tag: task}
  adr:  {db_type: research, tag: adr}

path_type_fallback: {}                # raw_type when neither paths[].type nor frontmatter set it

# How to pull [[links]] / [md](links.md) / ID-refs out of a page body:
ref_extraction:
  - {kind: wiki-link, regex: '\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', target_group: 1}
  - {kind: id-ref,    regex: '\b(ADR-\d+|task-\d+)\b',         target_group: 1}

# Synthesise a title for docs that lack frontmatter (e.g. a bare ROADMAP.md):
frontmatter_synthesis: {enabled: true, title_source: first_h1, fallback_title: filename_stem}

# Render a rebuildable-markdown ledger from a set of source pages:
auto_indexes:
  - {source_type: known-issue, output: KNOWN_ISSUES.md, group_by: category,
     sort_within_group: [severity, opened_at, id]}
```

Override per-vault via `<vault>/.wiki/layout.yaml` or a `WIKI_SCHEMA.md`
frontmatter `layout_config:` pointer.

> **Override merge semantics — a sharp edge (TASK 025).** A per-vault override does
> NOT merge uniformly: scalars overlay; **`ignore` UNIONs** the built-in list and
> **`type_mapping` deep-MERGES**; but **`paths` and `ref_extraction` REPLACE** the
> entire built-in list the moment you supply the key. To extend/deepen `paths` (e.g.
> add a per-module project rule to a course tree) you must **re-declare the base
> layout's `paths` verbatim plus your new rule** — a bare one-rule `paths:` override
> silently discards all built-in routing.

> **Custom frontmatter `type:` (TASK 025).** A note whose `type:` is not in the
> layout's `type_mapping` raises `UnmappedTypeError` and is skipped at reindex
> (`skip:unmappable-type` at `wiki-sync`). If your vault carries a subtype the
> built-in lacks, add it under `type_mapping:` in `.wiki/layout.yaml` (it deep-merges
> over the base), e.g. `tutorial-summary: {db_type: summary, tag: tutorial}`. The
> obsidian-personal built-in pre-maps the common summary family
> (`summary`/`lesson-`/`meeting-`/`webinar-`/`tutorial-`/`article-`/`book-`/`video-`/
> `podcast-`/`course-summary` + `moc`); anything else is yours to map.

> **Typed knowledge classes (TASK 031) + agent-memory classes (TASK 034).** Seven
> knowledge classes — `decision`, `requirement`, `risk`, `incident`, `hypothesis`,
> `fact`, `event` — plus the six TASK-034 agent-memory classes — `agent`, `tool`,
> `workflow`, `capability`, `execution`, `pattern` — ship as zero-DDL `type_mapping`
> tag-routes (onto the existing `pages.type` enum).
>
> - They are first-class in the **`cybos`** layout (folder-driven) and the knowledge
>   classes are available opt-in in **`dev-project`** (via explicit frontmatter `type:`).
>   To adopt them in any other vault (e.g. `obsidian-personal`), add the block to
>   `.wiki/layout.yaml` — it UNIONs in (proven on a real PARA vault).
> - Per-class retrieval is the list-membership filter (`wiki-search --tag decision`,
>   TASK 033). The note **templates** live at `templates/page-types/*.md`; full
>   reference at [`docs/layouts/cybos.md`](../layouts/cybos.md).
> - Typed page-to-page *edges* — the event graph proper (`wiki-graph`) — **shipped** in
>   TASK 032/034 (ADR-004, schema v7): author
>   `implements`/`supersedes`/`caused_by`/`invalidated_by`/`uses`/`owns`/… in frontmatter,
>   one direction, inverse auto-derived. Point-in-time "what was active on date X" is then
>   a no-LLM `wiki-search --as-of` query (TASK 034).
> - Since **R-19 / TASK 054** an optional `ontology:` block in the layout promotes these
>   classes/edges/statuses from convention to a **declared, validated contract** —
>   `closed_types` + per-edge `from`/`to` (domain→range) + per-class `status` enums — so a
>   mis-typed edge (a `fact` that `implements` a `risk`) or a `status` outside its enum is
>   caught by `wiki-lint --strict` (`ontology-violation`) / `wiki-health ontology`.
>   Zero-DDL, cybos ships one, and it is **NOT a write gate** (a violating page still
>   indexes — markdown stays canonical).

Three design facts worth internalising:

- **Two separate config systems.** Per-vault *identity* (`config_loader.py` /
  `wiki-config.schema.yaml` — who this vault is, its `vault_id`) is deliberately
  distinct from per-layout-class *grammar* (the engine above — how this *kind* of
  vault is shaped). Don't conflate them.
- **Layouts are self-describing — a new built-in is a pure drop-in YAML (TASK 031).**
  The `--layout` choice set, the legacy alias map, and the two-tier-scaffold family are
  not hardcoded anywhere: each `layouts/*.yaml` declares its own optional `aliases:` and
  `init_scaffold:` (`two-tier` | `none`) keys, and the registry
  (`layout_config.layout_choices` / `resolve_alias` / `is_two_tier_scaffold`) derives
  everything by globbing that directory. Dropping a new `layouts/<name>.yaml` makes
  `--layout <name>` valid with **zero Python edits**.
- **Operator regexes are guarded against ReDoS** (regular-expression denial of
  service — a pathological pattern that can hang the matcher). Custom `ref_extraction[].regex`
  and `paths[].project_pattern` are checked at *load time* (a stdlib-`re` budget
  gate; a misspelled grammar key is a hard load error, exit 6, not a silent
  flood) and at *runtime* (a per-file deadline via the PyPI `regex` engine with
  `timeout=`, env-overridable via `WIKI_REDOS_BUDGET_S`, default 2.0s — on
  timeout the file is skipped with a WARN, never hangs). Built-in layouts use
  stdlib `re` and pay zero overhead (TASK 012 + 017).

> **✅ Key takeaways.** A vault's shape is YAML config, not code: a new layout is a
> drop-in file, a new note type is one `type_mapping` line, and no schema change is
> ever needed. Respect the merge semantics when overriding (`paths` /
> `ref_extraction` replace wholesale) and remember that any `type:` the layout
> cannot map is skipped loudly, not indexed wrongly.

### Reference: page types & relation types (the knowledge model)

The wiki's value comes from *typing* what a note IS and how notes RELATE. A note's **type**
routes it to a `pages.type` bucket + a filterable `tag` (so `wiki-search --tag <type>` lists
every note of that kind); its **relations** are typed page-to-page edges in the event graph
that `wiki-graph` traverses and `wiki-search --as-of` reads. You author the type + the edges
in frontmatter — everything below is the menu and what each entry is *for*.

#### Page types — what each one is for

**Knowledge classes (TASK 031 — the "what happened / what we know" layer):**

| `type:` | Purpose — when to use it | `pages.type` bucket |
|---|---|---|
| `decision` | A choice that was made, with its rationale ("we chose X because Y"). | research |
| `requirement` | Something the system MUST do — a spec / acceptance criterion. | brief |
| `risk` | Something that *might* go wrong (a pre-mortem / open threat). | research |
| `incident` | Something that *did* go wrong — an outage / postmortem. | research |
| `hypothesis` | An unverified assumption you intend to test. | research |
| `fact` | An atomic, verifiable statement of truth. | concept |
| `event` | A timestamped occurrence — a meeting, release, milestone. | summary |

**Engineering spine (shared with the `dev-project` layout):**

| `type:` | Purpose | `pages.type` |
|---|---|---|
| `task` | A unit of work and its spec. | brief |
| `adr` | An Architecture Decision Record. | research |
| `plan` | An implementation plan. | brief |

**Agent-memory classes (TASK 034 — the "who acts / what runs" layer; model the agentic system itself):**

| `type:` | Purpose | `pages.type` |
|---|---|---|
| `agent` | An autonomous actor — an LLM agent or a human role. | concept |
| `tool` | A callable capability surface — a CLI / API an agent invokes. | concept |
| `workflow` | A procedure / state machine (`draft`→`active`→`deprecated`→`superseded`). | brief |
| `capability` | An atomic skill an agent can perform (e.g. OCR, summarisation). | concept |
| `execution` | A timestamped record of a single run (`status: success/failed/partial`) — operational memory. | summary |
| `pattern` | A consolidated *second-order* finding ("most incidents trace to missing requirements"). | research |

**Base content types (always available):** `note` (a generic note), `summary` (a timestamped
narrative record — e.g. a meeting/lesson summary), `concept` (an atomic definitional unit),
plus layout specifics such as `daily-note`, `clipping`, `moc` (map-of-content). Two
system-authored types you never hand-write: `query` (a compounding cited RAG answer filed by
`wiki-query`) and `verification` (a `wiki-verify-multi` verdict page).

> Types are routed by the layout's `type_mapping`, so the *same* raw `type:` lands in the
> right `pages.type` CHECK-enum bucket with **zero schema change**. `--types <bucket>` is the
> coarse filter; `--tag <class>` (the precise per-class list-membership match) is what you
> usually want. The note **templates** for every class live at `templates/page-types/*.md`
> in the repo; `wiki-init` **copies all 13 into `<vault>/.wiki/page-types/`** for existing-tree
> layouts (`cybos`/`dev-project`/`obsidian-personal`) so an agent or human working IN the vault
> has them locally (under `.wiki/`, so they are never indexed).

#### Relation types — what each edge is for

Edges are **typed page-to-page links** authored in frontmatter on the SOURCE page (value =
`[[wikilink]]` / slug, scalar or list). You author **one** direction; the **inverse is
auto-derived** on the target at reindex, so the graph is navigable both ways without
double-bookkeeping. Traverse with `wiki-graph backlinks/neighbors/chain --kind <edge>`.

| Authored key | Meaning (source → target) | Auto-inverse | Example |
|---|---|---|---|
| `implements` | source fulfils / satisfies the target | `implemented-by` | a `decision` *implements* a `requirement` |
| `supersedes` | source replaces the target | `superseded-by` | `decision v2` *supersedes* `v1` |
| `superseded_by` | source is replaced by the target (the other end) | `supersedes` | `v1` is *superseded_by* `v2` |
| `causes` | source brings about the target | `caused-by` | a `decision` *causes* an `incident` |
| `caused_by` | source is brought about by the target | `causes` | an `incident` is *caused_by* a `decision` |
| `invalidated_by` | the target nullifies / voids the source (TASK 034) | `invalidates` | a `decision` *invalidated_by* an `incident` |
| `activated_by` | the target switches the source on / into effect (TASK 034) | `activates` | a `decision` *activated_by* a rollout `event` |
| `uses` | source (an `agent`/`workflow`) calls the target tool/capability (TASK 034) | `used-by` | an `agent` *uses* a `tool` |
| `owns` | source (an `agent`) owns / operates the target workflow (TASK 034) | `owned-by` | an `agent` *owns* a `workflow` |
| `relates_to` | a symmetric, undirected association | `related` (symmetric) | a `fact` *relates_to* a `decision` |

> **Two edges drive the temporal query.** `wiki-search --as-of <date>` treats a page as
> having stopped being active once the earliest **`superseded-by`** *or* **`invalidated-by`**
> successor's `date` has passed — so those two edges (plus the page's own `date`, or an
> optional `valid_to` override) answer "what was active on date X" with no LLM. `activated_by`
> does **not** retire a page (it only records what switched it on); a page's *start* is gated
> by its creation `date` / `valid_from`.
>
> **System ref-types you don't author** (derived automatically, listed for completeness):
> `mentioned` (a plain `[[wikilink]]` in the body), `cited` (a `query` page → a source it
> cited), `verifies` (a `verification` page → the query it audited), `defined-here`. Only the
> typed edges in the table above are authored in frontmatter.

#### Examples — authoring pages (and what they unlock)

A page is just a markdown file: the `type:` + the edge keys go in the frontmatter, the
content goes in the body. In a **`cybos`** vault each type lives in its own folder
(`decisions/`, `requirements/`, …) so you can even omit `type:`; in **`obsidian-personal`** /
**`dev-project`** add the `type_mapping` block (above) and the explicit `type:` works
anywhere. Edge values are `[[wikilinks]]` (or bare slugs), scalar or a list — **author one
direction, the inverse is auto-derived.**

A small connected scenario (mirrors the shipped `08 - CybOS Demo`):

```markdown
# requirements/throughput.md
---
type: requirement
title: Message throughput ≥ 10k/s
date: 2026-01-10
---
The broker must sustain 10 000 messages/second at peak.
```
```markdown
# decisions/use-rabbitmq.md
---
type: decision
title: Use RabbitMQ for async messaging
status: superseded            # proposed | accepted | superseded | rejected
date: 2026-02-01              # ← drives --as-of (when this decision took effect)
implements: [[throughput]]    # → satisfies the requirement   (inverse: implemented-by)
causes: [[queue-overflow]]    # → led to an incident          (inverse: caused-by)
superseded_by: [[switch-to-kafka]]  # → replaced later        (inverse: supersedes)
---
Chosen for operational simplicity.
```
```markdown
# decisions/switch-to-kafka.md
---
type: decision
title: Switch the broker to Kafka
status: accepted
date: 2026-05-01
implements: [[throughput]]
supersedes: [[use-rabbitmq]]  # the supersession lineage
---
A partitioned log scales past RabbitMQ's single-broker ceiling.
```
```markdown
# incidents/queue-overflow.md
---
type: incident
title: Queue overflow outage
status: resolved
date: 2026-03-15
caused_by: [[use-rabbitmq]]
---
Unbounded queue growth under burst load.
```

The supporting classes are just as short — `risk` (`relates_to: [[use-rabbitmq]]`),
`hypothesis` (`relates_to: [[queue-overflow]]`), `fact` (a standalone truth),
`event` (`type: event`, `date: 2026-05-01`, `relates_to: [[switch-to-kafka]]`).

And the agent-memory side — model the system itself:

```markdown
# agents/claude-code.md
---
type: agent
title: Claude Code
status: active
uses: [[wiki-query]]          # → a tool it calls          (inverse: used-by)
owns: [[ingest-pipeline]]     # → a workflow it operates   (inverse: owned-by)
implements: [[ocr]]           # → a capability it provides (inverse: implemented-by)
---
The orchestrator agent.
```

with `tool` (`# tools/wiki-query.md`), `workflow` (`# workflows/ingest-pipeline.md`,
`status: active`, optionally `supersedes:` a prior version), `capability`
(`# capabilities/ocr.md`), `execution` (`# executions/run-2026-06-16.md`, `type: execution`,
`status: failed`, `date: 2026-06-16`, `relates_to: [[ingest-pipeline]]`), and `pattern`
(`# patterns/missing-reqs.md`, `relates_to: [[queue-overflow]]`).

**What those pages now unlock — no LLM needed:**

```bash
wiki-search --tag decision --vaults V                # every decision (tags[] member match)
wiki-search --tag decision --as-of 2026-04-01 --vaults V   # → use-rabbitmq (active then; kafka is 05-01)
wiki-search --tag decision --as-of 2026-06-01 --vaults V   # → switch-to-kafka (rabbitmq superseded 05-01)
wiki-graph chain switch-to-kafka --kind supersedes --vault V   # lineage → use-rabbitmq
wiki-graph backlinks throughput --kind implements --vault V    # what implements the requirement → both decisions
wiki-graph backlinks ocr        --kind implements --vault V    # which agents can do OCR → claude-code
wiki-graph neighbors use-rabbitmq --direction out --vault V    # all its outgoing edges
wiki-search --tag execution --status failed --vaults V         # failed runs (operational memory)
wiki-query prepare "why did we leave RabbitMQ?" --vault-root V --follow-edges  # cited RAG, graph-expanded
```

> **✅ Key takeaways.** Typing is what turns notes into a queryable model: a `type:`
> routes the page into a filterable class, and a handful of frontmatter edge keys
> (`implements`, `supersedes`, `causes`, …) build a bidirectional graph — you
> author one direction, the inverse is derived. Two edges (`superseded-by`,
> `invalidated-by`) plus the page's own `date` are all the machinery behind the
> point-in-time `--as-of` query; none of it needs an LLM.

### Mixed vault: search-only areas + enrich-able course zones

Most real personal vaults are *mixed*: the bulk is finished notes you only want to
**search**, but a few subfolders are **collection zones** — you drop transcripts /
raw material there and want the system to `enrich` them into a compounding wiki
(e.g. a `Webinars/` or a per-course folder under `03 - Learning/`).

**Why this needs two vaults, not one layout.** In a karpathy vault `wiki-import`
produces the karpathy page kinds (`_sources/_concepts/_entities/`) — those folder
names come from the resolved layout, not the personal one — and a personal layout
(`obsidian-personal`) does not index them. So one layout can't serve both halves.
The clean model is **two registered vaults sharing the one global DB** (exactly what
multi-vault partitioning is for); search is unified via `--vaults a,b`.

```mermaid
flowchart TD
    OBS["your Obsidian vault (root)"] --> P["Vault P: personal<br/>layout = obsidian-personal<br/>SEARCH-ONLY"]
    OBS -->|"subtree: 03 - Learning/Courses/**"| L["Vault L: courses<br/>layout = karpathy<br/>ENRICH-able"]
    P -.->|"ignore: 03 - Learning/Courses/**"| X[" "]
    RAW["transcript / raw material"] -->|"wiki-import --source"| L
    SUMM["ready summary (your Summaries/)"] -->|"wiki-index-upsert (no LLM)"| L
    Q["wiki-search / wiki-query --vaults personal,courses"] --> DB[("one global.db")]
    P --> DB
    L --> DB
    style X fill:none,stroke:none
    classDef so fill:#eef7ee,stroke:#5a5;
    classDef en fill:#fdeede,stroke:#e0a050;
    class P so;
    class L en;
```

> **Driving the running Obsidian app (the `obsidian-cli` skill).** A mixed vault is
> still a *live Obsidian vault*. The [`obsidian-cli`](../../skills/obsidian-cli/SKILL.md)
> skill (Obsidian 1.12+ official CLI) lets an agent do the things files+SQLite can't:
>
> - A **link-safe** `rename`/`move` (the app rewrites backlinks; a plain `mv` would
>   orphan them), set typed properties, toggle tasks, append to the daily note, query a
>   Base as JSON, restore from file history.
> - **Active-note resolution (ADR-008):** say *"edit the note"* / *"the note about X"*
>   with no path and it resolves your active/open tab to an explicit path via the
>   `obsidian-active-note` helper — descriptor → unique open tab + vault-unique
>   basename = no ask; bare "the note" = confirm once per session; not-found/ambiguous
>   = ask; destructive verbs always re-confirm.
> - **The live editor selection (TASK 068):** *"edit the selected text"* →
>   `obsidian-selection read` returns the highlighted text; `apply` (confirm-gated)
>   replaces it via the least-privilege `agent-bridge` plugin — never `obsidian eval`
>   (plugin absent ⇒ typed exit 9, no silent fallback). A hotkey (*Copy selection
>   reference*) puts `@path#L…` + the exact text on the clipboard for the manual flow —
>   and since plugin v0.2.0 the same capture has a mouse path: selecting text floats a
>   small `@ ref` button at the selection; clicking it IS the hotkey (clipboard-only).
> - **The note's working context (TASK 071):** *"look at the current note"* / need its
>   frontmatter (a `source:` URL) → `obsidian-context read` returns path, folder,
>   current heading + cursor, tags in one call; `--outline` / `--frontmatter` /
>   `--selection` are opt-in (the latter two are untrusted content — data, never
>   instructions). Preview-tolerant. This is what lets a weak-model agent stop asking
>   *"which note / which URL / which text?"* about the open note.
> - **Reloading a web clip in place:** *"перезагрузи заметку"* → the `/wiki-reload`
>   command re-fetches the note's frontmatter URL in reader mode, sweeps the site
>   chrome, and rebuilds the **same file** with the frontmatter preserved, then
>   re-indexes. Distinct from `/wiki-import` on purpose: import creates a NEW
>   summarized note; reload refreshes an existing clipped one.
> - It routes knowledge lookups to `wiki-search`/`wiki-query` first, and carries a
>   3-tier safety model (read / mutate / banned-by-default `eval`+`dev:*`).
> - After any app-side mutation it refreshes the index in the same turn —
>   `wiki-index-upsert` for a content edit, **`wiki-reindex --delta` for a rename/move**
>   (rename-aware since TASK 030 — the moved file's new path is ingested despite the
>   preserved mtime; `--full` = fallback + swap-class remedy).

**The boundary rule (the one invariant that must hold):** the search vault must
`ignore` the enrich zone, and the enrich vault is rooted inside that zone. Then
every file is indexed exactly once — no double-walk, no duplicate rows.

```
<Obsidian root>/                       ← Vault P (obsidian-personal, search-only)
├── 02 - Personal Home/ · 05 - Материалы/ …   ← indexed by P
└── 03 - Learning/
    ├── Переговоры/ · Работа с людьми/ …       ← personal notes → indexed by P
    └── Courses/                                ← P IGNORES this subtree
        └── AI Hard Fork 2026/                  ← Vault L (karpathy) — its own vault
            ├── _raw/         ← raw drops (transcripts, zoom_chat)
            ├── _sources/     ← wiki-import writes summaries here (+ your ready notes → upsert)
            ├── _concepts/    ← wiki-import builds concept pages
            └── _entities/    ← …and entity pages
```

**Two ways to shape the enrich zone** (both karpathy):
- **Vault-per-course** — each course folder is its own `karpathy` vault_root with
  `_sources/_concepts/_entities/`. Simplest mental model; matches a self-contained
  course folder. New course = new folder + one `WIKI_SCHEMA.md (layout: karpathy)`
  + `wiki-init --register-existing`.
- **One courses vault + course tier** — many courses in one vault_id, each living
  under `Lessons/<Course>/_sources/…`; `wiki-import` routes with
  `--course="AI Hard Fork 2026"`. Less per-course setup when you keep
  adding courses.

**Recipe (test on a copy first):**

```bash
cp -R "/path/to/RealVault" samples/mixed-test            # never iterate on the live vault

# --- Vault P: personal, search-only ---
#  <root>/WIKI_SCHEMA.md:   layout: obsidian-personal
#  <root>/.wiki/layout.yaml: copy obsidian-personal, add "03 - Learning/Courses/**" to ignore
wiki-init --register-existing --vault personal
wiki-reindex --full --vault personal
wiki-search "переговоры с поставщиком" --vaults personal

# --- Vault L: a course (karpathy), import-able ---
#  ".../Courses/AI Hard Fork 2026/WIKI_SCHEMA.md":  layout: karpathy
wiki-init --register-existing --vault ai-hard-fork-2026
wiki-import --vault ai-hard-fork-2026 \
    --vault-root "samples/mixed-test/03 - Learning/Courses/AI Hard Fork 2026" \
    --source     ".../zoom_chat_20260224.txt"            # raw → summary + concepts
wiki-index-upsert --vault ai-hard-fork-2026 \
    --source ".../Courses/AI Hard Fork 2026/_sources/<ready-summary>.md"   # ready note, no LLM

# --- Unified search / RAG across everything ---
wiki-search "scaling laws" --vaults personal,ai-hard-fork-2026
```

**Caveats:**
- **Nested vault roots** (L inside P) are allowed at the DB level (`root_path` is
  UNIQUE); the overlap is removed by P's `ignore`. Verify on a copy before the live
  vault.
- **`wiki-import` creates `_sources/_concepts/_entities/`** in the course folder — expected
  (that's the system-managed zone). Already-distilled notes (your `Summaries/`) go
  through `wiki-index-upsert` (see [pre-made summary](#registering-a-pre-made-summary-not-raw)); only new raw goes through `wiki-import` (hand it a local `--source`).
- **HTML / office sources**: `wiki-import` handles these natively — its deterministic
  fetch+convert step turns `.html` / `.pdf` / office docs into text before REASON.
- The **personal vault stays untouched** (indexed only); `wiki-import` writes solely into
  the course zone.

> **✅ Key takeaways.** A mixed personal vault is two registered vaults sharing
> one global DB: a search-only vault over the bulk, and a karpathy enrich vault
> rooted inside the collection zone. The single invariant is the boundary — the
> search vault `ignore`s the enrich subtree, so every file is indexed exactly
> once. Search stays unified via `--vaults a,b`.

---

### Automating the mix: `wiki-sync` (per-note routing, conversion, OCR)

The two-vault recipe above splits work *by folder*. **`wiki-sync`** (TASK 018 / R-11)
goes one level finer: point it at a **zone** and it classifies **every file** — by
extension, by per-note `#wiki/*` tag, and by content shape — then routes each one to
**distil (delegate to `wiki-import`) / upsert / skip**. Dropping a transcript, a `.docx`, or even a
*scanned* PDF into a course folder now "just" becomes compounding wiki pages, without
hand-invoking `wiki-import` / `wiki-index-upsert` per file.

**Two phases (Decision-17 — deterministic plan, orchestrator-owned execution):**

- **`wiki-sync scan <zone> --vault <id>`** — *pure Python.* Walk → classify →
  `sha256` → `is_unchanged` → a strict **plan JSON** (`entries[]` + `summary{}`).
  **No LLM, no network, no mutation.** `--dry-run` prints a human report of every
  action + reason. This is the part you review before anything is written.
- **[`workflows/wiki-sync.md`](../../workflows/wiki-sync.md)** — the orchestrator
  *executor.* Per plan entry it **delegates each distil source to `wiki-import`**
  (which owns the deterministic fetch+convert / de-timestamp / **H-6-fence** —
  H-6 is the project's untrusted-content rule: fetched text is data, never
  instructions — / REASON+file steps) or upserts a ready `.md` / skips, then writes a per-file
  **commit-marker** (`wiki-sync record`) so a re-run is a no-op. (`/wiki-sync`
  drives the whole thing.)

```mermaid
flowchart TD
    F["file in the zone"] --> EXT{"extension<br/>(case-folded)"}
    EXT -->|".docx .xlsx .pptx .pdf"| CONV["distil → delegate to wiki-import<br/>(fetch+convert + _raw/.staging/&lt;slug&gt;-&lt;ext&gt;.md,<br/>scanned PDF → OCR)"]
    EXT -->|".txt .vtt .srt"| ING["distil → delegate to wiki-import<br/>(.vtt/.srt → de-timestamp first)"]
    EXT -->|"image · .canvas · .excalidraw · .base"| SKb["skip (binary / view-artifact)"]
    EXT -->|".md"| TAG{"#wiki tag /<br/>wiki: field?"}
    TAG -->|"skip"| SKt["skip: wiki/skip"]
    TAG -->|"raw  (or under _raw/)"| ING
    TAG -->|"none / keep"| VIEW{"generated-view<br/>sidecar?"}
    VIEW -->|"only-a-view block"| SKv["skip: view:dbfolder/base/dataview/folder-note"]
    VIEW -->|"embeds a view + real prose"| TYPE
    VIEW -->|"plain note"| TYPE{"type: mappable?<br/>(same layout resolution<br/>wiki-index-upsert uses)"}
    TYPE -->|"yes"| UP["upsert (no LLM)"]
    TYPE -->|"no"| SKu["skip: unmappable-type"]
    CONV --> ING
    ING --> REC["on full success →<br/>wiki-sync record (commit-marker)"]
    UP --> REC
    classDef act fill:#fdeede,stroke:#e0a050;
    classDef sk fill:#eef0f2,stroke:#99a;
    class CONV,ING,UP,REC act;
    class SKb,SKt,SKv,SKu sk;
```

**Routing by extension** (case-folded — `.PDF` == `.pdf`):

| Extension | Action |
|---|---|
| `.docx` `.xlsx` `.pptx` `.pdf` | **distil** → delegate to `wiki-import` (fetch+convert stages `_raw/.staging/<slug>-<ext>.md`, a *non-walked* dir) |
| `.txt` `.vtt` `.srt` | **distil** → delegate to `wiki-import` (`.vtt`/`.srt` de-timestamped first) |
| `.md` | content rules (tags → view → type, below) |
| images · `.canvas` · `.excalidraw.md` · `.base` · unknown | **skip** (binary / view-artifact / unknown-ext) |

**Routing by per-note tag** (`.md` only) — precedence **`skip` > `raw` > `keep` > default**.
Accepts both an inline `#<ns>/x` tag (outside code fences), a frontmatter `tags:` entry,
and a `<ns>:` field (`<ns>` = `tag_namespace`, default `wiki`):

| Tag / signal | Effect |
|---|---|
| `#wiki/skip` (or `wiki: skip`) | never index this note |
| `#wiki/raw` (or the file is under `_raw/`) | treat as **raw** → **distil** (delegate to `wiki-import`: summarise → note + concepts) |
| `#wiki/keep` | **rescue** a `.md` from an `exclude:` zone (only `keep` rescues — not `raw`) |
| *(no tag)* | a **mappable `type:`** → `upsert`; otherwise `skip: unmappable-type` |

**Generated-view sidecars are skipped** — they're navigation, not knowledge: DB Folder
(`database-plugin:` frontmatter and/or a ` ```yaml:dbfolder ` block), Bases (` ```base `),
Dataview (` ```dataview `/` ```dataviewjs `), folder-notes (stem == dir). The
**only-a-view guard** skips them *only* when the note is essentially one view block —
a real note that *embeds* a view alongside prose is content → `upsert` (no over-flagging).

**Scanned PDFs are OCR'd** (OCR — optical character recognition, extracting a text
layer from page images; wired 2026-06-03): a `.pdf` with no text layer
(`pdf_extract.py` exit `10 DocumentScanned`) is run through the `pdf` skill's
`pdf_ocr.py` (`ocrmypdf`, default languages **`eng+rus`**) → searchable text → ingest.
If the OCR engine isn't installed (`bash <pdf-skill>/scripts/install.sh --with-ocr`
+ system tesseract/ghostscript), the file is flagged **`needs-ocr`** and skipped —
never silently dropped.

**Config** — `<vault>/.wiki/sync.yaml` (optional): `zones`, `exclude`, `tag_namespace`
(default `wiki`), and `extensions` overrides. Strict schema (a misspelled key is a load
error); an untrusted file is size-capped (256 KiB) + anchor-banned + symlink-refused.
Inspect, validate, repair, and edit this file tree with **`wiki-config`** — full
copy-paste commands in [Configuring folders with `wiki-config`](#configuring-folders-with-wiki-config-provenance-repair-templates-web-editor).

**Recipe (test on a copy first):**

```bash
# 1. PLAN — deterministic, writes nothing; review every action + reason
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run

# 2. EXECUTE the plan — the orchestrator recipe (distil via wiki-import / upsert / skip per file).
#    Invoke /wiki-sync, or follow workflows/wiki-sync.md step by step.

# 3. RE-RUN — every recorded file now reports is_unchanged (a no-op).
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run
```

**Re-summarization policy — don't re-summarise what's already summarised** (TASK 019,
opt-in). Add a `resummarize:` block to `.wiki/sync.yaml` and `wiki-sync` will route a raw
source to **`skip`** instead of **distil** when a summary for it already exists — so re-running
a scan over a course you've already summarised doesn't burn tokens redoing it.

- "A summary exists" is the union of three detectors (cheapest-first):
  **`source_state`** (this exact raw was synced before) ∪ **provenance** (some
  summary's frontmatter `source:`/`sources:` cites this raw) ∪ **filesystem mirror**
  (a `Summary/` sibling shares the raw's key — `stem-relpath` 1:1, or
  `group_key`/`key` N:1 so many transcripts fold onto one lesson summary).
- `--force` bypasses the gate (re-summarise anyway).
- Rules are **per-folder overridable** (a deeper `<folder>/.wiki/sync.yaml`
  deep-merges over the vault root — e.g. a `Lessons/` zone keyed by date instead of
  lesson number).
- `wiki-config show <folder>` prints which effective value comes from where (and
  flags a root-only key a subfolder file can't override); `wiki-config report --open`
  renders the whole cascade as one HTML page.

**Freshness — `mode: if-changed` (TASK 051 / R-18).** The default gate skips whenever a summary
*exists* — so a source whose raw content **changed** since it was summarised is skipped too (only
`--force` or `mode: always` refresh it, and `always` re-LLMs the whole zone every scan).
`resummarize.mode: if-changed` closes that gap:

- It skips (`skip:summary-unchanged`) **only while the recorded content hash still
  matches the file**, and re-summarises a *changed* source **in place** — so a
  scheduled re-poll of a zone re-LLMs only the deltas, not the untouched majority.
- This is the *freshness mode* for a **connector zone**: any exporter that drops
  **one file per business object** (`PROJ-123.md`) with a **stable filename = stable
  external key** into a zone, plus a `.wiki/sync.yaml` with `mode: if-changed` (copy
  `templates/connector-zone.sync.yaml`), is a *connector* — the wiki stays a
  pull-refreshed cache of that source with **no adapter code** (an MCP tool may wrap
  a fetcher, but MCP is not the contract).
- The per-source half is `wiki-import prepare`'s **`is_unchanged` short-circuit**: an
  unchanged re-poll costs one fetch+hash, **not** an LLM (REASON) pass — the
  orchestrator STOPs on `{action:"unchanged", is_unchanged:true}`; `--force` bypasses.

#### Connectors — mirror a whole external system into the vault (TASK 051 / R-18)

`if-changed` is what makes a **connector** practical. A connector is **not** something this repo
ships — it is **any small program you own** (a shell/Python script, or an installed tool) that talks
to an external system's API and writes **one markdown file per object** into a `wiki-sync` zone,
naming each file by the object's **stable external key**. The wiki then keeps that zone fresh
cheaply; you never hand-import the objects one by one. `templates/connector-zone.sync.yaml` is only
the tiny per-zone **config** (`mode: if-changed` + a distil profile) — it holds no data; the
connector produces the content files.

**Worked example — mirror a Jira project.** You write `jira-export.sh` (~20 lines): for each issue
in `PROJ`, `curl` the Jira API and write `04 - Work/Jira/PROJ-123.md` (issue title/status as
frontmatter, body as markdown). You drop `04 - Work/Jira/.wiki/sync.yaml` — a copy of
`templates/connector-zone.sync.yaml`. Then you cron it nightly:

```bash
jira-export.sh                                    # YOUR connector: (over)writes one .md per issue
wiki-sync scan "04 - Work/Jira" --vault personal   # the wiki distils ONLY the changed issues
#   → the orchestrator runs the plan (workflows/wiki-sync.md): each changed/new issue → wiki-import distil;
#     the untouched majority → skip:summary-unchanged (zero tokens)
```

Every night `jira-export.sh` refreshes the issue files; `wiki-sync` with `if-changed` re-summarises
only the handful that changed and skips the rest. Your vault becomes an always-fresh,
FTS-searchable, cross-linked mirror of the project that `wiki-search`/`wiki-query` answer over.

**Why the filename must be a stable key.** `PROJ-123.md` is stable, so when the issue changes the
connector **overwrites the same file** → the wiki refreshes the note **in place** (same slug, its
`[[wikilinks]]` stay valid). A random filename each run would spawn duplicate notes and dangling
links — hence the contract: **one file per object, filename = the object's stable external key**. A
refreshed source is "the current snapshot", not a new event, so `supersedes`/`--as-of` history stays
reserved for knowledge-class pages.

**What you bring vs what R-18 gives.** *You* bring the connector — the API-specific dump script;
R-18 ships **no** adapters, by design. *R-18* gives (1) the contract above, and (2) cheap refresh in
two halves: **`wiki-sync … mode: if-changed`** for a whole zone (a batch of connector files), and
**`wiki-import prepare`'s `is_unchanged`** for a single source. The point of the scope is "any
exporter + a zone config" instead of "build an IMAP/Jira/Telegram adapter for every system". *(An
MCP tool may wrap a connector, but MCP is not the contract — the contract is "files in a zone".)*
You don't need any of this until you have a recurring source you actually re-poll; keep using
`wiki-import <url>` for one-off captures.

> **Provenance match mode (TASK 025) — `vault-rel-path` vs `basename`.** The provenance
> detector's `provenance_ref.match` chooses how a summary's cited `file:` is matched to a raw.
>
> - **`vault-rel-path`** (the default) is exact full-path equality — strict, but it
>   MISSES a summary that cites the raw by *basename* only.
> - **`basename`** basenames BOTH the cited value AND the raw target, so it matches
>   summaries citing by basename OR by full path — the robust choice when source
>   basenames are globally unique (e.g. YouTube-id transcripts `ID.ru.txt`) or an
>   existing corpus already cites by basename. Its only failure mode is two distinct
>   raws sharing a basename across folders.
> - Pick `basename` for id-named transcript corpora; `vault-rel-path` when you control
>   the writeback and want strict path equality. (The default is intentionally
>   `vault-rel-path` — flipping it could merge distinct same-basename raws.)

> **New raw under an already-summarised key → merge or split?** (TASK 021) If you drop a
> *new* transcript whose key already has a summary that doesn't cite it, `wiki-sync` keeps
> skipping it (your "group summarised → done" intent) but logs a **merge/split WARN**. Resolve
> it explicitly:
>
> - **MERGE** → `wiki-sync scan <zone> --force` regenerates the summary from all raws
>   sharing the key and writes them into `sources:`.
> - **SPLIT** → give the new raw a distinct key (finer `group_key` / own scope) or
>   author a second summary citing it.
> - **SUPERSEDE** → archive the old raw, then `--force`.
>
> `sources:` is the authoritative record; the key is just the default grouping.
> See `workflows/wiki-sync.md` Step 6.

**Idempotency & safety:** the executor writes a `source_state` commit-marker per file
**only on full success** — a partial failure records nothing, so the file is re-planned
next run (no half-done state survives). The plan is **deterministic** (entries sorted by
path, no timestamp → two scans byte-identical). Per-file isolation: one bad file
(`needs-ocr` / unconvertible / oversize) is flagged and skipped, never crashing the batch.
**Zero DDL** — idempotency rides a `source_state` partition on the existing schema.

> **`wiki-sync` vs the two-vault split:** they compose. Use the two-vault `ignore`
> boundary to keep search-only areas out of the enrich machinery; use `wiki-sync`
> *inside* an enrich zone to route its heterogeneous drops per-file. See
> `skills/wiki-sync/SKILL.md` for the full plan-JSON + exit-code contract.

> **✅ Key takeaways.** `wiki-sync` splits ingest into a deterministic *plan*
> (`scan` — review it before anything is written) and an orchestrator-executed
> run, with a per-file commit-marker so re-runs cost nothing. The `resummarize:`
> gate stops the system re-LLM-ing what is already summarised, and `mode:
> if-changed` upgrades that into cheap freshness — the basis of the connector
> pattern, where any script that writes one stably-named file per external object
> turns the vault into a pull-refreshed mirror.

---

### Configuring folders with `wiki-config` (provenance, repair, templates, web editor)

Every folder can carry its own `.wiki/sync.yaml` (see the
[config-files overview](#vault-configuration-files-overview)). Two facts make hand-editing
that tree error-prone, and `wiki-config` (TASK 058) exists to encode them for you:

- Only the **`resummarize:`** and **`summarize:`** blocks *cascade* per folder —
  i.e. a deeper folder's file overrides its ancestors' values (deepest wins;
  partial overrides inherit the parent's other keys; **lists replace, never
  extend**).
- `zones` / `exclude` / `extensions` / `transcript_dedup` / `tag_namespace` are
  **root-only** — placed in a subfolder file they are *silently ignored* (the tool
  flags this as `NON_CASCADING_KEY_IN_SUBFOLDER`).

How a key's effective value is resolved for a given folder:

```mermaid
flowchart TD
    K{"is the key<br/>root-only?"}
    K -->|"yes (zones · exclude · extensions ·<br/>transcript_dedup · tag_namespace)"| R["only the ROOT .wiki/sync.yaml counts;<br/>a subfolder copy is IGNORED<br/>(flagged NON_CASCADING_KEY_IN_SUBFOLDER)"]
    K -->|"no (resummarize · summarize)"| C["walk root → … → this folder:<br/>the DEEPEST file defining the key wins"]
    C --> P["keys the winner does not define<br/>are inherited from the ancestors;<br/>a LIST value REPLACES, never extends"]
    P --> D["nothing defined anywhere →<br/>the built-in default"]
    classDef warn fill:#fdd,stroke:#c66;
    class R warn;
```

**See where every value comes from.** `show` prints the effective config for one folder
with a per-key origin — `default` (built-in) / `root` / inherited-from-`<ancestor>` /
defined-HERE — plus what each override shadows. Without a folder argument it resolves
the folder of the **active Obsidian note** (then the CWD, then the vault root), so you
can just click into a note and ask:

```bash
# effective config + per-key origin (no folder → the active note's folder)
wiki-config show --vault-root ~/Vault
wiki-config show "06 - Business Development/Встречи" --vault-root ~/Vault

# vault-wide override map: who defines what, who overrides whom, what is IGNORED
wiki-config tree --vault-root ~/Vault
```

**Validate and repair.** `validate` lints every config file in the vault — the sync
tree, `.wiki/layout.yaml`, and `WIKI_SCHEMA.md`/`.wiki.yaml` — against a 40-code
taxonomy (typo suggestions, dead mirror regexes, redundant overrides, list-replace
surprises). `doctor` turns the findings into a read-only repair plan; `fix` applies it
by safety tier (SAFE automatically, CONFIRM only with `--yes`):

```bash
wiki-config validate --vault-root ~/Vault --strict
wiki-config doctor   --vault-root ~/Vault --report /tmp/doctor.md
wiki-config fix      --vault-root ~/Vault --yes
```

**Edit safely.** Every mutation is comment-preserving and verified before it lands
(semantic equality + comment survival; an unverifiable edit is downgraded and NOTHING
is written), backed up to `.wiki/backups/` (retention 10), and TOCTOU-guarded.
A root-only key in a subfolder is refused with a hint pointing at the root file:

```bash
wiki-config set   "Lessons" /summarize/profile lesson --vault-root ~/Vault
wiki-config unset "Lessons" /summarize/diagrams      --vault-root ~/Vault

# accidental delete / bad edit? every mutation left a backup:
wiki-config restore "Lessons" --list --vault-root ~/Vault
wiki-config restore "Lessons" --to 20260711T09 --yes --vault-root ~/Vault
```

**Set up a folder from a template.** Builtin profiles live in
`templates/sync-profiles/` (`meeting-zone` · `lessons-mirror` · `connector-zone` ·
`article-zone` · `root-baseline`); a vault can add its own under `.wiki/templates/`:

```bash
wiki-config templates --vault-root ~/Vault
wiki-config init "Lessons" --template lessons-mirror --var 'group_key=^(\d{8})' --vault-root ~/Vault
```

**One-page report & the web editor.** `report --open` renders a single self-contained
HTML file (hierarchical folder nav; per-key badges `default` / `ROOT` / `HERE` /
`↑ ancestor` / `⛔ IGNORED`; copy-paste fix commands). `serve` starts a local
(127.0.0.1, token-authenticated) editor:

```bash
wiki-config report --open --vault-root ~/Vault
wiki-config serve  --open --vault-root ~/Vault
```

The serve UI is a schema-driven form (hints from the schema, enum dropdowns, inherited
values as placeholders, a live `group_key` tester) plus a raw-YAML tab. Its tree shows
**every** vault folder: unconfigured ones are dimmed — click to inspect the effective
config, *Override here* creates the folder's `.wiki/sync.yaml`, *Delete config* returns
it to inherited values. Unsaved edits survive switching folders (red dots in the tree,
one global *Save all N*), templates are one click away in the panel header, and a folder
whose config was accidentally deleted shows a restore banner listing its backups by date.
Everything — form, report, provenance, validation — is generated at runtime from
`config/sync-config.schema.yaml` (+ `x-wiki-*` annotations), so a NEW config field
appears in every surface with zero interface-code changes. The tool needs no DB:
it works even while the index is broken.

> **✅ Key takeaways.** Never guess what a folder's effective config is — ask
> `wiki-config show` and read the per-key provenance. The two traps it exists to
> catch: root-only keys silently ignored in subfolder files, and list values that
> replace rather than extend. Every mutation is comment-preserving, backed up, and
> reversible via `restore`, so editing the tree through the tool is strictly safer
> than editing YAML by hand.

---

## Using the wiki as an external resource for other agents

A second agent — another Claude Code session, a cron job, a CI step, any
orchestrator — can treat the wiki as a **knowledge backend**. The contract is
deliberately simple and machine-friendly.

### The integration model: JSON envelopes + exit codes

Every CLI follows the same shape:

- **Input** via args and/or stdin (large payloads — an answer body, a citations
  array — go via stdin or a temp file inside the vault root).
- **Output** is exactly **one line of JSON on stdout** (`ensure_ascii=False`), an
  *envelope*. Success envelopes carry result fields; failures carry an `"error"`
  key with a stable machine-readable code.
- **Exit code** signals outcome for `$?`-based control flow. The conventions:

| Exit | Meaning |
|---|---|
| `0` | Success. |
| `2` | Pipeline/precondition error (e.g. `wiki-query` `NO_CONTEXT`, `QUESTION_CHANGED`). |
| `4` | Contract violation in supplied content (e.g. `CITATION_NOT_RETRIEVED`, `ANSWER_TOO_LARGE`). |
| `6` | Validation/look-up error — *or* a recorded negative verdict (`wiki-verify-multi` FAIL). |
| `7` | Interactive-confirm-required warning. |

Each `SKILL.md` documents its own codes precisely — treat the table above as the
shared spine, not a guarantee that every code appears in every tool. The golden
rule for an integrating agent: **branch on the exit code first, then read the
envelope's `error` field — never scrape human prose.**

A minimal external-agent loop:

```bash
out=$(wiki-search "vault bottleneck" --vaults my-vault) || { echo "search failed: $out"; exit 1; }
top_slug=$(printf '%s' "$out" | jq -r '.hits[0].slug')   # structured, not regex-on-prose
```

### The `prepare` / `apply` contract (Decision-17)

Three skills do LLM-shaped work but contain **zero `anthropic` import**:
`wiki-query`, `wiki-verify-multi`, `wiki-extract-concepts`. The Python is
deterministic plumbing; the LLM step is owned by the *calling agent*, sandwiched
between two CLI calls. This is what makes the wiki composable by *any* agent — the
agent supplies the reasoning; the CLI supplies retrieval, validation, and durable
filing.

```mermaid
flowchart LR
    Q["question"] --> P["wiki-query prepare<br/>deterministic retrieval"]
    P -->|"envelope: hits[] + question_hash"| A["agent reasoning<br/>wiki-query-synthesis contract:<br/>cited answer + citations JSON"]
    A --> AP["wiki-query apply<br/>strict validators"]
    AP -->|"files"| PG["_queries/&lt;slug&gt;.md<br/>indexed · FTS · cited backlinks"]
    classDef det fill:#e8f0ff,stroke:#5577cc;
    classDef llm fill:#ffe9cc,stroke:#e08a00;
    class P,AP det;
    class A llm;
```

The deterministic CLI owns retrieval + validation + filing; the agent owns only
the reasoning in the middle. The `wiki-query` recipe in practice (the others are
the same shape — see [`workflows/`](../../workflows/)):

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator / agent
    participant CLI as wiki-query CLI — deterministic
    participant LLM as Orchestrator — LLM
    participant Vault as Vault + index

    Op->>CLI: prepare "question" --vault … [scope]
    CLI->>Vault: retrieve (FTS5 BM25 + alias expansion)
    Vault-->>CLI: hits[]
    CLI-->>Op: envelope {query_slug, question_hash, is_unchanged, hits[]}
    Note over Op,LLM: exit 2 NO_CONTEXT → STOP (no outside-vault synthesis)<br/>is_unchanged → STOP (already filed)
    Op->>LLM: synthesise per wiki-query-synthesis (cite ONLY hits)
    LLM-->>Op: answer.md + citations JSON
    Op->>CLI: apply --question-hash [verbatim] --answer-stdin --citations-file … [same scope]
    CLI->>Vault: re-retrieve, recompute hash, validate citations ⊆ hits
    Note over CLI: hash mismatch → exit 2 QUESTION_CHANGED<br/>citation ∉ hits → exit 4 CITATION_NOT_RETRIEVED
    CLI->>Vault: file the _queries page (indexed, cited backlinks)
    CLI-->>Op: envelope {query_slug, cites, page_indexed}
```

Step by step:

1. **`wiki-query prepare "<question>" --vault <vid> --vault-root <path> [scope…]`**
   → envelope with `query_slug`, `question_hash`, `is_unchanged`, `hits[]`.
   - Exit 2 `NO_CONTEXT` → the vault has no grounding. **Stop; do not synthesise
     from outside the vault** (anti-hallucination). Retry with `--min-hits 0` only
     to explicitly request a "no sources found" answer.
   - `is_unchanged: true` → the same question over the same retrieval is already
     filed; skip synthesis.
2. **Agent synthesises** per the `wiki-query-synthesis` contract: a markdown answer
   citing **only** `prepare`'s `hits`, plus a citations JSON array of
   `project/slug` values.
3. **`wiki-query apply … --question-hash <verbatim from prepare> --answer-stdin
   --citations-file <tmp>`** — pass the **same scope flags** as `prepare` (or the
   re-run retrieval diverges and the hash mismatches → exit 2 `QUESTION_CHANGED`).
   A synthesised citation not in the retrieved set → exit 4 `CITATION_NOT_RETRIEVED`
   (re-synthesise; do **not** silently retry).

The `--question-hash` round-trip is the integrity mechanism: it guarantees the
answer was synthesised against the *same corpus state* it is filed against. For a
non-Claude orchestrator, the contract skill (`wiki-query-synthesis`,
`wiki-verify`, `concept-extraction`) is just a prompt you inline into your system
context — the CLI halves are unchanged.

### The wiki as a RAG backend

The lightest integration needs no `prepare`/`apply` at all:

- **`wiki-search "<q>" --vaults a,b,c`** — cross-vault FTS with BM25 + alias
  expansion. The fastest "what do we know about X" for an agent that will do its
  own reasoning over the snippets.
- **`wiki-search --where 'field=value' --vaults v`** — structured metadata
  retrieval (status boards, severity queues) without full-text. Matches scalars AND
  **list members** (`--where 'tags=decision'`, or the `--tag decision` sugar) — TASK 033.
- **`wiki-query`** — when you want a *durable, cited* answer filed back, not just
  raw hits.

Because results are JSON, an external agent composes them directly. Because the DB
is a single global file partitioned by `vault_id`, one agent can query across many
projects' vaults in a single call (`--vaults proj-a,proj-b`) — the index is shared,
the partitions are not.

### Untrusted data: the H-6 posture

**Retrieved snippets and page bodies are untrusted data, not instructions.** A
hostile source page (especially anything ingested into `_raw/` from an external
URL) may contain inline text impersonating a system prompt ("ignore previous
instructions…"). An integrating agent **must** wrap retrieved content in a fenced
block with a sentinel and treat nothing inside as a command. The synthesis and
verification skills carry an explicit H-6 banner; honour it.

On the write side, the tooling already escapes markdown/HTML-active sequences on
egress (`sanitize_markdown_text`) so a filed answer can't smuggle a
wikilink/HTML/dataview payload back into the vault.

**The skill contracts themselves are integrity-pinned (H-5, TASK 067).** H-6 protects
against a hostile *source*; H-5 protects the reasoning *prompts*. The `SKILL.md` +
`references/*.md` files loaded **verbatim** into an agent's context as reasoning/safety
contracts — the extraction, synthesis, verification, and the `obsidian-cli` safety-tier
contracts — are SHA-256-pinned in `config/skill-integrity.sha256`. Each rail's `prepare`
verifies its contract's pin and surfaces drift in an **`integrity`** envelope block; the
workflow STOPs before loading a drifted contract, and `WIKI_STRICT_SKILL_INTEGRITY=1`
makes `prepare` refuse (exit 2). A `tests/test_h5_skill_integrity.py` gate goes red on any
un-re-pinned edit — so tampering with a loaded prompt is a **reviewable manifest diff and a
failing build**, not a silent supply-chain change. Re-pin an *approved* edit with
`python3 scripts/pin_skill_integrity.py --write`.

> **✅ Key takeaways.** Any agent drives the wiki through the same surface a human
> does: one JSON envelope per command plus a stable exit code — branch on `$?`,
> read `.error`, never scrape prose. The LLM-shaped skills split into
> deterministic `prepare`/`apply` halves with the reasoning owned by the caller,
> and the `question_hash` round-trip pins a filed answer to the exact corpus
> state it was synthesised against. Whatever retrieval returns is data, never
> instructions (H-6) — fence it before showing it to a model; and the loaded
> reasoning contracts are hash-pinned (H-5), so a `prepare` reporting
> `integrity.status != "ok"` means STOP.

---

## Policy, provenance & read-audit (ADR-009)

Three optional **retrieval-scope** controls, shipped in TASK 049 (R-16) and TASK 050
(R-17). Each is **default-OFF**: without any of them the search/RAG behaviour is
byte-identical to before, and the schema is unchanged (**zero-DDL** — they ride
`frontmatter_json` + the existing event graph; `user_version` stays 7).

- They scope **what the model is shown**, which is least-privilege for cooperating
  agents and subagents — **not** access control against someone who can read the
  files or the DB. That boundary is deliberate: a local single-owner tool cannot
  defend against its own owner; the markdown and the DB stay fully readable and
  nothing is encrypted.
- The honest value is (a) keeping classified or low-trust pages out of a
  model/subagent context and out of durable filed artifacts, and (b) an attributable
  read/write trail.
- The one always-on addition is a derived `trust` key on every `wiki-query prepare`
  hit (below).

### 1. Policy — classification + `--audience` (R-16)

Three steps: declare the ladder of levels, mark pages, set the audience at query time.

**Step 1** — the ladder in `WIKI_SCHEMA.md` frontmatter (ordered low→high):

```yaml
policy:
  levels: [public, internal, restricted]   # your own level names are fine too (≤16)
  default_level: internal                  # assumed for any page with no `classification:` key
  # default_audience: internal             # OPTIONAL — declaring it ACTIVATES the layer with no flag
```

**Step 2** — mark individual pages (a plain frontmatter string; unmarked pages take `default_level`):

```yaml
---
title: Salary Review 2026
classification: restricted
---
```

**Step 3** — the audience now decides what enters the model's context. Pages *above* the
audience level are dropped **in SQL, before the `LIMIT`** (edge-expansion through
`--follow-edges` is gated too), so the model can neither see nor cite them:

```bash
wiki-search "salary" --vaults personal --audience public      # the restricted page is NOT in the results
wiki-search "salary" --vaults personal --audience restricted  # visible (top of the ladder)
wiki-search "salary" --vaults personal                        # no flag → layer OFF → visible, as before
# the same --audience flag exists on `wiki-query prepare|apply` and `wiki-verify-multi`.
```

Key properties:

- **Fail-closed.** An unknown / out-of-ladder label is excluded even at the *top*
  audience level (it is never a member of the allowed set); a non-string
  `classification:` fails closed the same way.
- **Errors (exit 2).** A bad `--audience` value → `INVALID_AUDIENCE`; a
  present-but-malformed `policy:` block → `INVALID_POLICY` (fail-loud; the offending
  value is never echoed — CWE-209).
- **Lint.** `wiki-lint` reports an out-of-ladder label as `invalid-classification` (a
  `warning`) and a lower-level page that cites a higher-level one as
  `classification-leak` (escalated to `error` under `--strict` — a filed answer
  republishing restricted content is the canonical leak). Note `wiki-lint --strict` is
  **severity-blind**: it exits non-zero on *any* issue (including the normal
  `orphan-link` backlog), so it's a whole-vault clean-slate gate, not a
  classification-specific one.
- **Activation & hashes.** Without `--audience` *and* without `default_audience` the
  layer is OFF (byte-identical). Declaring `default_audience` activates it with no flag
  but re-keys every filed `_queries/*` hash once (the next re-query reports
  `is_unchanged=false` — expected, not an error).
- **`apply` must match `prepare`.** `wiki-query apply` must repeat the *same*
  `--audience` the `prepare` used — the level folds into `question_hash`, so a mismatch
  fails `QUESTION_CHANGED` (exit 2), and a citation to a page the audience hid fails
  `CITATION_NOT_RETRIEVED` (the model cannot launder a restricted source into a filed
  answer).

### 2. Provenance — the derived `trust` tier + `--min-trust` (R-17)

Every `wiki-query prepare` hit carries a **derived** `trust` tier — no new authored field:

| Tier | What it means |
|---|---|
| `external` | The page declares an **`http(s)` provenance key** in frontmatter — `source:` / `url:` / `URL:` **and their case variants** `Source:` / `SOURCE:` / `Url:` (TASK 061; `wiki-import` writes the uppercase `URL:`, web clippers often write `Source:`). These are captures/clippings that may carry inline instructions (H-6 indirect prompt injection). *A page under `_raw/` also counts, but that is a **backstop you will not meet in practice**: every built-in layout excludes `**/_raw/**` from the index, so a `_raw/` capture is never a search hit — the frontmatter key is the operative signal.* |
| `internal` | An ordinary vault page. |
| `verified` | A page with an inbound `verifies` edge (a verification/verdict page vouches for it). |

**Origin taints (MIN-rule).** An external-origin page never rises above `external` even
if something verifies it — checked *first*, so the `verified`/`internal` branch is only
reached when the page is not external.

```bash
# no flag — trust is visible on every prepare hit:
wiki-query prepare "trading strategy" --vault personal --vault-root .
#   hits: [{"slug": "quickfinger-luc-strategy", "trust": "external"},   ← a web clipping (url:)
#          {"slug": "my-td-sequential-note",    "trust": "internal"}]   ← your own note
# with the flag — the floor is applied in SQL, BEFORE the LIMIT:
wiki-query prepare "trading strategy" --vault personal --vault-root . --min-trust internal
#   → external clippings dropped; the answer grounds on YOUR notes (a larger internal set surfaces)
```

`--min-trust {external,internal,verified}` floors retrieval **in SQL, before the
`LIMIT`**:

- `internal` drops untrusted clippings (letting a larger trusted set surface);
  `verified` additionally requires an inbound `verifies` edge *and* excludes
  external-origin pages, so the SQL floor is taint-consistent with the displayed tier.
- If nothing meets the floor you get `NO_CONTEXT` (exit 2).
- `external` imposes no SQL clause but *still* folds into `question_hash` (so
  `prepare`/`apply` must both carry it).
- The tier is a provenance **signal for grounding**, NOT access control (that is
  `--audience`). For a clippings-heavy corpus, `--min-trust internal` is the
  high-value default when you want an answer grounded on your own notes rather than
  saved web pages.

### 3. Read-audit — `WIKI_ACTOR_ID` + opt-in read logging (R-17)

Every knowledge-write leaves a row in the `log_events` ledger. The env var
`WIKI_ACTOR_ID` signs that row with the acting agent's name — the "who did what"
attribution that is the whole point of the audit.

**Example — tag WHICH agent filed an answer.** `WIKI_ACTOR_ID` is set ONCE in the
subagent's environment (no need to repeat it per command):

```bash
WIKI_ACTOR_ID=critic-security wiki-query apply --vault personal --vault-root . \
    --query-slug td-sequential-risks --question "What are the risks of TD Sequential?" \
    --question-hash <hash from prepare> --answer-file answer.md --citations-file cites.json
```

The resulting `log_events` row carries the cited slugs, the action, and the actor:

```json
{"cites": 2, "cited": ["Материалы/td-sequential", "Материалы/wyckoff"],
 "action": "filed", "actor": "critic-security"}
```

**Multi-agent scenario.** An orchestrator runs several subagents, each with its own
`WIKI_ACTOR_ID` (`critic-security`, `critic-logic`, `research-agent`, …). They all write
to the same `log_events`, but now every row shows whose it is. The rules:

- **Name shape** — `^[a-z0-9._:@-]{1,64}$`. An invalid or unset value → no `actor` key at
  all (never an error — an ambient env var can't break a CLI).
- **Who stamps `actor`** — all knowledge-write CLIs: `wiki-query apply`,
  `wiki-verify-multi apply`, `wiki-append-log`, plus import / upsert / sync. An explicit
  `--orchestrator-id` (or `actor` in `--details-json`) wins over the env var.
- **What is recorded** — `wiki-query apply` on *every* success (including an idempotent
  re-file, `action: unchanged`) writes the `cited` slug list + `action`.
  `wiki-verify-multi apply` has its own shape (only on a changed run, no `cited`/`action`);
  `wiki-append-log` writes an operator-supplied event.

**Read logging (opt-in).** Reads are not logged by default. These flags record "who
searched / retrieved what":

```bash
WIKI_ACTOR_ID=research-agent wiki-search "smart money" --vaults personal --log-access
#   → envelope: "access_logged": true
#   → log_events gains a Class-C (DB-only) row: query text + the hit slugs + actor="research-agent"
wiki-query prepare "..." --vault personal --vault-root . --log-retrieval    # same for the retrieval set
```

Read logging is **best-effort**: if the insert fails the envelope reports
`"access_logged": false`, but the read itself NEVER breaks.

**Survives a rebuild (D5).** These Class-C audit rows (NULL `log_md_byte_offset`) are
*spared* by `wiki-reindex --full` — a Class-B rebuild does not wipe operational Class-C
state — and the `--delta` staleness cutoff excludes read/`unchanged` telemetry so an
audited read can't mask a changed file.

### When to use which (single-owner vs multi-agent)

- **Solo / interactive:** the one high-value control is **`--min-trust internal`**
  (cleaner RAG on a clippings-heavy vault; also cuts the H-6 surface). Zero config — it
  works off your existing `url:` / `source:` fields.
- **Policy / `--audience`:** worth it only to sandbox cooperating subagents or gate an
  export; a solo owner has file access anyway, so keep it OFF (declare the ladder if you
  want it ready).
- **Read-audit / `WIKI_ACTOR_ID`:** earns its keep under named multi-agent pipelines
  (who filed / read what).

> **✅ Key takeaways.** All three controls are default-OFF and zero-DDL: without
> the flags, behaviour is byte-identical to before. They scope what a model is
> *shown* — least-privilege for cooperating agents — not who can read the files;
> nothing is encrypted and a local owner keeps full access. For a solo operator
> the one habit worth adopting is `--min-trust internal` on a clippings-heavy
> vault; `--audience` and `WIKI_ACTOR_ID` earn their keep only when named
> subagents share the corpus.

---

## Health & maintenance, methodologically

Maintenance is what keeps the compounding honest.

```mermaid
flowchart TD
    L["wiki-lint findings"] --> D["1. Dangling links<br/>[[X]] with no page X"]
    D --> C["2. Contradictions<br/>awaiting an operator decision"]
    C --> M["3. Missing concept pages<br/>mentioned in N+ sources, no page"]
    M --> O["4. Orphans<br/>nothing links here — maybe stale"]
    D -.->|"fix the link or create X"| FIX1[" "]
    M -.->|"feed to wiki-extract-concepts"| FIX2[" "]
    style FIX1 fill:none,stroke:none
    style FIX2 fill:none,stroke:none
    classDef hi fill:#fdd,stroke:#c66;
    classDef lo fill:#eef;
    class D hi;
    class O lo;
```

- **`wiki-lint` is your truth meter.** Run it after a batch of ingests and
  periodically. Triage in priority order:
  1. **Dangling links** — a `[[X]]` with no page is a promise the corpus didn't
     keep; create the page or fix the link.
  2. **Contradictions** — operator decisions waiting to be made.
  3. **Missing concept pages** — concepts mentioned across N sources with no
     dedicated page; the densification backlog for `wiki-extract-concepts`.
  4. **Orphans** — pages nothing links to; possibly stale.
  Plus the integrity findings: **hash drift** (a file changed without a reindex)
  and **type mismatches** (a page's frontmatter type disagrees with its layout —
  note these are layout-`type_mapping`-aware, so a `dev-project` `brief`-routed
  task isn't a false positive).
- **`wiki-reindex --full` is the rebuildability gate.** Periodically prove the
  vault survives it. If `--full` loses information, a Class A→B boundary has been
  violated (knowledge leaked into the DB-only layer) — that's a bug to fix, not to
  work around.
- **Schema upgrades are reindexes, not `ALTER`s.** Because the DB is a Class B
  cache, a `vN→vN+1` migration on a populated DB is: delete the
  `.db`/`-wal`/`-shm`, then `wiki-init --register-existing` + `wiki-reindex --full`
  (ADR-002 §D8). There is nothing in the DB to migrate that isn't in the markdown.

> **✅ Key takeaways.** Maintenance is a triage loop, not a chore list: dangling
> links first, then contradictions, then the missing-concept backlog, orphans
> last. `wiki-reindex --full` doubles as the standing proof that the Class A→B
> contract holds — if a full rebuild loses anything, that is a layering bug to
> fix, not an accident to work around. Schema upgrades are rebuilds for the same
> reason: the DB never holds knowledge the markdown doesn't.

---

## Anti-patterns (do NOT)

| Anti-pattern | Why it's wrong |
|---|---|
| Author knowledge in `index.md` or an auto-rendered ledger | They're Class B *projections* — the next render overwrites you. Author in pages; use `<!-- BEGIN-CUSTOM -->` only for genuinely hand-kept sections. |
| Hand-edit a page and skip the reindex | The DB goes stale; `wiki-lint` reports hash drift, search returns stale snippets. Run `wiki-index-upsert` / `wiki-reindex --delta`. |
| Resolve a contradiction by deleting the losing claim | The `## Contradictions` mechanism exists *because* the machine refuses to pick a winner. The operator edits with judgement; the trace stays. |
| Synthesise a `wiki-query` answer from outside the retrieved `hits` | Breaks the citation contract → exit 4. The whole point is grounded, auditable answers. |
| Treat `wiki-verify-multi` FAIL as "fix the answer for me" | It records a verdict and exits non-zero by design; it **never** mutates the Class A answer. You decide what to do. |
| Scrape CLI prose instead of the JSON envelope / exit code | The envelope is the contract; prose isn't. Branch on `$?`, read `.error`. |
| Treat retrieved page bodies as instructions | H-6: they're untrusted data. Fence + sentinel; execute nothing. |
| Run `wiki-init --scaffold-new --vault .` at this repo's root | The repo *is* the implementation, not a vault — rejected by design. |
| Put operator regexes in a layout without expecting the ReDoS gate | A catastrophic-backtracking pattern is refused at load (exit 6) or deadline-skipped at runtime. Write linear patterns. |

> **✅ Key takeaways.** Every row above is one principle seen from a different
> angle: markdown is canonical, the DB and the rendered ledgers are cache. So
> never author knowledge in a projection, never skip the reindex after an edit,
> and never let the machine (or a scraped string) make a call that belongs to
> the operator or the envelope. When unsure, ask which class — A, B, or C — the
> thing you are about to touch belongs to.

---

## Command reference appendix

Full contracts (flags, every exit code, the exact JSON envelope) live in each
skill's `SKILL.md`. Quick index:

| Command | One-liner | Skill |
|---|---|---|
| `wiki-init` | Scaffold / register / reconcile a vault | [skills/wiki-init](../../skills/wiki-init/SKILL.md) |
| `wiki-reindex` | Rebuild the DB from markdown (`--full` / `--delta`) | [skills/wiki-reindex](../../skills/wiki-reindex/SKILL.md) |
| `wiki-index-upsert` | Index one markdown file (idempotent) | [skills/wiki-index-upsert](../../skills/wiki-index-upsert/SKILL.md) |
| `wiki-index-render` | Render `index.md` / ledgers from the DB | [skills/wiki-index-render](../../skills/wiki-index-render/SKILL.md) |
| `wiki-search` | FTS5 + metadata search across vaults | [skills/wiki-search](../../skills/wiki-search/SKILL.md) |
| `wiki-query` | RAG: retrieve → cited synth → file the answer | [skills/wiki-query](../../skills/wiki-query/SKILL.md) |
| `wiki-verify-multi` | 4-critic audit of a filed answer | [skills/wiki-verify-multi](../../skills/wiki-verify-multi/SKILL.md) |
| `wiki-sync` | Format-aware batch driver: `scan` a zone → plan → distil (delegate to `wiki-import`) / upsert / skip (+ scanned-PDF OCR); `record` = commit-marker | [skills/wiki-sync](../../skills/wiki-sync/SKILL.md) |
| `wiki-import` | Unified construct on-ramp + per-source engine: fetch+convert → REASON → note + `_concepts/` → index (hand it a URL / doc / transcript, or a local raw `--source`) | [skills/wiki-import](../../skills/wiki-import/SKILL.md) |
| `wiki-extract-concepts` | Two-pass concept extraction | [skills/wiki-extract-concepts](../../skills/wiki-extract-concepts/SKILL.md) |
| `wiki-extract-decisions` | Typed-knowledge rail: decision/requirement/risk pages + edges, ontology-validated before any write | [skills/wiki-extract-decisions](../../skills/wiki-extract-decisions/SKILL.md) |
| `wiki-append-log` | Append a structured log event | [skills/wiki-append-log](../../skills/wiki-append-log/SKILL.md) |
| `wiki-confirm` | Promote/demote a candidate entity | [skills/wiki-confirm](../../skills/wiki-confirm/SKILL.md) |
| `wiki-alias` | Manage entity aliases | [skills/wiki-alias](../../skills/wiki-alias/SKILL.md) |
| `wiki-merge` | Fold a duplicate entity | [skills/wiki-merge](../../skills/wiki-merge/SKILL.md) |
| `wiki-lint` | SQL-level health-check (+ lifecycle-drift & ontology-violation contradictions; gate `--strict`) | [skills/wiki-lint](../../skills/wiki-lint/SKILL.md) |
| `wiki-config` | Per-folder `.wiki/sync.yaml` interface: show/tree/validate/doctor+fix/set/init/report/serve (no DB access) | [skills/wiki-config](../../skills/wiki-config/SKILL.md) |
| `wiki-graph` | Event-graph traversal: `backlinks` / `neighbors` / `chain` over typed edges | [skills/wiki-graph](../../skills/wiki-graph/SKILL.md) |
| `wiki-health` | Read-only knowledge-health report: `coverage` (missing relations) + `ontology` (contract violations); always exit 0 | [skills/wiki-health](../../skills/wiki-health/SKILL.md) |

Contract skills (LLM-side, no CLI; loaded by the orchestrator between
`prepare`/`apply`): `wiki-query-synthesis`, `wiki-verify`, `concept-extraction`.

---

## Appendix A. Glossary

Every term of the project's jargon, in plain language, grouped by theme. Each
term is also glossed at its first use in the text above — this appendix is the
lookup table for when you meet one again later.

### A.1. The core model

- **Vault** — an Obsidian-style folder of markdown notes; the unit this system manages.
- **Layout** — the on-disk grammar of a vault: which folders hold which kinds of pages, and how files map to types. Defined in YAML, not code.
- **Karpathy layout** — the standard layout (`_sources/` `_concepts/` `_entities/` …), named after the llm-wiki pattern's author.
- **PARA** — Projects/Areas/Resources/Archives: a common personal-vault folder method; one of the layout families `wiki-import` can file into.
- **Class A / B / C** — the data-layering contract: A = canonical markdown you author; B = derived state fully rebuildable from A (the DB, generated ledgers); C = minimal DB-only operational state (locks, audit rows).
- **Frontmatter** — the YAML metadata block (`---` … `---`) at the top of a markdown note; the index reads types, tags, and relations from it.
- **Wikilink** — Obsidian's `[[double-bracket]]` link between notes; "dangling" when the target page does not exist.
- **Slug** — the file-name-safe identifier derived from a title (e.g. `my-article`).
- **Footnote citation** — the `[^src-…]` markdown footnote that ties a claim on a concept page back to its source page; the auditability invariant.
- **Contradiction block** — the `## Contradictions` section the tooling inserts when sources disagree; the operator resolves it, the machine only surfaces it.
- **Projection / ledger** — generated, read-only markdown rendered *from* the DB (`index.md`, `KNOWN_ISSUES.md`-style roll-ups); Class B, never hand-authored.
- **`vault_id`** — the wiki's identifier for a registered vault (what `--vault`/`--vaults` take); independent of the Obsidian vault *name*.
- **`WIKI_SCHEMA.md`** — the vault's identity card: `vault_id`, `layout:`, optional `index_db:` and `policy:`; also `wiki-init`'s discovery marker.

### A.2. The index and search machinery

- **FTS5** — SQLite's built-in full-text-search engine, the backbone of `wiki-search`.
- **BM25** — the standard keyword-relevance ranking formula FTS5 uses to order hits.
- **WAL** — write-ahead logging, a SQLite mode that lets readers and a writer coexist safely.
- **Stemming** — matching a word by its root so one typed form finds its inflected siblings; `--exact` turns it off.
- **Reindex (`--full` / `--delta`)** — rebuilding the DB from markdown: `--full` wipes and rebuilds (the rebuildability gate), `--delta` catches recent edits incrementally.
- **Hash drift** — a file changed on disk but the index was not told; `wiki-lint` flags it.
- **mtime** — a file's modification timestamp; what `--delta` uses to spot changes cheaply.
- **Idempotent** — safe to re-run: an unchanged input is a no-op (e.g. `wiki-index-upsert` on a matching file hash).
- **Zero-DDL** — a feature that adds no database schema change; it rides existing columns such as `frontmatter_json`.
- **`user_version`** — SQLite's schema version stamp (7 here); a bump means a rebuild, never an in-place `ALTER`.
- **Global vs vault-local index** — one shared DB for all vaults (default) vs an `index_db:` DB that travels inside one vault (an island: no cross-DB search).

### A.3. Commands, contracts, and ingest

- **Envelope** — the single line of JSON each CLI prints on stdout; the machine-readable result an agent parses instead of prose.
- **Exit code** — the numeric process result (`$?`) an integrating script branches on before reading the envelope.
- **Orchestrator** — the main agent driving a session; it owns the LLM reasoning step between `prepare` and `apply`.
- **`prepare` / `apply`** — the two deterministic halves of an LLM-shaped skill: `prepare` stages and retrieves, `apply` validates and files; the reasoning in between belongs to the calling agent (Decision-17).
- **Decision-17** — the design rule that the Python plumbing carries no LLM calls (`no import anthropic`); any agent can therefore drive the skills.
- **REASON step** — the LLM summarisation pass inside `wiki-import` (the `summarizing-meetings` harness), owned by the calling agent, not by Python.
- **Distil** — run raw material through the LLM summarisation into a note; **upsert** — index a ready markdown file as-is, no LLM.
- **Zone** — a folder subtree you designate for batch ingest with `wiki-sync`.
- **Commit-marker / `source_state`** — the per-file "done" record `wiki-sync record` writes on full success, making re-runs no-ops.
- **Connector** — any small script you own that writes one stably-named markdown file per external object into a zone; with `mode: if-changed` the vault becomes a pull-refreshed mirror.
- **OCR** — optical character recognition: extracting a text layer from scanned page images (wired in for text-less PDFs).
- **Cascade** — per-folder config inheritance: a deeper `.wiki/sync.yaml` overrides its ancestors' values (deepest wins; lists replace, never extend).
- **Provenance (config)** — where a folder's effective config value comes from: built-in default, root, an ancestor, or the folder itself; `wiki-config show` prints it per key.
- **Root-only key** — a `sync.yaml` key (`zones`, `exclude`, `extensions`, `transcript_dedup`, `tag_namespace`) that only counts in the vault-root file; in a subfolder it is silently ignored.
- **TOCTOU** — a time-of-check/time-of-use race: the file changes between validating it and writing it; `wiki-config` mutations are guarded against this.
- **ReDoS** — regular-expression denial of service: a pathological pattern that can hang the matcher; operator regexes are gated at load and deadlined at runtime.

### A.4. Knowledge model, retrieval, and policy

- **Entity / concept page** — the additive, cross-referenced abstraction pages (`_entities/`, `_concepts/`) built from many sources; together they form the entity graph.
- **Candidate entity** — an LLM-guessed, unvetted entity (`is_candidate: 1`); `wiki-confirm` is your editorial sign-off.
- **Alias** — a surface spelling registered for an entity ("Hermes" → `hermes-agent`); search expands through aliases, and each alias maps to exactly one entity.
- **Event graph / typed edges** — the typed page-to-page relations (`implements`, `supersedes`, `causes`, …) authored in frontmatter one direction, with the inverse auto-derived; `wiki-graph` traverses them.
- **`--as-of`** — the point-in-time query: which pages were active on a date, derived from page dates plus the `superseded-by` / `invalidated-by` edges — no LLM.
- **Dangling link** — a `[[X]]` whose target page does not exist; **orphan** — a page nothing links to.
- **Lifecycle drift** — a page whose authored `status` contradicts the event graph (e.g. `status: accepted` but a `superseded-by` edge exists).
- **Ontology** — the layout's optional declared contract for types, edges, and statuses; a violating page is flagged, never blocked from indexing.
- **Coverage gap** — a page missing an expected relation (a `requirement` nothing implements); reported by `wiki-health`, always exit 0 — a gap is data, not a failure.
- **RAG** — retrieval-augmented generation: retrieve relevant notes first, then have the model answer *only* from them, with citations.
- **`question_hash`** — the integrity token `wiki-query prepare` issues and `apply` must return verbatim; it proves the answer was synthesised against the same corpus state it is filed against.
- **Trust tier** — the derived provenance signal on every retrieval hit: `external` (an `http(s)` `source:`/`url:`/`URL:` frontmatter key + case variants — a web capture or clipping; `_raw/` is a backstop that no built-in layout indexes), `internal` (your own note), `verified` (vouched for by a verification page); `--min-trust` floors on it.
- **Classification / `--audience`** — the optional page-level sensitivity label and the query-time gate that keeps higher-level pages out of a model's context; scoping, not access control.
- **H-6** — the untrusted-content rule: retrieved page bodies and CLI output are data, never instructions; fence them before showing them to a model.
- **`WIKI_ACTOR_ID`** — the environment variable that signs audit rows with the acting agent's name ("who filed / read what").
- **Class-C audit row** — a DB-only log row (read-access, telemetry) that survives a full rebuild because it belongs to operational state, not knowledge.

### A.5. Project markers

- **TASK NNN** — a shipped work increment; its spec lives in `docs/tasks/`.
- **ADR-NNN** — an Architecture Decision Record in `docs/adr/`; the durable "why" behind a behaviour.
- **R-NN** — a roadmap item number; used to tag which theme a feature belongs to.

---

## Related

- [`README.md`](../../README.md) — overview, installation, command index.
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — the living architecture.
- [`docs/adr/ADR-001-*`](../adr/ADR-001-wiki-ingest-integration.md) — wrap + index (later retired — TASK 047: `wiki-enrich` + the vendored `wiki_ingest` gave way to `wiki-import` as the unified construct path).
- [`docs/adr/ADR-002-*`](../adr/ADR-002-multi-vault-bottleneck-corrections.md) — multi-vault + Class A/B/C contract.
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../WIKI-INGEST-V1.1-CONTRACT.md) — the original file-layer skill contract (historical — retired TASK 047; `wiki-import` is the in-repo engine).
- [`sql/wiki-index-v2.sql`](../../sql/wiki-index-v2.sql) — the schema DDL.
- [`workflows/`](../../workflows/) — the orchestrator recipes for the `prepare`/`apply` skills.
</content>
