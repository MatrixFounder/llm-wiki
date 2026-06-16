# 11. Open Questions

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

### 11a. RESOLVED (по итогам TASK iteration 2)

- Q-A: SQLite vs Postgres — **SQLite default**, Postgres opt-in через DAL. См. [SQLITE-VS-POSTGRES.md](./SQLITE-VS-POSTGRES.md).
- Q-B: Code location — этот репо `obsidian-llm-wiki/`.
- Q-C: PK NULL semantics — fixed sentinel `'_vault_'` в schema.
- Q-D: vault_hash storage — `vault_metadata` table.
- Q-E: trust_level per adapter — manual=high, transcript/light=medium.
- Q-F: required_frontmatter для flat — без `project`.
- **Q-012-e (TASK 012): `auto_indexes[]` template mechanism** — **RESOLVED: dependency-free Python renderer** driven by `group_by` / `sort_within_group`, with an optional `assets/<name>.md.tmpl` (`string.Template`) for the surrounding shell. No Jinja dependency (NFR-3). See §3.5.
- **Q-012-f (TASK 012): per-vault layout-override merge policy** — **RESOLVED: `paths[]`/`ref_extraction[]` REPLACE on operator-supplied key; scalars overlay.** Predictable (no partial-list merge surprises); pinned by schema-validation tests. See §3.5.
- **Q-012-g (TASK 012): peer dev-vault for the cross-project acceptance (UC-33)** — default `Universal-skills` unless operator prefers `trade-agents`; either satisfies the bar (low-stakes, operator confirms at Bead 15).
- **Q-013-a (TASK 013): `wiki-search` metadata-filter CLI surface** — **RESOLVED (operator, 2026-06-01): general repeatable `--where 'field=value'` primitive + `--status`/`--severity` convenience sugar** (the sugar desugars into `where_fields`). Filters ANY frontmatter field; the two common fields get shortcuts. Closes R-X3-META-FILTER fix-option 1 (zero DDL — predicate over the existing `pages.frontmatter_json`, **not** FTS-projected). See `docs/issues/r-x3-fts-frontmatter-metadata-filter.md`.
- **Q-013-b (TASK 013): DAL shape** — **RESOLVED: extend `search_pages` with optional `where_fields: list[tuple[str,str]] | None` and make the FTS `query` optional.** When a MATCH term is present → today's `pages_fts JOIN pages` path + `AND CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?` predicates; when the query is empty AND ≥1 `where_fields` → a **non-FTS path** (`SELECT … FROM pages p WHERE <predicates>`, no `pages_fts` join, no BM25). One method, internal branch — no separate `filter_pages()`. The `CAST(… AS TEXT)` matches by **string representation** so a numeric/boolean frontmatter value (`priority: 1`) matches the always-string CLI value; string values stay byte-identical (post-`/vdd-multi` refinement).
- **Q-013-c (TASK 013): query-less ordering** — **RESOLVED: `ORDER BY p.project, p.slug, p.vault_id` (deterministic on the full page identity).** No BM25 exists without a MATCH term; `(project, slug)` alone is ambiguous for a cross-vault duplicate, so `vault_id` (the third PK column) is the tiebreaker (`/vdd-multi` critic-logic fix). Test-locked.
- **Q-013-d (TASK 013): field-name injection policy** — **RESOLVED: static allowlist regex `[a-z][a-z0-9_]*` matched via `re.fullmatch` (NOT `.match`+`$`, which matches before a trailing `\n` — `/vdd-multi` critic-security fix) at the CLI boundary AND re-validated in the DAL (library-caller defense); the JSON path `'$.'+field` and the value are BOTH bound parameters** (SQLite accepts `json_extract(col, ?)`). Two predicates on the same field are rejected (equality-only → could never match). A per-layout `filterable_fields` allowlist is a YAGNI follow-up. Error envelope `INVALID_FILTER` (exit 2) never echoes the value (CWE-209/117).
- **Q-017-1 (TASK 017): built-in vs operator-custom pattern detection (for "built-ins pay zero")** — **RESOLVED: two provenance booleans on the frozen `LayoutConfig`** (`ref_extraction_operator_supplied`, `paths_operator_supplied`), set in `load_layout_config` from whether the per-vault override supplied that key. The Q-012-f merge policy already **replaces** the whole list on operator override, so provenance is exact and free; `resolve_layout_config`'s built-in-only path leaves both `False` → built-ins run on stdlib `re` (byte-identity), only operator patterns route through `regex`+`timeout=`. See §3.5 "Runtime ReDoS deadline".
- **Q-017-2 (TASK 017): regex-timeout scope (per-call vs per-file)** — **RESOLVED: per-file wall-clock budget**, not per-`finditer` call (`extract_refs` runs `finditer` per line → a per-call timeout would allow `N_lines × ceiling`). One `deadline = monotonic() + WIKI_REDOS_BUDGET_S` per file; each call gets the *remaining* time as `timeout=`. Default `WIKI_REDOS_BUDGET_S = 2.0 s` (module constant, env-overridable; distinct from the load-gate's 50 ms ceiling). See §3.5.
- **Q-017-3 (TASK 017): `--mtime-skip` surface + P-3 default** — **RESOLVED (operator, D-017-B): default = always full-hash** (drift is integrity-first; a preserved-mtime tamper must not slip); the mtime short-circuit is an **opt-in `wiki-lint --mtime-skip` flag** only. The always-on default win is the PyYAML→regex `type:` fast-path. Zero DDL (reuses `pages.last_modified`; **no** `file_size` column — D-017-C). See §8.4.
- **Q-017-4 (TASK 017): `regex` typing under `mypy --strict`** — **RESOLVED: add `types-regex` (dev)**, consistent with the existing `types-PyYAML`/`types-jsonschema` stub pattern (the `regex` wheel ships no inline stubs — verified: no `py.typed`/`.pyi`). Fallback if stubs are inadequate: per-module `ignore_missing_imports`. See §6.1.

- **Q-018-1 (TASK 018): execution shape.** **RESOLVED: Decision-17 split — `wiki-sync scan`
  (deterministic plan-only) + `workflows/wiki-sync.md` orchestrator executor.** Forced by the
  grounding fact that the vendored `ingest()` is *summary-passthrough* (returns
  `needs-pre-summarization` on raw) ⇒ the raw→ingest path requires an orchestrator LLM step
  (`summarizing-meetings`). `wiki-sync` carries **no `import anthropic`**; `scan` does **no
  LLM/network**, only filesystem classification → a strict plan JSON. Subcommand surface:
  `wiki-sync scan <zone> [--dry-run]`. (A `wiki-sync apply --plan` convenience that batch-runs
  the *deterministic-only* actions — `upsert`/`skip`/state-record — and returns the
  LLM-required worklist is a **Planning-phase YAGNI option**, not part of the core contract.)
- **Q-018-2 (TASK 018): classifier reuse vs new.** **RESOLVED: new `scripts/wiki_skills/wiki_sync.py`
  + a `_sync` classifier helper. Vendored reuse is limited to `wiki_ingest._classify._count_md_structure`
  (it MAY back the only-a-view body heuristic); `_detect_grouping` is NOT reused — it is filename-list
  folder-role grouping, irrelevant to per-file extension/tag/view routing (RC-5).** The wiki-sync routing axis
  (extension + tag + view-marker → one of {convert+ingest, ingest, upsert, skip}) is a *different
  purpose* from vendored `classify_folder` (which role-classifies the files of ONE multi-file
  ingest as primary/metadata/merge/…). No fork of vendored code; acyclic imports; **zero
  behavioural change to vendored callers** (guarded by the existing vendored tests). *(am-1:
  depend on the vendored `_classify` privates only if stable across `sync_wiki_ingest.sh`;
  else reimplement the small needed bits in `_sync` — the routing logic is new regardless.)*
- **Q-018-3 (TASK 018): conversion wiring + staging path.** **RESOLVED: the plan NAMES the
  converter per extension (`converter ∈ {docx,xlsx,pptx,pdf}`); the ORCHESTRATOR executes it via
  the harness `docx`/`pdf`/`pptx`/`xlsx` skills (Decision-17 — the deterministic CLI never shells
  out to a skill).** Converted markdown lands at a deterministic, **collision-safe** in-vault
  staging path **`_raw/.staging/<slug(stem)>-<ext>.md`** (SEC-A4 — extension-disambiguated;
  refuse-overwrite-on-different-content) in the **non-walked `.staging/` subdir** so the converter
  output is **never re-discovered as a fresh raw drop** (closes the convert+ingest self-ingest loop
  — re-gate RG-1/W-3/SEC-N5; the walk excludes `_raw/.staging/**` alongside `_raw/.locks`/`_raw/failed`).
  Empty-slug fallback `_raw/.staging/sync-<sha8(src-path)>-<ext>.md` (SEC-N1) is a Planning detail.
  Universal-skills converter scripts are an interchangeable backend for the same skills.
- **Q-018-4 (TASK 018): config home.** **RESOLVED: per-vault `.wiki/sync.yaml`** (operational
  state, NOT vault identity — consistent with the "two separate config systems" principle and the
  existing `.wiki/` dir). Declares `zones: [globs]`, `exclude: [globs]` (default-excluded, e.g.
  `_daily/**`), `tag_namespace` (default `wiki`), `extensions` overrides. **MVP also accepts the
  zone as a CLI arg** (`wiki-sync scan <zone-path>`); `.wiki/sync.yaml` is for persistent
  multi-zone config. Schema-validated like `layout-config` (strict; misspelled key → load error).
- **Q-018-5 (TASK 018): canonical `ingest` chain.** **RESOLVED:** for an `ingest` action —
  (0) [`.vtt`/`.srt`] **de-timestamp/caption-dedup pre-step** (deterministic — reuse
  transcript-fetcher `scripts/sources/_vtt_to_text.py`; RC-1); (1) [binary] convert via skill →
  collision-safe non-walked `_raw/.staging/<slug(stem)>-<ext>.md`; (2) **H-6 fence the raw/converted body** then
  orchestrator `summarizing-meetings` (raw → summary) — ⚠️ `summarizing-meetings` is the FIRST
  LLM stage and has NO built-in H-6 banner, so the executor MUST fence before it (SEC-A1);
  (3) **`wiki-enrich --source <summary>`** (the vendored summary-passthrough files it into
  `_sources/` + indexes the source page + log_event — `register-summary` is the vendored primitive
  it uses); (4) **`wiki-extract-concepts` prepare/apply** densifies → concept/entity pages;
  (5) on full success the executor writes the `sync` idempotency row (Q-018-8). Net = the source
  page + 10–15 compounding pages. (Feeding *raw* to `wiki-enrich` returns `needs-pre-summarization`
  — hence step 2 precedes step 3.)
- **Q-018-6 (TASK 018): PDF-OCR gap — NOW CLOSED (2026-06-03, the upstream OCR block shipped).**
  Scan plans `.pdf` → `convert+ingest` (unchanged — the deterministic walk/classifier never
  changed, as predicted). The **executor convert step now WIRES OCR**: `pdf_extract.py` exit
  `10 DocumentScanned` (image-only) → `pdf_ocr.py … --lang eng+rus` (the pdf skill's `ocrmypdf`
  hop) → extract the searchable text → proceed as `ingest`. **`needs-ocr` is now only the
  soft-optional-engine fallback** — if `pdf_ocr.py` reports `OcrEngineUnavailable`/
  `LanguagePackMissing` (engine not installed: `install.sh --with-ocr`), the file is flagged in
  the report and skipped (batch continues, never dropped). Text-layer PDFs convert normally.
  (Scan stays light — the text-layer probe + OCR remediation live in the executor/converter,
  not the deterministic walk; `workflows/wiki-sync.md` Step 4a.)
- **Q-018-7 (TASK 018): tag surface + precedence.** **RESOLVED: accept BOTH the Obsidian tag
  `#wiki/{raw,skip,keep}` (frontmatter `tags:` or inline) AND an equivalent frontmatter field
  `wiki: {raw,skip,keep}`.** Precedence: **`skip` always wins** → then `raw` → then `keep` (only
  meaningful in a default-excluded zone) → then the extension/path default (`_raw/` ≡ implicit
  `raw`). `tag_namespace` overridable via `.wiki/sync.yaml`.
- **Q-018-8 (TASK 018): idempotency — SUPERSEDES the architecture-018-review AM-1 fix, which the
  `/vdd-adversarial` CRITICAL cluster proved wrong against the code.** **RESOLVED: a `wiki-sync`-owned
  `source_state` partition.** Verified: `wiki-enrich`/vendored `ingest()` write **no** `source_state`
  row (raw idempotency is a `source_hash:` frontmatter *footer* keyed by the summary slug), and the
  only `source_state` writer is `wiki-extract-concepts` (`source_kind='extract-concepts'`, scope=
  source-page slug) — **neither keyed on the raw file `scan` discovers, and the slug is unknowable at
  scan time.** So AM-1's "`is_unchanged` keys on the `source_state` the chain writes" was uncomputable.
  Fix: `source_state(source_kind='sync', scope=<vault-relative source path>, key='source_hash',
  value=sha256(file bytes))` — original binary bytes for `convert+ingest` (CONS-4); **`scan`** reads it
  via a new read-only `get_source_state(...)`; the **executor** writes it via `set_source_state(...)`
  **only after the per-file chain fully succeeds** (commit marker → partial-failure resumes, ID-4).
  **Zero DDL** (`source_state` has no `source_kind` CHECK; `'sync'` is data). The earlier "no new DAL
  surface" claim (interfaces §5.4) is corrected → **two new generic zero-DDL `source_state` get/set
  methods** (F2/ID-2/CONS-2). Uniform across all non-skip actions — also dissolves the
  `pages.file_hash`/file_path/rename edge of ID-3 (a rename = new path = new row = re-process, documented).
- **Q-018-9 (TASK 018): the scan walk + upsert feasibility — corrects two HIGH design errors.**
  **RESOLVED:** (a) `wiki-sync scan` does **NOT** reuse R-X1 `iter_pages` (EC-1/ID-5 — `iter_pages`
  filters to the layout's `.md` page-globs and would discover **zero** `.txt`/`.vtt`/`.docx`/`.pdf`
  drops); it implements its **own** zone walk over the wiki-sync extension set, *mirroring*
  `iter_pages`' single-stat + case-folded early-extension-skip discipline (EC-6), pruning `exclude:`
  non-`.md` immediately but reading `exclude:`-zone `.md` for `#wiki/keep`. (b) A no-tag `.md` routes
  to `upsert` **only if** it carries a layout-mapped frontmatter `type:` (or a `path_type_fallback`
  subdir); else → `skip` reason `unmappable-type` (EC-2 — `wiki-index-upsert`→`normalize_frontmatter`
  raises `UnmappedTypeError` on a type-less prose note, so "upsert as-is" is not free). (c) Degenerate
  inputs never raise: empty file → `skip:empty-source`; unparseable frontmatter → route-by-path,
  `frontmatter-unparseable` (EC-7). See functional-architecture *Sync Dispatcher → Classification*.
- **Q-018-10 (TASK 018): architecture-review **re-gate** corrections (run wf_29fce9ba-39b; the
  re-gate found my Q-018-8/9 fixes had introduced new holes — `docs/reviews/architecture-018-rereview.md`).**
  **RESOLVED:** (a) **convert+ingest convergence** — staged output moved to the non-walked
  `_raw/.staging/` (RG-1/W-3/SEC-N5); (b) **scan read-cost honesty (W-2/am-2)** — the uniform
  `sync` `sha256(file bytes)` key means `scan` reads every eligible file; the superseded AM-1's
  "no re-read fast-path" claim is dropped; acceptable because enrich zones are scoped + binaries
  skipped pre-read + huge dirs `exclude`d (optional mtime short-circuit = Planning YAGNI); (c)
  **SEC-A5 corrected (SEC-N3)** — `yaml.safe_load` does NOT stop an anchor-bomb (it expands
  aliases); the real bound is the 256 KiB size-cap **+ a custom `SafeLoader` that forbids
  anchors/aliases**; (d) **flock specified (SEC-N4)** — `LOCK_EX|LOCK_NB` on `<vault>/.wiki/sync.lock`,
  exit 2 `SYNC_IN_PROGRESS` if held, fd-scoped auto-release, guards wiki-sync runs against each
  other only; (e) **unmappable-type predictor is layout-general (W-1)** — predicts against the same
  `normalize_frontmatter` resolution `wiki-index-upsert` uses, not a karpathy assumption. Re-gate
  residual after these = LOW/Planning only (RC-4 matcher, RC-5 reuse, SEC-N1 empty-slug,
  RG-5 wording). **Still zero DDL** (`user_version` 5).
- **Q-019-1 (TASK 019): policy-gate placement + component layout.** **RESOLVED:** the
  re-summarization policy is a **gate between the classifier and the plan-entry build**, in
  `wiki_sync._build_entries`: after `classify_file` returns an action, if action ∈
  `{ingest, convert+ingest}` the gate MAY downgrade it to `skip`; it **never** touches
  `upsert`/`skip`/`record` (the gate is monotone — only `ingest → skip`). New module
  `scripts/wiki_skills/_resummarize.py` (SRP; acyclic `wiki_sync.py → _resummarize.py`,
  which consumes `_sync` types + the open `repo`; `_sync.py` stays the pure classifier).
  D1/D2a take the open `repo`; D2b is pure FS. (AC-1.)
- **Q-019-2 (TASK 019): config schema `$def Resummarize` (strict, opt-in).** **RESOLVED:**
  new strict `$def Resummarize` under `SyncConfig.resummarize` in
  `config/sync-config.schema.yaml` (`additionalProperties:false`); **absent ≡ TASK 018
  behavior** (AC-7). Shape: `mode ∈ {if-missing(default), always, never}`; `detect:
  {source_state:bool=true, provenance_ref:{enabled, fields:[source,sources]},
  mirror:{enabled, raw_dirs:[…], summary_dir, summary_ext='.md', match ∈
  {stem-relpath,group-key}, group_key(shorthand) | key:{raw_regex, summary_regex, template,
  flags:[ignorecase,unicode]}}}`. Omitted `detect` → `{source_state:true}` (OQ-5).
  `summary_dir: "."` = the raw file's own folder (Pattern B). Loader hardening reused from
  `sync_config` (256 KiB cap + anchor-ban `SafeLoader`; `INVALID_SYNC_CONFIG` exit 6, value
  never echoed — CWE-209/117). (AC-9/AC-11.)
- **Q-019-3 (TASK 019): per-folder override = Option A cascade (operator-decided).**
  **RESOLVED:** a `<folder>/.wiki/sync.yaml` carrying a `resummarize:` block overrides for
  files **under** it. Per scanned file the resolver walks ancestor dirs from vault-root →
  file-dir, reads each `<dir>/.wiki/sync.yaml` `resummarize`, **deep-merges deepest-wins**
  over the vault-root global (dicts merge, scalars replace → partial override: set only
  `mode`, inherit `detect`). **Per-directory memoization** (resolve once per dir, not per
  file → AC-10 determinism + perf, §8). The `.wiki/` dir is **read directly** and is **pruned
  from the content walk** (`_is_pruned_dir` dot-segment) → an override file is never itself
  ingested. Path hardening reused from `.wiki/layout.yaml`: raw-`is_symlink` refuse +
  `validate_inside_vault` + size-cap + anchor-ban. Scope = `resummarize` only (not
  `zones`/`exclude`/`tag_namespace`/`extensions`). **Fixture anchor:** `Module-NN/.wiki/sync.yaml`
  (`group_key '^(\d+)'`) vs `Lessons/.wiki/sync.yaml` (`group_key '^(\d{8})'`) — a real
  divergence that *requires* the cascade. (AC-5.)
- **Q-019-4 (TASK 019): detectors — union + cheapest-first short-circuit.** **RESOLVED:**
  "summary exists" = **D1 ∪ D2a ∪ D2b** (any match → covered). Order: **D1** `get_source_state(
  vault,'sync',rel,'source_hash')` present (existing, ~free) → **D2a** new read-only DAL
  `find_pages_citing_source(vault_id, rel_path, fields)` = parameterized
  `json_extract(frontmatter_json,'$.source')==? OR rel_path ∈ '$.sources[]'` (TASK 013
  mechanism; vault-rel match, OQ-3) → **D2b** mirror (FS). Match → `skip:summary-exists:
  {source_state|provenance|mirror}`. `mode: never` → `skip:resummarize-never` regardless;
  `mode: always`/`--force` → bypass detectors (reason `forced` for `--force`). **Fixture
  reality:** the `samples/Demand-generation` summaries currently carry **no** `source:`
  frontmatter ⇒ D2a is dormant there and **D2b group-key is the operative detector**; the
  writeback (Q-019-7) then populates D2a. (AC-1/2/3/3b/4/8.)
- **Q-019-5 (TASK 019): D2b mirror algorithm + extended regex + ReDoS guard.** **RESOLVED:**
  anchor = **nearest** ancestor of the raw file whose dir-name ∈ `raw_dirs`; scope = sibling
  `<anchor.parent>/<summary_dir>/` (or the anchor dir itself when `summary_dir: "."`,
  Pattern B). Strategies: **`stem-relpath`** (1:1 — `<scope>/<same-relpath-stem><summary_ext>`
  exists; covers `Resources/X.docx ↔ Resources/X.md`) and **`group-key`** (N:1 — derive a key
  from the raw stem via `key.raw_regex` named groups → `template`, and from each candidate
  summary stem via `key.summary_regex`; covered iff some summary in scope shares the composed
  key; `group_key` = same-regex-both-sides shorthand; default `^(\d+)`). **Operator regexes
  are ReDoS-guarded** reusing TASK 017: `_redos_budget_check` load-gate at config-parse
  (catastrophic → `INVALID_SYNC_CONFIG`, value not echoed) + per-file `guarded_search`
  deadline at match (timeout → no-mirror-match + WARN, never hang). Empty/no-key → no match
  (fall through). **Documented limitation:** a raw whose name yields no key (e.g.
  `Transcripts/Модуль 1 Урок 4 ….pdf` under `^(\d+)`) falls through to convert/ingest; the
  robust cover is D2a once `sources:` exist (Q-019-7). *Planning residual (LOW):* recursive-
  vs-flat scope scan; multi-pair `raw_dirs↔summary_dir`. (AC-3/3b/12.)
- **Q-019-6 (TASK 019): `--force` + `exclude > policy` precedence.** **RESOLVED:** `wiki-sync
  scan <zone> [--force]` — `--force` bypasses detectors + `mode`, plans every raw actionable
  (`reason="forced"`), **zone-scoped** (the zone arg is a course/module, never the whole
  vault; persistent per-subtree force = `mode: always`). **`exclude:` wins:** an
  `exclude:`-matched path is pruned in `iter_sync_candidates` (the walk) **before**
  classification → it never reaches the gate. `exclude:` = "never walk"; policy = "walk but
  skip-if-summarized". (AC-4; OQ-4/OQ-6.)
- **Q-019-7 (TASK 019): provenance writeback (executor).** **RESOLVED:** when
  `workflows/wiki-sync.md` *generates* a summary from N raw sources it writes `sources:
  [<raw vault-rel paths>]` into that summary's frontmatter (deterministic, idempotent) → the
  next scan detects via the exact D2a signal regardless of naming, making the corpus
  self-describing. Also retro-fits `samples/Demand-generation` (whose summaries lack
  `sources:`) on first wiki-sync-driven regeneration. (AC-13.)
- **Q-019-8 (TASK 019): data model — zero DDL.** **RESOLVED:** no new entity/column. D1 =
  existing `SourceState` (`source_kind='sync'`); D2a = existing `Page.frontmatter_json` via
  parameterized `json_extract` (read-only); D2b = filesystem only. **One new read-only DAL
  method** `find_pages_citing_source` (pure SELECT). `user_version` stays **5**. (AC-9.)
- **Q-019-9 (TASK 019): back-compat + determinism + dogfood.** **RESOLVED:** no `resummarize`
  block ⇒ **byte-identical** plan to TASK 018 (regression-locked, AC-7); per-dir-memoized
  resolution is order-independent ⇒ byte-identical plans (AC-10); **no `import anthropic`**.
  **Dogfood `samples/Demand-generation`** exercises patterns A (group-key modules), B
  (same-dir stem Resources), C (date-key Lessons) end-to-end. **Cross-task prerequisite (NOT
  TASK 019 scope):** the summaries use `type: lesson-summary`, unmapped by obsidian-personal's
  `type_mapping` → `wiki-index-upsert` would `skip:unmappable-type`; the dogfood vault needs a
  layout mapping `lesson-summary` (TASK 012 TYPE_MAPPING tag-route) for the summary `upsert`
  leg — orthogonal to the re-summarization gate, flagged so dogfood isn't surprised.
- **Q-019-10 (TASK 019): SHIPPED + `/vdd-multi` hardening (2026-06-07).** The as-built
  implementation refines Q-019-3/4/5/8 after the 3-critic convergence (Logic ✓ Security ✓
  Performance ✓):
  (a) **per-scan `Caches`** (one per `_build_entries`) memoizes the resolved policy per parent
  dir, the D2a citation set per `(fields, match)`, and the D2b summary-key index per scope —
  collapsing the per-file hot path from O(R×S) mirror + O(R×F×P) provenance to **O(S+R)** +
  **O(P+R)** per scan;
  (b) D2a adds a **second** read-only DAL method `all_cited_sources(vault_id, fields) -> set`
  (the bulk citation set, hoisted once) beside `find_pages_citing_source` (Q-019-8); `match`
  has **two equally-supported modes** — `vault-rel-path` (default, strict full-path equality)
  and `basename` (basenames BOTH sides → matches basename- OR path-cited summaries), the latter
  preferred for globally-unique/basename-cited corpora (documented TASK 025 / Q-025-4 — no
  longer an "orphaned knob");
  (c) D2b's summary-key index is built **once per scope under a single shared ReDoS deadline**
  (bounds the S-side aggregate) + an operator-regex **load-gate** (`layout_config.is_pattern_redos_safe`,
  cached) rejecting an uncompilable/catastrophic pattern → `INVALID_SYNC_CONFIG` exit 6, no echo
  (beyond the per-call deadline); the mirror `scope` is `validate_inside_vault`-contained +
  walked `recurse_symlinks=False` (operator `summary_dir` can't probe out-of-vault);
  (d) `resolve_policy` signature is `(path, *, vault_root, caches)` (the parsed config can't
  serve the RAW-dict partial-merge, so the resolver re-reads each level incl. the root);
  (e) `--force` sets reason `forced` uniformly across `never`/`if-missing`; `_compose_key`
  empty-key → no-match; `_norm` is `isascii()`-guarded. **1039 pytest (+4 skipped), mypy strict.**
- **Q-019-11 (TASK 019): post-ship dogfood hardening (2026-06-08).** A full end-to-end
  dogfood on the operator's real `samples/Demand-generation` vault (6 modules + Lessons,
  159 files) + a 14-agent adversarial verification workflow proved the gate **correct with
  zero data-loss** (all 88 skips cross-checked to a real covering summary; D1∪D2a∪D2b all
  exercised, incl. the date-key per-folder override + stem-relpath same-dir; the union's
  value confirmed — a transcript D2a missed under a transiently-incomplete index was caught
  by the FS-based D2b). Two fixes landed:
  (a) **dead-detector WARN** — `_resummarize._scope_key_index` now logs once per scope when
  mirror is enabled but the `group_key`/`key` regex keys **0 of N** summaries (the silent
  symptom of a misconfigured pattern, e.g. a YAML double-backslash `'^(\\d+)'` that compiles
  to "literal-backslash + d"); the index is built BEFORE the raw-side `rkey` short-circuit so
  the WARN fires even when the regex matches neither side;
  (b) **`ignore` UNION** — `load_layout_config` now EXTENDS (base ∪ override, base-first,
  deduped) rather than replaces the base `ignore` on a per-vault `.wiki/layout.yaml` override
  (paths/ref_extraction stay REPLACE for their ReDoS provenance), making the `wiki-init`
  CLAUDE.md/WIKI_SCHEMA "extend `ignore`" guidance true and stopping a real Obsidian vault's
  `.obsidian/`/`_templates/` from leaking into the index the moment an operator sets a custom
  ignore. **1041 pytest, mypy strict.**
  **Separate finding (NOT fixed — TASK-012 surface):** `wiki-reindex` SILENTLY drops a page
  on an intra-project slug collision (two identically-titled lessons in one `project`) —
  it reports the file count but the DB has fewer rows and `skipped`/`alias_collisions` are
  empty, so the operator gets no signal and D2a then under-detects. Mitigated in the dogfood
  by giving each module its own `project` (project_pattern); the indexer-side warn/guard
  **shipped in TASK 020 [LIGHT]** — `reindex_full`/`reindex_delta` now emit a
  `slug_collisions` envelope field (`{slug, project, kept, dropped}`) + a one-shot WARN
  (detection-only). See `docs/tasks/task-020-reindex-slug-collision.md`.

### 11b. Defer-able (не блокирует Architecture, можно решать в Plan/Dev)

- **Q-1: Embedding модель для Epic 8**.
- **Q-2: light-summary LLM model** — Haiku (default, $) vs Sonnet (quality).
- **Q-3: Cron / launchd для daily automation** — Epic 6 detail.
- **Q-4: Plugin packaging format** — после MVP стабилизации.
- **Q-5: `wiki-source-light` text input limit** — спека `≤ 10K chars` стоит ли расширить? Решается в Dev по UX feedback'у.

### 11c. Architecture-specific Open Questions

- **Q-A1: ABI compatibility transcript adapter ↔ summarizing-meetings**. Какой именно contract?
  - **Default assumption**: subprocess invocation `claude /generate-detailed-meeting-summary --source <transcript>` → читаем stdout JSON envelope с output path. Если skill эмиттит другой формат — adapter parser нужно адаптировать.
  - **Resolution**: подтверждается при первом end-to-end тесте transcript adapter (Epic E3 I-3.3).

- **Q-A2: Should `wiki-init` cron-job creation быть default ON or OFF?**
  - **Current TASK answer**: interactive prompt, default OFF.
  - **Architecture stance**: согласен — automation — opt-in для предотвращения surprise behavior.

- **Q-A3: Schema migration framework выбор**.
  - **Default assumption**: rolling files в `scripts/migrations/v{N}_to_v{N+1}.py` без external lib (Alembic-style — overkill).
  - **Resolution**: confirmed для MVP. Re-evaluate если migration count > 5.
  - **TASK 005 note**: the v2→v3 `entity_aliases` PK change needs **no migration script** — the DB is a Class B rebuildable cache, so `wiki-reindex --full` is the migration. Bump `PRAGMA user_version` + `schema_meta` only.

- **Q-A4 (TASK 005): alias-expansion breadth cap.** What maximum number of OR-terms per query before truncation (FTS-blow-up perf guard)?
  - **Default assumption**: cap at the matched entity's own alias set + canonical name; **no transitive expansion**. Non-blocking — tune in Dev on real-vault feedback.

- **Q-A5 (TASK 005): auto-promote log-event granularity.** Should `wiki-confirm --auto` emit one `entity-confirmed` log event per promoted slug, or a single batch event?
  - **Default assumption**: one event per promotion (backlink traceability). Resolve in Planning. Non-blocking.

- **Q-A6 (TASK 007 — decide BEFORE R-6.6 planning): query idempotency hash content.** Should the `source_state` `value` hash the **question only** or **question + the ordered retrieved `project/slug` set**?
  - **Default assumption**: hash question + retrieved-slug-set, so a re-query after the corpus changed re-synthesises (defines UC-17 `is_unchanged` semantics + whether the compounding loop picks up new sources). Borderline-blocking — finalise in Planning.

- **Q-A7 (TASK 007): `cites:` identifier format.** Bare `slug` vs `project/slug`?
  - **Default assumption**: `project/slug` (disambiguates course-tier vs vault-tier; matches the `wiki-search` link shape; is the grounding comparison key). Non-blocking.

- **Q-A8 (TASK 007): body citation rendering.** Inline `[[project/slug]]`, a trailing `## Sources` list, or both?
  - **Default assumption**: a trailing `## Sources` list of `[[project/slug]]` wikilinks (Obsidian-native backlinks); `cites:` frontmatter remains the machine-readable source of truth. Non-blocking — interacts with Q-A9.

- **Q-A9 (TASK 007 — Task Reviewer O-2 / Arch-Reviewer M-1/M-2): dual ref-type coexistence + reindex mechanism.** A query page rendering both `cites:` (→ `'cited'` via R-6.5e) and body `## Sources` wikilinks (→ `'mentioned'` via `extract_wiki_links`) produces two `page_entity_refs` rows to the same target with different `ref_type`.
  - **Resolved (design):** allowed and consistent — the composite PK keeps the two rows distinct. **Mechanism (M-1):** both ref-types are written in the page's **single** `replace_refs` call (the `cited` refs are unioned into Step 2's `out.refs`) — never a second `replace_refs`, which is delete-all-then-insert and would clobber. **AM-3 (M-2):** Step 2.5 canonicalizes `cited` refs' `entity_slug` through the alias map just like `mentioned` refs (a merged-away cited target still resolves), rewriting `entity_slug` only — `ref_type` is preserved, so `cited` never degrades to `mentioned` (UC-20 holds structurally). `find_orphan_links`/backlink consumers key on the canonical slug and are unaffected. Whether to render body wikilinks at all (Q-A8) is the only residual sub-choice (`cites:` frontmatter is already authoritative). Non-blocking.

