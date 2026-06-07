# TASK 019 — `wiki-sync` re-summarization policy: skip-if-summarized + `--force` + per-folder rule overrides

### 0. Meta Information
- **Task ID:** 019
- **Slug:** `sync-resummarize-policy`
- **Mode:** VDD (full pipeline — `/vdd-start-feature`)
- **Status:** ✅ **SHIPPED 2026-06-07** (uncommitted). Full VDD pipeline — task/arch/plan
  reviews APPROVED → 10 beads Stub-First green-throughout (`skill-tdd-strict` on the
  back-compat / DAL / gate-monotonicity / ReDoS beads) → **`/vdd-multi` converged**
  (Logic ✓ Security ✓ Performance ✓; iter-1 found 2 HIGH perf + 1 MED sec + 2 MED/3 LOW
  logic, iter-2 verified all fixed + 1 security DiD). **1039 pytest (+4 skipped), mypy
  strict (73 files)**, **zero DDL** (`user_version` 5), **no `import anthropic`**.
  Implementation notes / deviations vs the as-planned design: (a) `resolve_policy` takes
  `(path, *, vault_root, caches)` (not `vault_config`) — the cascade must deep-merge the
  RAW dicts to honor partial overrides, so it re-reads each level incl. the root;
  (b) D2a hoists a **second** read-only DAL method `all_cited_sources` (bulk citation set
  per scan) alongside `find_pages_citing_source` (vdd-multi PERF — N+1→O(P+R));
  (c) D2b builds a **once-per-scope** summary-key index + a ReDoS **load-gate**
  (`is_pattern_redos_safe`), beyond the per-file deadline (vdd-multi PERF/SEC). See
  `docs/reviews/{task,architecture,plan}-019-review.md` + the `/vdd-multi` convergence.
- **Post-ship dogfood hardening (2026-06-08).** Full end-to-end dogfood on the operator's
  real `samples/Demand-generation` course vault (6 modules + Lessons, 159 files) + a
  14-agent adversarial verification workflow: the gate is **correct on real data, zero
  data-loss** (all 88 skips cross-checked to a real covering summary; the only 3 `ingest`
  entries are genuinely-uncovered `08-*` lessons). The dogfood surfaced two issues, **both
  fixed here**: (1) a **silent dead mirror detector** — a misconfigured `group_key` (e.g. a
  YAML double-backslash `'^(\\d+)'`) that keys nothing left D2b inert with no signal →
  `_scope_key_index` now WARNs "mirror keyed 0 of N summaries … likely a misconfigured
  pattern"; (2) **`ignore` now UNIONs** (not replaces) the base layout's exclusions on a
  per-vault `.wiki/layout.yaml` override (`layout_config.load_layout_config`), making the
  `wiki-init` templates' "extend `ignore`" guidance true. **1041 pytest (+4 skipped), mypy
  strict.** (Also confirmed by the dogfood: `wiki-reindex` SILENTLY drops a page on an
  intra-project slug collision — a separate TASK-012 indexing gap, documented in
  `docs/ARCHITECTURE.md` §11a Q-019-11, **not** fixed here.)
- **Source:** Operator request 2026-06-07 — "пересуммаризацию делать только если
  `--force` указан или сама суммаризация отсутствует"; detection rules + per-folder
  overrides declared **in YAML**.
- **Builds on / Predecessor:** TASK 018 (`wiki-sync`, SHIPPED 2026-06-03) — archived in
  lockstep to `docs/tasks/task-018-wiki-sync.md` + `docs/plans/plan-018-wiki-sync.md`.
  This task extends the **same** deterministic `scan` half; it does **not** touch the
  Decision-17 orchestrator contract.

---

### 1. Problem Description

`wiki-sync scan` routes every **raw source** (`.vtt`/`.txt`/`.srt` → `ingest`;
`.docx`/`.xlsx`/`.pptx`/`.pdf` → `convert+ingest`; a `#wiki/raw` `.md` → `ingest`) to
re-distillation. The **only** thing that makes a re-run a no-op today is the
`wiki-sync`-owned `source_state` hash marker (`source_kind='sync'`): `scan` sets
`is_unchanged` when `sha256(bytes)` matches a recorded marker, and the executor skips it.

Two gaps versus the operator's intended idempotency model ("kept current, not
re-derived"):

