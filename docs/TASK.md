# TASK 018 — `wiki-sync`: format-aware, tag-routed ingest/upsert dispatcher (R-11)

### 0. Meta Information
- **Task ID:** 018
- **Slug:** `wiki-sync`
- **Mode:** VDD (full pipeline — `/vdd-start-feature`)
- **Status:** ✅ **SHIPPED 2026-06-03** (uncommitted on branch `task-018-wiki-sync`).
  All 17 beads (018-00..16) merged + green; full VDD pipeline + `/vdd-multi`
  3-critic convergence (Logic ✓ Security ✓ Performance ✓). **986 pytest (+4
  skipped), mypy strict (72 files)**, zero DDL (`user_version` 5), no `anthropic`
  import. Shipped surface = `wiki-sync scan` + `wiki-sync record` +
  `workflows/wiki-sync.md` + `skills/wiki-sync/SKILL.md` + `config/sync-config.schema.yaml`
  + 2 generic `source_state` DAL methods. See `docs/PLAN.md`, `docs/tasks/task-018-*.md`,
  `docs/reviews/`.
- **Source:** ROADMAP **R-11** (`docs/ROADMAP.md` → P1 — Epic 7 entry-point) + the
  *Mixed vault* section of `docs/manuals/obsidian-llm-wiki_manual.md`.
- **First-cut scope (operator decision 2026-06-03):** **Full R-11** — all three
  layers, *including* the office/PDF→md conversion front-stage.
- **Predecessor:** TASK 017 (`drift-delta-redos-timeout`) — archived in lockstep to
  `docs/tasks/task-017-*.md` + `docs/plans/plan-017-*.md`.

---

### 1. Problem Description

The static layout engine (R-X1) classifies vault files **by path** and only
*indexes* the `.md` that already exists. A real, mixed personal vault needs more:
the operator drops **heterogeneous sources** into "collection" folders (course /
webinar / clippings zones) — transcripts (`.txt`/`.vtt`/`.srt`), office docs and
PDFs, already-distilled notes, and Obsidian **generated-view sidecars** (DB Folder
/ Bases / Dataview / folder-notes) — and wants each file **auto-routed** to the
right action:

- **convert → ingest** (office/PDF → md → distil),
- **ingest** (raw text → distil into compounding `_sources/_concepts/_entities`),
- **upsert** (a ready note → index as-is),
- **skip** (a generated-view sidecar / draft / binary).

This is the automation that closes Karpathy's **3 → 10–15 pages-per-ingest** gap on
a real vault, without the operator hand-invoking `wiki-enrich` / `wiki-index-upsert`
per file. `wiki-sync` is that **format-aware + content-aware dispatcher**, layered
over the existing idempotent CLIs.

### 1.1 Grounding facts (verified 2026-06-03 — anti-hallucination anchors)

These constrain the design and are **not** to be re-litigated by implementation:

1. **Vendored `wiki-ingest` (`scripts/wiki_ingest/commands/ingest.py`) is
   *summary-passthrough* in v1.1** — given a raw source it returns
   `phase="needs-pre-summarization"` pointing at the `summarizing-meetings` skill;
   it does **not** LLM-summarise in-process (this repo has no `anthropic` dep).
   ⇒ the `raw → ingest` path is **inherently orchestrator-coupled** (the LLM
   summarisation/extraction step lives in the calling agent). ⇒ `wiki-sync` MUST be
   **Decision-17 shaped**: a deterministic classify/plan half + an
   orchestrator-executed action half (same pattern as `wiki-query` /
   `wiki-extract-concepts`). **No `import anthropic` in `wiki-sync`.**