- **Q-021-1 (TASK 021 / HIGH-1 — D2b mirror merge-vs-split visibility).** The D2b
  filesystem mirror proves *key-equality*, not *"this raw was summarised"*. Under N:1
  group-keying a new raw sharing a key with an already-summarised sibling is skipped —
  the operator's intended "group summarised → don't re-summarise" semantics (TASK 019),
  but the coarse-key/merge-vs-split ambiguity was invisible.
  - **Resolved (Option A, operator-confirmed):** **behaviour-preserving + visibility.**
    The skip stays (monotone gate untouched); when a **group-key** match results in a
    skip **and provenance is enabled but does not cite this raw**, `summary_exists`
    emits ONE WARN naming the composed key, the raw, a representative colliding summary,
    and both resolution levers (MERGE = `--force` + AC-13 `sources:` writeback; SPLIT =
    finer key / own scope / a 2nd summary citing the raw). Provenance is the authoritative
    merge/split record; the key is only the default grouping. `stem-relpath` (1:1) is exact
    → never warns. Provenance disabled → no per-file warn (operator opted into pure-key
    grouping). No new state, log-only; B/C (auto-ingest / mirror-advisory) rejected as
    behaviour-changing. The two latent sharp-edges are documented, not "fixed": `^(\d+)`
    +`_norm` is a leading-zero-insensitive numeric equivalence class; `summary_ext` is
    single-valued (one extension per mirror).

