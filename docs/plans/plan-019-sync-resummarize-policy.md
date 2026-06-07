# PLAN — TASK 019 `sync-resummarize-policy` (wiki-sync re-summarization gate)

> ✅ **SHIPPED 2026-06-07** — all 10 beads merged green; `/vdd-multi` converged (Logic ✓
> Security ✓ Performance ✓). **1039 pytest (+4 skipped), mypy strict (73 files).** As-built
> refinements vs this plan are logged in `docs/ARCHITECTURE.md` §11a **Q-019-10** + `docs/TASK.md`
> Status (per-scan `Caches`; the bulk DAL `all_cited_sources`; a once-per-scope mirror index +
> operator-regex load-gate; `resolve_policy(path,*,vault_root,caches)`).

Stub-First, **green-throughout**. **10 beads** (019-00…09). **Zero DDL** (`user_version`
stays **5** — reuse `SourceState` + `Page.frontmatter_json`; +1 read-only DAL method).
`mypy --strict scripts/` + full `pytest` green at **every** bead. `wiki-sync` keeps **no
`import anthropic`**. **Back-compat byte-identity**: with no `resummarize:` block the plan
is identical to TASK 018 output (locked at bead 00).

Design is locked: [docs/TASK.md](docs/TASK.md) (RTM E1–E4 + AC-1..13) +
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §11a **Q-019-1..9**. Reviews:
[task-019](docs/reviews/task-019-review.md) · [architecture-019](docs/reviews/architecture-019-review.md).

> **`skill-tdd-strict` (RED-first) for the correctness/security-critical beads:** **02**
> (back-compat byte-identity + unknown-key refusal), **05** (D2a DAL — provenance match
> correctness + injection-safety), **06** (gate **monotonicity** — only `ingest`→`skip`,
> never touches `upsert`/`skip`), **07** (ReDoS — RED must show a catastrophic operator
> regex is *refused at load* or *timed-out per-file*, never hangs). All other beads are
> Stub-First green-throughout.

## Shape (locked, Q-019-1)

- The policy is a **monotone gate** in `wiki_sync._build_entries`, **between**
  `classify_file` and the plan-entry build: it may turn an `ingest`/`convert+ingest` into
  `skip`; it **never** touches `upsert`/`skip`/`record`.
- New SRP module **`scripts/wiki_skills/_resummarize.py`** — `resolve_policy` (per-folder
  cascade) + `summary_exists` (D1 ∪ D2a ∪ D2b) + `apply_policy` (mode + `--force` + reasons).
  `_sync.py` stays the pure classifier; `wiki_sync.py` stays CLI/plan. Acyclic.
- Detectors: **D1** `repo.get_source_state` (existing) · **D2a** new read-only
  `repo.find_pages_citing_source` (`json_extract`/`json_each` over `frontmatter_json`,
  reusing the TASK 013 query pattern) · **D2b** filesystem mirror (`stem-relpath` |
  `group-key` extended regex, ReDoS-guarded via TASK 017 `guarded_search`).
- Config: a strict `$def Resummarize` under `SyncConfig.resummarize` (opt-in; absent ≡
  TASK 018). Per-folder override = `<folder>/.wiki/sync.yaml` `resummarize:` read by reusing
  `load_sync_config` (all its hardening) + `config_loader.deep_merge` deepest-wins.

## Phases

- **Phase 0 — anchor** (00): baseline green + new test module + **back-compat byte-identity** lock.
- **Phase 1 — config** (01 stub, 02 logic): `$def Resummarize` schema + `SyncConfig.resummarize` + loader parse + `detect` defaults.
- **Phase 2 — resolver** (03 stub, 04 logic): `_resummarize.py` surface + per-folder cascade resolver (deepest-wins, per-dir memo, hardening reuse).
- **Phase 3 — detectors + gate** (05 D2a DAL, 06 gate D1∪D2a + mode, 07 D2b mirror + extended regex + ReDoS).
- **Phase 4 — CLI + executor** (08): `wiki-sync scan --force` + dry-run report; `workflows/wiki-sync.md` `--force` + `sources:` writeback; SKILL/schema docs.
- **Phase 5 — acceptance + close** (09): dogfood `samples/Demand-generation` (D2a/D2b/force) + e2e + README/.AGENTS/ROADMAP/CLAUDE/KNOWN_ISSUES.