1. **No `--force`.** There is no way to *deliberately* re-summarize (e.g. after the
   summariser prompt improved). The argparse for `scan` has no such flag (verified).
2. **"Already summarized" is too narrow.** It is known **only** when `wiki-sync` itself
   recorded the ingest. Summaries authored **outside** `wiki-sync` — manually, or before
   adopting the tool — carry **no** `source_state` marker. So the **first** `scan`
   re-ingests them (re-summarization): wasted LLM tokens, and a real risk of producing
   duplicate / overwriting compounding pages. This is exactly the operator's situation:
   raw transcripts kept **"for history"** beside **already-generated** summaries.

**Desired rule.** A raw source is planned as `ingest` / `convert+ingest` **only if**:
- `--force` is given, **OR**
- **no summary exists** for it.

"Summary exists" is decided by **configurable detectors** (union of three), declared in
**YAML**, set **vault-globally** and **overridable per-folder** (a specific course can
deviate from the vault default).

> This **supersedes the `_transcripts/` `exclude:` workaround** explored earlier: instead
> of *hiding* raw dirs from the walk, `wiki-sync` *scans* them and the policy decides
> "skip — a summary already exists." `exclude:` is reserved for "never even look."

### 1.1 Grounding facts (verified 2026-06-07 — anti-hallucination anchors)

Not to be re-litigated by implementation:

1. **Current scan idempotency** — `source_hash = sha256(bytes)`; `is_unchanged =
   source_hash is not None and get_source_state(vault,'sync',rel,'source_hash') ==
   source_hash` (`scripts/wiki_skills/wiki_sync.py:165`). Executor skips `is_unchanged`.
2. **No `--force`** in `scan` argparse (`scan` has `zone`, `--vault`, `--vault-root`,
   `--dry-run`, `--db-path`).
3. **Extension front-stage wins early** — `.vtt/.txt/.srt` → `ingest` by extension
   **before** the tag/`_raw/` logic; a **nested** `_raw/` is NOT implicit-raw (only the
   vault-root `_raw/` is). ⇒ today the *only* freeze lever is `exclude:` (proven on code).
3a. The classifier’s verdict for raw sources lives in `_sync.classify_file` /
   `_classify_md`; `is_unchanged` is computed one layer up in `wiki_sync._build_entries`.
   The new policy gate sits **between** classification and the plan entry (it can only
   ever turn an `ingest`/`convert+ingest` into a `skip`, never the reverse).
4. **Frontmatter is queryable** — pages store `frontmatter_json`; TASK 013 added a
   parameterized `CAST(json_extract(frontmatter_json, ?) AS TEXT) = ?` filter. ⇒ a
   provenance-ref lookup ("is there a page whose `source:` points at this raw file?") is
   feasible with **zero DDL**.
5. **`sync-config.schema.yaml` is STRICT** (`additionalProperties: false`); a new
   `resummarize:` block must be an **opt-in `$def`**, and its **absence ≡ today's
   behavior** (back-compat). The loader is hardened (256 KiB cap + anchor-ban SafeLoader)
   and **never echoes** offending values (CWE-209/CWE-117) — the override files inherit
   this posture.
6. **Layered-config precedent exists** — `.wiki/layout.yaml` deep-merges over the
   built-in layout (lists *replace*); `config_loader` walks **up** for a `.wiki.yaml`
   project override. **Zero DDL expected** (`user_version` stays **5**); **no
   `import anthropic`**.