- **Q-021-2 (TASK 021 / HIGH-2 — cross-batch delta slug-collision).** `reindex_delta`
  detected only *within-batch* `(slug,project)` PK collisions (in-memory `seen_keys`),
  so a delta file colliding with a row written by a *prior* batch (mtime ≤ cutoff, not
  re-walked) silently clobbered it — the same silent-overwrite class TASK 020 closed for
  `--full`, reopened across `--delta` runs (the documented primary workflow).
  - **Resolved (refined by the `/vdd-multi`-style review L-1/L-2/PERF):** read the `pages`
    rows **once** (`SELECT slug, project, file_path`) and seed `seen_keys` with ONLY the
    prior-batch rows whose file is **still on disk AND not re-walked this batch**
    (`mtime <= cutoff`). This makes the cross-batch report fire for a genuinely-untouched
    prior row, while (L-1) a re-walked survivor is left to the within-batch loop — no
    double-count / inverted-direction record — and (L-2) a renamed-away file is not falsely
    flagged. The single read is reused for orphan deletion (PERF-021-1: was a second scan).
    `_detect_slug_collision`'s `prior != rel` guard additionally no-ops a self-update. Zero
    DDL (reuses `pages`); `slug_collisions` is no longer "within-batch only". The same fix
    shape lets `wiki-reindex --all-vaults` honour `--delta` (was silently `--full`).

