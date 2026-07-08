# 2.3. The construct path — one pipeline, two orthogonal axes (TASK 039)

**Contents**

- [2.3.1 Construct-path hardening](#231-construct-path-hardening-2026-06-dogfooding--a-14-round-adversarial-vdd-multi)
- [2.3.2 Transcript-fetcher — a third wrapped external skill for video sources](#232-transcript-fetcher--a-third-wrapped-external-skill-for-video-sources-task-044--extends-adr-001)
- [2.3.3 Embedded-video discovery](#233-embedded-video-discovery-opt-in---embedded-videos--task-044-r-13)
- [2.3.4 Converged construct pipeline — one engine, one batch driver](#234-converged-construct-pipeline--one-engine-one-batch-driver-task-046)
- [Legacy PARA-import framing (superseded)](#legacy-para-import-framing-superseded-23--task-038-retired-task-047)

Knowledge enters the wiki through **one** config-driven construct path, **`wiki-import`**
(`wiki-import-article` is a back-compat alias). It is **not** forked per layout; it has two
**orthogonal** concerns:

- **content-type → WHICH REASON harness** (the generation step — the orchestrator's one LLM step,
  Decision-17): **all content-types run the ONE universal `summarizing-meetings` harness** (it
  auto-detects + handles meetings AND articles/papers/threads); finished `summary` → no REASON
  (register directly). `prepare --kind auto` detects the kind (for the note `type:` + reporting); `--kind` overrides.
- **layout (CONFIG) → WHERE it files**: `resolve_layout_config` decides Karpathy (`_sources/` + **root**
  `_concepts/`) vs PARA (topic-folder + **sibling** `_concepts/`) — the SAME code path already used by
  `wiki-index-upsert` (TASK 024) and `wiki-extract-concepts` (TASK 037).

The two axes are independent, so `{meeting, article, paper, thread, summary} × {Karpathy, PARA, …}`
all flow through this one path. The load-bearing discipline — **the REASON harness is fed
`known_concepts`** so `[[wikilinks]]` reuse existing names and never dangle/collide — holds for every cell.

```mermaid
flowchart LR
    SRC[/"source<br/>URL · PDF · dropped file"/] --> PREP["wiki-import<br/>prepare"]
    PREP -->|acquire| ACQ[["html / pdf<br/>(external)"]]
    PREP --> KIND{{"detect content-type<br/>(--kind auto)"}}
    KIND -->|meeting| R
    KIND -->|article · paper · thread| R
    KIND -->|finished summary| FILE
    KC{{"known_concepts<br/>injected"}} -.->|reuse names| R
    subgraph REASON["REASON — orchestrator's one LLM step; harness by content-type"]
      R(["summarizing-meetings<br/>(universal content harness)"])
    end
    R -->|note JSON| FILE["wiki-import<br/>apply"]
    FILE --> LAY{{"layout<br/>(resolve_layout_config)"}}
    LAY -->|karpathy| KP[/"_sources/&lt;slug&gt;.md<br/>+ ROOT _concepts/"/]
    LAY -->|para| PA[/"&lt;topic-folder&gt;/&lt;note&gt;.md<br/>+ SIBLING _concepts/"/]
    FILE --> IDX["wiki-extract-concepts<br/>+ wiki-index-upsert"] --> DB[("SQLite index")]
    classDef cli fill:#eef7ee,stroke:#5a5,color:#000;
    classDef ext fill:#fdeede,stroke:#e0a050,color:#000;
    classDef disc fill:#fff3cd,stroke:#d4a017,color:#000;
    classDef store fill:#eee,stroke:#999,color:#000;
    classDef harness fill:#f0e8fe,stroke:#85a,color:#000;
    class PREP,FILE,IDX cli; class ACQ ext; class KIND,LAY,KC disc; class SRC,KP,PA,DB store; class R harness;
```

**Orthogonality (every cell = the same path):**

| content-type \ layout | Karpathy (`_sources/`+root) | PARA (folder+sibling) |
|---|---|---|
| **meeting** → `summarizing-meetings` | ✓ | ✓ (closes the TASK 038 hole) |
| **article/paper/thread** → `summarizing-meetings` (same universal harness) | ✓ | ✓ (TASK 038) |
| **finished summary** → register directly | ✓ | ✓ |

**Retired (TASK 047):** the original Karpathy-raw on-ramp `wiki-enrich` → vendored `wiki-ingest`
(ADR-001 Option I) that overlapped the top-left cells was **deleted** — `wiki-import` is the unified
construct path (any layout), and concept-page compounding is a derived Class-B render (see §2.3).
Decision-17 throughout: every CLI is deterministic plumbing; the single reasoning step is the
harness-guided LLM, never inside a CLI. Skill-call detail + the `summarizing-meetings` note-JSON
alignment: TASK 039 + the `summarizing-meetings` postanovka.

## 2.3.1 Construct-path hardening (2026-06; dogfooding + a 14-round adversarial `/vdd-multi`)

Six properties were added/repaired so the path works **universally across all four built-in
layouts and any output language**:

- **Internationalization (no hardcoded locale).** The rendered note's language follows the
  vault's `language` (`WIKI_SCHEMA`; **English fallback**, via the guarded `_vault_language`).
  Section headings/labels/origin phrases are localized through a `NOTE_TEMPLATES` registry
  (en + ru built in; a new language = one dict entry); `prepare` emits `language` so the REASON
  step produces title/tldr/bullets/body in it. The note-JSON contract uses **neutral
  `title`/`body`** (legacy `title_ru`/`ru_body` accepted as back-compat aliases).
- **Clickable `_raw` link.** The filed note links to its source capture with an Obsidian
  wikilink `[[_raw/<slug>]]` (resolves in any vault), and `reindex._body_refs` **skips
  `_raw/`-targeted refs** so the link is never a false orphan; `sources:` frontmatter still
  carries the machine-readable path (resummarization).
- **Concept-filing gate.** Concept pages are filed only when the resolved layout can actually
  index a `_concepts/<slug>.md` page (`_layout_indexes_concepts`: a `concept` `type_mapping`
  **and** a glob reaching the sibling `_concepts/`). Concept-capable = karpathy / obsidian-personal
  / cybos; a structured-doc layout like dev-project files the summary note **without** concepts
  (reported, not a failure) — preserving the Class A/B rebuildability invariant (no orphaned,
  non-`--full`-rebuildable markdown).
- **Layout `type_mapping` + ignore.** dev-project + cybos gained `summary`/`article-summary`/
  `meeting-summary`/`lesson-summary` → db_type summary (imported notes index); cybos also gained
  concept/external/person/company/product/group (its concept pages index). karpathy +
  dev-project + cybos gained `**/_raw/**` in `ignore` (the `_raw/` capture is never indexed as a
  phantom page that could clobber the curated note on a shared `(vault_id, slug, project)`).
- **Decision-17 entry points.** A missing `--folder`/`--vault-root` → clean `INVALID_FOLDER`/
  `INVALID_VAULT_ROOT`; a schemaless vault → language `en` (no crash); a hung `html` →
  `FETCH_FAILED(timeout)` with the temp dir reclaimed; the note JSON is a **bounded read**
  (`NOTE_TOO_LARGE` over 32 MiB); and `main()` has a **catch-all backstop** emitting a typed
  `INTERNAL_ERROR` (exception class only — never `str(e)`, CWE-209) so no path raw-tracebacks.
- **Global install is reproducible.** `bin/install-globally.sh` (→ `~/.local/bin` + `~/.claude/ skills` + `~/.claude/commands`) and `bin/install-project-symlinks.sh` (in-repo `.claude`/
  `.agent` vendor trees) are safe + idempotent (skip-foreign / repair-repo-owned / per-item
  report). **Run them after adding a new `bin/wiki-*`, `skills/wiki-*/`, or `commands/wiki-*.md`**
  — new entries are not auto-propagated.

## 2.3.2 Transcript-fetcher — a third wrapped external skill for video sources (TASK 044 — extends ADR-001)

`dispatch_fetch` in `scripts/wiki_skills/wiki_import_article/_fetch.py` previously routed every
source to one of TWO external skills (`html` or `pdf`). A video URL therefore hit the `html` skill
and captured only the watch-page chrome — no spoken content. TASK 044 adds a THIRD external-skill
fetch branch, `transcript-fetcher`, following the exact composition pattern of `html`/`pdf`
(NF-2, ADR-001 "Wrap + Index").

**External skill contract.** `transcript-fetcher` lives at
`/Users/sergey/dev-projects/Universal-skills/skills/transcript-fetcher/`; its own venv is
`scripts/.venv/bin/python scripts/fetch.py`.

- **CLI:** `fetch.py <URL> --out <path.txt> --json-errors [--lang <code>] [--prefer manual|auto] [--with-description] [--cookies-file PATH] [--cookies-from-browser BROWSER] [--max-duration-min N]`.
- **Output:** a plain-text `.txt` (no frontmatter) + a sibling `<out>.stat.json` sidecar carrying
  `transcript_origin` (`embedded-captions | macwhisper | whisper-cli | whisper-cpp | openai-api`),
  `quality_flag` (e.g. `english_auto_translation`), and title/uploader/duration. Optional
  `<out>.description.md`.
- **Exit codes:** typed; exit 7 = `MissingDependency`.
- **Interpreter:** a `_transcript_python()` helper mirrors `_pdf_python()` — prefers the skill's own
  venv interpreter.

**Routing table (DECISION 2 — hybrid, URL-shape + `--video` flag; Decision-17: zero LLM guesses,
zero network probes in the default path).**

| Source shape | Default route | `--video` flag |
|---|---|---|
| `youtube.com`, `youtu.be`, `vimeo.com` | transcript-fetcher AUTO | n/a (unambiguous) |
| Skool lesson URL (`skool.com/*/…/lesson/`) | transcript-fetcher AUTO | n/a (unambiguous) |
| `x.com/i/broadcasts/<id>`, `x.com/i/spaces/<id>` | transcript-fetcher AUTO | n/a (unambiguous) |
| `x.com/<user>/status/<id>` (ambiguous: text OR video) | existing `html` path | forces transcript path |
| Any other URL / local file | existing `html`/`pdf` dispatch (byte-identical) | — |

Auto-routing applies only to hosts that have **no usable text path** (html returns login/landing
chrome) — it is a pure win with zero regression. The ambiguous `status/<id>` URL stays on the html
default (most tweets are text) so the existing text-only path is never broken.

**Text + video concatenation for `--video` on a status URL (DECISION 3).** When `--video` is
given on an `x.com/<user>/status/<id>` URL both fetches are run: the `html` skill (tweet prose)
AND `transcript-fetcher` (video). The written `_raw/<slug>.md` = the tweet text as a header
section followed by the video transcript as the body. Nothing is lost; neither branch is
short-circuited.

**Typed-error / FETCH_FAILED mapping and the no-media → html fallback.** The `_fetch_transcript()`
function maps transcript-fetcher exit codes into `FetchResult.error` using the same
`FetchResult(ok=False, engine="transcript:<origin>", error={…})` shape as `_fetch_html`/
`_fetch_pdf_url`. Key behaviours:

- **"No media" (transcript-fetcher exit 3 = "no transcript producible") — fallback is SCOPED BY
  HOST CLASS:**
  - on an **`ambiguous_x_status`** URL under `--video`, `_fetch_transcript` returns a typed
    no-media result → `dispatch_fetch` falls back to the existing `_fetch_html` path (mirrors the
    `arxiv_no_html` → pdf fallback). A misused `--video` flag degrades gracefully to the tweet prose.
  - on an **`unambiguous_video`** URL (YouTube/Vimeo/Broadcast/Space) exit 3 maps to
    **`FETCH_FAILED` (exit 10), NO html fallback** — there is no useful text path (html would return
    only the watch-page chrome this task removes). Note exit 3 conflates genuine no-media with
    "ASR produced nothing on real media"; on an unambiguous-video host both are a hard FETCH_FAILED.
  - No `_raw/` is written on an empty/failed result either way (R-3 holds).
- **Broadcast/Space with no ASR backend (exit 7)** — mapped to the `FETCH_FAILED` envelope with
  `DEP_MISSING` semantics (exit code 6), carrying an actionable "install ffmpeg + a whisper
  backend" message. No `_raw/` is written on failure (R-3). The `--transcript-bin` flag enables
  fail-fast absent-binary detection via the existing `require_bin()` helper.
- **Login-walled video** — surfaces the same cookies guidance as the existing `_is_x_login_wall`
  check; suggests `--cookies-from-browser` / `--cookies-file`.
- **`quality_flag: english_auto_translation`** — surfaced to the operator in the prepare envelope
  AND recorded in the note frontmatter provenance. This is a hard rule of the transcript-fetcher
  skill.

**Provenance.**

- `FetchResult.engine` is set to `transcript:<origin>`.
- As shipped (S0 contract verification against the real transcript-fetcher source):
  `transcript_origin` is set ONLY by the X adapter, so for youtube/vimeo/skool the origin falls
  back to the stat's `chosen_track_kind` (+`asr_backend` for ASR) — e.g.
  `transcript:embedded-captions` / `transcript:auto`.
- wiki-import ALWAYS passes `--with-description` (so the stat carries `title`/`uploader`/`upload_date`)
  and `--lang <vault-language>` (never the skill's `ru` default).
- The `.txt` output carries no frontmatter, so the existing `ensure_source_frontmatter()` function
  — which already handles the PDF/text-dump no-FM case — injects the `source:` field without any new code.
- The `<out>.txt.stat.json` sidecar + exit-code map (transcript 7→DEP_MISSING exit 6 ·
  6=rate-limit→FETCH_FAILED · 5=auth→cookies hint · 3=no-media) were pinned against the real source
  (resolves Q-044-2).

**Content-type axis stays orthogonal (Decision-17 + `_detect.py` unaffected).** `--kind`
detection in `_detect.py` is unchanged: a transcript body with timestamps/speaker-turns heuristically
maps to `kind=meeting`; the operator may override `--kind`. The one universal `summarizing-meetings`
harness handles all kinds — no new `kind` is introduced. The routing decision in `dispatch_fetch`
is deterministic (URL shape + `--video` flag), never an LLM guess.

**Path-dependent dependency posture.** Captioned YouTube/Vimeo/x-status-video need only `yt-dlp`
(light path). Caption-less broadcasts/spaces additionally need `ffmpeg` + a whisper backend (ASR
path). `ffmpeg` is REQUIRED for HLS sources; absent → exit 7 → `DEP_MISSING` envelope in
`dispatch_fetch`. No new entry in `requirements.txt` — `transcript-fetcher` is an external binary
(like `html`/`pdf`) loaded via `--transcript-bin` (or discovered via `require_bin()`), not a Python
runtime import. **Zero new Python runtime deps; zero SQLite DDL** (`user_version` 7 untouched).

**Invariants preserved.**

- Decision-17 (no `import anthropic`; deterministic routing).
- Class A/B/C layering (`_raw/` written only on a non-empty `ok` result, R-3).
- `validate_inside_vault` + H-6 frontmatter-injection guards on all write paths (R-26).
- Vendor-agnostic (subprocess + flags, runs identically under claude/codex/gemini/pi/hermes).
- Zero-DDL posture.

New CLI flags (`--video`, `--transcript-bin`, `--max-duration-min`, `--cookies-from-browser`,
`--cookies-file`, `--lang`) land in `__init__.py`/`__main__.py` and are passed through to
`dispatch_fetch`. Design residuals: Q-044-1.

## 2.3.3 Embedded-video discovery (opt-in `--embedded-videos` — TASK 044 R-13)

When the operator passes `--embedded-videos`, `dispatch_fetch` extends the `not_video` html path:
after the html skill fetches the page prose it also discovers, filters, and transcribes `<iframe>`
video embeds found in the raw HTML. The flag is **off by default** and is a **NO-OP** on
`unambiguous_video` and `ambiguous_x_status` URLs (those are `--video`'s domain). Passing both
`--video` and `--embedded-videos` on the same URL is a usage error (exit 2).

**Why raw-HTML scan, not html-skill output.** The html skill (`preprocess.py`) strips `<iframe>`
and `<video>` elements before emitting Markdown, and its `meta.json` sidecar carries no embed
URLs. Composing with the html skill's output is therefore impossible for embed discovery — the
raw page HTML must be read directly. Discovery uses a **single SIZE-CAPPED raw-HTML GET** (reuses
the `urllib` + browser-UA + byte-cap pattern of `_download_pdf`; cap constant
`_EMBED_FETCH_MAX_BYTES`, default 2 MB) followed by a bounded, anchored, ReDoS-safe regex scan
for video-embed URL patterns. The raw-HTML GET is the only additional network call; the html
skill's own fetch (which already ran for the article prose) is separate and unchanged. Design
rationale: Q-044-9 / Q-044-10.

**Filter chain — order is fixed and always applied in full when `--embedded-videos` is set.**

```
allowlist → ad-network denylist → ad-context → ad-param → dedup → cap → fetch
```

1. **Allowlist (H-6 / SSRF).** Only known video-host embed patterns pass:
   `youtube.com/embed`, `youtube-nocookie.com/embed`, `youtu.be`, `player.vimeo.com/video`,
   `vimeo.com`. Any `<iframe src>` not matching is silently dropped — the page cannot trigger a
   fetch to an arbitrary host. Residual SSRF surface (operator-trusted, allowlisted hosts only)
   is documented in `skills/wiki-import/SKILL.md` alongside the pdf residual.

2. **Ad-network host denylist (always-on belt-and-braces).** Drop any embed whose host matches
   a known ad-network domain: `doubleclick.net` (incl. `*.doubleclick.net`,
   `googleads.g.doubleclick.net`, `g.doubleclick.net`), `googlesyndication.com` (incl.
   `pagead2.googlesyndication.com`), `imasdk.googleapis.com` (Google IMA SDK), `2mdn.net`,
   `adnxs.com`, `adservice.google.*`. Most of these are already rejected at step 1 (outside the
   allowlist), but they are listed explicitly here as a belt-and-braces guard against
   youtube-hosted IMA/ad URLs that carry an allowlisted host but resolve to an ad endpoint.
   Logged as skip reason `ad-denylist`.

3. **Ad-context exclusion (always-on, bounded scan).** Skip any allowlisted embed whose
   ENCLOSING element (inspected within a **bounded character window** around each matched
   `<iframe>` — not a full DOM parse) carries class/id/data-* attributes that signal an ad or
   non-content slot. Word-boundary, case-insensitive match on:
   `ad`, `ads`, `advert`, `advertisement`, `advertising`, `sponsor`, `sponsored`, `promo`,
   `promoted`, `dfp`, `adsbygoogle`, `googlead`, `outbrain`, `taboola`, `recommend`, `related`,
   `widget`. Also excluded: embeds inside `<ins class="adsbygoogle">`, inside `<aside>`, inside
   `[role=complementary]`, and inside `[aria-hidden="true"]`. The scan uses a fixed-length
   character window and bounded-quantifier regex — no nested quantifiers, ReDoS-safe by
   construction (same posture as the layout-config load-gate). Logged as skip reason `ad-context`.

4. **YouTube ad-param drop (always-on).** Drop any youtube/youtube-nocookie embed URL carrying
   ad marker query parameters: `ad_type`, `adformat`, `ad_companion` (case-insensitive key match
   on the parsed query string). Logged as skip reason `ad-param`.

5. **Dedup.** The same embed URL appearing multiple times in the raw HTML is fetched once
   (set-based dedup applied after ad-exclusion, before cap). Logged as skip reason `dedup`.

6. **Cap (`--embedded-videos-max N`, default 5).** Applied after ad-exclusion and dedup, so
   ad embeds never consume cap slots. Embeds surviving filtering beyond N are dropped; a note
   naming the count dropped is appended to the prepare envelope's `details` list. Logged as
   skip reason `cap`.

7. **Fetch.** Each surviving embed URL is passed to the existing `_fetch_transcript()` function
   (reused without modification) with `--lang` always forwarded (R-11 invariant).

**Ad-exclusion is always-on — there is no flag to disable it.** When `--embedded-videos` is
active, the three ad-exclusion filters (steps 2–4) are unconditional. Advertising and promotional
embeds must never be transcribed; this is an operator hard requirement. The `--embedded-videos`
flag itself is the opt-in control; ad-exclusion has no separate toggle. Design rationale:
Q-044-11.

**Per-embed failure isolation (contrast §2.3.2's hard-fail).** A transcript failure for one
embed (exit 3 no-media / exit 7 dep-missing / exit 5 auth) is skipped with a logged note in the
envelope `details` and does NOT abort the page import — the article prose remains the primary
content and `_raw` is still written. This is the inverse of the `unambiguous_video` path in
§2.3.2, where exit 3 is a hard `FETCH_FAILED`: embedded videos are supplementary, not primary.

**Skip-reason logging — no silent behavior.** The prepare envelope's `details` MUST log every
discovered embed URL and the reason it was skipped or fetched. Skip reasons are exactly:
`ad-denylist` / `ad-context` / `ad-param` / `not-allowlisted` / `dedup` / `cap` /
`transcript-failure`. An embed that proceeds to fetch and fails is logged as
`transcript-failure`. No embed is silently dropped at any filtering stage.

**`_raw` assembly and provenance.** `_raw` = article prose (primary output of the html skill
fetch), with each successfully transcribed embed appended as a level-2 heading:
`## Embedded video <k> — <title or url>`. `FetchResult.engine = "html+embedded:<count_transcribed>"`,
where `count_transcribed` is the number of embeds that produced a transcript. `_raw` is written
only if the html result was ok and non-empty (R-3 invariant); embedded transcripts are strictly
additive. Each embed's `transcript_origin` is preserved in its heading; any `quality_flag`
(e.g. `english_auto_translation`) from any embed sidecar is aggregated and surfaced in the
prepare envelope per R-8.

**Reuse.** `_fetch_transcript()`, `_video_host()` (for allowlist matching), `require_bin`,
`ensure_source_frontmatter`, and `_fm_safe` are all reused without modification; no fetch or
parse logic is duplicated. Zero new Python runtime deps; zero SQLite DDL (`user_version` 7
untouched). `mypy --strict scripts/` clean; no `import anthropic` (Decision-17).

**Ad-exclusion residual.** Ad-exclusion is a heuristic — a sufficiently disguised embed (no ad
signal in class/id, allowlisted host, no ad query params) may slip through. The residual is
bounded by:

1. `--embedded-videos` is opt-in,
2. cap bounds total embed count,
3. per-embed failure isolation means a slipped-through ad that returns no transcript is logged harmlessly,
4. full skip-reason logging gives the operator visibility.

The residual and its boundary conditions are documented in `skills/wiki-import/SKILL.md`. Design
rationale: Q-044-11.

## 2.3.4 Converged construct pipeline — one engine, one batch driver (TASK 046)

Through TASK 039–044 **two** code paths owned *acquire + distil*: `wiki-import`
(fetch → article-`assemble_note` → always-concepts) **and** `wiki-sync` ingest
(convert/de-timestamp → `summarizing-meetings` pyramid → file/index → always-concepts).
The overlap was real (it is why a PARA transcript had no "rich pyramid, no concepts"
path). TASK 046 retires it by making **`wiki-import` the single per-source engine** and
**`wiki-sync` a pure batch driver that delegates to it** — the convergence §2.3 above
anticipated. **One owner per concern:**

| Concern | Single owner | Was duplicated? |
|---|---|---|
| acquire + normalize (any format → `_raw/<slug>.md`) | `wiki-import` `prepare` | ✅ → now ONE (absorbs `wiki-sync`'s office/`.vtt` convert) |
| distil (raw → summary note) | `wiki-import` REASON + `apply` | ✅ → now ONE (`apply` grammar by `--kind`: pyramid for meeting/lesson, article for article/paper/thread) |
| batch sweep + new/re-ingest decision | `wiki-sync` (`source_state`/`resummarize`/`--force`) | no |
| index one file | `wiki-index-upsert` (shared leaf) | no |
| concept filing | `wiki-extract-concepts` (shared leaf, `--concepts/--no-concepts` toggle) | no |

`wiki-import` gains FOUR knobs (also reachable per-zone via `.wiki/sync.yaml`
`summarize:` → flags):

1. **output-grammar by `--kind`** (adds `lesson`),
2. **`--diagrams`** (selective-mermaid overlay),
3. **`--concepts/--no-concepts`** (default ON = back-compat),
4. `prepare`'s **universal acquire** (docx/pptx/xlsx + `.vtt`/`.srt` + md, on top of url/pdf/video).

`wiki-sync` drops its inline summarise/enrich/extract and calls `wiki-import` per due source item
(ready notes → `wiki-index-upsert`; skips unchanged).

```mermaid
flowchart TD
    subgraph DRIVER["wiki-sync — batch driver (new / re-ingest)"]
        direction TB
        Z[scan zone] --> CLS{classify + decide<br/>source_state · resummarize · --force}
        CLS -->|ready note| UP[wiki-index-upsert]
        CLS -->|skip| SK[skip view/binary/unmappable]
        CLS -->|source, due| DEL[delegate per item<br/>flags ← .wiki/sync.yaml summarize:]
    end
    ONE[/"direct: /wiki-import one source"/] --> ENG
    DEL ==>|once per item| ENG
    subgraph ENG["wiki-import — per-source engine (ONE source)"]
        direction TB
        PREP["prepare: acquire+normalize → _raw/.md<br/>url · pdf · video · docx/pptx/xlsx · vtt · md"] --> REAS["REASON harness by --kind<br/>output-grammar: pyramid ∣ article"]
        REAS --> APP["apply: file layout-aware · provenance"]
    end
    APP --> IDXL[wiki-index-upsert]
    UP --> DB[("SQLite index")]
    IDXL --> DB
    APP -.concepts toggle.-> CEX[wiki-extract-concepts]
    classDef cli fill:#eef7ee,stroke:#5a5,color:#000;
    classDef store fill:#eee,stroke:#999,color:#000;
    class Z,DEL,UP,SK,PREP,REAS,APP,IDXL,CEX cli; class ONE,DB store;
```

**Invariants held:**

- Decision-17 (the REASON LLM step stays the orchestrator's, between `prepare` and `apply`;
  `wiki-sync scan` stays deterministic plan-only).
- zero-DDL (`summarize:` is file config; `user_version` 5).
- back-compat (concepts default ON; `--kind article` byte-identical; absent `summarize:` ≡ today's defaults).

(`wiki-enrich` — the legacy Karpathy on-ramp mentioned as a pending retirement here — was retired
in TASK 047.) Design rationale: Q-046-1.

## Legacy PARA-import framing (superseded §2.3 — TASK 038; retired TASK 047)

> **Superseded (TASK 047).** Retained for history; the retirement is recorded in §2.3 and §2.3.4 above.

**The baseline it started from.** The framework's Karpathy construct path is `wiki-enrich` → external
`wiki-ingest` → (Phase 2) `summarizing-meetings` → concept/entity wiring → index, whose
load-bearing discipline is *passing the known-concepts list to the summary generator* so
`[[wiki-links]]` reuse existing names and never dangle/collide. **PARA had no packaged
equivalent** — `wiki-ingest` writes Karpathy `_sources/` + root `_concepts/_entities/`,
wrong for PARA (TASK 024 finding #2).

**What this component added.** It packages the PARA path as a new **Decision-17** CLI (no
`import anthropic`; `prepare`/`apply`) plus a skill/command/workflow triple. It is **composition,
not reinvention** (NF-2):

- `prepare` shells out to the global `html` (URL/HTML — which post-2026-06-18 itself owns the
  Wikipedia-REST-HTML and arXiv-`/html/` rewrites + typed `EmptyExtraction`/`arxiv_no_html`) and
  the `pdf` skill (PDF), writes `_raw/<slug>.md` **only on a non-empty fetch**, and emits an
  envelope adding `known_concepts[]` + `existing_page_slugs[]` (sourced from the existing
  `wiki-extract-concepts` machinery).
- The orchestrator (LLM) owns translation/summary, **fed the known_concepts** (R-6, the core fix).
- `apply` is the authoring glue the DAO/#01 batches did by hand — per-mode note assembly
  (full/summary/thread), `_NAME_ALLOWLIST` name sanitization, verbatim-`source_quote` guarantee,
  and the **collision guard** (skip a candidate whose slug == the source note's own slug, or
  collides with an `existing_page_slugs` entry — so a generic `defi` concept never evicts the
  owner's `Defi.md`) — then delegates concept filing to `wiki-extract-concepts apply` and indexing
  to `wiki-index-upsert`/`wiki-reindex`.

**Two distinct hashes (do not conflate):**

- `prepare.source_hash = sha256(_raw bytes)` is for wiki-import-article's own import idempotency
  (R-7) only.
- the `--source-hash` fed to `wiki-extract-concepts apply` is a **fresh `sha256` of the
  just-written PARA note body** (apply re-resolves + re-hashes the *filed note* and rejects a
  mismatch as `SOURCE_CHANGED_DURING_EXTRACTION`), with the note's own slug as that call's
  `--source-page`.

**Sanitization + write-surface guards.** The name sanitizer is a **pre-normalizer that feeds** the
existing `_validation._sanitize_name` reject-gate (rewrite `/`/em-dash/guillemets → safe so
the candidate then passes that gate; reuses its `_NAME_ALLOWLIST`, no duplicate). All write
surfaces (`_raw/`, note, concept pages) route through `validate_inside_vault` (R-26) +
`_is_valid_slug` (a hostile fetched title cannot traverse). For the assembled note body:

- YAML frontmatter scalars (title/URL/author/published/tldr) are newline/control-stripped and
  quoted (H-6 frontmatter-injection guard).
- the note BODY is orchestrator-authored markdown, kept structural (escaping a translation's
  headings/lists would defeat the purpose — same trust posture as `wiki-ingest`/`summarizing-meetings`
  summaries).
- the generated **concept pages** are markdown-sanitized by extract-concepts' `write_concept_page`
  (`_sanitize_markdown_text`).

**Dependency + surface impact.** The `html`/`pdf` shell-outs are external skill **binaries**
(configurable `--*-bin`, fail-fast if absent) — NOT Python runtime dependencies, so NF-1
"zero new deps" holds. Zero impact on §4 Data Model (no DDL — rides
`pages`/`entities`/`page_entity_refs`), §6 Stack (no deps). §5 Interfaces gains ONE new CLI
surface (`wiki-import-article prepare|apply` + envelopes). Batch import (the DAO/#01 pattern)
stays a documented **Workflow-tool recipe** in `workflows/wiki-import-article.md` (parallel
translation; serialized DB writes), not a CLI mode.

**Skill-call flow diagrams (Karpathy vs PARA, mermaid)** are in §2.3 above.
Design rationale: open-questions Q-038-*.