7. **ReDoS-guard infra exists (reuse, don't reinvent)** — TASK 017 / R-X1-REDOS-RT added
   operator-regex guarding in `layout_config.py`: the PyPI `regex` engine with a per-call
   `timeout=`, a load-gate (`_redos_budget_check` over an adversarial payload), and
   `WIKI_REDOS_BUDGET_S`. The mirror `key.raw_regex`/`key.summary_regex` are a **new
   operator-supplied regex surface** ⇒ they MUST run under the same guard (load-gate at
   config parse + per-file deadline at match; on timeout → report-and-skip, never hang).

---

### 2. Requirements Traceability Matrix (Epics → Issues)

> **MVP?** marks the thin vertical slice proven first under Stub-First. `☐` rows are
> same-task hardening.

#### Epic E1 — Re-summarization policy (the decision rule)
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E1.1 | `--force` on `wiki-sync scan` | ✅ | (a) re-plans raw sources as actionable, **bypassing all detectors**; (b) scoped to the whole scan run (not per-file — OQ-6); (c) plan entry `reason="forced"`; (d) flag absent → default policy applies |
| E1.2 | `mode` policy | ✅ | (a) `if-missing` (**default**) — ingest a raw source only if NO summary detected; (b) `always` — re-summarize every run; (c) `never` — never auto-ingest raw (manual only) → `skip:resummarize-never`; (d) applies to actions `ingest` + `convert+ingest` ONLY (never to `upsert`/`skip`) |
| E1.3 | Skip-reason taxonomy | ✅ | (a) `summary-exists:source_state` / `:provenance` / `:mirror`; (b) recorded in the plan entry `reason`; (c) counted in the dry-run report; (d) **no silent skip** (every gated file listed with its reason) |

#### Epic E2 — "Summary exists" detectors (D1 ∪ D2)
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E2.1 | **D1** — `source_state` marker | ✅ | (a) an existing `sync` hash marker ⇒ summary exists; (b) toggle `detect.source_state`; (c) **default on** (preserves TASK 018 behavior) |
| E2.2 | **D2a** — provenance-ref | ✅ | (a) a page's frontmatter `source:`/`sources:` points at the raw file ⇒ exists — the **authoritative, precise** signal (no key-guessing); (b) match by **vault-rel path** (DECIDED — OQ-3); **N:1 via list-valued `sources:`** (raw covered if its rel-path ∈ any summary's `sources` list); (c) DAL query over `frontmatter_json` (zero DDL); (d) configurable field list (`source`/`sources`); (e) **index-currency dependency** — D2a sees only *indexed* pages, so a summary not yet `wiki-reindex`-ed is invisible → **D2b (mirror) is the index-independent fallback**, union-combined; (f) **back-ref writeback** — when the executor *generates* a summary from N raw sources it **writes `sources: [<raw rel-paths>]`** into that summary's frontmatter, so every subsequent run detects via the exact D2a signal (mirror is then only the fallback for legacy/manual summaries lacking back-refs) |
| E2.3 | **D2b** — structural mirror | ✅ | (a) raw file under a **configurable** `raw_dirs` ancestor (default `_raw`/`_transcripts`; operator's case `Transcripts` — names are illustrative); (b) summaries in a **sibling** `summary_dir` (default `_summary`; e.g. `Summary`), `summary_ext` default `.md`; (c) **two match strategies**: `stem-relpath` (1:1) and **`group-key` (N:1)**; (d) **extended regex key extraction** — a `key:` block with **separate** `raw_regex` + `summary_regex` (Python **named groups**), composed via a `template` (e.g. `${module}-${lesson}`), plus `flags` (`ignorecase`/`unicode`); a one-line `group_key` is shorthand applying one regex to both sides; default `^(\d+)`; a raw is "covered" iff some summary in the sibling `summary_dir` yields the **same composed key**; (e) **operator regexes are ReDoS-guarded** — reuse TASK 017 / R-X1-REDOS-RT (`regex` engine + load-gate `_redos_budget_check` + per-file deadline; report-and-skip on timeout); (f) pure FS check (**index-independent** → works for not-yet-reindexed corpora) |
| E2.4 | Combination semantics | ✅ | (a) "summary exists" = **ANY** enabled detector matches (union); (b) each detector independently toggleable; (c) all-off + `if-missing` ⇒ always ingest (degenerate, documented, warned) |

#### Epic E3 — YAML config surface + per-folder overrides
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E3.1 | Vault-global `resummarize` block | ✅ | (a) new strict `$def Resummarize` in `config/sync-config.schema.yaml`; (b) **optional** → absent = today's behavior; (c) validation errors never echo file content |
| E3.2 | **Per-folder rule override** | ✅ | (a) a subtree may override `mode` and/or any `detect.*` for files **under** it; (b) **mechanism = Option A (cascade), DECIDED 2026-06-07** — a `<folder>/.wiki/sync.yaml` carrying a `resummarize:` block; the resolver walks each scanned file's ancestor dirs up to the vault root and **deep-merges deepest-wins** over the vault-root global ("rules inside a folder override the global ones"); (c) deterministic + per-dir memoized; (d) **partial** override deep-merges (a folder may set only `mode` and inherit `detect`); (e) per-folder override is scoped to `resummarize` **only** in v1 (NOT `zones`/`exclude`/`tag_namespace`/`extensions` — those stay vault-level) |
| E3.3 | Per-file resolution + determinism | ✅ | (a) effective config for each scanned file resolved deterministically; (b) **memoized per directory** (perf — no repeated walk/stat per file); (c) same inputs → **byte-identical** plan |
| E3.4 | Override-file safety | ☐ | (a) any in-folder override config is path-contained inside the vault + **symlink-refused** (mirror the `.wiki/layout.yaml` posture); (b) reuse the `sync_config` loader hardening (size cap + anchor-ban) |

#### Epic E4 — Integration, back-compat, tests
| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| E4.1 | Workflow integration | ✅ | (a) `workflows/wiki-sync.md` threads `--force`; (b) executor path for `skip` unchanged; (c) document the new reasons; (d) **provenance writeback** — a summary generated from N raw sources gets `sources: [<raw rel-paths>]` written into its frontmatter so the next scan detects via the exact D2a signal (AC-13) |
| E4.2 | Back-compat + invariants | ✅ | (a) **no `resummarize` block ⇒ plan byte-identical to TASK 018**; (b) **zero DDL** (`user_version` 5); (c) **no `import anthropic`** |
| E4.3 | Tests | ✅ | (a) each detector D1/D2a/D2b **pos + neg**; (b) `mode` if-missing/always/never; (c) `--force`; (d) per-folder override precedence; (e) back-compat byte-identity; (f) `mypy --strict` clean |

---

### 3. Use Cases (with worked examples)

**Actors:** *Operator* (human), *wiki-sync* (deterministic CLI), *Orchestrator* (executes
the plan), *IndexRepository* (DAL, for D2a).

#### UC-1 — Frozen transcripts beside **manually-authored** summaries (MAIN)

The operator's real case: a course already has summaries (flat `.md` in the course
folder), and keeps raw transcripts for history. No `source_state` markers exist.

