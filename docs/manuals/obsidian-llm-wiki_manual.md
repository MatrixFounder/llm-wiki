# obsidian-llm-wiki — Manual

> **Companion to [`README.md`](../../README.md).** The README is the *entry point*
> (what the project is, how to install, the command index). **This manual is the
> *methodology*** — why each command exists, how to work with the vault's markdown
> documents (standard and custom layouts), and how to wire the wiki into another
> agent as an external knowledge resource. If you only want to get running, read
> the README. If you want to *operate* the wiki well, read this.

---

## Contents

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
  - [The standard (karpathy) layout](#the-standard-karpathy-layout)
  - [Page anatomy & the auditability invariants](#page-anatomy--the-auditability-invariants)
  - [The author's contract: markdown is canonical](#the-authors-contract-markdown-is-canonical)
  - [Registering a pre-made summary (not raw)](#registering-a-pre-made-summary-not-raw)
  - [Custom layouts: the layout engine](#custom-layouts-the-layout-engine)
  - [Mixed vault: search-only areas + enrich-able course zones](#mixed-vault-search-only-areas--enrich-able-course-zones)
  - [Automating the mix: `wiki-sync` (per-note routing, conversion, OCR)](#automating-the-mix-wiki-sync-per-note-routing-conversion-ocr)
- [Using the wiki as an external resource for other agents](#using-the-wiki-as-an-external-resource-for-other-agents)
  - [The integration model: JSON envelopes + exit codes](#the-integration-model-json-envelopes--exit-codes)
  - [The `prepare` / `apply` contract (Decision-17)](#the-prepare--apply-contract-decision-17)
  - [The wiki as a RAG backend](#the-wiki-as-a-rag-backend)
  - [Untrusted data: the H-6 posture](#untrusted-data-the-h-6-posture)
- [Health & maintenance, methodologically](#health--maintenance-methodologically)
- [Anti-patterns (do NOT)](#anti-patterns-do-not)
- [Command reference appendix](#command-reference-appendix)
- [Related](#related)

---

## Overview

**obsidian-llm-wiki** is the *index + tooling layer* for an Obsidian-style
[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). The
file layer (LLM-driven page synthesis) is owned by the `wiki-ingest` skill,
vendored in-process; this repo reads that output into a SQLite index and serves
fast, structured queries, an entity graph, cited RAG answers, and a verification
layer.

| Property | Value |
|---|---|
| **Type** | Multi-vault knowledge-base index + CLI toolkit |
| **Canonical source** | Markdown in the Obsidian vault (Class A) |
| **Derived cache** | One global SQLite DB (FTS5 + WAL), partitioned by `vault_id` (Class B/C) |
| **Surface** | 15 CLIs (`wiki-*`), each also a `/wiki-*` slash command inside Claude Code |
| **I/O contract** | stdin/args in → one-line JSON envelope on stdout + exit code |
| **Core invariant** | The DB is 100% rebuildable from markdown (`wiki-reindex --full`) |
| **Schema** | `user_version = 5` (`sql/wiki-index-v2.sql`) |
| **Runtime** | Python 3.14+; deps in `requirements.txt` |

---

## Why an index layer at all (the methodology)

The standard RAG pattern is **stateless**: every question re-derives knowledge
from raw documents, and nothing accumulates. Karpathy's llm-wiki inverts that —
the LLM **incrementally builds and maintains a persistent, interlinked wiki** that
sits between you and the raw sources. Knowledge **compounds**: each ingest enriches
the corpus the next query reads.

`wiki-ingest` does the *file-layer* half of that loop (synthesise pages, merge
additively, flag contradictions). This repo does the half that makes the
compounding *usable at scale*:

```mermaid
flowchart LR
    SRC["raw source /<br/>external summary"] --> C
    C["CONSTRUCT<br/>enrich · extract · upsert"] -->|"writes"| MD["MARKDOWN<br/>Class A — canonical"]
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

---

## How to run the commands

The `wiki-*` commands are ordinary **shell CLIs** that operate on the vault's
markdown files. Obsidian itself does not *execute* them — Obsidian's role is the
editor/viewer of the Class-A markdown — but you can run them right inside the
Obsidian window with the `Terminal` community plugin (an embedded real shell; see
below), so in practice you needn't leave Obsidian at all. By default the SQLite index
lives outside the vault entirely (`~/Library/Application Support/wiki-index/global.db` on
macOS) — one global DB shared by all vaults, partitioned by `vault_id`. A vault can instead
own a **vault-local** index that travels with it (`index_db: .wiki/index.db` in
`WIKI_SCHEMA.md`); you pick global vs local once, at init — see
[Choosing the index database](#choosing-the-index-database-global-default-vs-vault-local)
under Vault lifecycle. The working loop is: **edit in Obsidian → run a command → reindex
catches the cache up → search / query reflects it** — and Obsidian picks up the on-disk
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
/ `wiki-enrich` this is effectively the *required* surface, because the middle of
their `prepare`/`apply` contract is an LLM reasoning step the orchestrator owns (see
[the `prepare`/`apply` contract](#the-prepare--apply-contract-decision-17)). You
*can* run their deterministic halves by hand, but then you must do the
synthesis/critique yourself. Other vendors (Gemini CLI, etc.) drive the same
vendor-neutral binaries — each workflow's `## Fallback` section explains the
non-Claude-Code path (inline the contract skill into the system context instead of
`Skill({…})`).

### Which surface for which command

| Command | Plain terminal / Obsidian `Terminal` plugin | Claude Code `/wiki-*` | Gemini / other agents |
|---|---|---|---|
| `init` · `search` · `lint` · `reindex` · `index-upsert` · `index-render` · `confirm` · `alias` · `merge` · `append-log` · `sync scan` · `sync record` | ✅ run directly | ✅ | ✅ |
| `query` · `verify-multi` · `extract-concepts` · `enrich` · `sync` *(executor)* *(need an LLM step)* | ⚠️ deterministic halves only — you'd supply the LLM reasoning by hand | ✅ **recommended** | ✅ via each workflow's `## Fallback` |

> **The one discipline that matters:** after you hand-edit markdown in Obsidian,
> tell the index — `wiki-index-upsert` for one file, `wiki-reindex --delta` for
> many. Until you do, `wiki-search` returns stale snippets and `wiki-lint` reports
> hash drift. The markdown is canonical; the reindex is how the cache learns.

---

## The command vocabulary, by purpose

The 15 CLIs are not a flat list — each plays a role in the loop above. Below,
each command is given as *why it exists* and *when to reach for it*, not just its
flags (those live in each [`SKILL.md`](../../skills/)).

### 1. Construct knowledge

These turn raw material into compounding pages.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-sync`** | The **zone-level dispatcher** (the multi-file on-ramp). `scan <zone>` classifies *every* file by extension + `#wiki/*` tag + content shape and emits a deterministic **plan** (convert / ingest / upsert / skip); the [`wiki-sync` workflow](#automating-the-mix-wiki-sync-per-note-routing-conversion-ocr) executes it idempotently (office/PDF→md, **scanned-PDF OCR**, `.vtt` de-timestamp, summarise→enrich→extract, ready-note upsert, view-sidecar skip). Reach for it instead of hand-routing a folder of heterogeneous drops file-by-file. Deterministic core, no LLM; `wiki-sync record` is the per-file commit-marker. |
| **`wiki-enrich`** | The **raw-material** on-ramp (single file). Hand it a raw source file; it invokes the (vendored) `wiki-ingest` synthesis layer (which **LLM-summarises** the source), then mirrors the produced manifest into the index. ⚠️ `wiki-enrich` **always treats `--source` as raw** — there is no "skip the summary" mode. If you *already have a finished summary*, do **not** use `wiki-enrich`; use the [pre-made-summary recipe](#registering-a-pre-made-summary-not-raw) instead. (`wiki-sync` composes `wiki-enrich` under the hood for `ingest`-routed files.) |
| **`wiki-extract-concepts`** | The *retroactive* on-ramp. Given a source page already in the index, it extracts the concepts/entities it mentions but that have no page yet — turning implicit knowledge into explicit, linkable pages. A two-pass `prepare`/`apply` skill (see [below](#the-prepare--apply-contract-decision-17)). Use it to *densify* an existing corpus, or after importing many sources at once — **regardless of how the source page got indexed** (raw-ingested or hand-registered). |
| **`wiki-index-upsert`** | The single-file primitive. Indexes one markdown file idempotently (a file-hash match is a no-op). Use it when you've hand-written, hand-edited, **or dropped in a finished summary from elsewhere** and want the index to reflect it immediately without a full reindex — **no LLM, no raw processing**. |
| **`wiki-append-log`** | Writes a structured event to `log.md` *and* mirrors it to the `log_events` table atomically (flock + fsync, bi-directional M-2 contract). The log is grep-friendly chronological memory for future agent sessions — git diff is for humans, the log is for the next LLM. |

### 2. Search & retrieve

The everyday read path — **search before you grep**.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-search`** | FTS5 BM25 full-text search across one or many vaults, ranked with snippets, expanding through entity aliases by default. This is the fast lookup that replaces re-reading raw files. It *also* does **metadata filtering**: `--status` / `--severity` / `--where 'field=value'` compile to a `CAST(json_extract(frontmatter_json, …) AS TEXT) = ?` predicate (not full-text), so hyphenated (`SEV-2`) and numeric (`priority=1`) values match by string; omit the query for a pure metadata *listing*. |
| **`wiki-index-render`** | Regenerates `index.md` — a *read-only projection* of the DB — preserving any operator-authored `<!-- BEGIN-CUSTOM:name -->` blocks. With `--auto-indexes` it also renders Class-B "rebuildable markdown" ledgers (e.g. a `KNOWN_ISSUES.md` rolled up from per-issue source files). Use it to refresh the human-browsable catalog after ingests. |

### 3. Resolve entities

The corpus accumulates *candidate* entities (LLM-guessed) and duplicate spellings.
These commands curate the entity graph so it stays a graph, not a pile.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-confirm`** | Promotes a *candidate* entity (`is_candidate = 1`, LLM-extracted, unvetted) to *confirmed* — your editorial sign-off that this is a real, canonical entity. `--undo` demotes; `--auto --threshold N` bulk-promotes anything mentioned ≥ N times. Confirm-state is Class A (entity-page frontmatter) mirrored to the DB. |
| **`wiki-alias`** | Registers surface-string aliases ("Hermes" → `hermes-agent`). Aliases are **hard-unique per vault** (one surface → exactly one entity) and `wiki-search` expands through them, so a query for any spelling finds the canonical page. Class A frontmatter + DB mirror. |
| **`wiki-merge`** | Folds a duplicate entity into the canonical one (`hermes-framework` → `hermes-agent`): re-points all references, absorbs + registers redirect aliases, and deletes the duplicate page. The alias table *is* the durable redirect — there is no wikilink rewriting to drift out of sync. |

### 4. Answer & verify (RAG)

The compounding payoff: turn the corpus into cited answers, and audit them.

| Command | Why it exists / what it does |
|---|---|
| **`wiki-query`** | Retrieval-augmented answering. `prepare` retrieves (FTS5 BM25 + alias/entity-graph expansion); the orchestrator agent synthesises a *cited* answer; `apply` files it as a first-class compounding `_queries/<slug>.md` page — indexed, FTS-searchable, with `cited` backlinks that survive a full reindex. This is "good answers can be filed back into the wiki" made durable. |
| **`wiki-verify-multi`** | An **off-by-default** four-critic prose audit (factual-grounding / logic-coherence / security-injection / completeness-faithfulness) of a filed answer *against the sources it cited*. It files a `_verifications/verify-<slug>.md` verdict page. A FAIL **records the verdict and exits non-zero — it never edits the answer**. Reach for it on high-stakes answers where a silent hallucination would be costly. |

### 5. Maintain health

| Command | Why it exists / what it does |
|---|---|
| **`wiki-lint`** | A SQL-level health-check over one vault or all of them. Surfaces **orphan links** (pages with no inbound links), **dangling refs** (`[[X]]` with no page X), **missing-on-disk** pages (DB/disk drift), **hash drift** (a file changed but wasn't reindexed), **type mismatches**, and **cross-vault concept duplicates**. Run it periodically; the findings have a natural action priority (dangling → contradictions → missing → orphans). `--mtime-skip` trades full-hash integrity for speed. |
| **`wiki-reindex`** | Rebuilds the DB from markdown. `--full` wipes and rebuilds (this is the **rebuildability gate** — if a vault can't survive `--full`, the Class A→B contract is broken); `--delta` does an incremental mtime/hash-based pass after manual edits. The authoritative reconciliation of cache ↔ canon. |

### 6. Vault lifecycle

| Command | Why it exists / what it does |
|---|---|
| **`wiki-init`** | Brings a vault under management. `--register-existing` indexes a pre-existing vault; `--scaffold-new --layout <name>` creates a fresh vault skeleton; `--reconcile` renames/re-points a registered vault. Add `--local` (or `--index-db <path>`) to give the vault its **own** index DB instead of the shared global one — see below. The one-time setup per vault. |

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
#     the sync root. Because WIKI_SCHEMA.md travels with the vault, an absolute
#     path needs an explicit opt-in so a synced/cloned config can't silently
#     redirect writes elsewhere on your disk:
WIKI_ALLOW_ABSOLUTE_INDEX_DB=1 \
  wiki-init --register-existing --vault /path/to/MyVault \
            --index-db ~/wiki-dbs/myvault.db
```

`--local` / `--index-db` are pure convenience — equivalently, hand-edit
`WIKI_SCHEMA.md` and add `index_db: .wiki/index.db` to the frontmatter. **Precedence
is always `--db-path` (a per-command override, mainly for tests) > `index_db`
(in `WIKI_SCHEMA.md`) > global.** So a vault is global until the day you add
`index_db`; remove the key and it's global again, byte-for-byte. **iCloud paths are
auto-rejected wherever they appear**, to prevent SQLite WAL/shm corruption.

---

## Working with documents in Obsidian

This is the half most operators get wrong: **what do the files look like, what may
I touch by hand, and how do I make the tooling fit a vault that isn't shaped like
Karpathy's?** Three parts: the standard layout, the page contract, and custom
layouts.

### The standard (karpathy) layout

`wiki-init --scaffold-new --layout karpathy` creates (and the tooling expects)
this shape. The leading-underscore folders follow the Obsidian system-folder
convention — they sort to the top and signal "meta-content, not user notes":

```
<vault>/
├── WIKI_SCHEMA.md          # this vault's identity + conventions (REQUIRED — holds vault_id)
├── index.md                # read-only catalog projection (## Sources / ## Concepts / ## Entities)
├── log.md                  # chronological append-only journal (mirrors log_events)
├── _sources/               # per-source summary pages         (type=summary)   ← wiki-ingest
├── _concepts/              # abstract concepts                (entities)        ← wiki-ingest
├── _entities/              # concrete people/companies/...     (entities)        ← wiki-ingest
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
    Q -->|"raw material<br/>(transcript, article, notes)<br/>— needs summarising"| ENR["wiki-enrich --source &lt;file&gt;<br/>= wiki-ingest LLM-summarises → _sources/ → index"]
    Q -->|"a FINISHED summary<br/>(already distilled elsewhere)"| REG["1. place it at _sources/&lt;slug&gt;.md (with frontmatter)<br/>2. wiki-index-upsert --source &lt;abs path&gt;<br/>= indexed verbatim, NO LLM, NOT raw"]
    ENR --> IDX["source page is now indexed (type=summary)"]
    REG --> IDX
    IDX -->|"optional: densify"| EXT["wiki-extract-concepts prepare/apply<br/>--source-page &lt;slug&gt;<br/>→ concept/entity pages"]
    classDef raw fill:#fdeede,stroke:#e0a050;
    classDef premade fill:#eef7ee,stroke:#5a5;
    class ENR raw;
    class REG premade;
```

`wiki-enrich` is **only** for raw material — it always invokes `wiki-ingest` to
*summarise*. For a finished summary, skip it entirely and register the page
directly. The full recipe:

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

> **Why not just point `wiki-enrich` at it?** `wiki-enrich` would hand your summary
> to `wiki-ingest` as *raw input* and produce a **summary-of-your-summary** —
> double-distilled, with new slugs. Registering directly keeps your text verbatim
> and canonical. Use `wiki-enrich` only when the LLM *should* do the distillation.

### Custom layouts: the layout engine

Not every vault is Karpathy-shaped. A software repo's `docs/` tree, a personal
Obsidian vault with numbered folders and Unicode titles — these need a different
"where do pages live / what type are they" grammar. Since TASK 012 that grammar is
**YAML config, not code** (`scripts/wiki_index/layout_config.py`, schema
`config/layout-config.schema.yaml`).

Three layouts ship built-in (`scripts/wiki_index/layouts/`):

| Layout | Shape | Slug strategy |
|---|---|---|
| `karpathy` | The standard layout above. **Byte-identical** to the legacy hardcoded behaviour (golden-anchor-guarded). | `identity` (verbatim stem) |
| `dev-project` | A repo's `docs/` — `tasks/*.md`, `adr/*.md`, `issues/*.md`, etc. | `transliterate` (ASCII-safe) |
| `obsidian-personal` | Numbered folders + Unicode | `preserve-unicode` |

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

Two design facts worth internalising:

- **Two separate config systems.** Per-vault *identity* (`config_loader.py` /
  `wiki-config.schema.yaml` — who this vault is, its `vault_id`) is deliberately
  distinct from per-layout-class *grammar* (the engine above — how this *kind* of
  vault is shaped). Don't conflate them.
- **Operator regexes are guarded against ReDoS.** Custom `ref_extraction[].regex`
  and `paths[].project_pattern` are checked at *load time* (a stdlib-`re` budget
  gate; a misspelled grammar key is a hard load error, exit 6, not a silent
  flood) and at *runtime* (a per-file deadline via the PyPI `regex` engine with
  `timeout=`, env-overridable via `WIKI_REDOS_BUDGET_S`, default 2.0s — on
  timeout the file is skipped with a WARN, never hangs). Built-in layouts use
  stdlib `re` and pay zero overhead (TASK 012 + 017).

### Mixed vault: search-only areas + enrich-able course zones

Most real personal vaults are *mixed*: the bulk is finished notes you only want to
**search**, but a few subfolders are **collection zones** — you drop transcripts /
raw material there and want the system to `enrich` them into a compounding wiki
(e.g. a `Webinars/` or a per-course folder under `03 - Learning/`).

**Why this needs two vaults, not one layout.** `wiki-enrich` always produces the
karpathy page kinds (`_sources/_concepts/_entities/`) — those folder names are fixed
by the vendored `wiki-ingest`, not configurable — and a personal layout
(`obsidian-personal`) does not index them. So one layout can't serve both halves.
The clean model is **two registered vaults sharing the one global DB** (exactly what
multi-vault partitioning is for); search is unified via `--vaults a,b`.

```mermaid
flowchart TD
    OBS["your Obsidian vault (root)"] --> P["Vault P: personal<br/>layout = obsidian-personal<br/>SEARCH-ONLY"]
    OBS -->|"subtree: 03 - Learning/Courses/**"| L["Vault L: courses<br/>layout = karpathy<br/>ENRICH-able"]
    P -.->|"ignore: 03 - Learning/Courses/**"| X[" "]
    RAW["transcript / raw material"] -->|"wiki-enrich"| L
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
            ├── _sources/     ← enrich writes summaries here (+ your ready notes → upsert)
            ├── _concepts/    ← enrich builds concept pages
            └── _entities/    ← …and entity pages
```

**Two ways to shape the enrich zone** (both karpathy):
- **Vault-per-course** — each course folder is its own `karpathy` vault_root with
  `_sources/_concepts/_entities/`. Simplest mental model; matches a self-contained
  course folder. New course = new folder + one `WIKI_SCHEMA.md (layout: karpathy)`
  + `wiki-init --register-existing`.
- **One courses vault + course tier** — many courses in one vault_id, each living
  under `Lessons/<Course>/_sources/…`; enrich routes with
  `--ingest-arg=--course="AI Hard Fork 2026"`. Less per-course setup when you keep
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

# --- Vault L: a course (karpathy), enrich-able ---
#  ".../Courses/AI Hard Fork 2026/WIKI_SCHEMA.md":  layout: karpathy
wiki-init --register-existing --vault ai-hard-fork-2026
wiki-enrich --vault ai-hard-fork-2026 \
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
- **enrich creates `_sources/_concepts/_entities/`** in the course folder — expected
  (that's the system-managed zone). Already-distilled notes (your `Summaries/`) go
  through `wiki-index-upsert` (see [pre-made summary](#registering-a-pre-made-summary-not-raw)); only new raw goes through `wiki-enrich`.
- **HTML / office sources**: `wiki-ingest` expects text — convert `.html` to
  `.txt`/`.md` first.
- The **personal vault stays untouched** (indexed only); enrich writes solely into
  the course zone.

---

### Automating the mix: `wiki-sync` (per-note routing, conversion, OCR)

The two-vault recipe above splits work *by folder*. **`wiki-sync`** (TASK 018 / R-11)
goes one level finer: point it at a **zone** and it classifies **every file** — by
extension, by per-note `#wiki/*` tag, and by content shape — then routes each one to
**convert / ingest / upsert / skip**. Dropping a transcript, a `.docx`, or even a
*scanned* PDF into a course folder now "just" becomes compounding wiki pages, without
hand-invoking `wiki-enrich` / `wiki-index-upsert` per file.

**Two phases (Decision-17 — deterministic plan, orchestrator-owned execution):**

- **`wiki-sync scan <zone> --vault <id>`** — *pure Python.* Walk → classify →
  `sha256` → `is_unchanged` → a strict **plan JSON** (`entries[]` + `summary{}`).
  **No LLM, no network, no mutation.** `--dry-run` prints a human report of every
  action + reason. This is the part you review before anything is written.
- **[`workflows/wiki-sync.md`](../../workflows/wiki-sync.md)** — the orchestrator
  *executor.* Per plan entry it converts / de-timestamps / **H-6-fences** /
  summarises / enriches / extracts / upserts / skips, then writes a per-file
  **commit-marker** (`wiki-sync record`) so a re-run is a no-op. (`/wiki-sync`
  drives the whole thing.)

```mermaid
flowchart TD
    F["file in the zone"] --> EXT{"extension<br/>(case-folded)"}
    EXT -->|".docx .xlsx .pptx .pdf"| CONV["convert+ingest<br/>→ _raw/.staging/&lt;slug&gt;-&lt;ext&gt;.md<br/>(scanned PDF → OCR)"]
    EXT -->|".txt .vtt .srt"| ING["ingest<br/>(.vtt/.srt → de-timestamp first)"]
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
| `.docx` `.xlsx` `.pptx` `.pdf` | **convert** → staged `_raw/.staging/<slug>-<ext>.md` (a *non-walked* dir) → **ingest** |
| `.txt` `.vtt` `.srt` | **ingest** (`.vtt`/`.srt` de-timestamped first) |
| `.md` | content rules (tags → view → type, below) |
| images · `.canvas` · `.excalidraw.md` · `.base` · unknown | **skip** (binary / view-artifact / unknown-ext) |

**Routing by per-note tag** (`.md` only) — precedence **`skip` > `raw` > `keep` > default**.
Accepts both an inline `#<ns>/x` tag (outside code fences), a frontmatter `tags:` entry,
and a `<ns>:` field (`<ns>` = `tag_namespace`, default `wiki`):

| Tag / signal | Effect |
|---|---|
| `#wiki/skip` (or `wiki: skip`) | never index this note |
| `#wiki/raw` (or the file is under `_raw/`) | treat as **raw** → full ingest (summarise → concepts) |
| `#wiki/keep` | **rescue** a `.md` from an `exclude:` zone (only `keep` rescues — not `raw`) |
| *(no tag)* | a **mappable `type:`** → `upsert`; otherwise `skip: unmappable-type` |

**Generated-view sidecars are skipped** — they're navigation, not knowledge: DB Folder
(`database-plugin:` frontmatter and/or a ` ```yaml:dbfolder ` block), Bases (` ```base `),
Dataview (` ```dataview `/` ```dataviewjs `), folder-notes (stem == dir). The
**only-a-view guard** skips them *only* when the note is essentially one view block —
a real note that *embeds* a view alongside prose is content → `upsert` (no over-flagging).

**Scanned PDFs are OCR'd** (wired 2026-06-03): a `.pdf` with no text layer
(`pdf_extract.py` exit `10 DocumentScanned`) is run through the `pdf` skill's
`pdf_ocr.py` (`ocrmypdf`, default languages **`eng+rus`**) → searchable text → ingest.
If the OCR engine isn't installed (`bash <pdf-skill>/scripts/install.sh --with-ocr`
+ system tesseract/ghostscript), the file is flagged **`needs-ocr`** and skipped —
never silently dropped.

**Config** — `<vault>/.wiki/sync.yaml` (optional): `zones`, `exclude`, `tag_namespace`
(default `wiki`), and `extensions` overrides. Strict schema (a misspelled key is a load
error); an untrusted file is size-capped (256 KiB) + anchor-banned + symlink-refused.

**Recipe (test on a copy first):**

```bash
# 1. PLAN — deterministic, writes nothing; review every action + reason
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run

# 2. EXECUTE the plan — the orchestrator recipe (convert/ingest/upsert/skip per file).
#    Invoke /wiki-sync, or follow workflows/wiki-sync.md step by step.

# 3. RE-RUN — every recorded file now reports is_unchanged (a no-op).
wiki-sync scan "courses/AI Hard Fork 2026" --vault ai-hard-fork-2026 --dry-run
```

**Re-summarization policy — don't re-summarise what's already summarised** (TASK 019,
opt-in). Add a `resummarize:` block to `.wiki/sync.yaml` and `wiki-sync` will route a raw
source to **`skip`** instead of `ingest` when a summary for it already exists — so re-running
a scan over a course you've already summarised doesn't burn tokens redoing it. "A summary
exists" is the union of three detectors (cheapest-first): **`source_state`** (this exact raw
was synced before) ∪ **provenance** (some summary's frontmatter `source:`/`sources:` cites
this raw) ∪ **filesystem mirror** (a `Summary/` sibling shares the raw's key — `stem-relpath`
1:1, or `group_key`/`key` N:1 so many transcripts fold onto one lesson summary). `--force`
bypasses the gate (re-summarise anyway). Rules are **per-folder overridable** (a deeper
`<folder>/.wiki/sync.yaml` deep-merges over the vault root — e.g. a `Lessons/` zone keyed by
date instead of lesson number).

> **New raw under an already-summarised key → merge or split?** (TASK 021) If you drop a
> *new* transcript whose key already has a summary that doesn't cite it, `wiki-sync` keeps
> skipping it (your "group summarised → done" intent) but logs a **merge/split WARN**. Resolve
> it explicitly: **MERGE** → `wiki-sync scan <zone> --force` regenerates the summary from all
> raws sharing the key and writes them into `sources:`; **SPLIT** → give the new raw a distinct
> key (finer `group_key` / own scope) or author a second summary citing it; **SUPERSEDE** →
> archive the old raw, then `--force`. `sources:` is the authoritative record; the key is just
> the default grouping. See `workflows/wiki-sync.md` Step 6.

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
  retrieval (status boards, severity queues) without full-text.
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
verification skills carry an explicit H-6 banner; honour it. On the write side, the
tooling already escapes markdown/HTML-active sequences on egress
(`sanitize_markdown_text`) so a filed answer can't smuggle a wikilink/HTML/dataview
payload back into the vault.

---

## Health & maintenance, methodologically

Maintenance is not chores — it is what keeps the compounding honest.

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
| `wiki-sync` | Format-aware dispatcher: `scan` a zone → plan → convert/ingest/upsert/skip (+ scanned-PDF OCR); `record` = commit-marker | [skills/wiki-sync](../../skills/wiki-sync/SKILL.md) |
| `wiki-enrich` | Ingest a raw source, then index it | [skills/wiki-enrich](../../skills/wiki-enrich/SKILL.md) |
| `wiki-extract-concepts` | Two-pass concept extraction | [skills/wiki-extract-concepts](../../skills/wiki-extract-concepts/SKILL.md) |
| `wiki-append-log` | Append a structured log event | [skills/wiki-append-log](../../skills/wiki-append-log/SKILL.md) |
| `wiki-confirm` | Promote/demote a candidate entity | [skills/wiki-confirm](../../skills/wiki-confirm/SKILL.md) |
| `wiki-alias` | Manage entity aliases | [skills/wiki-alias](../../skills/wiki-alias/SKILL.md) |
| `wiki-merge` | Fold a duplicate entity | [skills/wiki-merge](../../skills/wiki-merge/SKILL.md) |
| `wiki-lint` | SQL-level health-check | [skills/wiki-lint](../../skills/wiki-lint/SKILL.md) |

Contract skills (LLM-side, no CLI; loaded by the orchestrator between
`prepare`/`apply`): `wiki-query-synthesis`, `wiki-verify`, `concept-extraction`.

---

## Related

- [`README.md`](../../README.md) — overview, installation, command index.
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — the living architecture.
- [`docs/adr/ADR-001-*`](../adr/ADR-001-wiki-ingest-integration.md) — wrap + index.
- [`docs/adr/ADR-002-*`](../adr/ADR-002-multi-vault-bottleneck-corrections.md) — multi-vault + Class A/B/C contract.
- [`docs/WIKI-INGEST-V1.1-CONTRACT.md`](../WIKI-INGEST-V1.1-CONTRACT.md) — the file-layer skill contract.
- [`sql/wiki-index-v2.sql`](../../sql/wiki-index-v2.sql) — the schema DDL.
- [`workflows/`](../../workflows/) — the orchestrator recipes for the `prepare`/`apply` skills.
</content>