- **Q-022-1 (TASK 022 / vault-local-db-resolution — the resolution chain).** A vault may declare
  its index DB in `WIKI_SCHEMA.md` (the **identity** layer) via an optional `index_db:` so the DB
  lives with the vault; absent ⇒ byte-identical to today (global `global.db`, ADR-002 §D1). This
  implements the "future per-vault opt-out flag" already named in `factory._resolve_db_path`.
  - **Resolved (components — `make_repo` UNTOUCHED, YAGNI):** two small additions, no `factory`
    change and no new `config_loader`→`factory` edge:
    - `config_loader.resolve_index_db_path(vault_root) -> Path | None` — NEW pure function next to
      the existing `find_vault_root`/`load_root_config`. Reads `index_db` from the **raw
      `WIKI_SCHEMA.md` frontmatter only** (NOT the `CLAUDE.md::wiki:` overlay — single redirect
      surface), validates, and resolves it.
    - `_common.build_repo_config(vault_id, *, vault_root, db_path_flag) -> dict` — NEW CLI-shared
      helper encoding the chain **`--db-path` flag > `index_db` (resolved) > global**. It simply
      populates `config['db_path']`; `factory.make_repo` then takes its existing
      `db_path_override` path and applies the **unchanged** R-03 iCloud guard + global fallback. So
      `make_repo` stays path-only (no `config_loader` import; `factory` remains a leaf). `_common` is
      an acyclic home, but `build_repo_config` **lazily imports `config_loader` inside the function**
      (matching `_common.resolve_entity_file`'s lazy `security` import) — never a top-level
      `_common→wiki_index` edge that `rendering` would transitively pull on every render. [arch-review M-3]
  - **Data model:** zero DDL (`user_version` 5). The only new "data" is the optional `index_db`
    frontmatter key (Class A identity). The `vaults` table is unchanged — for a local-DB vault its
    single row simply lives in the local DB, not `global.db`.

- **Q-022-2 (TASK 022 — the ordering inversion + CLI surface).** The fleet pattern is
  `make_repo(config)` FIRST, then read `root_path` from the opened DB (`repo.get_vault(args.vault)`,
  `wiki_query`/`wiki_sync._derive_vault_root`). For a local-DB vault that opens GLOBAL then fails
  `get_vault` → the resolution MUST invert: resolve `vault_root` (`--vault-root` flag →
  `config_loader.find_vault_root(cwd)` walk-up) **before** `make_repo`. `wiki-index-upsert` and
  `wiki-extract-concepts prepare` already do this — the template.
  - **Resolved (per-CLI inventory, 3 classes + internal sites):** (i) already root-before-make_repo
    — `wiki-index-upsert`, `wiki-extract-concepts` (reuse helper); (ii) `--vault-root` flag but
    derive-after — `wiki-query`, `wiki-sync`, `wiki-verify-multi` (move resolution earlier); (iii)
    **no `--vault-root`** — `wiki-search`, `wiki-lint`, `wiki-reindex`, `wiki-index-render`,
    `wiki-alias`, `wiki-confirm`, `wiki-merge`, `wiki-append-log` (ADD `--vault-root` or cwd
    walk-up). The helper must also reach the internal ingest sites — **concretely (M-2,
    split-brain risk):** `wiki_enrich.main` runs `build_repo_config(...)` and passes the resolved
    `config['db_path']` down via the EXISTING `db_path=` kwarg of `_manifest_consumer.index_from_manifest`
    (and `wiki_index_upsert.upsert_one` inherits via the open `repo`) — **no signature change**. If
    skipped, `wiki-enrich` writes GLOBAL while the rest of the vault is local — worse than a clean
    fallback. Bare `--vault <id>` + no discoverable root + not-in-global → an unresolved-root error;
    **reuse the existing `VAULT_ROOT_NOT_FOUND` (`wiki_index_upsert`) / `INVALID_VAULT_ROOT`
    (`wiki_sync`) code rather than mint a third near-duplicate** (MN-3); no path-content echo
    (CWE-209/117), not a silent global hit.
  - **`wiki-init`:** all three subcommands — `--register-existing`/`--scaffold-new` accept
    `--index-db <relpath>` (or `--local` ⇒ `.wiki/index.db`), write `index_db:` into
    `WIKI_SCHEMA.md`, and register the `vaults` row into the **local** DB; `--reconcile` honours a
    declared `index_db` (no silent global open).

- **Q-022-3 (TASK 022 — security, cloud posture, island; operator-resolved OQ-1/OQ-5).**
  - **`index_db` validation (Security §7):** the **relative** form (default, e.g. `.wiki/index.db`)
    is validated at the **string level** before any filesystem call (reject `..`/absolute-when-
    relative/NUL), then its **parent is `resolve()`-d THEN checked** —
    `(vault_root / rel).parent.resolve(strict=False).is_relative_to(vault_root.resolve())` — so a
    symlinked `<vault>/.wiki/ → out-of-vault` (the TASK 018 SEC-A3 / `resolve_entity_file` F3
    class) cannot escape; a lexical check alone is insufficient (arch-review M-1). This is NOT
    `security.validate_inside_vault` on the not-yet-created DB file, which `resolve(strict=True)`s
    and raises `FileNotFoundError` (the codebase already sidesteps this in `wiki_sync.scan`). The
    **absolute/`~`** form is the explicit operator escape for cloud-synced vaults — same trust
    surface as `--db-path` (`WIKI_SCHEMA.md` is Class A operator-authored), still subject to the
    iCloud guard. JSON-schema: add `index_db: {type: string, minLength: 1}` to `WikiRootConfig`
    (today `additionalProperties:true` → must be added; path semantics validated in code, not a
    schema pattern — MN-2) and **ban** it in `WikiProjectOverride` via
    `allOf:[{not:{required:[vault_id]}},{not:{required:[index_db]}}]` (a single
    `not:required:[vault_id,index_db]` only rejects having BOTH — wrong; MN-1). DiD only —
    `resolve_index_db_path` reads raw frontmatter, never the merged override.
  - **OQ-5 → robust-to-both (cloud):** the R-03 iCloud guard (`validate_db_path`) STAYS and fires on
    the resolved path. A relative in-vault DB works for non-synced folders; for an iCloud/Dropbox
    vault the guard rejects the in-vault path with the relocation hint → the operator points
    `index_db` at an explicit non-synced (absolute) path, or leaves it unset (global). No new
    detection heuristic — the existing guard is the backstop.
  - **OQ-1 → island (Scalability §8):** a local-DB vault is self-contained. `--vault all` /
    `--all-vaults` resolve through `repo.list_vaults()` over the **connected** DB only — there is no
    registry of local DBs, so cross-DB federation is architecturally impossible without new state
    and is explicitly OUT of scope (YAGNI). Documented as the contract; ADR-002 §D1 partitioning is
    untouched (global stays the default when `index_db` is absent). **Nested-vault consequence
    (MN-4):** `find_vault_root` returns the NEAREST `WIKI_SCHEMA.md`, so a sub-vault that declares
    its own `index_db` routes to a different DB than its parent — by-design island behaviour; note
    it in the island contract / README so it does not read as a surprise.

- **Q-022-4 (TASK 022 — `/vdd-multi` security hardening, post-implementation).** The adversarial
  multi-critic pass found that `index_db` travels INSIDE the vault config, so a cloned/synced/handed
  vault is an **attacker-shippable** config — a fundamentally different trust source than a `--db-path`
  flag typed this session. Resolution (`resolve_index_db_path` / `build_repo_config`) was hardened:
  - **Leaf-symlink escape (HIGH-S1):** the relative containment now refuses a symlinked **leaf** and
    `resolve()`-s the **full** candidate (not just the parent) before `is_relative_to(vault_root)` —
    the parent-only check let `<vault>/.wiki/index.db → /outside` become an arbitrary-write primitive
    (`make_repo` mkdir+writes the schema through the symlink).
  - **Absolute write primitive (HIGH-S2):** an absolute/`~` `index_db` is now gated behind the
    explicit env `WIKI_ALLOW_ABSOLUTE_INDEX_DB` (else `ConfigValidationError`); `$VAR` expansion was
    removed. This **amends OQ-5**: the cloud-vault "absolute non-synced path" escape now requires the
    operator to set that env (a freshly-cloned vault can't silently redirect writes). The iCloud guard
    still applies on top.
  - **Wrong-DB via CWD walk-up (HIGH-L1):** `resolve_index_db_path(vault_root, *, expected_vault_id)`
    returns `None` when the root's WIKI_SCHEMA `vault_id` ≠ the addressed vault — so a walk-up (or a
    mismatched `--vault-root`) can't open a *different* vault's DB; `build_repo_config` passes the
    addressed id (the global sentinel opts out → island). 
  - **Error contract (MED):** a malformed/unsafe `index_db` → a single `INVALID_INDEX_DB` JSON
    envelope + `SystemExit(6)` from `build_repo_config` (never a raw traceback; value never echoed,
    CWE-209).
  - **Frontmatter injection (MED-S1):** `wiki-init`'s `_validate_index_db_rel` rejects every YAML
    line-break (proved to cover PyYAML's full break set via `str.isspace()` — incl. U+0085/U+2028/
    U+2029), a `---` fence, and a `": "` map token; `_ensure_index_db` writes fence-aware + atomically
    and errors (`INDEX_DB_ALREADY_DECLARED`) on a conflicting prior value. Two adjacent residuals
    noted as out-of-scope follow-ups (pre-existing unwrapped `_split_frontmatter` `safe_load`;
    `--description`/`_sanitize_desc` doesn't strip U+2028/U+2029). 1083 pytest, mypy strict.
- **Q-024-1 (TASK 024 / R-1 — `wiki-index-upsert` layout-awareness; corrects an
  implementation gap vs the Q-018-10(e)/W-1 claim).** The architecture has asserted since
  Q-018-9/10 that `wiki-index-upsert` resolves frontmatter "against the same
  `normalize_frontmatter` resolution" as the layout (W-1, layout-general). **The
  implementation never did:** `wiki_index_upsert.main` calls
  `normalize_frontmatter(out.frontmatter, source_path=src)` with NO `type_mapping`/`glob_type`
  (→ falls back to the module-level karpathy `TYPE_MAPPING`), and `ManualSourceAdapter.fetch`
  derives identity via `derive_slug` (→ `_vault_` fallback, `parsing.py`) + hardcoded
  `extract_wiki_links`. On an `obsidian-personal` (PARA) vault this filed pages at project
  `_vault_` with karpathy types — diverging from `reindex` and (under a later `reindex --full`)
  creating a DUPLICATE `(vault_id, slug, project)` row (2026-06-08 full-dogfood finding). Worse,
  it would `UnmappedTypeError` on `type: note`/`moc`/`daily-note`/`clipping`/`webinar-summary`
  (obsidian-personal types karpathy lacks). **RESOLVED:** the per-page derivation in
  `reindex.reindex_full` (`reindex.py:506-545`: `iter_pages` → `replace(page_slug=disc.slug,
  project=disc.project)` → `_synthesize_fm(frontmatter_synthesis)` →
  `normalize_frontmatter(type_mapping, path_type_fallback, extra_tags=disc.extra_tags,
  glob_type=disc.raw_type)` → `_build_page` + `_body_refs(slug_strategy)` + `_frontmatter_refs`)
  is factored into a **single shared per-file helper** — first step `adapter.fetch(item)`
  (which RETAINS the `validate_inside_vault` + `parse_frontmatter` + `compute_file_hash` seam,
  `manual.py:30`), then `replace(slug,project)` → `_synthesize_fm` → `normalize_frontmatter(4
  args)` → `_build_page` → `_body_refs(slug_strategy)` + `_frontmatter_refs` — that **THREE**
  sites call → guaranteed byte-parity (slug, project, type, tags, title, refs): `reindex_full`
  (`reindex.py:506-549`), `reindex_delta` (`reindex.py:368-394` — a byte-identical derivation
  block today; collapsing it into the helper PREVENTS full/delta drift, arch-review C-2), and
  `wiki-index-upsert.upsert_one`. The helper needs a **single-file `DiscoveredPage` derivation**
  (`glob` first-match + `_derive_project` + `slug_strategy` + per-glob tags + `raw_type`)
  extracted from `iter_pages`' per-entry logic (since `iter_pages` walks the whole vault);
  `upsert_one` resolves the layout via `resolve_layout_config(vault_root)` first. The
  `_frontmatter_refs` `cite_skipped` accumulator that `reindex` surfaces in its envelope is
  **discarded** by `upsert_one` (it passes `[]`, the established pattern — cf.
  `wiki_query.py:340`, `wiki_verify_multi.py:368`). **Karpathy byte-identical** (layout values
  equal the old `derive_slug`/karpathy `TYPE_MAPPING` outputs for that grammar — golden anchor).
  **Blast radius (was OQ-2):** `upsert_one` has a **fourth caller** the first draft missed —
  `_manifest_consumer.index_from_manifest` (`_manifest_consumer.py:138`, the `wiki-enrich`
  manifest path); making `upsert_one` layout-aware makes the enrich/manifest write layout-aware
  too — **desirable** (a PARA enrich would otherwise mis-file at `_vault_`) and byte-identical
  for karpathy/two-tier (a karpathy enrich/manifest regression test pins this; intersects R-3's
  "enrich path stays valid"). Separately, `ManualSourceAdapter.fetch` is used DIRECTLY (not via
  `upsert_one`) by `wiki-query`/`wiki-verify-multi`/`benchmark` to file host-only compounding
  pages (`_queries/`, `_verifications/`); R-1 does NOT touch those call sites — their
  page-filing layout-awareness is an out-of-scope residual (**Q-024-residual-1**, flagged not
  silently changed). **Q-024-residual-2 — RESOLVED by TASK 030 (UC-30-3 A4)**: the original
  residual was `derive_discovered_page`'s case-SENSITIVE `full_match` vs `iter_pages`' concrete-FS
  `vault_root.glob` (case-insensitive on macOS/Windows). The 030-05 single-pass walk made
  `iter_pages` case-sensitive too (the `_PatternState` matcher uses `fnmatch.fnmatchcase`) — the
  walk↔single-file parity gap is CLOSED; both sides now share one matcher semantics. A custom
  layout relying on a case-mismatched literal glob now misses CONSISTENTLY on every platform
  (the enumerated Q-030-2 v4 delta-i, pinned by descent-table + engine-level tests) instead of
  platform-dependently. The `disc=None` fallback uses the resolved layout's `type_mapping` (an off-glob
  file reindex never indexes can be upserted → self-heals on the next `reindex --full`). A
  malformed/empty operator glob is `full_match`-`ValueError`-guarded (fail-soft, never escapes the
  exit-6 envelope). **Zero DDL** (`user_version` 5).
- **Q-024-2 (TASK 024 / R-2 — FTS indexes the FULL body, not `body_excerpt[:1000]`; resolves
  OQ-1).** `pages_fts` is an **internal-content** FTS5 table whose `AFTER INSERT/UPDATE`
  triggers index `new.body_excerpt` (`sql/wiki-index-v2.sql:358-389`), and `body_excerpt =
  normalize_body_for_fts(body)[:1000]` (`reindex.py:294`, `wiki_index_upsert.py:101`). So the
  **search corpus is only the first 1000 chars** — a term deeper in a long summary is unfindable
  (dogfood: `"дофамин"` past char 1000 → no hit). **RESOLVED → zero-DDL (Option B):** drop the
  `[:1000]` slice at the two write sites so `body_excerpt` stores the **full normalized body**
  (= the FTS corpus); the triggers are unchanged. **Display stays bounded** — every search
  result's shown text is `snippet(pages_fts, -1, …, 16)` (a ~16-token match window); grep
  confirms **no consumer renders `pages.body_excerpt` raw** (the Page field is populated but
  only `snippet()` is displayed; `wiki-verify-multi` computes its OWN excerpt from `file_path`
  via `_EXCERPT_CHARS`, not the column). So AC-2.3's "display length contract" holds at the
  *display* surface (the column is an internal corpus, not a display surface). **Rejected —
  Option A** (new `body` column + trigger over it, keep `body_excerpt` as the 1000-char slice):
  cleaner separation but `apply_schema` is `CREATE TABLE IF NOT EXISTS` only (no auto-ALTER) →
  needs a migration helper + `user_version` bump, against the TASK-012..022 zero-DDL posture for
  a column with no raw display consumer. **Rejected — Option C** (`content=''` contentless FTS):
  breaks `snippet()`. **Migration: none** — `user_version` stays 5; existing DBs gain full-body
  search on the next `reindex` (Class-B repopulation, ADR-002 §D8 — not a drop-from-scratch).
  `body_excerpt`'s documented role becomes "full normalized FTS body" (column name retained to
  stay zero-DDL; `models.py`/`base.py` docstrings updated). **Cost:** `pages.body_excerpt` + the
  internal-content FTS index each store the full body (acceptable at personal-vault scale; noted).
