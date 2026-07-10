---
name: wiki-import
description: >-
  The unified construct path — import an external article / paper / X-thread / meeting
  transcript / lesson / finished summary into any Obsidian vault. Orthogonal axes: content-type
  (--kind) sets the note type AND its grammar — meeting/lesson → a pyramid digest (no full-text
  wrapper), article/paper/thread → the article wrapper; all run the ONE universal
  summarizing-meetings harness (summary→register); the vault LAYOUT (config) picks where it files
  (Karpathy vs PARA). Generation modifiers: --diagrams (opt-in selective mermaid), --no-concepts
  (author entities but defer filing to /wiki-extract-concepts). Deterministic fetch+convert
  (html/pdf/office/.vtt) → orchestrator REASON FED the known-concepts list → authored note +
  concept pages + index. Triggers: "import this into the vault", "wiki-import",
  "add this paper/article/transcript/lesson to the wiki". (`wiki-import-article` is a back-compat alias.)
tier: 2
version: 2.1
---

# wiki-import

**Purpose**: the **unified construct path**. Turns any external source into a compounding
node — a translated/summarized note **plus** its `_concepts/` entity pages, indexed into
SQLite — across **two orthogonal axes** (plus two opt-in generation modifiers):
- **content-type (`--kind`) → the note `type:` + its GRAMMAR + what the REASON harness emphasizes**
  (the one LLM step): meeting / lesson / article / paper / thread all run the ONE universal
  [`summarizing-meetings`](../summarizing-meetings/) harness; finished `summary` → register directly.
  **Grammar splits by kind:** `meeting`/`lesson` → a **pyramid digest** (the body IS the
  summarizing-meetings two-level pyramid — TL;DR → detailed sections / decisions / action items —
  filed verbatim under the H1 with **no** `## Полный текст (перевод)` wrapper; `type:`
  `meeting-summary`/`lesson-summary`); `article`/`paper`/`thread` → the per-`mode` **article wrapper**
  (Саммари / Ключевые сущности / Полный текст). One code path — `apply` selects the grammar from `--kind`.
- **layout (CONFIG) → where it files**: `resolve_layout_config` decides Karpathy (`_sources/`
  + root `_concepts/`) vs PARA (topic folder + sibling `_concepts/`). One code path, not a fork.

**Generation modifiers (orthogonal to both axes):** `--diagrams` → the REASON step adds *selective*
mermaid (illustrative flows/loops only — never decorative); `--concepts`/`--no-concepts` (default ON)
→ `--no-concepts` still authors `entities[]` but **defers** concept filing to a separate
`/wiki-extract-concepts` run (the envelope reports `concepts_deferred: true`).

A Decision-17 skill: **no `import anthropic`** — Python does the deterministic plumbing
(`prepare`/`apply`); the **orchestrator owns the one reasoning step** (the harness).

## When to use
- You have a URL or a local file (`.md`/`.html`/`.pdf`/transcript) to file into a vault folder.
  Works for **any layout** (Karpathy or PARA) — the layout is read from config, not chosen by you.
- `--kind auto` (default) detects the content-type; pass `--kind {meeting,lesson,article,paper,thread,summary}`
  to override (`lesson` is **opt-in only** — never auto-detected; a course/lecture transcript that
  should file as a pyramid `lesson-summary`). The vault is registered (`/wiki-init --register-existing`).
- `--diagrams` (opt-in) → ask the REASON step for selective mermaid diagrams; `--no-concepts` → author
  `entities[]` but skip filing the `_concepts/` pages (defer to `/wiki-extract-concepts`).
- `--classification <level>` (TASK 049 / ADR-009, opt-in) → stamp `classification: <level>` into the
  `_raw/` capture (**prepare**) AND the authored note (**apply** — pass the same value to both). This
  is the H-6 quarantine for hostile external content: a `restricted`-stamped import never enters a
  lower-`--audience` retrieval envelope (`wiki-search`/`wiki-query`/`wiki-verify-multi`). Shape
  `[a-z][a-z0-9_-]{0,15}`; an out-of-ladder value is flagged by `wiki-lint` (`invalid-classification`).

## When NOT to use
- Re-index an existing note → `wiki-index-upsert`. `wiki-import` is THE construct path; the
  legacy `wiki-enrich` → vendored `wiki-ingest` on-ramp was retired (TASK 047) and the additive
  concept-compounding it provided is now a derived Class-B render (`wiki-index-render --concept-mentions`).

## The loop (prepare → REASON → apply)

