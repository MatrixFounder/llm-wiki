---
name: wiki-import
description: >-
  The unified construct path — import an external article / paper / X-thread / meeting
  transcript / finished summary into any Obsidian vault. Two orthogonal axes: content-type
  (--kind) sets the note type — all content-types run the ONE universal summarizing-meetings
  harness (summary→register); the vault LAYOUT (config) picks where it files (Karpathy vs PARA).
  Deterministic fetch+convert (html2md/pdf) → orchestrator REASON FED the known-concepts list
  → authored note + concept pages + index. Triggers: "import this into the vault", "wiki-import",
  "add this paper/article/transcript to the wiki". (`wiki-import-article` is a back-compat alias.)
tier: 2
version: 2.0
---

# wiki-import

**Purpose**: the **unified construct path**. Turns any external source into a compounding
node — a translated/summarized note **plus** its `_concepts/` entity pages, indexed into
SQLite — across **two orthogonal axes**:
- **content-type → the note `type:` + what the REASON harness emphasizes** (the one LLM step):
  meeting / article / paper / thread all run the ONE universal
  [`summarizing-meetings`](../summarizing-meetings/) harness; finished `summary` → register directly.
- **layout (CONFIG) → where it files**: `resolve_layout_config` decides Karpathy (`_sources/`
  + root `_concepts/`) vs PARA (topic folder + sibling `_concepts/`). One code path, not a fork.

A Decision-17 skill: **no `import anthropic`** — Python does the deterministic plumbing
(`prepare`/`apply`); the **orchestrator owns the one reasoning step** (the harness).

## When to use
- You have a URL or a local file (`.md`/`.html`/`.pdf`/transcript) to file into a vault folder.
  Works for **any layout** (Karpathy or PARA) — the layout is read from config, not chosen by you.
- `--kind auto` (default) detects the content-type; pass `--kind {meeting,article,paper,thread,summary}`
  to override. The vault is registered (`/wiki-init --register-existing`).

## When NOT to use
- Re-index an existing note → `wiki-index-upsert`. The legacy Karpathy-raw on-ramp `wiki-enrich`
  → `wiki-ingest` still exists (external); `wiki-import` is the config-driven successor.

## The loop (prepare → REASON → apply)