- **Q-024-3 (TASK 024 / R-3 — PARA-native ingest guidance; docs only).** `wiki-enrich`/vendored
  `wiki-ingest` writes Karpathy `_sources/_concepts/_entities` at the vault root and needs a
  two-tier course-root — wrong for a PARA (`obsidian-personal`) vault. **RESOLVED (docs):**
  `workflows/wiki-sync.md` Step 4b states that on a non-Karpathy layout the generated summary is
  filed as a **note in the target folder + indexed via the (now layout-aware, Q-024-1)
  `wiki-index-upsert`/`reindex`**, NOT enriched into root `_sources/`; Step 4c notes `upsert` is
  layout-aware post-R-1; the Karpathy `_sources`/`wiki-enrich` path is documented as **still
  valid for Karpathy/two-tier vaults** (guidance is layout-conditional, not "never enrich").
  Mirrored in the `CLAUDE.md` vault template / `README` pointer. No code/schema change;
  `no import anthropic`. (Out of scope, user-owned elsewhere: the pptx→markdown extraction step.)
- **Q-024-4 (TASK 024 / R-4 — D2a provenance NFC/NFD normalisation; dogfood #3 finding,
  folded into TASK 024).** A Cyrillic-named raw source (`Кейс Ярли общая преза.pptx` — `й`
  decomposes) re-converted on EVERY `wiki-sync scan` despite an existing, citing summary.
  Root cause: `_resummarize.summary_exists` compared `cand.rel` — which the filesystem walk
  yields in **NFD** on macOS (HFS+/APFS store decomposed) — against the D2a citation set built
  from frontmatter `sources:`, which is **NFC**; the two Unicode forms are unequal so provenance
  missed (ASCII YouTube-id transcripts were unaffected; dogfood #2 had masked it via the
  `source_state` marker). **RESOLVED:** NFC-normalise BOTH sides at the D2a comparison boundary
  (`unicodedata.normalize("NFC", …)` on the cited set + the target) — localised to D2a because
  D1 `source_state` is NFD-on-both-sides (self-consistent: set + get both use the walked `rel`)
  and D2b mirror is FS-vs-FS. Verified end-to-end: the pptx now `skip:summary-exists:provenance`,
  zero `convert+ingest` remaining. Regression `test_gate_d2a_provenance_nfc_nfd`. **Zero DDL**
  (`user_version` 5), no new deps. **1103 pytest, mypy strict.**

- **Q-025-1 (TASK 025 / R-1+R-2 — installer index_db pre-write guard + error-contract
  unification; adoption-currency audit).** `wiki-init` validated an `index_db` flag value with
  only `_validate_index_db_rel` (a YAML-injection check that an absolute path PASSES), wrote it
  into `WIKI_SCHEMA.md` via `_ensure_index_db`, and only THEN — at `build_repo_config →
  resolve_index_db_path` — rejected an ungated absolute path, leaving a **half-applied Class-A
  mutation** on a failed command. **RESOLVED:** the path-safety validation (NUL / absolute→
  `WIKI_ALLOW_ABSOLUTE_INDEX_DB` gate / relative symlink+escape) is extracted from
  `resolve_index_db_path` into a **shared pure validator** `config_loader.validate_index_db_value(val,
  vault_root)`; `wiki-init` calls it **before** `_ensure_index_db` writes (pre-write guard, mirroring
  the existing fail-fast for the U+0085 injection case), so a rejected `index_db` never touches the
  file. The validator stays the single source of truth (`resolve_index_db_path` now delegates to it).
  Error contract unified: `INVALID_INDEX_DB` is exit **6** / `field: "index_db"` at every site
  (was exit 2 / `index-db` in `wiki_init.py`, exit 6 / `index_db` in `_common`); the module
  docstring exit-code legend gains exit 2 (INVALID_VENDOR, INDEX_DB_ALREADY_DECLARED). No DDL; no
  behaviour change for valid inputs. New regression in `tests/test_cli_local_db_resolution.py`
  (ungated-absolute → exit 6 + schema **unchanged**).

- **Q-025-2 (TASK 025 / R-3+R-4 — obsidian-personal built-in adequacy; back-compatible
  additive).** The PARA built-in silently dropped a note carrying a summary subtype absent from its
  `type_mapping` (dogfood: `tutorial-summary` → UnmappedTypeError) and had no `ignore` for the
  `_raw`/`.staging` scratch trees its companion `wiki-sync` already prunes (`_sync.py`
  `_EXPLICIT_PRUNE_RELDIRS`), so raw scratch markdown could enter the search index. **RESOLVED:**
  `type_mapping` pre-maps the common summary family (`tutorial-/article-/book-/video-/podcast-/
  course-summary` → `db_type: summary` + a distinguishing tag — purely a tag distinction, all route
  to `summary`, so zero re-classification risk); `ignore` adds `**/_raw/**` + `**/.staging/**`
  (raw/staging markdown stays out of the search index at ANY depth). **Note (vdd-multi logic MED):**
  this is INTENTIONALLY BROADER than — and distinct in purpose from — `wiki-sync`'s own walk, which
  prunes only `_raw/.staging|.locks|failed` and otherwise INGESTS top-level `_raw/` to distil it;
  the search index excludes ALL raw markdown (undistilled) while the sync walk distils it — they
  deliberately disagree on `_raw`. `_raw`/`.staging` are reserved scratch-dir names under this
  layout. Both are **additive** — they never change an
  already-indexed page's type/slug/project and do not touch Karpathy/dev-project (golden-anchor
  byte-identity preserved). `_transcripts` is deliberately NOT ignored (it holds the distilled
  `.txt` that `wiki-sync` ingests; `.txt` is already excluded by `file_extensions: ['.md']`).

- **Q-025-3 (TASK 025 / R-5 — layout-aware `CLAUDE.md` agent template).** `_write_agent_files`
  rendered the single Karpathy-centric `CLAUDE.md.tmpl` for EVERY `--layout`, documenting
  `_sources/_concepts/_entities`, promote/demote, and a rebuild step hardcoding `rm
  "$HOME/Library/Application Support/wiki-index/global.db"` — actively wrong for a `dev-project`/
  `obsidian-personal` vault (no Karpathy tiers; a local-`index_db` vault's DB is elsewhere).
  **RESOLVED:** (a) the Karpathy template's rebuild snippet drops the `rm` (a `wiki-reindex --full`
  rebuilds from Class-A without manually deleting any DB — and resolves the declared `index_db`);
  (b) a layout-aware template `CLAUDE.layout.md.tmpl` (for the existing-tree layouts: reindex/upsert
  in place, `.wiki/{layout,sync}.yaml` tuning, lookup-priority, no `_sources`/promote) is selected
  per `--layout` in `_write_agent_files` (Karpathy family → `CLAUDE.md.tmpl`; non-Karpathy →
  `CLAUDE.layout.md.tmpl`). Vendor mapping in `templates/agent-files.yaml` unchanged for the
  Karpathy default; the layout switch lives in the renderer.

- **Q-025-4 (TASK 025 / R-6 — `basename` provenance match documented as a first-class mode; docs
  only).** The `match: basename` mode basenames BOTH the cited `file:` value AND the walked raw
  target (`_resummarize.py` L156-170), so it matches summaries citing by basename OR by full
  vault-rel path — the **correct** choice when source basenames are globally unique (YouTube-id
  transcripts) or an existing corpus cites by basename. It was undocumented (ARCHITECTURE Q-019-10
  called it an "orphaned knob"). **RESOLVED (docs):** schema `ProvenanceRef.match` gains a
  description; the manual + `workflows/wiki-sync.md` state the choose-which rule; this Q softens the
  "orphaned knob" framing — `basename` and `vault-rel-path` are equally-supported modes, `basename`
  preferred for globally-unique/basename-cited corpora, `vault-rel-path` (the default) for
  writeback-controlled corpora wanting strict full-path equality. **The default is NOT changed**
  (back-compat: a default flip could merge distinct same-basename raws elsewhere). Also documents
  the `paths`/`ref_extraction` = REPLACE merge asymmetry (R-7) in the schema/manual and the
  custom-`type:` → per-vault `type_mapping` override need (R-8).

