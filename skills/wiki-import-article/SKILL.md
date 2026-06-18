---
name: wiki-import-article
description: >-
  Import an external article / paper / X-thread into a PARA Obsidian vault — the
  PARA analog of wiki-enrich. Deterministic fetch+convert (html2md/pdf) → orchestrator
  translation/summary FED the known-concepts list → authored PARA note + concept pages
  + index. Triggers: "import this article into the vault", "wiki-import-article",
  "add this paper to Материалы".
tier: 2
version: 1.0
---

# wiki-import-article

**Purpose**: the **PARA construct path** — the PARA-layout analog of `wiki-enrich`
(which is Karpathy-only). Turns an external source into a compounding node of a PARA
vault: a translated/summarized `article-summary` note in its topic folder **plus**
sibling `_concepts/` entity pages, indexed into SQLite. A Decision-17 skill: **no
`import anthropic`** — Python does the deterministic plumbing (`prepare`/`apply`); the
**calling orchestrator owns the one reasoning step** (translation / summary).

## When to use
- You have a URL (or a local `.md`/`.html`/`.pdf`) for an article/paper/thread and want
  it filed into an existing PARA folder (e.g. `05 - Материалы/Криптовалюты/`).
- The vault is registered (`/wiki-init --register-existing`) and uses a PARA layout
  (`obsidian-personal`). For **Karpathy** vaults use `wiki-enrich` instead.

## When NOT to use
- Karpathy `_sources/` ingest → `wiki-enrich`. Meeting/lecture transcripts →
  `/generate-detailed-meeting-summary`. Re-index an existing note → `wiki-index-upsert`.

## The loop (prepare → REASON → apply)

### 1. `prepare` — deterministic fetch + context
```bash
wiki-import-article prepare --vault <id> --vault-root <abs> \
  --source <URL|file> --folder "05 - Материалы/<Topic>" --mode full|summary|thread
```
Dispatches to `html2md` (URL/HTML — it already owns the Wikipedia-REST-HTML and
arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html` exits) or the `pdf`
skill (PDF), writes `_raw/<slug>.md` **only on a non-empty fetch**, and emits:
```
{ action, raw_path, folder, slug, project, mode, title, author, date,
  source_hash, known_concepts: [{slug,name}…], existing_page_slugs: […] }
```
On an unreachable/empty source it emits `{error:"FETCH_FAILED", upstream:…}` (exit 10)
and writes **nothing** — file a `needs-manual` stub by hand.

### 2. REASON (the orchestrator's job — the one LLM step)
**Full contract:** [`references/reason-contract.md`](references/reason-contract.md) — the
canonical schema + depth-by-mode + hard rules (reuse it verbatim; the summary below is the digest).
Read `raw_path`, then produce the structured note:
```
{ title_ru, title_orig?, author?, published?, tldr, summary_bullets[],
  ru_body?,                       # full RU body (mode=full/thread); null for summary
  entities: [{name, definition, quote, type}] }   # type ∈ concept|external|person|company|product|group
```
Depth by mode: **full** = complete RU translation; **summary** = thorough RU digest
(`ru_body` null, detailed `summary_bullets`); **thread** = tight RU конспект.

> ## 🔴 HARD RULE — inject `known_concepts` (R-6, the core fix)
> You MUST pass `prepare`'s `known_concepts` into your reasoning context and **reuse an
> existing concept's `name`** whenever an entity matches one — do NOT mint a new variant
> ("AMM" vs "Автоматический маркет-мейкер"). This is the exact discipline `wiki-ingest`
> enforces (SKILL.md:34). Skipping it is what produced dangling `[[wikilinks]]` and slug
> collisions in the ad-hoc DAO/#01 imports. Each `entities[].quote` MUST be copied
> **verbatim** from the Russian text you produce.

### 3. `apply` — author + file + index
```bash
wiki-import-article apply --vault <id> --vault-root <abs> \
  --folder "05 - Материалы/<Topic>" --mode <same> \
  --raw-rel <prepare.raw_path> --source-url <URL> --source-lang en|ru \
  --existing-page-slugs '<prepare.existing_page_slugs JSON>' --note-stdin   # note JSON on stdin
```
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
documented **Workflow-tool recipe** — see [`workflows/wiki-import-article.md`](../../workflows/wiki-import-article.md)
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
- [`docs/tasks/task-038-wiki-import-article-para-ingest.md`](../../docs/tasks/) · ARCHITECTURE §2.3 · open-questions §11d
- `wiki-enrich` (Karpathy analog) · `wiki-extract-concepts` (concept filing) · `wiki-index-upsert`