## Beads

| # | Bead | Phase | Files | Stub-First RED → GREEN | RTM |
|---|------|-------|-------|------------------------|-----|
| **019-00** | Anchor + back-compat lock | 0 | `tests/test_wiki_sync_resummarize.py` (new) | Baseline `pytest -q` + `mypy --strict` green; **byte-identity** test: a fixture vault with **no** `resummarize:` → `_build_entries` plan == TASK 018 plan (locks AC-7 before any change). | AC-7 |
| **019-01** | [STUB] `$def Resummarize` schema + dataclass + loader stub | 1 | `config/sync-config.schema.yaml`, `scripts/wiki_index/sync_config.py`, `tests/…` | Add strict `$def Resummarize` (`mode`,`detect{source_state,provenance_ref{enabled,fields},mirror{…,match,group_key\|key{raw_regex,summary_regex,template,flags}}}`) + `SyncConfig.resummarize: ResummarizeConfig\|None=None` (frozen). Loader stub: parse absent→None. RED: valid block validates; unknown `resummarize.*` key → `INVALID_SYNC_CONFIG`. | E3.1, AC-9/11 |
| **019-02** | [LOGIC] loader parse + defaults + back-compat | 1 | `scripts/wiki_index/sync_config.py`, `tests/…` | Parse `resummarize` into the frozen `ResummarizeConfig`; omitted `detect` → `{source_state:True}` (OQ-5); absent block → `None` (≡ TASK 018, bead-00 lock still green). GREEN: defaults; `mode` enum; unknown-key exit 6 (value not echoed). **`skill-tdd-strict`.** | E3.1, AC-7/9/11 |
| **019-03** | [STUB] `_resummarize.py` surface | 2 | `scripts/wiki_skills/_resummarize.py` (new), `tests/…` | `resolve_policy(path,*,vault_root,vault_config)->ResummarizeConfig`; `summary_exists(...)->str\|None`; `apply_policy(decision,*,…,force)->Decision`. Stubs: `resolve_policy`→vault global; `summary_exists`→None; `apply_policy`→decision unchanged (no gate). RED matrix (mode/force/detector shape). | E1, E2, E3.2 |
| **019-04** | [LOGIC] per-folder cascade resolver | 2 | `scripts/wiki_skills/_resummarize.py`, `tests/…` | `resolve_policy`: collect dirs vault_root→`path.parent`; per dir reuse `load_sync_config(dir).resummarize` (all hardening: size/anchor/symlink/schema) **per-dir-memoized**; `config_loader.deep_merge` **deepest-wins** over the vault global (partial override). GREEN AC-5 (`Module-NN ^(\d+)` vs `Lessons ^(\d{8})`) + AC-10 (order-independent). | E3.2/3.3/3.4, AC-5/10 |
| **019-05** | [STUB→LOGIC] D2a DAL `find_pages_citing_source` | 3 | `scripts/wiki_index/repository.py`, `scripts/wiki_index/sqlite_repository.py`, `tests/…` | ABC `find_pages_citing_source(vault_id, rel_path, fields)->list[str]` (stub `NotImplementedError`, RED). Impl: per **allowlisted** field (`re.fullmatch(r'[a-z_]+')`) `CAST(json_extract(frontmatter_json,?)AS TEXT)=?` **OR** `EXISTS json_each(frontmatter_json,'$.<field>') WHERE value=?` (list-valued `sources:`), values **bound** (injection-safe; reuses the TASK 013 pattern). GREEN AC-2 (pos+neg, list-valued, vault-scoped). **`skill-tdd-strict`.** | E2.2, AC-2/9 |
| **019-06** | [LOGIC] gate: D1∪D2a union + mode + monotonicity | 3 | `scripts/wiki_skills/_resummarize.py`, `scripts/wiki_skills/wiki_sync.py`, `tests/…` | `summary_exists` = D1 `get_source_state` ∪ D2a `find_pages_citing_source` (short-circuit). `apply_policy`: action∉{ingest,convert+ingest}→unchanged (**monotone**); `never`→`skip:resummarize-never`; `always`→unchanged; `if-missing`→`skip:summary-exists:{source_state\|provenance}` if matched. Wire into `_build_entries`. GREEN AC-1/4/8. **`skill-tdd-strict`** (monotonicity: never gates `upsert`). | E1.2/1.3, E2.1/2.2/2.4, AC-1/8 |
| **019-07** | [LOGIC] D2b mirror + extended regex + ReDoS | 3 | `scripts/wiki_skills/_resummarize.py`, `tests/…` | Anchor=nearest `raw_dirs` ancestor; scope=sibling `summary_dir` (or `.`); `stem-relpath` (1:1) + `group-key` (N:1) via `key{raw_regex,summary_regex,template,flags}` (shorthand `group_key`; default `^(\d+)`). Operator regexes **ReDoS-guarded** (reuse `layout_config.guarded_search` + a load-gate). GREEN AC-3/3b/12 (group-key N:1, same-dir stem, asymmetric `M01_L02`↔`02`, catastrophic-regex refused/timeout). **`skill-tdd-strict`.** | E2.3, AC-3/3b/12 |
| **019-08** | [LOGIC] `--force` CLI + dry-run report + workflow writeback | 4 | `scripts/wiki_skills/wiki_sync.py`, `workflows/wiki-sync.md`, `skills/wiki-sync/SKILL.md`, `config/sync-config.schema.yaml` (doc), `tests/…` | argparse `scan --force` → thread `force` into `_build_entries`/`apply_policy` (reason `forced`, zone-scoped); dry-run report counts the new skip reasons (no silent truncation). Workflow: thread `--force`; **`sources:` writeback** on generated summaries (AC-13 contract). SKILL/schema docs. GREEN AC-4(force)/AC-13. | E1.1, E4.1, AC-4/13 |
| **019-09** | [ACCEPTANCE] dogfood + e2e + close | 5 | `tests/test_wiki_sync_resummarize_e2e.py` (new), `README.md`, `*/.AGENTS.md`, `docs/ROADMAP.md`, `CLAUDE.md`, `docs/issues/*` | e2e over `samples/Demand-generation`: D2a (generated `sources:`), D2b group-key (`Module-01`), date-key (`Lessons`), same-dir stem (`Resources`), `--force`, re-run no-op. Record the `lesson-summary` type-mapping prerequisite (Q-019-9) in KNOWN_ISSUES. GREEN AC-5/6/9 end-to-end. | AC-5/6/9 |