- **Q-026-1 (TASK 026 — `wiki-init` ships the vault `.claude/settings.json`).** TASK 025 added
  the Claude Code permissions template (`templates/vault.claude-settings.json`) that stops a vault
  re-confirming every `wiki-*`/safe command, but the operator had to copy it by hand. **RESOLVED:**
  `templates/agent-files.yaml` lets a vendor declare an optional `settings_file` + `settings_template`
  (claude → `.claude/settings.json` + `vault.claude-settings.json`); `_load_vendor_config` returns a
  third per-vendor `settings` map; `_write_agent_files` (both `scaffold_new` + `register_existing`)
  drops it where the `--vendor` agent file is written. Three invariants: (a) **VERBATIM copy** — the
  JSON carries a `$schema`, so it is `atomic_write_text`-copied, NEVER `string.Template.substitute`-d
  (which would `KeyError` on `$schema`); (b) **INDEPENDENT of the agent file** — the prior
  `target.exists() → continue` short-circuit was refactored to an if/else so an existing `CLAUDE.md`
  no longer skips the settings write; (c) **NON-destructive** — an existing `.claude/settings.json`
  (incl. the operator's accumulated rules) is `"exists"`/untouched without `--force`, and
  `settings.local.json` is NEVER written (it stays the personal-override surface). Gemini declares no
  `settings_file` → nothing written, no `.claude/` created. Layout-agnostic (same settings for any
  layout). `.claude/settings.json` is `.json`, never indexed (file_extensions `['.md']` + dot-dir
  prune) — no SYSTEM_FILES change. **Zero DDL** (`user_version` 5), no new deps. Live-verified on the
  real test vault (settings written byte-identical, `settings.local.json` preserved). New tests in
  `tests/test_wiki_init_flows.py`; the envelope-shape assertions updated (claude agent_files now also
  carry `.claude/settings.json`). **1114 pytest, mypy strict.**

- **Q-028-1 (TASK 028 — the two-mechanism search-normalization split).** The FTS layer is
  `unicode61 remove_diacritics 2`: no stemming, no ё/е fold. TASK 028 broadens recall WITHOUT a
  tokenizer/DDL change by splitting the problem into two orthogonal mechanisms with different
  on/off semantics. **(1) Normalization (ALWAYS on, NOT `--exact`-gated):** fold `ё→е`/`Ё→Е` (case-preserving) on
  BOTH sides — the index body corpus (`body_excerpt`) and every query term. This is corpus
  canonicalisation: both sides agree → `ещё`/`еще` are one token. **(2) Broadening (default on,
  `--exact`/`--no-stem` disables):** per-term snowball stem + prefix `*`. Rationale (OQ-1): the two
  production misses were *default* searches, so auto-broaden is the point; `--exact` is the
  precision escape hatch. This split resolves the F-3 contradiction (a "byte-identical `--exact`
  anchor" is impossible once the index is ё-folded) — the corrected anchor is **byte-identical for
  ё-free content, folded-consistent for ё-content**. **Zero DDL** (`user_version` 5); the body fold
  takes effect on the next `wiki-reindex --full` (Class-B rebuild, ADR-002 §D8) — stemming + the
  query-side ё-fold work immediately, so only *body* ё-recall is reindex-gated (OQ-2).
- **Q-028-2 (TASK 028 — engine, script generality, typing).** New pure module
  `scripts/wiki_index/query_normalizer.py` over a thin typed wrapper `scripts/wiki_index/_snowball.py`.
  Per-term: fold ё → **detect script** (Cyrillic→`russian`, Latin→`english`, any other script /
  digits / too-short→**literal**, never mangled) → stem (when broadening) → guard. Generalises to
  other languages by script, NOT Russian-only (snowball ships **36** stemmers, pure-Python); a
  per-vault `language:`-driven Latin-stemmer override is a documented future extension; `--vaults all`
  works because detection is per-term, not per-vault. **MIN gate on POST-stem length** (OQ-3 / F-6):
  if `len(stem) < MIN` (≈3 Cyrillic) emit the term literal (no `*`) — a long word collapsing to a
  2-char stem must NOT become a catch-all `аг*`. **Idempotency via the `*`-guard, not the stemmer**
  (F-4): snowball is NOT idempotent (`осведомлен`→`осведомл`), but re-running the FTS rewrite on its
  own output is a no-op because every produced term ends in `*` (and an already-`*` term is passed
  through). **Typing (F-7):** `snowballstemmer` ships no `py.typed`; the single
  `# type: ignore[import-untyped]` lives in `_snowball.py` (a per-language stemmer cache + typed
  `str→str` facade), keeping the rest of `scripts/` strict-clean — no `types-snowballstemmer` exists.
  **Determinism (C1):** the dep is pinned EXACT `snowballstemmer==3.1.1` (not `>=`) because a stem
  change alters the retrieved **hit set**, which (not the stem text itself) is what feeds
  `wiki-query`'s `question_hash`; a silent bump would change the hit set → break filed-answer
  reproducibility — a stem-algorithm change is a deliberate, re-query/reindex-affecting event.
- **Q-028-3 (TASK 028 — TWO distinct call sites, corrected composition).** The shared primitive is
  the per-term core; the two consumers wire it DIFFERENTLY (F-2 — they must NOT collapse to one):
  **(a) `wiki-search`** — an FTS-expression-aware lexer (F-9) walks the raw MATCH expr and stems+folds
  ONLY bare, sigil-free, unquoted content tokens, passing through verbatim: quoted phrases, paren
  groups, `NEAR(...)`+args, column filters (`col:`, `{a b}:`), the uppercase operator keywords
  `AND/OR/NOT/NEAR`, any already-`*` term, and `^`/`-`/`+`-sigil terms. **Composition (OQ-4 / F-1,
  corrected):** stem the bare query FIRST, then OR-in the (quoted, folded, **unstemmed**) alias
  surfaces → `(<stemmed-folded-raw>) OR "alias1" OR "alias2"` — NOT `stem(expand_query(raw))`
  (`expand_query` quotes the WHOLE raw query, so a quote-preserving stemmer would broaden nothing on
  an alias hit). **(b) `wiki-query`** — `_build_match_query` already `fts_quote`s every token, so the
  stem happens at the TOKEN level BEFORE `fts_quote`, emitting `"<stem>"*` (valid FTS5); alias
  surfaces use the raw token for lookup, folded + quoted. The **DF-1** `OperationalError` fallback is
  kept in shape (fold-aware: re-runs the literal folded quoted phrase), and the lexer is proven never
  to PRODUCE an un-parseable expr from a valid input. `search_pages` (the DAL) is UNCHANGED — the
  rewrite happens above it; no DAL signature/contract change. **Pre-existing perf note
  (vdd-multi perf MED, NOT a TASK-028 regression — verified the loop pre-dates this task on
  `main`):** `wiki-query._build_match_query`'s alias expansion is a V×T fan-out
  (`for vid: for tok: expand_query_aliases`), invisible at 1–2 vaults but an N+1 on
  `--vaults all` over a large fleet. TASK 028 kept the identical loop (added only the per-token
  stem). A prefetch (`list_all_aliases` per vault → in-memory probe) is a future perf follow-up;
  `wiki-search`'s `alias_surfaces` already does the cheaper one-lookup-per-vault shape.
- **Q-028-4 (TASK 028 — `wiki-query` question_hash symmetry; C1).** `_question_hash` is recomputed in
  `apply` (mismatch → `QUESTION_CHANGED`), so `--exact`/`--no-stem` is threaded SYMMETRICALLY through
  `prepare` AND `apply` via the shared `_retrieve` (precedent: the existing `--no-expand-aliases`).
  Verified semantics: prepare-default→apply-default reproduces the hash; prepare-default→apply-exact
  → `QUESTION_CHANGED` (documented, expected, not a bug); the stemmer is byte-stable for the pinned
  version. The RAG path's stemming is independently eval'd (not assumed from the wiki-search tests).
- **Q-028-5 (TASK 028 — ё/е index fold site + display semantics).** The fold rides
  `normalization.normalize_body_for_fts` → `body_excerpt` (the route taken by `wiki-index-upsert` +
  both `reindex` paths through `_build_page`; the FTS triggers copy `body_excerpt` verbatim, so
  folding at the row-write site needs no trigger change — zero DDL). `pages.title`/`tldr` are NOT
  folded → titles keep `ё` (display fidelity); residual (vdd-multi logic MED, F-5 / R-028-4): only
  `body_excerpt` is folded, but `pages_fts` ALSO indexes `title`, `tldr`, and `tags` UNFOLDED while
  the query is always folded → a **ё-form** query for a term living ONLY in a `title`/`tldr`/`tag`
  (no body occurrence) is a narrow ё-form-only recall regression vs pre-028, and `--exact` is
  byte-identical only for ё-FREE content there. The е-form query (common Russian typing) is
  unaffected; the body case is improved. Full symmetry needs trigger DDL (`tags` ride the trigger's
  `json_extract`) → out of zero-DDL scope; folding `title`/`tldr` into the FTS shadow would also need
  the trigger (folding `pages.title` itself would regress display). Alias resolution stays
  ё-sensitive (exact-match) — a future fold-aware lookup is a documented consistency follow-up.
  `snippet()` IS a real
  display consumer of `body_excerpt` (corrects the spec's "no display consumer" wording) → result
  snippets render the е-form — a deliberate, accepted cosmetic change for ru ё/е; `wiki-verify-multi`
  reads the raw FILE (`_read_page_text`), so its excerpts keep `ё` (unaffected). Layout-agnostic
  (applies to every layout incl. karpathy) — the one intentional indexing delta vs golden-anchor
  byte-identity, which otherwise holds for ё-free content.
- **Q-028-6 (TASK 028 — docs currency, R-028-5).** Only `skills/wiki-search/SKILL.md` (4 claim sites +
  version + Contract) and `skills/wiki-search/evals/evals.json` (eval #4 + description) assert the
  now-false "no stemming" / "ё is NOT folded" facts as current behaviour or prescribe manual
  compensation; both are corrected (manual stem-prefix recast as a fallback/explicit-control lever).
  Evals #1-#4 are reconciled with default-on stemming (eval #2 КПЧ↔ПКЧ transposition is NOT a
  morphological variant → stemming does NOT fix it → it stays the fallback-broadening + anti-
  hallucination contract; #3 grounding kept). Manuals (EN+RU), quick-ref (EN+RU), this ARCHITECTURE,
  and README carry no false claim to delete but gain the new behaviour. The `tokenize=` DDL string
  (`sql/wiki-index-v2.sql` L366, README L142) stays UNCHANGED — zero-DDL invariant.
- **Q-029-1 (TASK 029 — eval grading without a Python grader).** **RESOLVED (default; task-review
  finding #2 incorporated):** v1 grades agentically/manually, BUT every `evals.json` case carries
  machine-checkable expectation fields (`expect_routes_to`, `expect_command_substring`,
  `expect_command_absent` [e.g. `mv`], `expect_refusal`, `expect_tier_cited`) + a per-class
  deterministic checklist in `evals/README.md` — PASS/FAIL stays replayable on an Obsidian minor
  bump; a `grade.py` (TASK 009 pattern) is a follow-up only if eval volume grows.
- **Q-029-2 (TASK 029 — Universal-skills cross-publication).** **RESOLVED: DEFER.** The skill is
  designed standalone-capable (the §2.2 coherence invariant self-disables on unregistered vaults),
  so a later copy is mechanical; no dual-home sync policy needed now.
- **Q-029-3 (TASK 029 — `wiki-init` template mention).** **RESOLVED: optional non-MVP bead**
  (TASK 029 I-4.3) on the TASK 025/026 adoption surface; dropped without ceremony if the task
  runs long.
- **Q-029-4 (TASK 029 — `version` listed-but-unrunnable anomaly, F-3).** **OPEN** (investigate at
  dev; non-blocking — the availability probe avoids `version` entirely and uses `obsidian help`).
  Working hypothesis: registration lag or plugin-gating misreport in 1.12.7. The finding feeds the
  command-reference's `[core]`/`[plugin-gated]`/`[doc-only]` tagging.
- **Q-029-5 (TASK 029 — skill tier).** **RESOLVED: `tier: 2`** (load-when-needed), matching the
  `wiki-search` frontmatter convention.
- **Q-030-1 (TASK 030 — P-1 acceptance gate vs the no-CI reality).** The P-1 issue file gates the
  bulk-tx fix on "`enforce_slos` testing at N=10k wired into CI" — but the repo has NO CI at all
  (no `.github/`; task-001-33 scoped the workflow file out). **RESOLVED (default):** the gate is
  reinterpreted as (i) an opt-in `@pytest.mark.slow` + env-gated (`WIKI_BENCH_SLO=1`) SLO-enforcement
  test at `--n 1000`, (ii) a documented runbook line for the manual `--n 10000 --enforce-slos` run,
  (iii) a one-time committed 10k before/after measurement in §8.4. P-4 (the CI scale gate proper)
  stays OPEN — its scope is unchanged by this task.
- **Q-030-2 (TASK 030 — single-pass walk semantics envelope).** **RESOLVED (v2, reversed by the
  arch-consistency review):** the rewrite reproduces `Path.glob` discovery semantics EXACTLY —
  incl. the empirically-confirmed 3.14 symlink asymmetry (`**` never descends symlinked dirs; an
  explicit non-`**` segment can; leaf file symlinks discoverable). The v1 idea (blanket
  symlink-dir refusal as a "security-positive tightening") was REJECTED: it would silently
  orphan-delete previously-indexed rows under a symlinked area dir, and in-vault symlinks are
  deliberately tolerated (TC-UNIT-02). The enumerated behavior deltas (**v4** — extended by the
  030-04 Sarcasmotron empirical probes): (i) literal glob components match case-SENSITIVELY
  everywhere (today: FS-dependent), which RESOLVES the Q-024-residual-2 walk↔single-file parity
  gap — both sides now share one matcher; (ii) traversal cost (pruning) — the match SET is
  preserved; **(iii) `..` segments in operator globs go EFFECTIVELY dead** (today
  `Path.glob('v/../*.md')` happily traverses parent dirs, escaping pattern anchoring; under the
  walk, `os.scandir` never yields a child named `..`, so the position can never advance past it —
  vault-containment-positive, TASK-022 posture; pinned by descent + file-match unit rows; same
  family: an ABSOLUTE glob — out-of-contract per the schema's "vault-root-relative" — today
  CRASHES `Path.glob` with `NotImplementedError`, under the walk it goes silently dead (the `'/'`
  segment never matches a scandir name) — 030-05 pins this with a conformance case so an
  operator typo empties the entry loudly in tests, not silently in production; `glob: '.'` is
  the same family — old engine `ValueError`, walk silently-dead — pinned 030-05); **(iv) trailing-slash
  globs keep their 3.13+ dirs-only semantics explicitly** (`_PatternState.dirs_only` — zero file
  matches, exactly like today's enumerate-dirs-then-die-on-`S_ISREG`; `PurePosixPath.parts`
  would otherwise silently eat the slash). A fifth probe (zero-segment trailing `**` after a
  final explicit segment, `a.md/**` vs FILE `a.md`) was a genuine matcher BUG — fixed
  (`matches_file` requires the explicit final segment to BE final), not enumerated. **v3 (arch+plan gate):** parity is achieved via
  **per-pattern alive-sets** threaded down the walk — a pattern stays alive across a SYMLINKED dir
  component only if it consumes it with an explicit (non-`**`) segment; descent = alive-set ≠ ∅;
  **attribution = first match among patterns alive at the containing dir** (a boolean any-pattern
  descent + symlink-blind global matching would inflate the match set AND flip attribution on
  overlap+symlink operator layouts — the spec-validator H-1 counterexample `Areas/**/*.md` +
  `Areas/*/notes/*.md` with `Areas/link` symlinked is the pinning fixture). The walk is ITERATIVE
  (explicit stack) — a Python-recursive scandir would add a `RecursionError` DoS class (TASK 018
  deep-nesting precedent); pathological-depth test pinned. The single-file twin
  `derive_discovered_page` stays symlink-blind (sees one rel path) — pre-existing upsert-path
  asymmetry recorded, not widened.
- **Q-030-3 (TASK 030 — fresh-vault `--delta` widening).** With the new-path predicate, the first
  `--delta` after registration ingests the whole vault (cutoff = `registered_at`; previously only
  files newer than registration). **RESOLVED: accept + document** — the correct reading of "index
  reflects disk"; visible via the additive `new_path_ingested` envelope field. **Cost claim
  corrected post-`/vdd-multi` (PERF-030-M2, verifier-confirmed):** a whole-vault delta is ~1.7×
  SLOWER than the chunked `--full` at 2k (763.6 vs 446.6 ms — per-file atomic txns vs K=500
  flushes; the per-file cadence is deliberate, it is what fixed the LOGIC-MED partial-write hole).
  Routine renames/small deltas: `--delta`-first stands. KNOWN bulk ingest: prefer `--full`.
  Residual filed: `docs/issues/p-030-delta-bulk-ingest-per-file-txns.md` (SEV-3, scale-gated).
- **Q-030-4 (TASK 030 — obsidian-cli skill update depth after the DF-029-1 code fix).**
  **RESOLVED (default):** the skill's coherence rule flips to `--delta`-first for rename/move
  (+ `--full` universal fallback + the swap-class caveat); re-run eval **E-07 + the routing
  canaries only** — the text delta is confined to the coherence rule, so the full 14-eval suite
  is not re-billed. All TEN live doc surfaces carrying the `--full`-for-rename rule (TASK 030
  F-12: issue file, ARCHITECTURE §2.2, ROADMAP ×2, skill ×3 files + E-07, README, 2 templates,
  2 manuals) update in lockstep at close.
- **Q-030-5 (TASK 030 — chunked-tx shape + error semantics; v3 stage-then-flush).** **Lock-hold
  (arch-review HIGH-2):** a chunk txn must NEVER span file I/O — at the SLO bound, K=500 pages of
  in-txn derivation would hold the WAL write lock ~10 s while `_connect` has only the default 5 s
  busy timeout → "database is locked" for any concurrent writer on a shared `global.db`
  (multi-vault) and unbounded holds on cold iCloud reads (TASK 022 OQ-5). **Resolved:** the loop
  STAGES a chunk outside any txn (all `derive_indexed_page` I/O → a buffer bounded by K=500 pages
  ∧ `REINDEX_TX_CHUNK_BYTES` 32 MiB, full-body pages since TASK 024), then FLUSHES DML-only under
  one `BEGIN IMMEDIATE` (ms-scale lock). Error semantics: derivation errors are caught at staging,
  OUTSIDE the txn → `skipped`, zero DML (STRICTLY better isolation than today); mid-flush DML
  errors are statement-atomic — the file's partial DML commits with the chunk while the file lands
  in `skipped` (equivalent end-state to today's committed-partial), pinned by an error-path test
  (injection: helper raises for one slug); fatal mid-flush (injection: monkeypatched COMMIT —
  the per-file catch never sees it) → chunk ROLLBACK + `finish_batch_run("failed")`, FTS row count
  stays equal to `pages`. Commit accounting: only **per-page** commits collapse (~2N → ceil(N/K));
  per-log-event and step-2.5 autocommits are fixture-dependent and stay — the AC-2.4 exact count
  runs on a constrained fixture (zero log events, fixed entity/alias counts). The within-batch
  equal-hash collision corner is a deliberate delta: the bulk path's ON CONFLICT (no pre-SELECT)
  makes the LAST file's `file_path` win, ALIGNING the DB with the TASK-021 `slug_collisions.kept`
  record (today's pre-SELECT "unchanged" short-circuit misreports). The pre-SELECT skip was chosen
  for this alignment, NOT for perf (an in-txn PK SELECT is µs — recorded so the next reviewer
  doesn't reopen it). **Delta-side sibling (arch-review HIGH-1):** the `upsert_page` "unchanged"
  short-circuit returns BEFORE any UPDATE, so a new-path re-ingest of unchanged content would
  never refresh `pages.file_path` → perpetual re-detection. R-030-1 therefore issues a targeted
  `UPDATE pages SET file_path=?, last_modified=? WHERE …` on the `is_new_path ∧ "unchanged"`
  outcome (zero-DDL, one statement) — convergence pinned by AC-1.9 (second delta = true no-op).
- **Q-030-6 (TASK 030 — descent predicate as a first-class requirement).** The naive single-pass
  walk would traverse `.obsidian/`/`.git/`/attachment trees on Karpathy vaults (whose per-glob walk
  today never touches the root tree — a §3.5-documented property; `karpathy.yaml` has `ignore: []`).
  **RESOLVED:** R-030-6 — descend a directory iff its alive-set is non-empty under the **PROPER
  prefix** rule (the pattern can still consume ≥1 further segment — a dir fully matching a
  file-glob like `*.md` does NOT descend) AND it is not covered by a prunable `<prefix>/**`-shaped
  ignore glob. Karpathy keeps "root **subtrees** never walked" BY CONSTRUCTION (instrumented
  fat-fixture test; footnote: the rewrite adds exactly ONE root scandir that today's
  literal-anchored pathlib joins avoid — covered by the lean ±5% check); obsidian-personal gains
  real ignore-pruning (`**/_raw/**`, `.obsidian/**` subtrees never scandir'd — previously only
  post-walk string-filtered). Verified per-layout by the arch-review: karpathy/dev-project/
  obsidian-personal have NO under-descent case (the ANY-alive descent is a traversal superset of
  today's per-glob walks); the 030-04 property test asserts full **DiscoveredPage-tuple** equality
  (not just reachability) against the old engine on diverse fixtures incl. trailing-`**`,
  mid-`**`-then-literal, a directory literally named `foo.md`, dot-files, and symlink topologies.
- **Q-031-1 (TASK 031 — classification vs the event graph).** The "CybOS 2.0" vision wants typed
  classes AND typed edges; these are independent engine concerns. **RESOLVED:** Phase 1 ships
  *classification* only — tag-route the 7 classes onto the existing db_type enum (zero DDL). The
  *event graph* (typed page-to-page edges) is deferred Phase-2 (Q-031-5 / ROADMAP R-13). Promoting
  every class to a first-class db_type was REJECTED (worst cost/value: max schema churn, still no
  graph). See ADR-003 D1/D4.
- **Q-031-2 (TASK 031 — db_type routing of the 7 classes; is zero-DDL achievable?).** **RESOLVED:
  yes** — every class routes onto an existing enum value + a filterable tag: decision/risk/incident/
  hypothesis→`research`, requirement→`brief`, fact→`concept`, event→`summary` (closest "timestamped
  narrative record" bucket). No class forces a new db_type; `pages.type` CHECK + `TypeMappingEntry.db_type`
  enum untouched (`user_version` 5). **Trade-off recorded:** the tag lands in the `tags:` LIST, and
  `wiki-search --where` is scalar-equality (`sqlite_repository.py:547-562`), so precise per-class CLI
  filtering is `--types <db_type>` (bucket) + FTS on the tag word, NOT `--where tag=decision`. A
  list-membership `--where` is a candidate follow-on (ROADMAP), not in Phase-1 scope.
- **Q-031-3 (TASK 031 — both homes vs one; where do the classes live?).** **RESOLVED: both** —
  `dev-project.yaml` gains the 7 `type_mapping` entries only (opt-in via explicit `type:`; its
  `paths[]` untouched), AND a new built-in `cybos` layout ships the full folder structure. Per-project
  bespoke types use the existing `<vault>/.wiki/layout.yaml` `type_mapping` **UNION** override (Q-012-f /
  TASK 025 R-7) — no fork, no Python. See ADR-003 D2.
- **Q-031-4 (TASK 031 — de-hardcode the layout registry without breaking strict-schema load).** The
  operator flagged `wiki_init.py:50-51` (`_LAYOUT_CHOICES`/`_KARPATHY_LAYOUTS`; IDE-selected 50-53) as hardcoded. **RESOLVED:** add two OPTIONAL additive
  `LayoutConfig` keys `aliases: [string]` + `init_scaffold: {two-tier, none}` (default `none`); the
  registry helpers (`layout_choices`/`is_two_tier_scaffold`/`resolve_alias`) read the **raw built-in
  YAML** (the 3 top-level keys), NOT the frozen `LayoutConfig` dataclass (`_build` carries no arbitrary
  keys), and are **cached** (parse built-ins once — does not worsen R-X1-CFG-COST). **Ordering (sharp
  edge):** because `LayoutConfig` is `additionalProperties:false` (`schema:148`), the schema amendment
  MUST land before/with the karpathy.yaml key additions, else `_validate` rejects every layout at load.
  The keys are init-only — they do not touch discovery/pages/refs, so the Karpathy golden anchor +
  `test_karpathy_config_matches_layout_constants` stay green. See ADR-003 D3.
  **Post-ship `/vdd-multi` (3 critics + adversarial verify, all findings empirically reproduced):
  converged with 5 LOW findings — 3 FIXED, 2 accepted-residual, no MED/HIGH.** Fixed: the registry
  now (a) globs in SORTED order + raises on a duplicate alias / an alias shadowing a stem (was
  glob-order/host-dependent — the de-hardcode's own "drop-in a new layout" path was the trigger),
  (b) TYPE-validates the two registry-only keys at build (`aliases` must be a list — a bare string
  would otherwise iterate into per-char aliases; `init_scaffold` ∈ {two-tier, none}), raising loudly
  on a built-in authoring slip, and (c) builds the registry ONCE in `is_two_tier_scaffold` (was 2×).
  **Accepted residuals (LOW, documented):** an absent `LAYOUTS_DIR` makes `layout_choices()` empty
  (a broken-install precondition — the engine fails at real load regardless; re-hardcoding a fallback
  would defeat R-031-3); and `resolve_alias` adds one `scandir` + per-built-in `stat` per
  `load_layout_config` (the deliberate drop-in-correctness cost — bounded by the ~handful of
  built-ins, microseconds; the per-file regex recompile dominates R-X1-CFG-COST). Guards pinned by
  `tests/test_layout_config.py::test_registry_rejects_{duplicate_alias,alias_shadowing_stem,non_list_aliases,bad_init_scaffold}`.
- **Q-031-5 (TASK 031 — the event graph: build now or defer?).** **RESOLVED: defer to a separate task**
  (ROADMAP R-13). Typed edges (`implements`/`supersedes`/`caused-by`/`relates-to`), a `page_entity_refs.ref_type`
  extension, reindex frontmatter-edge extraction, and schema v5→v6 follow the TASK 008 precedent. The
  edge keys are **reserved (authored-but-inert)** in the Phase-1 templates so the canonical Markdown
  already carries the data — Markdown canonical, DB rebuildable (ADR-002 §D8). See ADR-003 D4.
- **Q-032-1 (TASK 032 — the v6 `ref_type` set; inverse-closed; relates_to home).** **RESOLVED:** add 6
  inverse-pair values (`implements`/`implemented-by`, `supersedes`/`superseded-by`, `causes`/`caused-by`)
  and **reuse the dormant symmetric `related`** for `relates_to` (NO parallel `relates-to`). Explicit
  key→ref_type map (underscore key → hyphen enum); each member is both authorable + derivable. ADR-004 D1/D2.
- **Q-032-2 (TASK 032 — where inverse edges are written, given M-1).** The inverse row lives on the
  *target* page; `_replace_refs_in_txn` is per-page delete-all (`sqlite_repository.py:386-429`) so it
  **cannot** ride the source's single `replace_refs` (task-review C-1). **RESOLVED:** forward edges ride
  the per-page write (M-1 intact, `_edge_refs` unioned into `_frontmatter_refs`); inverses are a **GLOBAL
  post-pass** — a sibling of the Step-2.5/AM-3 alias pass (`reindex_full:842-879`), ordered AFTER
  canonicalization so both endpoints are canonical; idempotent (PK dedup), no self-loops,
  bidirectional-author convergence. ADR-004 D3.
- **Q-032-3 (TASK 032 — delta-inverse-closure; `reindex_delta` has no global ref pass).** **RESOLVED
  (refined in dev for provenance-safety):** delta runs inverse **ADDITIONS only, SCOPED to the TOUCHED
  source pages** (`_derive_inverse_edges(..., source_slugs=touched)`, gated on `touched or deleted`) — an
  added/changed edge's inverse appears on the (un-walked) target. Inverse **REMOVAL is deferred to `--full`**:
  a stored `(B→A, inv)` row is indistinguishable from an edge B AUTHORED directly (same `ref_type`, no
  provenance column), so deleting "stale" inverses could clobber an authored edge — and the symmetric
  derivation would RESURRECT a removed forward (inverse-of-the-inverse) if the pass touched un-walked pages,
  which is exactly why additions are scoped to touched sources. Delta never deletes an inverse; `--full`
  (wipe+rebuild) is authoritative — documented A5-class residual, NOT `delta==full`. ADR-004 D4.
- **Q-032-4 (TASK 032 — graph-aware RAG default + determinism).** **RESOLVED:** `wiki-query prepare
  --follow-edges` **default OFF** (preserves today's retrieval + `question_hash` for non-opt-in use);
  depth 1 default (`--edge-depth` capped 3); neighbors appended AFTER FTS hits, sorted `(project, slug)`
  (outbound edge preferred over auto-inverse for `via_edge` provenance — as-built), deduped, **excluding
  `type=query`/`type=verification`** (mirrors `_retrieve` exclude-prior-answers);
  the expansion is folded into `question_hash` (C1 / TASK 028). ADR-004 D5.
- **Q-032-5 (TASK 032 — traversal reader surface).** **RESOLVED: a new read-only `wiki-graph` CLI** (16th)
  — `neighbors`/`chain`/`backlinks` × `--kind`/`--direction`/`--depth` (capped, cycle-safe), JSON envelope,
  injection-safe (TASK 013 posture). `wiki-search --edges` REJECTED (overloads FTS). ADR-004 D6.
- **Q-032-6 (TASK 032 — DAL read API shape).** **RESOLVED:** additive `get_backlinks(…, ref_type=None)`
  kind-filter (ABC `repository.py:221` + impl in lockstep, mypy strict) + outbound `refs_from(...)` +
  bounded `neighbors`/`chain` (depth-capped, visited-set cycle-safe); existing `idx_refs_type/entity/page`
  support them. ADR-004 D-DAL.
- **Q-033-1 (TASK 033 — list-membership `--where`; the R-13 residual).** The TASK-013 `--where`
  predicate is scalar-only (`CAST(json_extract(fm, ?) AS TEXT) = ?`), so a list field like `tags[]`
  (which carries the TASK-031 typed-class tag) never matches a single member → no clean per-class
  filter. **RESOLVED: generalize the `search_pages` per-field predicate to
  `CAST(json_extract(fm, ?) AS TEXT) = ? OR EXISTS (SELECT 1 FROM json_each(fm, ?) WHERE value = ?)`** —
  the **proven `find_pages_citing_source` shape** (sqlite_repository.py:1359, TASK 019), lifted with
  **zero new mechanism**. Keep BOTH branches (do NOT collapse to `json_each`-only): the `=` branch is the
  robust scalar fast-path the codebase already trusts, and `json_each` over a scalar yields one row equal
  to the scalar (so the OR is a strict superset for scalars, a no-op for absent fields) → **backward-
  compatible**: scalar `--status`/`--severity` result sets are unchanged. The value is **bound TWICE**
  (path+value per branch — positional `?` can't be reused across subexpressions). A scalar sugar field now
  ALSO matches a list-valued member (intended, free). **Zero DDL** (`user_version` stays 6).
- **Q-033-2 (TASK 033 — `tag=decision` UX: magic field vs sugar flag).** The operator's literal ask was
  `--where tag=decision`, but the real frontmatter key is `tags` (a list). **RESOLVED: `--where` uses the
  HONEST field name (`--where 'tags=decision'`); a separate `--tag <value>` convenience flag** (mirroring
  `--status`/`--severity`) desugars to `where_fields += ("tags", value)`. We do NOT special-case a
  `tag→tags` rename inside `--where` (surprising; would collide with a hypothetical real `tag` field). The
  injection posture (allowlist `validate_filter_field`, twice-bound params, no value echo, one-predicate-
  per-field dup guard) is unchanged and covers `tags`/`--tag` identically. Perf = the same unindexed
  json scan class as the open R-X3-MF-SCAN (SEV-3) residual; no new index, no regression.
- **Q-034-1 (TASK 034 — temporal model: new `valid_from`/`valid_to` fields vs derive from the graph).**
  The RFC proposed authored `valid_from`/`valid_to` fields. **RESOLVED (operator correction): derive,
  don't author.** `valid_to` is unknowable at authoring time and `valid_from` duplicates the existing
  indexed `pages.date`. `wiki-search --as-of DATE` computes the half-open validity interval
  `[effective_from, effective_to)` where `effective_from = COALESCE(authored valid_from, pages.date)`
  and `effective_to` = authored `valid_to` **or** the `date` of the earliest page that supersedes/
  invalidates it (the TASK 032 graph, `ref_type IN ('superseded-by','invalidated-by')`) **or** ∞.
  `valid_from`/`valid_to` survive as **optional overrides only** (future-effective / known-sunset),
  never required. A page with neither `valid_from` nor `date` is EXCLUDED from `--as-of` so
  non-temporal pages don't pollute the result. Frontmatter dates are ISO strings via `_json_safe`
  (`normalization.py`) → `json_extract` text comparison is lexicographic = chronological. SQL is a
  `COALESCE(…, p.date) <= ?` + a correlated `NOT EXISTS` successor-walk; absent `as_of` → zero SQL
  delta (back-compat, R-1c). Perf rides `idx_refs_page` + the `pages` PK, bounded by `limit`.
- **Q-034-2 (TASK 034 — edge set: one authorable direction or both).** **RESOLVED: both** (TASK 032
  parity — `_INVERSE_REF_TYPE` already carries both ways). Four new inverse-closed pairs added —
  `invalidated_by`↔`invalidates`, `activated_by`↔`activates`, `uses`↔`used-by`, `owns`↔`owned-by` —
  i.e. **8 new authorable frontmatter keys + 8 new `ref_type` CHECK values** (schema v6→v7, Class-B
  rebuild). `invalidated-by`/`superseded-by` are the edges the Q-034-1 `--as-of` walk reads. A drift
  test asserts the three code maps (`_EDGE_KEY_TO_REF_TYPE`, `_INVERSE_REF_TYPE`, `models.py`) agree
  with the SQL enum. `wiki-graph --kind <new>` traverses them with no CLI change.
- **Q-034-3 (TASK 034 — agent-memory classes: where they live).** **RESOLVED: the `cybos` layout,
  config only.** `agent`/`tool`/`workflow`/`capability`/`execution`/`pattern` → `type_mapping`
  (existing `db_type` bucket + filterable tag, TASK 031 pattern) + `paths` globs
  (`agents/**`, …) + per-type `templates/page-types/*` — **zero Python**, zero DDL beyond Q-034-2.
  Karpathy unaffected. Aggregation reporting over these (RFC-003 "fails most often") needs a new
  GROUP-BY read surface → deferred (ROADMAP).
- **Q-034-4 (TASK 034 — `/vdd-multi` + dogfood hardening).** Three findings folded in, all
  empirically reproduced before acceptance: **DF-034-1** (dogfood, SEV-2) — `wiki-graph`'s
  `--kind` allow-list was a hardcoded TASK-032 list that silently dropped the v7 edge kinds
  (`invalidates`/`uses`/… → `INVALID_KIND`); now **derived** `tuple(sorted(_INVERSE_REF_TYPE))`
  so the traversal allow-list can never drift from the extractor (single source of truth).
  **MED-1** (logic critic) — the `--as-of` successor walk JOINs the project-less `entity_slug`,
  so on a multi-project vault a same-slug page in ANOTHER project could wrongly retire P; fixed
  with the same `COUNT=1` ambiguity guard `_derive_inverse_edges` uses (conservative "stay
  active when ambiguous" — over-report, never silent retirement; aligned with the data layer;
  residual confined to the TASK-020/021 cross-project slug-collision hygiene case). **MED-2**
  (logic critic) — a datetime-valued `valid_from`/`valid_to` override broke the half-open day
  boundary (`"…T14:30:00" > "2026-02-01"`); fixed by comparing `substr(json_extract(…),1,10)`
  (the date part); `pages.date` is already a pure ISO date (unwrapped). **Perf** (perf critic):
  the `--as-of` *scalar* `json_extract(valid_from/valid_to)` branch is a co-beneficiary of a
  future generated-column/expression index — recorded against the open R-X3-MF-SCAN issue
  (the `--where` *membership* `json_each` branch is NOT; the scalar one is). No new index now.
- **Q-035-1 (TASK 035 — R-X3-MF-SCAN, which branch to fix).** Measuring the real deployments
  decided it (ADR-005): the **2493-page** `personal` vault is past the issue's ~1k trigger and
  `--tag` is used routinely → the **`tags`-membership branch is hot** (`tags` on 2493/2493
  pages). The **scalar** (`status` 59, `severity` 22 on a 413-page vault) and **temporal**
  (`valid_from`/`valid_to` on **0** pages) branches are NOT — an expression index / generated
  column there would re-introduce the exact **P-5** dead-weight the schema removed once.
  **RESOLVED: fix only the membership branch, zero-DDL, by reusing the index that already
  exists** — `pages_fts.tags` (the FTS triggers already project `json_extract(fm,'$.tags')`).
- **Q-035-2 (TASK 035 — how to reuse FTS without changing results).** **RESOLVED: "FTS
  narrows, json_each confirms."** On the metadata-only path (`not has_match`) with a `tags`
  predicate whose value has ≥1 alnum char, `search_pages` switches `FROM pages p` to
  `FROM pages_fts JOIN pages p ON pages_fts.rowid = p.id WHERE pages_fts MATCH ?` with a
  column-filtered phrase `'tags : ' + <phrase-quoted value>` (column literal fixed; value
  `"`-doubled — injection-safe). The existing `json_each(...) = ?` confirm and every other
  AND-clause stay, so the FTS set (a *superset* — the same tokenizer folds both sides, so the
  array element's tokens always appear in the FTS text) is filtered back to the **byte-identical
  result list**. A zero-token value (pure punctuation) → fall back to the scan (FTS would ∅ and
  could under-match a literal-punctuation tag); a degenerate-MATCH `OperationalError` also falls
  back. Empirically validated: 40 real tags (hyphenated/numeric/Cyrillic) → 0 mismatches. The
  FTS branch (a real query present) and the scalar/temporal/non-tags-list branches are
  **untouched**. Zero DDL (`user_version` stays 7), no layering inversion (the phrase-quote is
  inlined in the DAL — `wiki_index` must not import `wiki_skills`).