2. **Existing primitives to build on (don't reinvent):** vendored
   `wiki_ingest/commands/classify_folder.py` (Phase-0 folder role-classifier:
   grouping + primary/metadata/merge/link/derived-output/skip), `scan.py`,
   `register_summary.py`; this repo's `wiki-enrich`, `wiki-index-upsert`,
   `wiki-extract-concepts` (all idempotent via `source_state`/file-hash); the R-X1
   layout engine + the multi-vault *search-only + enrich-zone* split.
3. **Conversion capability exists:** harness `docx`/`pdf`/`pptx`/`xlsx` convert
   skills + Universal-skills converter scripts (pdf→md task-013, xlsx2md task-012,
   docx). **PDF-OCR is a known upstream gap** (Universal-skills task-013 OCR block
   unfinished) — `wiki-sync` must **flag** image-only/empty-text PDFs as
   `needs-ocr`, never silently drop.
4. **Zero DDL expected** (`user_version` stays **5**): reuse `source_state` for
   idempotency; `wiki-sync` produces no new page type.

---

### 2. Requirements Traceability Matrix (Epics → Issues)

> **MVP?** = in this task's first cut (operator chose **Full R-11**, so all four
> Epics are in-scope). "MVP" here marks the *thin vertical slice* proven first
> under Stub-First; non-MVP rows are same-task hardening.

#### Epic E1 — Format front-stage (route by extension, before indexing)
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E1.1 | Extension classifier | ✅ | (a) ext→{convert, ingest-text, md-route, skip-binary} map, **case-insensitive** (`.PDF`/`.Md`; EC-6); (b) configurable extra extensions; (c) unknown-ext → `skip` + reason; (d) `.excalidraw.md`/`.canvas` → `skip` (drawing, not prose) |
| E1.2 | Office/PDF → md conversion dispatch | ✅ | (a) plan emits `convert` step naming the converter per ext (docx/xlsx/pptx/pdf); (b) converted md lands at a deterministic in-vault staging path (e.g. `_raw/`); (c) orchestrator executes via convert skill; (d) conversion is deterministic (~0 LLM tokens) |
| E1.3 | Plain-text source handling (`.txt`/`.vtt`/`.srt`) | ✅ | (a) treated as **implicit raw** (no tag needed); (b) `.vtt`/`.srt` de-timestamp/caption-dedup normalisation pass; (c) encoding-safe read (bounded size) |
| E1.4 | PDF-OCR gap handling | ☐ | (a) detect image-only / empty-text-layer PDF; (b) flag `needs-ocr` in the plan with reason; (c) never silently drop; (d) text-layer PDFs still convert |