### 1. `prepare` — deterministic fetch + context
```bash
wiki-import prepare --vault <id> --vault-root <abs> \
  --source <URL|file> [--folder "<topic folder>"] --kind auto --mode full|summary|thread \
  [--known-concepts-format full|slugs-only]   # P-6: slugs-only shrinks the envelope on a large vault
```

> ### No `--folder`? prepare INFERS one (TASK 057 — W2)
> `--folder` is **optional on `prepare`** (still required on `apply`). Omitted → the fetch runs
> as usual, then a **vendor-independent inference chain** proposes the folder — and `prepare`
> **writes NOTHING into the vault**:
> 1. **Series-sibling (primary):** the detected title's series stem (`Building AI-Native
>    Startups [004]` → `Building AI-Native Startups`) is FTS-matched against the vault's own
>    index; siblings agreeing on ONE folder → `{action:"folder_proposed",
>    folder_inferred, basis:"series-sibling", confidence:"high", evidence:[…]}` (exit 0).
>    Needs no running app, no vendor — index + filesystem only.
> 2. **Active-note hint (secondary):** only if (1) is inconclusive — `obsidian-active-note
>    folder` when on PATH (basis `active-note`, confidence `medium`); ANY non-zero exit /
>    absence degrades silently.
> 3. **Ask:** neither → `{error:"FOLDER_UNRESOLVED", candidates:[…]}` (exit 2) — ask the
>    operator; never guess.
>
> Every no-folder outcome also carries **`staged_path`** — the converted capture persisted
> OUTSIDE the vault (frontmatter stamped with `source:`/title/author/date), so the confirmed
> re-run `prepare --folder "<F>" --source <staged_path>` is **fetch-free** (a 70-min broadcast
> is never transcribed twice). Staging keeps text only — re-run the ORIGINAL URL instead when
> the images matter.
Dispatches to one of **three** wrapped external skills (composition, not reinvention —
extends ADR-001): `html` (URL/HTML — it already owns the Wikipedia-REST-HTML and
arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html` exits), the `pdf`
skill (PDF), or **`transcript-fetcher`** (video — see *Video sources* below). It writes
`_raw/<slug>.md` **only on a non-empty fetch**, **detects the content-type** (`--kind auto`;
override with `--kind`), and emits:
> **Reader-only:** the `html` path runs with `--reader-only`, so the skill emits a SINGLE
> `<slug>.md` = the **reader extraction** (clean main content — no nav/"Skip to main
> content"/"Edit page" chrome), with its own whole-page fallback when the reader is
> empty/over-stripped. Only reader-referenced images are kept in `_attachments/`
> (chrome/avatar images dropped). Less junk in `_raw`.
```
{ action, raw_path, folder, slug, project, mode,
  kind, reason_harness, kind_confidence,            # ← content-type → which harness
  title, author, date, source_hash, images,         # images = count filed to _raw/_attachments/
  quality_flag,                                      # transcript: non-null (e.g. english_auto_translation) → WARN the operator BEFORE REASON
  embedded,                                          # --embedded-videos: per-embed [{url,reason}] log (fetched / ad-context / ad-denylist / cap / …); null otherwise
  known_concepts: [{slug,name}…], existing_page_slugs: […] }
```
> **Idempotent re-poll — `is_unchanged` STOP (TASK 051 / R-18).** If `_raw/<slug>.md`
> already exists and the freshly fetched+converted content is **byte-identical**, `prepare`
> skips the write and emits `{ action: "unchanged", is_unchanged: true, raw_path, slug,
> source_hash }` instead — the orchestrator **STOPs** (no REASON, no `apply`), exactly like
> the `wiki-extract-concepts` / `wiki-query prepare` short-circuit. A scheduled re-poll of an
> unchanged source therefore costs one fetch+hash, not one LLM pass. Pass **`--force`** to
> bypass (always rewrite + a full envelope — regenerate after a REASON-harness change or a
> corrupt prior summary). The fetch+convert still run; only the summarise (and the write) are
> skipped. This is the per-source half of R-18's freshness story; the `wiki-sync` half is
> `resummarize.mode: if-changed` (see the manual's *connector contract*).

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

> ### Video sources (TASK 044 — the `transcript-fetcher` branch)
> A **video URL routes deterministically by host** (URL-shape only — Decision-17, no LLM, no probe):
> - **Unambiguous video** (`youtube.com`/`youtu.be`, `vimeo.com`, a Skool `/classroom/` lesson,
>   `x.com|twitter.com/i/broadcasts/`+`/i/spaces/`) → **`transcript-fetcher`** automatically.
>   `engine = transcript:<origin>` (origin = `transcript_origin` for X, else `chosen_track_kind` —
>   e.g. `transcript:auto`/`transcript:embedded-captions`/`transcript:whisper-cli`). No html fallback:
>   if the video has no producible transcript it is a hard `FETCH_FAILED` (there is no text path).
> - **Ambiguous `x.com/<user>/status/<id>`** → stays the **`html`** path by default (most tweets are
>   text — zero regression). Pass **`--video`** to ALSO fetch the embedded clip and **concatenate**
>   (`## Tweet` + `## Video Transcript`, `engine = html+transcript:<origin>`); a tweet with no media
>   degrades gracefully to html-only.
> - **A non-video web page** is `not_video` → `html` as before. Pass **`--embedded-videos`** to ALSO
>   discover + transcribe video embeds on the page and append them (`## Embedded video <k>`,
>   `engine = html+embedded:<n>`). **Ad videos are ALWAYS excluded** (no off switch): the fixed chain is
>   *allowlist (youtube/vimeo only — bounds egress) → ad-network denylist → ad-context → ad-param → dedup
>   → cap*. `--embedded-videos-max N` (default 5) caps it; every discovered embed is logged in the
>   envelope `embedded[]` with its keep/skip reason (no silent drops). Ad-exclusion is best-effort
>   heuristic — a cleverly-disguised ad embed may slip; the opt-in + cap + per-embed skip bound the blast.
>   (`--video` and `--embedded-videos` are mutually exclusive — passing both is a usage error, exit 2.)
>
> **Passthroughs** to the transcript subprocess: `--lang` is ALWAYS forwarded (the vault language; never
> the skill's own `ru` default), plus `--max-duration-min` (clip long Broadcasts/Spaces),
> `--cookies-from-browser`/`--cookies-file` (login-walled video), and — TASK 057 (W1) —
> **`--transcript-concurrency`** → the skill's `--concurrent-fragments` (parallel HLS fragment
> downloads for X media) and **`--transcript-media-timeout`** → `--media-timeout-sec` (X media
> download budget). Omitted → the flags are NOT passed, so the skill's own env/`.env`/
> duration-derived defaults rule (the policy stays skill-owned). `--transcript-bin` overrides the
> skill path (absent → exit 6 when a video URL is hit).
>
> **Wall-clock (scoped — TASK 057 W1-3):** `WIKI_TRANSCRIPT_TIMEOUT_S` set → that bound for every
> transcript subprocess; unset → **3600 s** for a PRIMARY fetch (the URL is the content:
> unambiguous video / x-status `--video` — covers parallel download + ASR of a ≥60-min broadcast)
> and **300 s** per best-effort `--embedded-videos` fetch (hung embeds must never chain multi-hour
> stalls). NOTE: an embed fetch therefore clips a large `--transcript-media-timeout` at 300 s —
> raise the env knob when you genuinely want long embedded transcriptions.
>
> ### Announcement tweets (TASK 057 — W3)
> An `x.com/<user>/status/<id>` **without `--video`** whose reader capture merely ANNOUNCES a
> Broadcast/Space (low prose **AND** a first-party `/i/broadcasts/`+`/i/spaces/` link — both gates
> must fire, so a substantive tweet that also links a broadcast still imports) **writes nothing**
> and emits `{action:"announcement_only", broadcast_url, hint}` (exit 0): re-run `prepare` on the
> `broadcast_url`, or pass `--video` to concatenate tweet + transcript as before. No junk `_raw`,
> no avatar/emoji attachments, no `thread` mislabel.
>
> **Dependencies are path-dependent:** captioned YouTube/Vimeo/x-status-video need only **yt-dlp**
> (light); caption-less **Broadcasts/Spaces** additionally need **ffmpeg + a whisper backend** (ASR) —
> absent → a typed `DEP_MISSING` (exit 6) with remediation, never a junk `_raw`. A non-null
> `quality_flag` in the envelope (e.g. `english_auto_translation`) MUST be **surfaced to the operator
> before the REASON harness** runs.

### 2. REASON (the orchestrator's job — the one LLM step)
Run the **one universal content harness** — **[`summarizing-meetings`](../summarizing-meetings/)**
(`prepare` reports it in `reason_harness`). It auto-detects + handles **meetings AND
articles/papers/threads**, emitting the reason-contract note-JSON — there is no separate
articles/paper skill; use this one for every content type. For `kind: summary` (already a finished summary) →
**skip REASON**, register the source directly. (`--kind` still drives the note `type:`.)

The harness is model-agnostic (PRE-FLIGHT + self-verification) so the floor stays high on any
model/harness. **Full contract:** [`references/reason-contract.md`](references/reason-contract.md)
— the canonical schema + depth-by-mode + hard rules (reuse it verbatim; the digest follows).
Read **the WHOLE** `raw_path` (the entire file — never a `limit`/sample), then produce the structured
note **in the target `language`** that `prepare` reports (the vault's `language`; English fallback) —
the project is international, NOT RU-only:
```
{ title, title_orig?, author?, published?, tldr, summary_bullets[],
  body?,                          # full body in the target language (mode=full/thread); null for summary
  tags[],                         # 3–6 content topic tags (you read it → you tag it); no folder heuristic
  participants[],                 # MEETING/LESSON ONLY: attendees "Name — role/org" — the home for PEOPLE
  entities: [{name, definition, quote, type}] }   # type ∈ concept|external|person|company|product|group
                                  # entities[] = domain concepts; for meeting/lesson apply DROPS type:person
```
(`title_ru`/`ru_body` are accepted as legacy aliases.) Depth by mode: **full** = complete
translation into the target language; **summary** = thorough digest (`body` null, detailed
`summary_bullets`); **thread** = tight synopsis. All prose is in the target `language`.

> ## 🔴 HARD RULE — `mode=full` is a COMPLETE translation, not a summary
> Read the **ENTIRE** `raw_path` and translate **every section** (preserve headings / lists / tables /
> code / `$…$` formulae). A `mode=full` body that is a small fraction of the source is an accidental
> summary — a **FAILURE**. For a long source, **fan out by section** (parallel translators sharing a
> term glossary), then stitch — never truncate. You do NOT silently downgrade `full` to a digest
> (that is what `mode=summary` is for). See the contract's *Anti-rationalization* + *Coverage (mode=full)*
> blocks: [`references/reason-contract.md`](references/reason-contract.md).

> ## 🔴 HARD RULE — inject `known_concepts` (R-6, the core fix)
> You MUST pass `prepare`'s `known_concepts` into your reasoning context and **reuse an
> existing concept's `name`** whenever an entity matches one — do NOT mint a new variant
> ("AMM" vs "Автоматический маркет-мейкер"). The list is **already in the `prepare` envelope** —
> match against it in-context; don't run a separate command to enumerate the vault's concepts.
> This is the core additive-merge discipline. Skipping it is what produced
> dangling `[[wikilinks]]` and slug collisions in the ad-hoc DAO/#01 imports. Each
> `entities[].quote` MUST be copied **verbatim** from the target-language text you produce —
> **author the body first, then copy quotes out of it** (never quote the raw source).

> ## 🔴 HARD RULE — note GRAMMAR follows `--kind` (pyramid vs article wrapper)
> `--kind meeting`/`lesson` → the note is a **pyramid digest**, NOT a verbatim full translation:
> author the `body` as the summarizing-meetings two-level pyramid (TL;DR → detailed sections; for
> transcripts also decisions / action items / open questions). `apply` files that `body` **verbatim
> under the H1** with **no** `## Полный текст (перевод)` / `## Саммари` wrapper, and sets `type:`
> `meeting-summary`/`lesson-summary`. Do NOT produce a full-text-wrapped article note for a meeting/
> lesson — the pyramid IS the deliverable (even at `mode=full`, which here means "cover the whole
> transcript in the pyramid", not "translate every line verbatim"). `--kind article`/`paper`/`thread`
> keep the per-`mode` article wrapper (the depth-by-mode table above). See
> [`references/reason-contract.md`](references/reason-contract.md) *Note grammar by content-type*.
>
> **Participants ≠ entities (TASK 052):** for meeting/lesson, list attendees in `participants[]`
> ("Name — role/org"); keep `entities[]` for domain concepts only. `apply` DROPS a `type:"person"`
> entity for pyramid kinds (`skipped` reason `participant-not-concept`) → no person concept page.
>
> **`--diagrams`** → add *selective* mermaid only where it earns its place (a process flow, a state
> loop, an architecture relationship the prose can't carry); **never** a decorative diagram per
> section. **`--no-concepts`** → still author `entities[]` (so a later `/wiki-extract-concepts` run has
> them), but STATE that concept filing is deferred — `apply` will skip filing and report
> `concepts_deferred: true`.

### 3. `apply` — author + file + index
```bash
wiki-import apply --vault <id> --vault-root <abs> \
  --folder "<topic folder>" --mode <same> --kind <prepare.kind> \
  --raw-rel <prepare.raw_path> --source-url <URL> --source-lang en|ru \
  [--published <prepare.date>] [--diagrams] [--no-concepts] \
  --existing-page-slugs '<prepare.existing_page_slugs JSON>' --note-stdin   # note JSON on stdin
```
(`--published <prepare.date>` (WI-3): pass prepare's extracted source `date` — it's used as a
fallback for the note's `published` when the REASON note leaves it null, so a month-precision
publication date like arXiv `2025-10` isn't dropped. A `published` in the note JSON wins.)
(`apply` rejects `--kind auto` — pass the **resolved concrete** kind from `prepare`. `--diagrams`/
`--no-concepts` mirror the REASON modifiers above: `--diagrams` is recorded in the manifest;
`--no-concepts` skips concept filing and sets `concepts_deferred: true`.)
`apply` files the note **per the resolved layout** (Karpathy `_sources/` vs PARA topic folder),
selects the **grammar from `--kind`** (pyramid for meeting/lesson, article wrapper otherwise),
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
| 0 | ok (`action:"prepared"` / `"imported"` / `"unchanged"`; TASK 057: `"folder_proposed"` — folder inferred, capture staged, nothing filed yet; `"announcement_only"` — announcement tweet, nothing filed, re-route to `broadcast_url`) |
| 2 | bad argument (bad note JSON, invalid slug, folder escapes vault); TASK 057: `FOLDER_UNRESOLVED` — no `--folder` and inference couldn't resolve one (the `NO_CONTEXT`-family "input effectively missing"; envelope carries ranked `candidates` + `staged_path`) |
| 6 | a dependency missing (`html`/`pdf`/`transcript` bin absent; or no ffmpeg/ASR backend for caption-less video — `transcript-fetcher` exit 7); or partial (index/concept-file failed) |
| 10 | `FETCH_FAILED` (source unreachable/empty; or transcript no-media on an unambiguous-video URL / source-auth / rate-limit — propagated from html/pdf/transcript; no raw written) |

## Batch import
For a list (the DAO/#01 pattern) the CLI stays **per-article**; the batch fan-out is a
documented **Workflow-tool recipe** — see [`workflows/wiki-import.md`](../../workflows/wiki-import.md)
(parallel translation under a schema, then **serialized** `apply` to avoid SQLite WAL
write contention).

## Safety
- Fetch is deterministic (the html/pdf/transcript skills + URL-shape host routing) — never "convert in your head".
- All write paths (`_raw/`, note, concepts) go through `validate_inside_vault` (R-26) +
  a target-symlink refusal; the slug passes `_is_valid_slug` (no traversal). YAML
  frontmatter scalars are newline/control-stripped + quoted (H-6 frontmatter-injection
  guard); the note body is orchestrator-authored markdown (kept structural); concept pages
  are markdown-sanitized by `wiki-extract-concepts`.
- `html`/`pdf`/`transcript-fetcher`/office are external skill **binaries**, not Python deps.
  You rarely pass them: each is **auto-resolved** across the harness's skill dir (works on Claude
  Code, pi, codex, … alike). Pass `--html-bin`/`--pdf-extract-bin`/`--transcript-bin`/`--soffice-wrapper`
  only to point at a non-standard install; a truly missing skill fails fast (exit 6) with remediation.
- **Untrusted-content egress bound (H-6):** `--embedded-videos` discovers embed URLs from an
  untrusted page body, but only **allowlisted video hosts** (youtube/vimeo) are ever fetched — a
  page cannot drive a fetch to an arbitrary host; ad-network embeds are denylisted; the raw-HTML
  scan is size-capped and the discovery regex is ReDoS-safe (bounded). The transcript subprocess is
  invoked via an argv array (never a shell string). Operator-supplied URLs to the transcript/pdf
  subprocess are the same documented residual SSRF surface — run untrusted imports egress-restricted.

## Related
- [`references/reason-contract.md`](references/reason-contract.md) — the canonical REASON-step contract (schema + depth + hard rules)
- `docs/TASK.md` (TASK 039 — unified path) + `docs/tasks/task-038-…` (origin) · ARCHITECTURE §2.3 · open-questions §11d/§11e
- `wiki-extract-concepts` (concept filing) · `wiki-index-upsert` (re-index) · `wiki-index-render --concept-mentions` (derived concept compounding)
