# Project: obsidian-llm-wiki

Project-specific agent instructions. The agentic-development framework
(orchestrator prompt, skill loading protocol, pipeline phases) is imported
via `CLAUDE.local.md` → `CLAUDE.agentic.md`.

## What this project is

Multi-vault SQLite-indexed knowledge base implementing Karpathy's llm-wiki
pattern. Provides CLIs (`wiki-init`, `wiki-search`, `wiki-lint`,
`wiki-reindex`, `wiki-index-upsert`, `wiki-index-render`, `wiki-append-log`,
`wiki-enrich`, `wiki-extract-concepts`, the Epic 7 entity resolver
`wiki-confirm` / `wiki-alias` / `wiki-merge`, the Epic 7 RAG layer
`wiki-query`, and the Epic 7 RAG verification layer `wiki-verify-multi`)
over an `IndexRepository` DAL (SQLite + FTS5 + WAL).

Phase 3a complete (2026-05-26). Phase 3b: TASK 003 v2 shipped 2026-05-28;
TASK 003 v3.1 (Decision-17 deterministic refactor) shipped 2026-05-28
(commit `43812f2`); TASK 005 (Epic 7 entity resolution — R-4 confirmed/
candidate + `wiki-merge` + R-5 alias table) shipped 2026-05-29 (17 beads +
`/vdd-multi` 8-fix hardening; schema v2→v3 closes KNOWN_ISSUES L-4); TASK 006
(consolidation/hardening, schema v3→v4) shipped 2026-05-29 (`ba4fa92`);
TASK 007 (Epic 7 RAG layer — `wiki-query` R-6: retrieve→orchestrator-owned
cited synthesis→compounding `_queries/<slug>.md`) shipped 2026-05-29 (10 beads,
3 VDD gates + `/vdd-multi` ×2 + dogfood; **zero DDL**, `user_version` 4);
**TASK 008 (Epic 7 RAG verification — `wiki-verify-multi` R-8: off-by-default
4-critic prose audit of a filed answer→compounding `_verifications/verify-<slug>.md`;
FAIL=record+exit6, never mutate the answer) shipped 2026-05-29** (11 beads,
Stub-First green-throughout; 4 VDD gates incl. `/vdd-adversarial` on the plan;
**schema v4→v5** — verdict type + `verifies` ref + `verify` event; layout-agnostic
via `pages.file_path` (grep-guarded); 4 VDD gates + `/vdd-multi` post-ship
3-fix hardening — L-1 case-insensitive PASS/FAIL gate + enum validation, L-2
idempotency re-arm, L-3 vacuous-pass refusal; 672 pytest, mypy strict);
committed `49c7723`; **TASK 009 (R-9 critic-prompt hardening — scope the `wiki-verify`
4 lenses [anti-bleed] + a shared severity rubric + few-shot + the C2 `factual`-backstop;
plus a **durable, reproducible eval harness** at `skills/wiki-verify/evals/`) shipped
2026-05-30** (6 beads, Stub-First RED→GREEN; **6 gates** — task/arch/plan +
security-audit + code-review + `/vdd-multi` [2 HIGH instrument bugs fixed →
clean-pass]; **zero code/schema change**, `user_version` 5; measured baseline→enriched
delta: lens-bleed violations 10→3, false-positives 2→0, gate verdict-correctness +
recall →1.0, injection recall 100% held; **702 pytest, mypy strict**). TASK 010/011
(wiki-verify eval-v3/v4) shipped 2026-05-30..06-01. **TASK 012 (R-X1 universal
config-driven layout engine + R-X2 A-B + R-X3) — R-X1 SHIPPED + R-X2/R-X3 engine+tooling
SHIPPED 2026-06-01**: ~15 hardcoded layout surfaces replaced by a YAML-config engine
(`scripts/wiki_index/layout_config.py` + `config/layout-config.schema.yaml` + built-in
`scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`); two separate
config layers (per-vault identity vs per-layout grammar); byte-identical for Karpathy
(golden anchor); stdlib-`re` ReDoS load-gate; PW-G/H/Q (KNOWN_ISSUES splitter +
auto-rendered ledger + drift lint guard); `wiki-init --layout` (5 values); **zero DDL**
(`user_version` 5; new doc types via TYPE_MAPPING tag-route). ADR-002 §D8 amended
(Class-B "rebuildable markdown"). **810 pytest (+4 skipped), mypy strict.** The operator
decision (repo-root `WIKI_SCHEMA.md` vs `docs/`-relative globs) was **RESOLVED →
`docs/`-relative** (vault_root = `<repo>/docs`, committed `docs/WIKI_SCHEMA.md`,
repo root stays vault-free); the **live** dev-vault bootstrap of THIS repo + the
KNOWN_ISSUES dogfood are **DONE** — `docs/issues/*.md` are the Class-A per-issue
sources and `docs/KNOWN_ISSUES.md` is now the auto-rendered Class-B ledger. All 17
beads (012-00..16) + the `/vdd-multi` post-ship hardening (SEC-1 egress-sanitization
of the untrusted ledger, LOG-1 delta-reindex auto-index render, perf) are **committed
`c127b4b`** (on top of the R-X1 pre-flight `4608a50`). **R-X2 Phase C
(agentic-development archive hook) deferred** (ROADMAP R-X2c); residual perf/UX items
tracked in `docs/issues/`. See `docs/ARCHITECTURE.md`
§3.5, `docs/adr/` (ADR-002 §D8 TASK-012 amendment), `docs/tasks/` (`task-012-*.md`)
+ `docs/plans/`.
**TASK 013 (R-X3-META-FILTER — `wiki-search` frontmatter metadata filter) SHIPPED
2026-06-01, committed `177fd5a`**: general repeatable `--where 'field=value'` +
`--status`/`--severity` sugar → parameterized `CAST(json_extract(frontmatter_json, ?)
AS TEXT) = ?` predicate (string-rep match → numeric `priority=1` works; hyphenated
`SEV-2` via equality, not FTS); optional query → non-FTS `(project, slug, vault_id)`
listing; injection-safe (field allowlist `[a-z][a-z0-9_]*` via `re.fullmatch`,
path+value bound, dup-field rejected, `INVALID_FILTER` never echoes value); **zero DDL**
(`user_version` 5). Full VDD pipeline + `/vdd-multi` + code-review. **TASK 014
(dogfood-fixes) SHIPPED 2026-06-01** (uncommitted on `177fd5a`): closes
**R-X1-REF-SLUGIFY** (SEV-2 — `reindex._body_refs` slugifies ref targets via the
layout's `slug_strategy` so `[[Title Case]]`/`[[Идеи]]` resolve under non-`identity`
layouts; karpathy=no-op→byte-identity; dev-vault orphans 2228→2160) + two CLI-UX
fixes (`wiki-query --vault-root` now optional/derived; `wiki-alias --list` lists the
whole vault via new `repo.list_all_aliases`). **852 pytest (+4 skipped), mypy strict.**
**TASK 015 (perf-hardening-extract-concepts) SHIPPED 2026-06-01** (uncommitted): closes
the four SEV-2 hot-path issues **H-PERF-3** (`wiki_index_upsert.upsert_one(vault_id, src,
vault_root, repo)` programmatic entry-point — no argparse-in-loop; `main()` delegates),
**P-8** (`index_from_manifest` + `dispatch_to_indexer` optional `repo`; `apply --ingest`
threads its open repo → one `make_repo`), **P-6** (`prepare --known-concepts-format
{full,slugs-only}`), **P-7** (`prepare --batch <slugs.json>` + `apply --batch-candidates
<combined.json>` — one repo reused across all entries, per-entry isolation). `apply`
factored into `_apply_validate` (no repo — input errors never touch the DB, preserving the
CWE-117 canary ordering) + `_apply_write`; `prepare` into `_load_known_and_drift` +
`_recon_single`. Hardened by **`/vdd-multi` ×2 (all critics clean)**: `sqlite3.Error` in the
per-entry catch (DB fault isolates, never crashes the batch); batch `prepare` hoists
`known_concepts`/`missing_concept_files` to the envelope top level (O(N+|known|), not
O(N·|known|) stdout — deviation from R-015-4c, recorded in TASK.md); batch `apply` loads
known once + grows the dedup set in place (O(E), not O(N·E)); idempotency-failure →
per-entry `partial`; M-2 abspath leak closed; combined.json cap 1 MiB→10 MiB. **Deferred:**
single-outer-transaction batching (SQLite nested-txn limit). **Zero DDL** (`user_version`
5). **877 pytest (+4 skipped), mypy strict.**
**TASK 016 (split-extract-concepts-module) SHIPPED 2026-06-01** (uncommitted, branch
`task-016-split-extract-concepts`): pure structural refactor — the 2174-line
`wiki_extract_concepts.py` god-module split into a **package**
`scripts/wiki_skills/wiki_extract_concepts/` (facade `__init__.py` 1071 lines +
leaves `_validation`/`_sourcing`/`_db`/`_pages`/`_errors` + `__main__.py`). **Zero
behaviour/CLI/envelope/exit-code/schema change.** The patch-target lock is preserved:
the 8 monkeypatched names (`make_repo`, `load_known_entities`, `validate_manifest`,
`index_from_manifest`, `dispatch_to_indexer`, `_apply_candidates_to_db`,
`_try_update_idempotency_state`, `update_idempotency_state`) stay rebindable at
`scripts.wiki_skills.wiki_extract_concepts.<name>` as facade globals (`_db` carve-out
for `load_known_entities`+`update_idempotency_state`); acyclic import-direction
(facade→leaves; `_errors` sink). All moved bodies byte-identical (verbatim, hash-proven
per bead); green-throughout (full VDD pipeline: task/arch/plan reviews + Sarcasmotron
per bead). **879 pytest (+4 skipped), mypy strict (69 files).** See `docs/TASK.md`,
`docs/PLAN.md`, `docs/ARCHITECTURE.md` §2.1, `docs/tasks/task-016-*.md`.
**TASK 017 (drift-delta-redos-timeout) SHIPPED 2026-06-02** (uncommitted): closes the only
open **SEV-2 R-X1-REDOS-RT** + **P-2** + **P-3** as one bounded hardening task. **R-X1-REDOS-RT**
— a per-file runtime ReDoS deadline: operator-custom layout patterns (`ref_extraction[].regex`
+ `paths[].project_pattern`) run under the **PyPI `regex` engine with `timeout=`** (built-ins
stay stdlib `re` → byte-identity, zero overhead), gated by two provenance booleans on
`LayoutConfig` (`{ref_extraction,paths}_operator_supplied`, set in `load_layout_config` from
the Q-012-f override merge); per-file budget `WIKI_REDOS_BUDGET_S` (default 2.0 s, env-overridable);
on `TimeoutError` → report-and-skip (`extract_refs`→empty refs+WARN; `_derive_project`→`UNMATCHED_PROJECT`+WARN),
never hangs; the load-gate (`_redos_budget_check` + `_validate_path_patterns`) is engine-aligned
to `regex` for operator patterns (dialect: `regex` V0 = `re`-compatible). **P-2** — single-stat
walk: `DiscoveredPage.mtime` carries the walk's one `stat()`, reused by `reindex_delta` (no 2nd stat).
**P-3** — `check_drift` regex `type:` fast-path → PyYAML fallback (**measured 4.6× `wiki-lint`
@1k in default always-hash mode** — PyYAML dominated), + opt-in `wiki-lint --mtime-skip`
(integrity-relaxed; default always full-hashes, D-017-B). **Zero DDL** (`user_version` 5; reuses
`pages.last_modified`, no `file_size` column). New dep **`regex`** (+`types-regex`) — a deliberate,
measured relaxation of TASK 012's stdlib-only ReDoS posture (no pure-stdlib mechanism can interrupt
a catastrophic stdlib-`re` match; GIL-held C call — verified). Full VDD pipeline + per-phase
Sarcasmotron + `/vdd-multi` post-ship hardening (logic/security/performance → convergence clean;
1 HIGH fixed — `derive_project_for_path` was running operator `project_pattern` unguarded under
stdlib `re` on the extract-concepts ingest path [ReDoS-bypass + `re.error` crash] → now threads
`operator_supplied`; + MED `type:foo` fast-path + 4 LOW) + comprehensive CLI dogfood (5 scenarios:
ReDoS guard proven end-to-end via a gate-slipping `(aa|aa)*$`, HIGH-fix proven via
`wiki-extract-concepts prepare` on `\p{L}`, P-3 extraction == PyYAML on all 331 real docs files).
Dogfood found + fixed **DF-017-1** (SEV-3, pre-existing): `check_drift` type-mismatch ignored the
config-driven layout `type_mapping` → 56 false positives on the dev-project docs vault;
`_is_intentional_mapping` now unions `config.type_mapping` → 56→0. **909 pytest (+4 skipped), mypy
strict (69 files).** See `docs/TASK.md`, `docs/PLAN.md`, `docs/ARCHITECTURE.md` §3.5/§8.4, `docs/tasks/task-017-*.md`.
**TASK 018 (wiki-sync — R-11 ROADMAP) SHIPPED 2026-06-03** (uncommitted, branch
`task-018-wiki-sync`): the **15th CLI** `wiki-sync` — a format-aware, tag-routed
ingest dispatcher closing the *Mixed vault* (search-only areas + enrich-able course
zones) automation gap. **`wiki-sync scan <zone>`** = deterministic plan-only walk
(`scripts/wiki_skills/wiki_sync.py` + the routing brain `_sync.py`): own bounded
walk (one `lstat`/candidate, ext-prune-before-stat, symlink-refuse,
`_raw/.staging`/dot-dir prune) → `classify_file` (extension front-stage →
`#wiki/{raw,skip,keep}` tag precedence **skip>raw>keep>default** → generated-view
sidecar + **only-a-view guard** [DB Folder/Bases/Dataview/folder-note skip ONLY
when essentially one view block; embeds-a-view+prose → upsert] → **layout-general**
unmappable-type via the indexer's own `normalize_frontmatter`, W-1) → `sha256(bytes)`
→ `is_unchanged` → strict **plan JSON** (sorted by vault-rel POSIX path,
deterministic, no timestamp; `--dry-run` writes nothing). **`wiki-sync record`** =
the executor commit-marker. **`workflows/wiki-sync.md`** = the Decision-17
orchestrator (convert→non-walked `_raw/.staging/` · `.vtt`/`.srt` de-timestamp ·
**H-6 fence** before `summarizing-meetings` · `wiki-enrich` · `wiki-extract-concepts`
· `wiki-index-upsert` · per-vault lock · per-file isolation · `needs-ocr` flag).
**Zero DDL** (`user_version` 5): idempotency rides a new `source_state`
`source_kind='sync'` partition via two generic DAL methods (`get/set_source_state`)
+ `config/sync-config.schema.yaml` (strict; 256 KiB cap + anchor-ban `SafeLoader` +
`RecursionError`-safe → controlled `INVALID_SYNC_CONFIG`). **No `import anthropic`**
(grep-guarded). Full VDD pipeline + per-phase Sarcasmotron + **two adversarial
gates**: the per-phase 3-critic pass (security HIGH anchorless-deep-nesting DoS →
controlled exit 6; logic 2× malformed-frontmatter crash + 1× idempotency
`None`-hash false-positive; perf ext-set hoist) **and** a final full-surface
`/vdd-multi` (Logic ✓ Security ✓ Performance ✓ — converged L=2/S=3/P=1):
security MED `.md`-read OOM → `WIKI_SYNC_MD_MAX_BYTES` 8 MiB `oversize-source`
skip-before-read; logic MED UTF-8-BOM `.md` mis-skip → BOM-strip parity with the
indexer; logic MED `record` FK-path test; sec LOW `_is_clean_rel` canonicalisation
+ **full-path config-symlink containment** (a symlinked parent `.wiki/` can't
redirect the read out-of-vault); + workflow H-6 nonce-sentinel / `flock`-primary
lock / SEC-A3 staging-write guard — all fixed with regressions. **73 new tests**
(`tests/test_wiki_sync.py` + `tests/test_wiki_sync_e2e.py` over committed
`tests/fixtures/sync/**` incl. a real `yaml:dbfolder` sidecar). **986 pytest (+4
skipped), mypy strict (72 files).** Residual P2 (recorded in ROADMAP, not silent):
the `.md`-read-twice fuse. See `docs/tasks/task-018-wiki-sync.md`, `docs/plans/plan-018-wiki-sync.md`,
`docs/tasks/task-018-*.md` (beads), `docs/reviews/`.
**TASK 019 (sync-resummarize-policy — `wiki-sync` re-summarization gate) SHIPPED 2026-06-07**
(uncommitted): the dispatcher is now idempotent at the *knowledge* level — a raw source is
`ingest`/`convert+ingest`-ed **only if** `--force` **or** no summary exists. A **monotone**
gate in `wiki_sync._build_entries` (only `ingest`/`convert+ingest`→`skip`, never `upsert`),
new SRP module `scripts/wiki_skills/_resummarize.py`. "Summary exists" = **D1** `source_state`
∪ **D2a** provenance (two new read-only DAL methods over `frontmatter_json`:
`find_pages_citing_source` + the bulk `all_cited_sources` hoisted once per scan; rel-path ∥
basename; list-valued `sources:` ⇒ N:1) ∪ **D2b** filesystem mirror (`stem-relpath` 1:1 /
`group-key` N:1 via a configurable `key{raw_regex,summary_regex,template,flags}`; a once-per-scope
key index; ReDoS-guarded by a cached **load-gate** (`layout_config.is_pattern_redos_safe`) +
`guarded_search` per-call deadline; `scope` vault-contained). Rules = a strict opt-in
`$def Resummarize` in `config/sync-config.schema.yaml` under `SyncConfig.resummarize`
(absent ≡ TASK 018 / byte-identity), **per-folder overridable** (Option-A cascade:
`<folder>/.wiki/sync.yaml`, deepest-wins deep-merge on RAW dicts so a partial override inherits
`detect`; resolved policy + citation set + mirror index all memoized on a per-scan `Caches` →
O(S+R)/O(P+R)). `scan --force` (zone-scoped) + the executor's `sources:` writeback
on generated summaries (`workflows/wiki-sync.md` 4b/AC-13). **Zero DDL** (`user_version` 5 —
reuse `SourceState` + `frontmatter_json`); **no `import anthropic`**. Full VDD pipeline
(task/arch/plan reviews APPROVED) + Stub-First green-throughout (`skill-tdd-strict` on the
back-compat / DAL / gate-monotonicity / ReDoS beads) + **`/vdd-multi` converged** (Logic ✓
Security ✓ Performance ✓; iter-1 → 2 HIGH perf + 1 MED sec + 2 MED/3 LOW logic → iter-2
verified-fixed + 1 sec DiD). **1039 pytest (+4 skipped),
mypy strict (73 files).** Dogfood fixture `samples/Demand-generation` (6 modules + Lessons;
patterns A group-key / B same-dir stem / C date-key) + committed e2e
`tests/test_wiki_sync_resummarize_e2e.py`. Cross-task prereq (NOT in scope): obsidian-personal
`type_mapping` lacks `lesson-summary` → the summary `upsert` leg needs a layout mapping
(TASK 012 surface; ARCHITECTURE Q-019-9). **Post-ship dogfood hardening (2026-06-08,
ARCHITECTURE Q-019-11):** full end-to-end run on the real `samples/Demand-generation` vault
+ 14-agent adversarial verify → correct, **zero data-loss**; two fixes — (a) a **dead-mirror-
detector WARN** (`_scope_key_index`: "mirror keyed 0 of N summaries" when a `group_key` regex
matches nothing, e.g. a YAML double-backslash), (b) **`ignore` now UNIONs** the base layout
ignores on a `.wiki/layout.yaml` override (was replace) — `1041 pytest`. See `docs/tasks/task-019-sync-resummarize-policy.md`,
`docs/plans/plan-019-sync-resummarize-policy.md`, `docs/tasks/task-019-*.md` (beads),
`docs/reviews/{task,architecture,plan}-019-review.md`.
**TASK 020 (reindex-slug-collision) — [LIGHT] SHIPPED 2026-06-08** (uncommitted): the TASK 019
dogfood's separate finding fixed — `wiki-reindex --full`/`--delta` SILENTLY overwrote a page on
an intra-project `(vault_id, slug, project)` PK collision (reported N files, DB had fewer rows,
`skipped`/`alias_collisions` empty). Now both emit a new **`slug_collisions`** envelope field
(`{slug, project, kept, dropped}`, sibling of `alias_collisions`) + a one-shot WARN, via a shared
`reindex._detect_slug_collision` (detection-only — operator disambiguates via a per-folder
`project`/`project_pattern`; full=complete, delta=within-batch). **Zero DDL** (`user_version` 5),
additive envelope, no new deps. **1043 pytest (+4 skipped), mypy strict.** See `docs/TASK.md`,
`docs/tasks/task-020-reindex-slug-collision.md`.
**TASK 021 (dogfood-hardening) SHIPPED 2026-06-08** (uncommitted): a **repeat** comprehensive
dogfood of `samples/Demand-generation` (TASK 019+020) — confirmed correct + zero data-loss on the
frozen fixture (1044 pytest), then two `critic-logic` adversarial passes whose 2 HIGH findings were
**empirically reproduced** before acceptance → 5 fixes. **HIGH-1 (Option A, operator-confirmed,
behaviour-preserving):** D2b mirror proves *key-equality*, not *"this raw was summarised"* — under
N:1 group-keying a new raw sharing a key with an already-summarised sibling is SKIPPED (the intended
TASK 019 semantics), so the coarse-key merge-vs-split ambiguity was invisible. Now an N:1 `group-key`
skip emits ONE merge/split WARN **iff provenance is enabled but does NOT cite this raw**
(`summary_exists` passes `warn_uncited=pr.enabled` to `_mirror_match`; `_scope_key_index` →
`key→representative-summary` map; `stem-relpath` 1:1 never warns; skip unchanged). `sources:`
provenance is the authoritative merge/split record; key is only the default grouping; levers =
`--force` (merge) / finer key (split) / archive-old (supersede) — documented in `workflows/wiki-sync.md`
Step 6. **HIGH-2:** `wiki-reindex --delta` only detected *within-batch* `(slug,project)` PK collisions
→ a delta file colliding with a PRIOR-batch row (mtime ≤ cutoff, not re-walked) silently clobbered it.
Now `reindex_delta` seeds `seen_keys` from prior-batch rows **still-on-disk AND not-re-walked** (single
coalesced `pages` read, reused for orphan deletion). **MED:** `wiki-reindex --all-vaults` now honours
`--delta` (was silently `--full`; correct envelope `touched`/`deleted` vs `pages_indexed`). **LOW:**
collision tests assert `kept`/`dropped` direction + DB row == `kept`; doc-drift fix in
`samples/target-obsidian-vault/.wiki/layout.yaml` (ignore EXTENDS the base, REPLACE scoped to
`paths`/`ref_extraction`); schema notes (leading-zero numeric equivalence class, single-valued
`summary_ext`). Hardened by an **adversarial Workflow** (logic/security/perf critics → verify): 3
confirmed (L-1 double-count, L-2 rename false-positive, PERF-021-1 double-scan) — ALL fixed by the
refined still-on-disk+not-re-walked seed + regression tests. **Zero DDL** (`user_version` 5), no new
deps, no `import anthropic`. **1056 pytest (+4 skipped), mypy strict (73 files).** See
`docs/tasks/task-021-dogfood-hardening.md`, `docs/plans/plan-021-dogfood-hardening.md`, ARCHITECTURE
§11a Q-021-1/2.
**TASK 022 (vault-local-db-resolution) SHIPPED 2026-06-08** (uncommitted): a vault may declare
**`index_db:` in `WIKI_SCHEMA.md`** (the *identity* layer) → its SQLite index DB lives **with** the
vault (portable, gitignored, ADR-002 §D8-rebuildable); absent ⇒ the global DB, **byte-identical** to
before. Precedence **`--db-path` > `index_db` > global**. Two new units — `config_loader.resolve_index_db_path`
(reads RAW frontmatter, bypassing the `CLAUDE.md::wiki:` overlay) + `_common.build_repo_config`
(lazy-imports `config_loader`) — plus `_common.resolve_vault_root_for_cli` (`--vault-root` flag →
`find_vault_root(cwd)` walk-up). **`factory.make_repo` is UNCHANGED**; the **ordering inversion** runs
the resolution BEFORE `make_repo` across all 15 CLIs (incl. `wiki-init --local`/`--index-db` writing
into all 3 subcommands; `wiki-enrich`/`extract` thread the resolved `db_path` — no split-brain).
**Island** model (OQ-1): `--vault all` spans only the connected DB (no cross-DB federation). **Cloud
(OQ-5):** an iCloud/Dropbox vault uses an absolute non-synced path. Full VDD pipeline (task/arch/plan
reviews APPROVED) + Stub-First green-throughout. **`/vdd-multi` post-ship hardening** (it found real
holes the happy path missed): **HIGH-S1** leaf-symlink containment escape (now full-path resolve +
leaf-symlink refusal), **HIGH-S2** absolute `index_db` arbitrary-write under an attacker-shippable
config → gated behind **`WIKI_ALLOW_ABSOLUTE_INDEX_DB=1`** (amends OQ-5), **HIGH-L1** CWD walk-up
opening a *different* vault's DB → `resolve_index_db_path(..., expected_vault_id=)`, **MED** uncaught
`ConfigValidationError` → central `INVALID_INDEX_DB` JSON envelope + exit 6 (CWE-209 no-echo),
**MED-S1** YAML frontmatter key-injection via `--index-db` (Unicode line-separators U+0085/U+2028/
U+2029) → `_validate_index_db_rel` bans every `str.isspace()` break + `": "`; `_ensure_index_db`
fence-aware atomic write + `INDEX_DB_ALREADY_DECLARED` conflict. Re-verified Logic ✓ Security ✓
Performance ✓ (converged). **Zero DDL** (`user_version` 5), no new deps, no `import anthropic`.
**1083 pytest (+27), mypy strict (73 files).** New schema key `index_db` in `WikiRootConfig` (banned
in `WikiProjectOverride`). See `docs/tasks/task-022-vault-local-db-resolution.md`,
`docs/plans/plan-022-vault-local-db-resolution.md`, `docs/tasks/task-022-01..09-*.md`,
`docs/reviews/{task,architecture,plan}-022-review.md`, ARCHITECTURE §11a Q-022-1/2/3/4.
**TASK 023 (personal-vault dogfood hardening) SHIPPED 2026-06-08** (the ad-hoc batch that
preceded TASK 024; no separate `docs/tasks/` doc — recorded here + in the auto-memory
`personal-vault-adoption`): three framework features surfaced by a full end-to-end dogfood of
a real PARA Obsidian vault (`samples/personal-vault-dogfood`). (1) **obsidian-personal
`type_mapping`** gained `summary`/`lesson-summary`/`meeting-summary`/`webinar-summary`/`moc`
→ `db_type: summary` (closes ARCHITECTURE Q-019-9 — a `type: lesson-summary` note used to raise
`UnmappedTypeError` and be silently dropped at reindex / `skip:unmappable-type` in wiki-sync).
(2) **Structured `sources:` provenance** — `SQLiteRepository.all_cited_sources` now harvests the
scalar string members of OBJECT-valued `sources:` elements (the `{id, url, file}` shape
`generate-detailed-meeting-summary` emits), so D2a provenance links a summary to its raw by the
`file:` value; the global `generate-detailed-meeting-summary` workflow emits `file:` as a
**vault-relative path** (agnostic wording). (3) **`transcript_dedup`** — a new opt-in
`SyncConfig` block (`config/sync-config.schema.yaml` + `_sync.transcript_variant_skips`, wired
into `wiki_sync._build_entries` before the resummarize gate): among transcript-format files
sharing a (dir, identity) group only the highest-`prefer_ext` is ingested; lower ones →
`skip:transcript-variant:<ext>` (identity `stem` | `before-first-dot` for YouTube-id captions;
a lone caption is kept → still ingested). **Zero DDL** (`user_version` 5). Mirror/per-folder
cascade unchanged. **1093 pytest, mypy strict.**
**TASK 024 (upsert-layout-fts-hardening) SHIPPED 2026-06-08** (uncommitted): closes the
remaining TASK 023-dogfood findings via the full VDD pipeline (task/arch/plan reviews APPROVED +
`/vdd-multi` converged — Logic 1 MED + 2 LOW [LOW-2 fixed, MED-1/LOW-3 documented Q-024-residual-2],
Security ✓, Performance ✓). **R-1 — `wiki-index-upsert` is now LAYOUT-AWARE** (HIGH bug): a new
shared `reindex.derive_indexed_page` helper (single per-file derivation: `adapter.fetch` →
slug/project from `layout_config.derive_discovered_page` → `_synthesize_fm` →
`normalize_frontmatter(4 args)` → `_build_page` → `_body_refs`+`_frontmatter_refs`) serves all
THREE sites (`reindex_full`, `reindex_delta`, `upsert_one`; the 4th indirect caller
`_manifest_consumer.index_from_manifest` becomes layout-aware too) → upsert files
byte-identically to reindex (project/slug/type/title/refs). Was `derive_slug`'s `_vault_`
fallback + karpathy module `TYPE_MAPPING` → on PARA vaults it filed `_vault_` rows + duplicated
on the next `reindex --full`, and would `UnmappedTypeError` on `note`/`moc`/`daily-note`.
**R-2 — FTS full body**: `_build_page` drops the `body_excerpt=[:1000]` cap → `pages_fts` indexes
the whole normalized body (deep terms searchable; dogfood: `"дофамин"` past char 1000 now hits);
display stays bounded via `snippet()` (no consumer renders the column raw); zero-DDL Option B
(existing DBs gain it on next `reindex`, Class-B rebuild). **R-3 — docs**: `workflows/wiki-sync.md`
4b/4c documents the layout-conditional filing (PARA = note+`upsert`; Karpathy `_sources`/`wiki-enrich`
still valid). **R-4 — D2a provenance NFC/NFD normalisation** (dogfood #3, folded in 2026-06-09):
`_resummarize.summary_exists` NFC-normalises both the citation set + the target, so a Cyrillic-named
raw whose macOS FS-walked `rel` is NFD (`й`=и+◌̆) matches its NFC `sources:` (was re-converting every
scan; localised to D2a — D1 NFD-self-consistent, D2b FS-vs-FS). Dogfood #3 also re-validated the
**OCR convert+ingest path** end-to-end (scanned image-only PDF → `pdf_ocr.py` eng+rus → summary →
layout-aware upsert → searchable). **Zero DDL** (`user_version` 5), no new deps, `no import anthropic`.
New `tests/test_upsert_layout_parity.py` (9) + `test_gate_d2a_provenance_nfc_nfd`. **1103 pytest,
mypy strict (73 files).** See `docs/tasks/task-024-upsert-layout-fts-hardening.md`,
`docs/plans/plan-024-upsert-layout-fts-hardening.md`, ARCHITECTURE Q-024-1/2/3/4 (+residual-2).
**TASK 025 (adoption-currency-hardening) SHIPPED 2026-06-09** (uncommitted): closes the
findings of a **4-agent adoption-currency audit** run after the first real-vault dogfood of an
obsidian-personal PARA iCloud vault (`Downloads/TestVault/ObsidianNotes`; runbook
`docs/runbooks/personal-vault-adoption.md`). Schema↔code had **no drift** (verified); the gaps
were adequacy + docs, none blocking. **R-1/R-2 (installer):** `wiki-init`'s absolute `--index-db`
without `WIKI_ALLOW_ABSOLUTE_INDEX_DB` used to write `index_db` into `WIKI_SCHEMA.md` and THEN fail
(partial Class-A mutation) — now a **pre-write guard** validates BEFORE `_ensure_index_db` via a
shared pure `config_loader.validate_index_db_value(val, vault_root) -> Path` (extracted from
`resolve_index_db_path`, which keeps read+strip+`expected_vault_id` short-circuit and delegates;
byte-behaviour-identical, the HIGH-S1/S2/L1 posture preserved); `INVALID_INDEX_DB` unified to **exit
6 / field `index_db`** at every site (was exit 2 / `index-db`), docstring legend updated. **R-3/R-4
(obsidian-personal built-in, additive):** `type_mapping` pre-maps the common summary family
(`tutorial-/article-/book-/video-/podcast-/course-summary` → `db_type: summary` + tag); `ignore` +=
`**/_raw/**` + `**/.staging/**` (raw/staging markdown out of the search index at ANY depth —
INTENTIONALLY broader than wiki-sync's own walk, which prunes only `_raw/.staging|.locks|failed` and
INGESTS top-level `_raw/`; they deliberately disagree on `_raw`; `_raw`/`.staging` now reserved
scratch names). **R-5 (agent template):** dropped the hardcoded `rm …/global.db` from the Karpathy
`templates/CLAUDE.md.tmpl`; new layout-aware `templates/CLAUDE.layout.md.tmpl` selected per `--layout`
in `_write_agent_files` for dev-project/obsidian-personal (every vendor). **R-6/7/8 (docs):** the
`basename` provenance match mode (basenames BOTH sides; preferred for globally-unique/basename-cited
corpora) documented in schema/manual/workflow + ARCHITECTURE Q-019-10 softened ("orphaned knob" →
first-class mode); `paths`/`ref_extraction`=REPLACE merge asymmetry + custom-`type:`→per-vault
`type_mapping` documented. The resummarize default `match` is **NOT changed** (back-compat). Full VDD
pipeline (task/arch/plan reviews — arch+plan returned binding constraints, all incorporated) +
**`/vdd-multi` converged** (security clean-pass: posture preserved, footgun closed; performance
clean-pass: ignore globs a net syscall-saver; logic 1 MED + 2 LOW — all doc-accuracy, fixed:
corrected the `_raw` "alignment" wording, vendor-coupling NB, reserved-name note) + **code-review
APPROVED**. **Zero DDL** (`user_version` 5), no new deps, no `import anthropic`, Karpathy golden-anchor
byte-identity preserved. **1111 pytest (+8), mypy strict (73 files).** See
`docs/tasks/task-025-adoption-currency-hardening.md`, `docs/plans/plan-025-adoption-currency-hardening.md`,
ARCHITECTURE Q-025-1/2/3/4.
**TASK 026 (installer ships the vault `.claude/settings.json`) SHIPPED 2026-06-09** (committed
`1ee638f` with TASK 027): `wiki-init` drops the selected vendor's settings file (VERBATIM copy,
non-destructive, `--force` to overwrite) where the agent file is written, via a config-driven
`settings_file`/`settings_template` on `templates/agent-files.yaml`. See ARCHITECTURE Q-026-1,
`docs/tasks/task-026-installer-vault-claude-settings.md`.
**TASK 028 (R-Y1 — query-side stemming + ё/е folding) SHIPPED 2026-06-09** (uncommitted, branch
`task-028-query-stemming-yo-folding`): closes the two real-vault recall misses (literal multi-term
AND missed inflected `Сценарии продаж`; `продуктовое осведомление` ranked a tangential page and
missed the inflected `03-первое-касание`). Two orthogonal mechanisms, BOTH script-general:
**(1) ё/е fold — ALWAYS on** (corpus canonicalisation: `body_excerpt` at index + every query term;
the `unicode61 remove_diacritics 2` tokenizer does NOT fold precomposed `ё`); **(2) stemming —
default-on, `--exact`/`--no-stem` opts out** (per-term by SCRIPT — Cyrillic→`russian`,
Latin→`english`, other→literal; `snowballstemmer==3.1.1`, pure-Python, pinned EXACT because the stem
changes the hit set that feeds `wiki-query`'s `question_hash`). New pure modules
`scripts/wiki_index/{_snowball.py [the one type:ignore],query_normalizer.py}` (fold + script-detect +
per-term `normalize_term` + the wiki-search FTS-expression lexer); **two distinct call sites** —
wiki-search lexer (stems only bare sigil-free tokens; F-1 composition `(<stemmed>) OR "alias"`,
NOT `stem(expand_query)`) and wiki-query per-token `"<stem>"*` before `fts_quote` (F-2); `--exact`
threaded symmetrically through `prepare`+`apply` (C1 `question_hash`). Guards: post-STEM `MIN_STEM_LEN`
(no catch-all `аг*`, F-6), ALL-CAPS acronym guard, and a **stem-must-be-a-prefix** guard (English
`-y→-i` mutates → would miss the original; emit literal — found in dev). Body ё-fold rides
`normalize_body_for_fts` (zero trigger change; takes effect on next `wiki-reindex --full`, Class-B).
**Full VDD**: task/arch/plan reviews APPROVED (3-perspective task-review workflow) + `/vdd-multi`
converged (Security CLEAN; Logic 1 MED documented [ё-fold column asymmetry — title/tldr/tags indexed
unfolded, narrow ё-form-query residual] + 2 LOW fixed; Performance 1 MED **verified pre-existing**
[wiki-query V×T alias fan-out, not a 028 regression] + 3 LOW micro-opts; code-review MERGE — 3 LOW
fixed). **Zero DDL** (`user_version` 5), no `import anthropic`, Karpathy indexing byte-identical for
ё-free content (ё→е body fold = the one intentional, layout-agnostic delta). `skills/wiki-search/`
SKILL.md→v1.4 + evals.json (8 cases) + manuals EN/RU + README updated (R-028-5). A **second
`/vdd-multi` pass** (operator re-verify) caught + fixed a regression the first pass's empty-base
guard surfaced — `wiki-search "   "` (whitespace-only) crashed with an uncaught `ValueError`
(lexer→`""`→`search_pages` rejects, DF-1 only caught `OperationalError`); now stripped at the CLI
boundary → clean `INVALID_QUERY` (regression test added); re-converged Logic✓ Security✓
Performance✓. **1204 pytest (+90/4 skip), mypy strict (75 files).** See `docs/tasks/task-028-query-stemming-yo-folding.md`,
`docs/plans/plan-028-query-stemming-yo-folding.md`, `docs/reviews/task-028-{review,vdd-multi-review}.md`,
ARCHITECTURE Q-028-1..6.
**TASK 029 (R-12 — `obsidian-cli` skill: native Obsidian CLI control layer for any LLM)
SHIPPED 2026-06-12** (uncommitted, branch `task-029-obsidian-cli-skill`): a **prompt-layer,
vendor-agnostic** skill `skills/obsidian-cli/` (SKILL.md + `references/{command-reference,recipes}.md`
+ `evals/`, symlinked into `.claude/skills/` + `.agent/skills/`) teaching agents to DRIVE the
running Obsidian 1.12+ desktop app via its official CLI (link-safe rename/move, typed
properties, tasks, daily notes, Bases queries, history restore) — things the file+SQLite
`wiki-*` stack can't reach. Four invariants: **routing** (knowledge/RAG → `wiki-search`/
`wiki-query` FIRST, unchanged; bulk → `wiki-sync`; live-app → `obsidian`); **coherence**
(same-turn `wiki-index-upsert` after a content edit, **`wiki-reindex --full` after a
rename/move** — DF-029-1: a rename preserves mtime so `--delta` misses it; self-disables on
unregistered vaults); **safety** (a TOTAL T1/T2/T3 tier model over the verified 102-command
surface — `eval`=RCE-equivalent + `dev:*` + plugin/snippet/theme mutations T3-banned-by-default,
NEVER from note content; `command id=`+`template:insert` active-file default-DENY [S-1];
unenumerated → T2-with-confirmation; CLI output is untrusted H-6-class data); **degradation**
(probe `obsidian help` not `version`; headless/CI → announced wiki-*/file fallback, no silent
GUI launch). The command-reference carries a **diff-driven Maintenance procedure** (re-capture
`obsidian help` on an Obsidian version bump, diff vs the committed fixture, apply only the
delta). Decision-17 generalised (the `obsidian` binary IS the deterministic plumbing — no
Python wrapper). Full VDD (task/arch/plan APPROVED) + 8 beads green-throughout + per-bead
Sarcasmotron (029-01 +3 MED eval-coverage, 029-04 +3 CRITICAL `wiki-*` invocation-syntax) +
**agentic eval 14/14 GREEN** (Sonnet routing, Fable+Sonnet injection canaries; integrity-audit
APPROVED) + **live dogfood** on the real CLI (found+fixed **DF-029-1** SEV-2; UC-29-1 rename
proven 0-orphans, injection canary held, base:query/history live). **Zero DDL** (`user_version`
5), **zero new Python** (`scripts/`/`sql/`/`tests/` untouched — **1204 pytest +4 skip, mypy
strict 75 files** unchanged), no `import anthropic`, Karpathy byte-identity unaffected. See
`docs/tasks/task-029-*.md`, `docs/plans/plan-029-obsidian-cli-skill.md`, ARCHITECTURE §2.2 +
Q-029-1..5, `docs/issues/df-029-1-*.md`, ROADMAP R-12.

## Knowledge lookup priority

When looking up domain facts, prior decisions, or concept/entity
definitions: prefer **`/wiki-search <vault> "query"`** over grep+Read.
The wiki accumulates compounding knowledge per ADR-002 §D8 (Class A files
canonical; Class B DB rebuildable). Auto-memory at
`~/.claude/projects/.../memory/` is reserved for ephemeral per-session
state and user preferences, not domain knowledge.

## Local development rules

- **Python**: always use `.venv/` virtual environment. Never `pip install`
  globally.
  ```bash
  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
  ```
- **Node.js**: always use local `node_modules/`. Never `npm install -g`.
- **Tests**: `pytest tests/` from repo root with the venv activated.
- **Type-check**: `mypy --strict scripts/` is the contract for the
  `scripts/` tree.
- **Python version**: 3.14.4 via pyenv (the system 3.9 is incompatible
  with `python-frontmatter`).

## Conventions (orthogonal to the framework)

- New skills/commands/workflows go under repo root: `skills/<name>/SKILL.md`,
  `commands/<name>.md`, `workflows/<name>.md`. Symlinked into
  `.claude/skills/`, `.claude/commands/`, `.agent/skills/`,
  `.agent/workflows/` for vendor compatibility.
- The repo IS the implementation, NOT a vault. Never run
  `wiki-init --scaffold-new --vault .` here — the CLI now requires an
  explicit `--vault <path>` to prevent that mistake.
- Vault artifact paths (`_sources/`, `_concepts/`, `_entities/`, `_raw/`,
  `00-Vault-Index/`, `WIKI_SCHEMA.md`, `*.db*`) are gitignored
  belt-and-braces.
- **Testing & dogfooding vaults go under `samples/`** (e.g. `samples/<name>/`,
  used as `--vault-root samples/<name>`) — one known home instead of scattered
  `/tmp` vaults. `samples/` is **gitignored** (scratch tree — see `.gitignore`),
  so its `*.db*` + `_sources/`/`_concepts/`/… artifacts never get committed and
  the repo-is-not-a-vault invariant still holds. Durable, **committed** test
  fixtures (e.g. a skill's eval set) live under their owning
  `skills/<name>/evals/`, **not** `samples/`.

## Pointers

- `README.md` — overview, quick start, external dependencies, repo layout.
- `docs/tasks/` + `docs/plans/` — task/plan specs. **Latest: TASK 029
  `obsidian-cli-skill`** (R-12; `docs/TASK.md` + `docs/PLAN.md` + `docs/tasks/task-029-00..07-*.md`
  + `docs/plans/plan-029-obsidian-cli-skill.md` live at HEAD — the cycle is shipped but
  **not yet rotated** [it rotates at the next task's Analysis per `skill-archive-task`]).
  Preceded by **TASK 028 `query-stemming-yo-folding`** (archived
  `docs/tasks/task-028-query-stemming-yo-folding.md` + `docs/plans/plan-028-*.md`). Preceded
  by **TASK 026 `installer-vault-claude-settings`**
  (`docs/tasks/task-026-installer-vault-claude-settings.md`) + **TASK 025
  `adoption-currency-hardening`** (`docs/tasks/task-025-adoption-currency-hardening.md`
  + `docs/plans/plan-025-*.md`). Adoption runbook at `docs/runbooks/personal-vault-adoption.md`.
  Preceded by **TASK 024 `upsert-layout-fts-hardening`** (`docs/tasks/task-024-upsert-layout-fts-hardening.md`
  + `docs/plans/plan-024-*.md`). Preceded by the ad-hoc **TASK 023** personal-vault dogfood-hardening
  batch (obsidian-personal summary `type_mapping` + structured `sources:` provenance +
  `transcript_dedup`; recorded in the narrative above, no separate `docs/tasks/` doc → 023 gap is
  intentional). Predecessors archived: `task-022-vault-local-db-resolution.md` (+ `task-022-01..09-*.md`)
  + `plan-022-*`; `task-013-wiki-search-metadata-filter.md`
  (R-X3-META-FILTER, shipped `177fd5a`) + `plan-013-*`; `task-012-universal-layout-engine.md`
  (+ 17 per-bead `task-012-00..16-*.md`) + `plan-012-*`; `task-011`/`task-010`
  (wiki-verify eval-v3/v4); `task-009-wiki-verify-critic-rubric.md` (durable eval
  harness at `skills/wiki-verify/evals/` — `evals.json` + `grade.py` + `reports/`);
  `task-008-wiki-verify-multi.md`.
- `docs/ARCHITECTURE.md` — system architecture (multi-vault, ADRs 001+002,
  status header tracks Phase 3a/3b progress).
- `docs/KNOWN_ISSUES.md` — **auto-rendered Class-B ledger** (TASK 012 / R-X3) over
  the per-issue Class-A sources in `docs/issues/*.md`. Regenerate with
  `wiki-index-render --auto-indexes`; a manual edit is flagged by `wiki-lint`
  (PW-Q drift guard). Holds the deferred items (perf SEV-1 set, the R-X1-*
  residuals, R-X3-META-FILTER). Edit the per-issue files, never the ledger.
- `docs/adr/ADR-001-wiki-ingest-integration.md` — Option I (Wrap + Index).
- `docs/adr/ADR-002-multi-vault-bottleneck-corrections.md` — vault_id
  partitioning + Class A/B/C data layering contract.
- `docs/WIKI-INGEST-V1.1-CONTRACT.md` — external `wiki-ingest` skill
  contract; consumed by `wiki-enrich` (install globally before using).
- `scripts/wiki_index/layout.py` — single source of truth for the **karpathy**
  layout constants (`PAGE_SUBDIRS` = `INGEST_SHARED_SUBDIRS` ∪ `HOST_ONLY_SUBDIRS`
  incl. `QUERIES_SUBDIR`, `COURSE_TIER_DIR`, `SYSTEM_FILES`,
  `GLOBAL_VAULT_SENTINEL`, etc.; R-X1-forward role split per TASK 007). Since
  TASK 012 these are *projected into* `layouts/karpathy.yaml` but stay the source
  of truth (byte-identity anchor); they are NOT superseded by the engine below.
- `scripts/wiki_index/layout_config.py` — **TASK 012 / R-X1 config-driven layout
  engine** (`LayoutConfig`, `iter_pages`, `resolve_layout_config`, ReDoS load-gate);
  built-in layouts at `scripts/wiki_index/layouts/{karpathy,dev-project,obsidian-personal}.yaml`;
  schema `config/layout-config.schema.yaml`. The per-layout *grammar* layer,
  separate from the per-vault identity `config_loader.py` (two-systems split).