### 1. `prepare` — deterministic fetch + context
```bash
wiki-import prepare --vault <id> --vault-root <abs> \
  --source <URL|file> --folder "<topic folder>" --kind auto --mode full|summary|thread
```
Dispatches to `html2md` (URL/HTML — it already owns the Wikipedia-REST-HTML and
arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html` exits) or the `pdf`
skill (PDF), writes `_raw/<slug>.md` **only on a non-empty fetch**, **detects the
content-type** (`--kind auto`; override with `--kind`), and emits:
> **Reader-first:** the html2md path prefers the **reader extraction** (clean main
> content — no nav/"Skip to main content"/"Edit page" chrome) and falls back to the
> whole page only when reader is missing/over-stripped; only reader-referenced images
> are kept in `_attachments/` (chrome/avatar images dropped). Less junk in `_raw`.
```
{ action, raw_path, folder, slug, project, mode,
  kind, reason_harness, kind_confidence,            # ← content-type → which harness
  title, author, date, source_hash, images,         # images = count filed to _raw/_attachments/
  known_concepts: [{slug,name}…], existing_page_slugs: […] }
```
**The `_raw` is a self-contained capture (invariants):** it always carries a `source:`
frontmatter link to the original (injected for PDFs/text dumps that lack one), and — when
**image import is ON** — its images are downloaded into a sibling `_raw/_attachments/`
(relative `![](_attachments/<sha>.ext)` links). Image import is **config-driven, default ON**:
set `import_images: false` in `<vault>/.wiki/layout.yaml` to keep remote image URLs instead
(PDFs are text-only → no images either way). The filed note links to **both** the `_raw`
capture (an Obsidian-clickable wikilink `[[_raw/<slug>]]`) and the original URL (the localized
`Source` line). `sources:` frontmatter keeps the machine-readable `_raw/` path (resummarization).
On an unreachable/empty source it emits `{error:"FETCH_FAILED", upstream:…}` (exit 10)
and writes **nothing** — file a `needs-manual` stub by hand.

### 2. REASON (the orchestrator's job — the one LLM step)
Run the **one universal content harness** — **[`summarizing-meetings`](../summarizing-meetings/)**
(`prepare` reports it in `reason_harness`). It auto-detects + handles **meetings AND
articles/papers/threads**, emitting the reason-contract note-JSON; a separate
`summarizing-articles` would be redundant. For `kind: summary` (already a finished summary) →
**skip REASON**, register the source directly. (`--kind` still drives the note `type:`.)

The harness is model-agnostic (PRE-FLIGHT + self-verification) so the floor stays high on any
model/harness. **Full contract:** [`references/reason-contract.md`](references/reason-contract.md)
— the canonical schema + depth-by-mode + hard rules (reuse it verbatim; the digest follows).
Read `raw_path`, then produce the structured note **in the target `language`** that `prepare`
reports (the vault's `language`; English fallback) — the project is international, NOT RU-only:
```
{ title, title_orig?, author?, published?, tldr, summary_bullets[],
  body?,                          # full body in the target language (mode=full/thread); null for summary
  tags[],                         # 3–6 content topic tags (you read it → you tag it); no folder heuristic
  entities: [{name, definition, quote, type}] }   # type ∈ concept|external|person|company|product|group
```
(`title_ru`/`ru_body` are accepted as legacy aliases.) Depth by mode: **full** = complete
translation into the target language; **summary** = thorough digest (`body` null, detailed
`summary_bullets`); **thread** = tight synopsis. All prose is in the target `language`.

> ## 🔴 HARD RULE — inject `known_concepts` (R-6, the core fix)
> You MUST pass `prepare`'s `known_concepts` into your reasoning context and **reuse an
> existing concept's `name`** whenever an entity matches one — do NOT mint a new variant
> ("AMM" vs "Автоматический маркет-мейкер"). This is the exact discipline `wiki-ingest`
> enforces (SKILL.md:34). Skipping it is what produced dangling `[[wikilinks]]` and slug
> collisions in the ad-hoc DAO/#01 imports. Each `entities[].quote` MUST be copied
> **verbatim** from the target-language text you produce.

### 3. `apply` — author + file + index
```bash
wiki-import apply --vault <id> --vault-root <abs> \
  --folder "<topic folder>" --mode <same> --kind <prepare.kind> \
  --raw-rel <prepare.raw_path> --source-url <URL> --source-lang en|ru \
  --existing-page-slugs '<prepare.existing_page_slugs JSON>' --note-stdin   # note JSON on stdin
```
`apply` files the note **per the resolved layout** (Karpathy `_sources/` vs PARA topic folder)
and sets the note `type:` from `--kind` (layout-safe). The remainder:
`apply` assembles the per-mode PARA note, **sanitizes entity names** (normalizer that
feeds the extract-concepts name gate), **guarantees verbatim quotes**, runs the
**collision guard** (skips a candidate whose slug == the note's own slug, or collides
with an `existing_page_slugs` entry — so a generic `defi` never evicts the owner's
`Defi.md`), then files concept pages via `wiki-extract-concepts apply --source-page <the
note's own slug> --source-hash <fresh sha256 of the written note body>` and indexes the
note. Skipped candidates are reported in the manifest, never silently dropped.

## Exit codes
| Code | Meaning |
|---|---|
| 0 | ok (`action:"prepared"` / `"imported"`) |
| 2 | bad argument (bad note JSON, invalid slug, folder escapes vault) |
| 6 | a dependency missing (`html2md`/`pdf` bin absent), or partial (index/concept-file failed) |
| 10 | `FETCH_FAILED` (source unreachable/empty — propagated from html2md/pdf; no raw written) |

## Batch import
For a list (the DAO/#01 pattern) the CLI stays **per-article**; the batch fan-out is a
documented **Workflow-tool recipe** — see [`workflows/wiki-import.md`](../../workflows/wiki-import.md)
(parallel translation under a schema, then **serialized** `apply` to avoid SQLite WAL
write contention).

## Safety
- Fetch is deterministic (the html2md/pdf skills) — never "convert in your head".
- All write paths (`_raw/`, note, concepts) go through `validate_inside_vault` (R-26) +
  a target-symlink refusal; the slug passes `_is_valid_slug` (no traversal). YAML
  frontmatter scalars are newline/control-stripped + quoted (H-6 frontmatter-injection
  guard); the note body is orchestrator-authored markdown (kept structural); concept pages
  are markdown-sanitized by `wiki-extract-concepts`.
- `html2md`/`pdf` are external skill **binaries** (`--html2md-bin`/`--pdf-extract-bin`,
  fail-fast if absent) — not Python deps.

## Related
- [`references/reason-contract.md`](references/reason-contract.md) — the canonical REASON-step contract (schema + depth + hard rules)
- `docs/TASK.md` (TASK 039 — unified path) + `docs/tasks/task-038-…` (origin) · ARCHITECTURE §2.3 · open-questions §11d/§11e
- `wiki-enrich` (Karpathy analog) · `wiki-extract-concepts` (concept filing) · `wiki-index-upsert`