## Use Case / AC Coverage

| UC / AC | Beads |
|---|---|
| UC-1 (provenance) / AC-2 | 05, 06, 09 |
| UC-2 (mirror N:1) / AC-3, AC-3b | 07, 09 |
| UC-3 (`--force`) / AC-4 | 06, 08, 09 |
| UC-4 (per-folder override) / AC-5 | 04, 09 |
| UC-5 (back-compat) / AC-7 | 00, 02 |
| UC-6 (`never`) / AC-8 | 06, 09 |
| AC-1 (gate emits skip:summary-exists) | 06 |
| AC-9 (zero-DDL, no anthropic, mypy/pytest) | 05, every bead |
| AC-10 (determinism) | 04 |
| AC-11 (degenerate config) | 02 |
| AC-12 (extended regex + ReDoS) | 07 |
| AC-13 (`sources:` writeback) | 08, 09 |

## Task files

[019-00](docs/tasks/task-019-00-anchor-backcompat.md) ·
[019-01](docs/tasks/task-019-01-stub-resummarize-schema.md) ·
[019-02](docs/tasks/task-019-02-loader-parse-defaults.md) ·
[019-03](docs/tasks/task-019-03-stub-resummarize-module.md) ·
[019-04](docs/tasks/task-019-04-cascade-resolver.md) ·
[019-05](docs/tasks/task-019-05-d2a-provenance-dal.md) ·
[019-06](docs/tasks/task-019-06-gate-union-mode.md) ·
[019-07](docs/tasks/task-019-07-d2b-mirror-redos.md) ·
[019-08](docs/tasks/task-019-08-force-cli-writeback.md) ·
[019-09](docs/tasks/task-019-09-dogfood-e2e-close.md)