#### Epic E2 — Content classifier (the routing brain)
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E2.1 | Tag vocabulary (`wiki/` namespace) | ✅ | (a) parse `#wiki/raw`, `#wiki/skip`, `#wiki/keep` from frontmatter tags; (b) `_raw/` path ≡ implicit `#wiki/raw`; (c) `#wiki/skip` is the always-wins manual override |
| E2.2 | Generated-view sidecar detection → skip | ✅ | (a) DB Folder (`database-plugin:` frontmatter and/or ` ```yaml:dbfolder ` body); (b) Bases (` ```base ` body or `.base` companion); (c) Dataview (` ```dataview(js) ` body); (d) folder-note (stem == parent/sibling dir); (e) matched marker recorded as the skip `reason`; (f) **only-a-view guard (anti-over-flag)**: skip only when the body is *only/essentially* one view block (modulo frontmatter) — a content note that merely *embeds* a view block alongside prose is **NOT** skipped |
| E2.3 | Default `.md` routing rules | ✅ | (a) no wiki-tag + **layout-mappable `type:`** → `upsert`; **no-tag + unmappable type → `skip` reason `unmappable-type`** (flagged — `wiki-index-upsert` raises `UnmappedTypeError` on a type-less prose note, so "as-is" upsert is NOT free; EC-2); (b) `#wiki/raw`/`_raw/` → `ingest`; (c) `#wiki/skip`/sidecar → `skip`; (d) `#wiki/keep` → opt-in inside a default-excluded zone (rescues from the `exclude:` skip; action then per raw/type); (e) empty file → `skip:empty-source`; unparseable frontmatter → route-by-path, never raise (EC-7) |
| E2.4 | Reuse/extend vendored `classify_folder`/`scan` | ☐ | (a) decide reuse-vs-new in Architecture (OQ-2); (b) no behavioural regression to vendored callers; (c) shared helpers, acyclic imports |

#### Epic E3 — Dispatcher: deterministic plan + orchestrated execution (Decision-17)
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E3.1 | `wiki-sync` deterministic scan/plan | ✅ | (a) walk the configured zone(s); (b) classify each file (E1+E2); (c) emit **strict plan JSON** (per file: `action` ∈ {convert+ingest, ingest, upsert, skip}, `reason`, `converter`, `staged_target`, `normalize`, `source_hash`, `is_unchanged`); entries **sorted by vault-relative POSIX path** (determinism, AC-10); (d) **no LLM, no network**; (e) **its OWN bounded walk** mirroring `iter_pages`' single-stat + **case-folded** early-extension-skip discipline — NOT `iter_pages` reuse (`iter_pages` is `.md`-only; EC-1/ID-5); **excludes `_raw/.staging/**`, `_raw/.locks`, `_raw/failed`** so converter outputs are never re-ingested (RG-1/W-3); scan reads every eligible file to hash it (bounded — scoped zones; W-2) |
| E3.2 | Orchestrated execution (workflow) | ✅ | (a) `convert` → convert skill → collision-safe **`_raw/.staging/<slug(stem)>-<ext>.md`** (non-walked); (b) `ingest` → `[.vtt/.srt]` de-timestamp pre-step → **H-6 fence the body** → summarise (`summarizing-meetings`) → `wiki-enrich --source <summary>` → `wiki-extract-concepts`; (c) `upsert` → `wiki-index-upsert`; (d) `skip` → no-op; (e) per-file isolation (one failure ≠ batch crash); (f) on full per-file success → write the `sync` idempotency row (commit marker); (g) per-vault advisory `flock` (`LOCK_NB` → exit 2 `SYNC_IN_PROGRESS`) during execute |
| E3.3 | Idempotency + dry-run + report | ✅ | (a) skip already-processed via the **`wiki-sync`-owned `source_state` partition** (`source_kind='sync'`, scope=`<vault-relative path>`, `key='source_hash'`) read by scan, written by the executor on success — NOT the chain's own footer/extract keys (those aren't raw-keyed; CRITICAL cluster); (b) `--dry-run` writes nothing (reads `source_state` read-only); (c) per-file report (action, reason, result; lists every skip + reason — no silent truncation); (d) re-run is a no-op; partial-failure resumes (no commit marker) |
| E3.4 | JSON-envelope + exit-code contract | ✅ | (a) one-line JSON envelopes; (b) stable error codes; (c) consistent with existing CLIs (0 ok / 2 precondition / 4 contract / 6 validation); (d) two new generic zero-DDL DAL methods `get_source_state`/`set_source_state` (the earlier "no new DAL surface" claim was wrong) |

#### Epic E4 — Config, safety & UX
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E4.1 | Per-vault sync config | ✅ | (a) declare enrich zones + default-excluded folders (e.g. `_daily`); (b) home = WIKI_SCHEMA frontmatter ∥ `.wiki/sync.yaml` (OQ-4); (c) tag-namespace overridable |
| E4.2 | Dry-run plan report | ✅ | (a) human-readable per-file plan; (b) counts by action; (c) explicit "what was skipped and why" (no silent truncation) |
| E4.3 | Untrusted-input safety | ✅ | (a) **H-6**: raw/converted content is *data, not instructions*; (b) path-traversal validation on discovered + converted paths (inside vault); (c) converted output written atomically inside the vault; (d) no execution of file content |
| E4.4 | Explicit out-of-scope guards | ☐ | (a) binary-attachment indexing at scale → not handled, logged; (b) daily-note block-dedup → not handled; (c) PDF-OCR completion → upstream (Universal-skills), flagged not done |

---

### 3. Use Cases

**Actors:** *Operator* (human), *Orchestrator* (the calling LLM agent — Claude Code
/ Gemini / etc.), *wiki-sync* (deterministic CLI), *convert skills*, *existing
wiki-* CLIs* (System actors).

#### UC-1 — Transcript dropped into a webinar zone (main scenario)
- **Preconditions:** an enrich-zone vault (karpathy) registered; `wiki-sync` on PATH;
  the `summarizing-meetings` + `wiki-extract-concepts` skills loadable.