**Example — tree:**
```
03 - Learning/QED - Генерация спроса Мастердата/
├── Лекция 1 — обзор.md          # summary, frontmatter:  source: _raw/lec-01.vtt
├── Лекция 2 — мастердата.md     # summary, frontmatter:  source: _raw/lec-02.vtt
└── _raw/
    ├── lec-01.vtt               # raw, already summarised
    └── lec-02.vtt
```
**Example — vault config `.wiki/sync.yaml`:**
```yaml
resummarize:
  mode: if-missing
  detect:
    source_state: true
    provenance_ref:
      enabled: true
      fields: [source, sources]
      match: vault-rel-path
    mirror:
      enabled: false
```
- **Main scenario:** `wiki-sync scan "03 - Learning/QED - Генерация спроса Мастердата"`
  → `_raw/lec-01.vtt` classifies as `ingest` → policy gate runs D2a: a query finds
  `Лекция 1 — обзор.md` has `source == _raw/lec-01.vtt` → **gate flips it to**
  `skip` with `reason="summary-exists:provenance"`. Same for `lec-02.vtt`. The two
  summary `.md` route `upsert` as before.
- **Postconditions:** zero re-summarization; **re-run is a no-op**.
- **Acceptance:** AC-1, AC-2, AC-6.

#### UC-2 — Structural mirror, **N raw → 1 summary** (operator's real `Module-01`)

The operator's bootstrap course: many numbered transcripts in `Transcripts/` distil into
one numbered summary in `Summary/`, grouped by the **leading lesson number** (stems do
NOT match → `group-key`, not `stem-relpath`).

**Example — real tree (abridged):**
```
demand-generation-bootstrap/Module-01/
├── Transcripts/
│   ├── 01-1 - Ценностное предложение.txt
│   ├── 01-2 - Ценностное предложение.txt
│   ├── 02-1 Решение vs транзакция-1.txt
│   ├── 02-2 Решение vs транзакция-2.txt
│   ├── 02-3 Что такое оффер.txt
│   ├── 02-4 Что первично - продукт или клиент.txt
│   ├── … (05-1/05-2/05-3, 06-1/06-2/06-3, …)
│   └── 07 - Восемь типов продукта … .txt
└── Summary/
    ├── 01 - Ценностное предложение.md
    ├── 02 - Решение vs транзакция.md
    ├── … 03 / 04 / 05 / 06 …
    └── 07 - Восемь типов продукта.md
```
**Config (per-folder `Module-01/.wiki/sync.yaml`, Option A) — extended regex:**
```yaml
resummarize:
  mode: if-missing
  detect:
    provenance_ref:                # authoritative if the summary has `sources:`
      enabled: true
      fields: [source, sources]
    mirror:                        # fallback for summaries WITHOUT back-refs
      enabled: true
      raw_dirs: [Transcripts]      # names illustrative — set to your real dirs
      summary_dir: Summary
      summary_ext: .md
      match: group-key
      key:                         # EXTENDED: separate regex per side + template + flags
        raw_regex: '^(?P<lesson>\d+)'        # e.g. "02-3 Что такое оффер" → lesson=02
        summary_regex: '^(?P<lesson>\d+)'    # e.g. "02 - Решение vs транзакция" → lesson=02
        template: '${lesson}'                # composed key (multi-group ok: '${module}-${lesson}')
        flags: [ignorecase]
      # shorthand:  group_key: '^(\d+)'   ← applies one regex to BOTH sides; default if `key:` omitted
```
- **Main:** `…/Transcripts/02-3 Что такое оффер.txt` → anchor `Transcripts` → scope sibling
  `…/Summary/` → raw key `02` → a `…/Summary/*.md` with key `02` exists
  (`02 - Решение vs транзакция.md`) → **`skip:summary-exists:mirror`**. All `02-*` collapse
  onto the one `02` summary (N:1).
- **Negative:** add `08-1 ….txt` with no `08 - ….md` yet → key `08` has no summary →
  **not** skipped → `ingest` (this lesson gets summarised).
- *(1:1 variant: `match: stem-relpath` maps `_raw/<sub>/x.vtt` ↔ `_summary/<sub>/x.md` by
  stem — for vaults whose raw/summary share names + structure.)*
- **Acceptance:** AC-3, AC-3b.

#### UC-3 — Forced re-summarization (`--force`)

- **Main:** operator improved the summariser and wants to regenerate this course:
  `wiki-sync scan "<course>" --force` → **every** raw source planned actionable
  (`reason="forced"`), all detectors bypassed; the existing summaries are overwritten
  by the executor downstream. Without `--force`, the same scan is a no-op.
- **Acceptance:** AC-4.

#### UC-4 — **Per-folder override** (the added requirement) — WITH EXAMPLE

Vault default is `mode: if-missing`, but one **actively-edited** course should
**always** regenerate (its transcripts are still being corrected), while a **reference**
course should **never** auto-ingest. **OQ-1 RESOLVED → Option A (cascade): rules inside a
folder override the global.**

**Vault-root global — `.wiki/sync.yaml`:**
```yaml
resummarize:
  mode: if-missing
  detect: { source_state: true, provenance_ref: { enabled: true } }
```
**Per-folder override — `03 - Learning/QED - Генерация спроса Мастердата/.wiki/sync.yaml`:**
```yaml
resummarize: { mode: always }            # this subtree always re-summarizes (inherits `detect`)
```
**Per-folder override — `03 - Learning/Справочник/.wiki/sync.yaml`:**
```yaml
resummarize: { mode: never }             # reference course: never auto-ingest raw
```
- **Walkthrough:** for each scanned file the resolver walks its ancestor dirs to the
  vault root and deep-merges **deepest-wins**. So `…/QED …/_raw/lec.vtt` → `mode=always`;
  `…/Справочник/_raw/x.vtt` → `mode=never` (→ `skip:resummarize-never`); a raw file
  anywhere else → the vault default `if-missing`. A folder override may set **only**
  `mode` and **inherit** the global `detect` (partial deep-merge).
- *(Rejected alternative — Option B, centralized `overrides[]` glob-list in one file —
  kept in OQ-1 history for context.)*
- **Acceptance:** AC-5.

#### UC-5 — Back-compat (no `resummarize` block)

- **Main:** a vault whose `.wiki/sync.yaml` has **no** `resummarize` key (or no file at
  all) → `scan` produces a plan **byte-identical** to TASK 018 (only `source_state`
  idempotency, no behavior change, no `--force` effect unless passed).
- **Acceptance:** AC-7.

#### UC-6 — `mode: never` on a search-only zone (edge)

- **Main:** a zone where raw should never be auto-distilled → all raw sources
  `skip:resummarize-never`; `.md` ready notes still `upsert`. The report lists each
  skipped raw with the reason.