- **Main scenario:** Operator drops `ai-hard-fork.vtt` into `…/Webinars/_raw/` (or
  tags a note `#wiki/raw`) → runs `/wiki-sync` on the zone → `wiki-sync` scan
  classifies it `ingest` (text source; `.vtt` de-timestamped) → Orchestrator
  summarises → files `_sources/<slug>.md` → `wiki-extract-concepts` builds
  concept/entity pages → compounding pages appear, FTS-searchable.
- **Postconditions:** new `_sources/` + `_concepts/` + `_entities/` pages indexed;
  `source_state` records the hash. **Re-running `/wiki-sync` is a no-op.**
- **Acceptance:** AC-1, AC-3, AC-5, AC-8.

#### UC-2 — Office / PDF sources
- **Main scenario:** Operator drops `slides.pdf` + `report.docx` → scan plans
  `convert+ingest` naming the pdf/docx converter → Orchestrator converts to md
  (staging) → ingest path as UC-1.
- **Alternative (PDF-OCR gap):** an image-only `scan.pdf` has no text layer →
  classified `needs-ocr` with reason; reported to operator; **not dropped**, **not**
  crashing the batch.
- **Acceptance:** AC-3, AC-7 (no silent drop), AC-9.

#### UC-3 — Mixed course folder (ready notes + sidecar + draft)
- **Main scenario:** a folder holds a ready summary (no tag), a DB Folder sidecar
  (`database-plugin:` / ` ```yaml:dbfolder `), and a `#wiki/skip` draft → scan:
  ready → `upsert`, sidecar → `skip` (reason: `db-folder-view`), draft → `skip`
  (reason: `#wiki/skip`).
- **Alternative (anti-over-flag):** a real content note that *embeds* a `dataview`
  block alongside prose → classified `upsert` (the only-a-view guard, E2.2f), **not**
  skipped.
- **Acceptance:** AC-2, AC-2b, AC-4.

#### UC-4 — Dry-run (alternative)
- **Main scenario:** Operator runs `wiki-sync scan <zone> --dry-run` → emits the plan
  + per-file action/reason; **writes nothing** to vault or DB.
- **Acceptance:** AC-1, AC-6.

#### UC-5 — Per-file failure isolation (error scenario)
- **Main scenario:** one file is oversize / unconvertible / `needs-ocr` → flagged in
  the plan with a reason; the remaining files still process; the report lists the
  flagged file. **The batch never aborts wholesale.**
- **Acceptance:** AC-7, AC-9.

#### UC-6 — Empty / no-eligible-files zone (edge)
- **Main scenario:** `wiki-sync` is run on a zone with no eligible files (all
  skipped / empty) → emits an **empty plan**, exit 0, report says "0 actions".
- **Acceptance:** AC-1, AC-6.

---

### 4. Acceptance Criteria (binary, verifiable)

- **AC-1** — `wiki-sync` scan/plan emits **valid plan JSON**; every file carries
  `action` + `reason`; the scan is **deterministic** (no LLM, no network) and
  idempotent (same inputs → same plan).
- **AC-2** — Generated-view sidecars are classified `skip` with the matched marker
  as `reason`; a **fixture using the operator's real `yaml:dbfolder` sample**
  (+ Bases, Dataview, folder-note fixtures) all skip.
- **AC-2b** (negative / anti-over-flag) — a content note that merely **embeds** a
  `dataview`/`base` block alongside real prose is classified **`upsert`, NOT
  `skip`** (the only-a-view guard, E2.2f); fixture-tested.
- **AC-3** — Extension routing: `.txt`/`.vtt`/`.srt` → `ingest`(text);
  `.docx`/`.xlsx`/`.pptx`/`.pdf` → `convert+ingest`; `.md` → tag-rules;
  images/other binary → `skip`.
- **AC-4** — Tag routing: `#wiki/raw`(or `_raw/`) → `ingest`; no-tag `.md` →
  `upsert`; `#wiki/skip` → `skip`; `#wiki/keep` → opt-in in a default-excluded zone.
- **AC-5** — End-to-end on a sample zone: a `.vtt` becomes a compounding `_sources/`
  page + concept/entity pages via the orchestrated flow; **re-run is a no-op**.
- **AC-6** — `--dry-run` writes nothing (vault + DB unchanged, asserted) and prints
  a per-file plan report with action counts.
- **AC-7** — Safety: discovered + converted paths validated inside the vault root;
  file content treated as data (H-6 banner honoured); **no silent drops**
  (`needs-ocr`/unconvertible/oversize are flagged with reasons); per-file isolation.
- **AC-8** — **Zero DDL** (`user_version` 5); idempotency via the `wiki-sync`-owned
  `source_state` partition (`source_kind='sync'`, scope=path, `source_hash`); the
  only new code surface is two generic `get_source_state`/`set_source_state` DAL
  methods (pure DML on the existing table).
- **AC-9** — Full test suite green + `mypy --strict` clean; `wiki-sync` carries
  **no `import anthropic`**; JSON-envelope/exit-code contract matches existing CLIs.
- **AC-10** (determinism, META-1) — two scans of an untouched zone emit
  **byte-identical** plan JSON; `entries[]` sorted by vault-relative POSIX path
  (no timestamp in the core).
- **AC-11** (degenerate inputs never crash, EC-7) — an empty/zero-byte file →
  `skip:empty-source`; a file with unparseable frontmatter → routed by path with
  `frontmatter-unparseable`, **never** an unhandled exception; fixture-tested.
- **AC-12** (upsert feasibility + staging safety, EC-2/SEC-A4) — a no-tag prose `.md`
  **without** a layout-mapped `type:` → `skip:unmappable-type` (not an
  `UnmappedTypeError` crash); two convert sources sharing a stem produce **distinct**
  `_raw/.staging/<slug(stem)>-<ext>.md` targets and never silently clobber.
- **AC-14** (convert+ingest convergence, RG-1/W-3) — running `wiki-sync` twice over a
  zone containing an office/PDF source is a **no-op on the second run**: the staged
  `_raw/.staging/…` output is **not** re-discovered/re-summarised (it lives in the
  non-walked `.staging/` subdir); fixture-tested.
- **AC-13** (report completeness, META-3/E4.2) — the run report lists **every**
  non-processed file with its reason (binary / sidecar / `#wiki/skip` /
  excluded-zone / `unmappable-type` / `empty-source` / `needs-ocr`) + action counts;
  no silent truncation.

---

### 5. Open Questions (for the Architecture phase)

- **OQ-1 (shape, near-decided):** Confirm the **Decision-17 split** — deterministic
  `wiki-sync` scan→plan + an orchestrator workflow that executes convert/ingest/
  upsert/skip. (Grounding fact #1 makes this all-but-forced; Architecture to lock
  the subcommand surface, e.g. `scan`/`plan` vs `prepare`/`apply`.)
- **OQ-2 (reuse):** Reuse/extend the vendored `classify_folder`/`scan` classifier vs
  a new `scripts/wiki_skills/_sync` module — without regressing vendored callers and
  keeping imports acyclic.
- **OQ-3 (conversion):** Call the **harness** `docx`/`pdf`/`pptx`/`xlsx` skills vs
  the **Universal-skills** converter scripts; the deterministic staging path for
  converted md (`_raw/`?); how the plan tells the orchestrator *which* converter.
- **OQ-4 (config home):** WIKI_SCHEMA frontmatter vs `.wiki/sync.yaml`; how enrich
  zones + default-excluded folders (`_daily`) + tag-namespace are declared.
- **OQ-5 (raw→ingest chain):** canonical composition for `ingest` — `summarizing-
  meetings` → `register-summary` + `wiki-extract-concepts`, vs `wiki-enrich` (which
  needs a pre-made summary). Lock the exact step order.
- **OQ-6 (PDF-OCR):** flag `needs-ocr` + defer (recommended), vs attempt text-layer
  extraction only; coordination with the upstream Universal-skills OCR block.
- **OQ-7 (tag surface):** `#wiki/raw` tags only, vs also a frontmatter field
  (`wiki: raw`); precedence rules.

---

### 6. Out of scope (this task)

- Indexing binary attachments at scale (6000+ images/office files) — flagged, not
  handled.
- Dedup of repeated blocks across `_daily/` notes.
- **PDF-OCR completion** — lives upstream in Universal-skills; `wiki-sync` only
  *flags* `needs-ocr`.
- Cross-vault entity-graph traversals (R-X5).