- **Acceptance:** AC-8.

---

### 4. Acceptance Criteria (binary, verifiable)

- **AC-1** — With `mode: if-missing` and a matching detector, a raw source that would be
  `ingest`/`convert+ingest` is emitted as `skip` with `reason="summary-exists:<which>"`;
  the scan stays deterministic (no LLM/network) and idempotent.
- **AC-2** — **D2a (provenance):** given a page whose `source:` (or `sources:`) frontmatter
  equals the raw file's vault-rel path, the raw is skipped `summary-exists:provenance`;
  with **no** such page it is **not** skipped (negative fixture).
- **AC-3** — **D2b (mirror, 1:1 `stem-relpath`):** `_raw/<sub>/<stem>.<ext>` with an
  existing `_summary/<sub>/<stem>.md` → `skip:summary-exists:mirror`; with the mirror
  **absent** → **not** skipped (negative fixture).
- **AC-3b** — **D2b (mirror, N:1 `group-key`):** with `match: group-key` +
  `group_key: '^(\d+)'`, every `Transcripts/NN-*.txt` is skipped iff a `Summary/*.md`
  shares the leading-number key `NN` (fixture from the operator's `Module-01`); a raw
  whose key has **no** matching summary (e.g. a new `08-*`) is **not** skipped.
- **AC-4** — `--force` re-plans every raw source as actionable (`reason="forced"`),
  bypassing all detectors and `mode`.
- **AC-5** — **Per-folder override:** a raw file under an override subtree resolves the
  overridden `mode`/`detect`; a sibling file outside it resolves the vault default;
  precedence is deterministic and fixture-tested.
- **AC-6** — Re-running a fully-summarized zone is a **no-op** (all raw skipped); the
  dry-run report lists every skipped raw + reason + action counts (no silent truncation).
- **AC-7** — **Back-compat:** with no `resummarize` block, the plan is **byte-identical**
  to the TASK 018 output for the same zone (regression-locked).
- **AC-8** — `mode: never` → all raw sources `skip:resummarize-never`; `upsert`/`skip`
  routing for non-raw files unchanged.
- **AC-9** — **Zero DDL** (`user_version` 5); D2a uses the existing `frontmatter_json`
  + a parameterized `json_extract` query (a new read-only DAL method is acceptable; no
  schema change); **no `import anthropic`**; full suite green + `mypy --strict`.
- **AC-10** (determinism) — two scans of an untouched zone (with policy active) emit
  byte-identical plan JSON; per-file config resolution is order-independent.
- **AC-11** (degenerate config) — `detect` all-off + `mode: if-missing` → every raw is
  ingested (documented), and the loader emits a one-line WARN, never a crash; an unknown
  `resummarize.*` key → `INVALID_SYNC_CONFIG` (exit 6) without echoing the value.
- **AC-12** (extended mirror regex + ReDoS) — `mirror.key` with **distinct**
  `raw_regex`/`summary_regex` + multi-group `template` (e.g. `${module}-${lesson}`)
  composes a comparable key across asymmetric naming (fixture: raw `M01_L02_part3` ↔
  summary `02 - …` via per-side regex). A **catastrophic** operator regex is rejected at
  config-load (`INVALID_SYNC_CONFIG`, value not echoed) or times out per-file →
  report-and-skip (never hangs), reusing the TASK 017 guard (grounding #7).
- **AC-13** (provenance writeback) — a summary the executor generates from N raw sources
  carries `sources: [<N raw rel-paths>]` in its frontmatter; on the **next** scan those N
  raw are skipped `summary-exists:provenance` (the exact D2a signal, mirror-independent).

---

### 5. Open Questions (for the Architecture phase)

- **OQ-1 — ✅ RESOLVED (2026-06-07) → Option A (cascade).** A `<folder>/.wiki/sync.yaml`
  carrying a `resummarize:` block overrides the policy for files **under** that folder;
  the resolver walks each scanned file's ancestor dirs up to the vault root and
  **deep-merges deepest-wins** over the vault-root global. Partial overrides allowed
  (set only `mode`, inherit `detect`). The per-folder file is **read directly** by the
  resolver (the `.wiki/` dir is pruned from the content walk, so it is never itself
  ingested). Architecture to lock: the resolver's read+merge order, per-dir memoization
  for determinism/perf, and reuse of the `.wiki/layout.yaml` symlink-refuse + size-cap +
  anchor-ban hardening for these in-folder files.
- **OQ-2 — ✅ RESOLVED (2026-06-07) → extended-regex mirror + N:1 + provenance.**
  Names in the examples are **illustrative** → everything is config-driven. Mirror match:
  (1) `raw_dirs`/`summary_dir`/`summary_ext` are configurable; (2) `match ∈ {stem-relpath,
  group-key}`; (3) **extended key extraction** — a `key:` block with **separate**
  `raw_regex` + `summary_regex` (named groups), a `template` to compose a normalized key
  from ≥1 group (`${module}-${lesson}`), and regex `flags`; one-line `group_key` is the
  shorthand (default `^(\d+)`). Operator regexes are **ReDoS-guarded** (grounding #7). A
  raw is covered iff some summary in the sibling `summary_dir` yields the same composed
  key. **Provenance (D2a) is the authoritative path when summaries carry `source:`/
  `sources:`** (and the executor writes those back on generated summaries — E2.2f); mirror
  is the fallback for back-ref-less summaries; both union with D1. Architecture to lock:
  anchor = nearest ancestor in `raw_dirs`; scope = sibling `summary_dir` (flat vs
  recursive); empty-key → no mirror match (fall through); detector short-circuit order
  (provenance → mirror → source_state).
- **OQ-3 — ✅ RESOLVED (2026-06-07) → match by vault-rel path.** D2a matches a raw file
  iff its **vault-rel path** ∈ a page's `source:`/`sources:` frontmatter (not `basename` —
  avoids cross-course `lec-01.txt` collisions). List-valued `sources:` ⇒ N:1. **Index
  currency** stays a documented dependency: D2a sees only *indexed* pages, so the
  not-yet-reindexed corpus relies on **D2b (mirror, FS-based)** within the union — `scan`
  stays index-backed for D2a (no separate on-disk frontmatter read in v1).
- **OQ-4 — ✅ RESOLVED (2026-06-07) → `exclude:` kept, distinct from the policy.**
  `exclude:` means **"do not walk at all"** (the file is pruned before classification —
  invisible, not in the plan). The `resummarize` policy is the **opposite lever**: the
  file **IS** walked and appears in the plan, but is gated to `skip:summary-exists:*`
  (and is reachable by `--force`). They coexist — `resummarize` does **NOT** replace
  `exclude:`. **Precedence: `exclude:` always wins** (a path matched by `exclude:` never
  reaches the policy gate, even if a per-folder override would process it). Operators
  choose per case: `exclude:` for "never touch"; leave raw dirs walked + rely on the
  policy for "keep for history but don't re-summarize, and let `--force` reach it."
- **OQ-5 — ✅ RESOLVED (2026-06-07) → omitted `detect` = `{source_state: true}` only.**
  `source_state` is the existing SQLite table where `wiki-sync record` writes a
  "successfully ingested this exact file (by sha256)" commit-marker; `detect.source_state:
  true` means "treat *wiki-sync already ingested this* as proof a summary exists" (= D1,
  today's idempotency). Default-on = least surprise + back-compat. **Note for the
  operator's corpus:** externally-authored summaries have NO `source_state` marker, so D1
  never fires there — `mirror` (and/or `provenance_ref`) must be **explicitly enabled** to
  cover them.
- **OQ-6 — ✅ RESOLVED (2026-06-07) → `--force` is per-`scan`-invocation (zone-scoped).**
  `wiki-sync scan` already takes an explicit **zone** (a course/module folder), so
  `--force` is naturally targeted — never "the whole vault" unless you literally scan the
  vault root (which you don't). The **persistent** per-subtree force is the Option-A
  override `resummarize: { mode: always }` in that folder's `.wiki/sync.yaml`. ⇒ **no
  `--force-path` in v1** (zone arg + per-folder `mode: always` already cover it).

---

### 6. Out of scope (this task)

- **Mutating / regenerating** existing summary pages — the policy only ever turns an
  `ingest` into a `skip`; it never edits a summary (regeneration happens via `--force`
  → the normal executor overwrite path, unchanged).
- Block-level dedup of `_daily/` notes; PDF-OCR; binary-attachment indexing at scale
  (all unchanged from TASK 018).
- Cross-vault provenance (D2a is scoped within the vault).
