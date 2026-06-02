# PLAN — TASK 017 `drift-delta-redos-timeout`

Stub-First, green-throughout. **14 beads** (017-00…13). **Zero DDL** (`user_version`
stays 5). `mypy --strict scripts/` + full `pytest` green at **every** bead. Built-in-layout
byte-identity (`tests/test_karpathy_byte_identity.py`) green throughout.

Closes: **R-X1-REDOS-RT** (SEV-2, security — beads 01–06), **P-2** (07–08), **P-3** (09–11).

> **`skill-tdd-strict` for Phase 1 (SEV-2 security).** Beads 01–06 follow strict TDD:
> **AC-017-1** is a strict regression — the catastrophic-pattern test must **hang/timeout with
> the guard removed** and pass with it (guard the assertion with a wall-clock bound /
> `pytest.mark.timeout`). The other phases follow Stub-First green-throughout.
Design is locked in [docs/TASK.md](docs/TASK.md) (RTM + D-017-A/B/C) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3.5 "Runtime ReDoS deadline" + "Single-stat
walk", §8.4, §6.1, §7.3, §11a Q-017-1..4.

## Design (locked)

### Phase 1 — R-X1-REDOS-RT: per-file regex deadline, operator-custom only (beads 01–06)

- **Dependency:** add `regex>=2024.0` (runtime) + `types-regex` (dev) to `requirements.txt`;
  `pip install` into `.venv`. The wheel ships no inline stubs (verified) → `types-regex`
  carries the `mypy --strict` typing.
- **Provenance (Q-017-1).** Add two booleans to the frozen `LayoutConfig`
  (`scripts/wiki_index/layout_config.py`): `ref_extraction_operator_supplied: bool = False`,
  `paths_operator_supplied: bool = False`. Set in `load_layout_config` from whether the
  per-vault override dict supplied that key (the Q-012-f merge **replaces** the whole list,
  so provenance is per-list-exact). `resolve_layout_config`'s built-in-only path leaves both
  `False`.
- **Guard helper (Q-017-2).** New module-level helper in `layout_config.py`
  (importable by `wiki_source/parsing.py` — that module already imports `RefRule` from here,
  so no new cycle) + constant `WIKI_REDOS_BUDGET_S = 2.0` (env-overridable
  `WIKI_REDOS_BUDGET_S`). Shape:
  ```python
  WIKI_REDOS_BUDGET_S: float = _env_float("WIKI_REDOS_BUDGET_S", 2.0)

  def guarded_finditer(pattern: str, text: str, *, operator: bool, deadline: float | None):
      """operator=False → stdlib re.compile(pattern).finditer(text) (byte-identity).
         operator=True  → regex.compile(pattern).finditer(text, timeout=remaining),
         remaining = deadline - monotonic(); raises builtin TimeoutError past the deadline."""
  ```
  A sibling `guarded_search` for the single-shot `_derive_project` case. The consumer owns
  the per-file `deadline = monotonic() + WIKI_REDOS_BUDGET_S` and passes the *remaining* time
  to each call (per-file budget, not per-call — `extract_refs` runs `finditer` per line).
- **`extract_refs` wiring (R-017-1c).** `scripts/wiki_source/parsing.py::extract_refs(body,
  rules, *, operator_supplied: bool = False, budget_s: float = WIKI_REDOS_BUDGET_S)`. When
  `operator_supplied`: compute one deadline, route each line's `finditer` through
  `guarded_finditer(..., operator=True, deadline=...)`; on `TimeoutError` → return **empty
  refs** + a `logging.warning` naming the file/line-count only (CWE-117/209), never raise.
  When not: today's stdlib path verbatim. Caller `reindex.py:228` (`_body_refs`) passes
  `operator_supplied=config.ref_extraction_operator_supplied`.
- **`_derive_project` wiring (R-017-1d).** `layout_config.py::_derive_project(rel_posix,
  entry, *, operator_supplied=False)`; when operator → `guarded_search(entry.project_pattern,
  rel_posix, operator=True, deadline=monotonic()+WIKI_REDOS_BUDGET_S)`; on `TimeoutError` →
  `UNMATCHED_PROJECT` + WARN (exact parity with the existing pattern-miss branch). `iter_pages`
  passes `operator_supplied=config.paths_operator_supplied`.
- **Load-gate alignment (R-017-1f).** `_redos_budget_check` compiles/probes each pattern under
  the engine it will run under (operator→`regex`, built-in→`re`). Kept as defense-in-depth.
  Dialect note (`regex` V0 = `re`-compatible near-superset) documented in the `layout_config`
  module docstring + `config/layout-config.schema.yaml` notes.

### Phase 2 — P-2: single-stat delta walk (beads 07–08)

- **`DiscoveredPage.mtime` (R-017-3a).** Add `mtime: float | None = None` to the
  `DiscoveredPage` NamedTuple (layout_config.py:134). In `iter_pages`, replace the
  `path.is_file()` check with a single `st = path.stat()` (or `os.scandir` `DirEntry`),
  deriving is-file via `stat.S_ISREG(st.st_mode)` and carrying `st.st_mtime` onto the tuple.
  Iteration order + match-set unchanged (golden anchor).
- **`reindex_delta` reuse (R-017-3).** At `reindex.py:299`, read `disc.mtime` instead of
  `path.stat().st_mtime` (fall back to a stat only if `disc.mtime is None`, for any
  non-`iter_pages` caller). One stat/file on the no-op delta path.

### Phase 3 — P-3: check_drift fast-paths, integrity-first default (beads 09–11)

- **`_extract_frontmatter_type` regex fast-path (R-017-2a).** Replace `yaml.safe_load`
  (sqlite_repository.py:676) with a regex match `^type:[ \t]*(\S.*?)[ \t]*$` (MULTILINE) on
  the frontmatter block, stripping surrounding quotes; **fall back to PyYAML** when the value
  looks non-trivial (leading `[`/`{`/`|`/`>`/`&`/`*`, unbalanced quote). Byte-identical type
  on the corpus.
- **`--mtime-skip` opt-in (R-017-2c, Q-017-3).** `wiki_lint.py` adds `--mtime-skip`
  (default off) → threads `mtime_skip` through `lint.py` → `repo.check_drift(vid,
  trust_mtime=mtime_skip)`. `check_drift` adds `last_modified` to its `SELECT`; when
  `trust_mtime` and stored `last_modified == disk mtime` → skip read+sha256 for that file
  (still hashes on mismatch). **Default (trust_mtime=False) = always full-hash** (D-017-B
  integrity-first). Zero DDL (column already exists).

### Phase 4 — evidence + close (beads 12–13)

- Benchmark before/after (delta no-op + lint) at `--n 1000` (+`10000` if feasible); record in
  TASK status. Flip the 3 issues → `fixed`; re-render `docs/KNOWN_ISSUES.md`; update
  `requirements.txt`/`README.md`/`.AGENTS.md`/`ROADMAP`/CLAUDE status.

## Beads

| # | Bead | Phase | Files | Stub-First RED → GREEN | RTM |
|---|------|-------|-------|------------------------|-----|
| **017-00** | Anchor + deps | setup | `requirements.txt`, `tests/test_task017_hardening.py` (new) | Add `regex>=2024.0` + `types-regex`; `pip install`; baseline `pytest -q` + `mypy --strict`; 1 smoke test (`import regex`; `from scripts.wiki_index.layout_config import WIKI_REDOS_BUDGET_S` will fail until 01 — assert import of module only). | NF3, NF6 |
| **017-01** | [STUB] guard helper + provenance fields + budget const | 1 | `scripts/wiki_index/layout_config.py`, `tests/test_task017_hardening.py` | Add `WIKI_REDOS_BUDGET_S` (+ env read); `guarded_finditer`/`guarded_search` stubs (`raise NotImplementedError`); add `ref_extraction_operator_supplied`/`paths_operator_supplied=False` to `LayoutConfig`. RED `test_guarded_finditer_timeout` (catastrophic op pattern) + RED `test_provenance_flags_on_override`. | R-017-1a/b partial, Q-017-1 partial |
| **017-02** | [LOGIC] provenance in loader | 1 | `scripts/wiki_index/layout_config.py` | Set the two booleans in `load_layout_config` from override keys; `test_provenance_flags_on_override` GREEN + `test_provenance_false_builtin` (resolve_layout_config → both False). | Q-017-1, R-017-1e |
| **017-03** | [LOGIC] implement guard helper | 1 | `scripts/wiki_index/layout_config.py` | Implement `guarded_finditer`/`guarded_search` (re passthrough vs regex+`timeout=remaining`); `test_guarded_finditer_timeout` GREEN (`TimeoutError` on 100 KB line < budget+ε) + `test_guarded_builtin_uses_re` (operator=False ≡ stdlib finditer output). | R-017-1b |
| **017-04** | [LOGIC] wire `extract_refs` | 1 | `scripts/wiki_source/parsing.py`, `scripts/wiki_index/reindex.py`, `tests/…` | Add `operator_supplied`/`budget_s` kwargs; per-file deadline; `TimeoutError`→empty+WARN; `reindex._body_refs` passes `config.ref_extraction_operator_supplied`. GREEN UC-1 (`test_extract_refs_operator_timeout_skips`) + UC-2 (`test_extract_refs_builtin_byte_identical`). | R-017-1c, AC-017-1/2 |
| **017-05** | [LOGIC] wire `_derive_project` | 1 | `scripts/wiki_index/layout_config.py`, `tests/…` | Add `operator_supplied` kwarg; operator→`guarded_search`; timeout→`UNMATCHED_PROJECT`+WARN; `iter_pages` passes `config.paths_operator_supplied`. GREEN `test_derive_project_operator_timeout_unmatched`. | R-017-1d |
| **017-06** | [LOGIC] align load-gate engine + dialect docs | 1 | `scripts/wiki_index/layout_config.py`, `config/layout-config.schema.yaml` | `_redos_budget_check` probes operator→`regex`, built-in→`re`; document V0 dialect. GREEN `test_redos_gate_rejects_operator_regex_under_regex_engine`. | R-017-1f/h |
| **017-07** | [LOGIC] `DiscoveredPage.mtime` single-stat | 2 | `scripts/wiki_index/layout_config.py`, `tests/…` | Add `mtime` field; one `stat` per file in `iter_pages` (derive is-file + mtime); golden anchor + order tests green; `test_iter_pages_populates_mtime`. | R-017-3a/b, AC-017-2 |
| **017-08** | [LOGIC] `reindex_delta` reuse mtime | 2 | `scripts/wiki_index/reindex.py`, `tests/…` | Read `disc.mtime` (stat fallback if None); `test_reindex_delta_single_stat_per_file` (stat-count spy on no-op delta). | R-017-3, AC-017-4 |
| **017-09** | [LOGIC] `type:` regex fast-path | 3 | `scripts/wiki_index/sqlite_repository.py`, `tests/…` | Replace PyYAML in `_extract_frontmatter_type` w/ regex + fallback; `test_extract_type_regex_equals_pyyaml` over a sample matrix (bare/quoted/folded/list). | R-017-2a, AC-017-3 (part) |
| **017-10** | [STUB] `--mtime-skip` flag + param thread | 3 | `scripts/wiki_skills/wiki_lint.py`, `scripts/wiki_index/lint.py`, `scripts/wiki_index/sqlite_repository.py`, `tests/…` | Add `--mtime-skip` (default off); thread `trust_mtime` param to `check_drift` (accepted, **ignored** = stub); RED `test_check_drift_mtime_skip` (asserts skip behavior — fails until 011). | R-017-2c partial, Q-017-3 |
| **017-11** | [LOGIC] `check_drift` trust_mtime | 3 | `scripts/wiki_index/sqlite_repository.py`, `tests/…` | Add `last_modified` to SELECT; skip read+hash on mtime-match; `test_check_drift_mtime_skip` GREEN + `test_check_drift_default_detects_preserved_mtime_tamper` (integrity) + `test_check_drift_mtime_change_still_hashed`. | R-017-2c/d, AC-017-3 |
| **017-12** | Benchmark evidence + regression | 4 | `docs/TASK.md` (status block) | `scripts/benchmark.py --n 1000` (delta + lint) before/after; record numbers; full `pytest` + `mypy --strict` + byte-identity green. | R-017-4d, NF7, AC-017-5 |
| **017-13** | Close issues + docs gate | 4 | `docs/issues/{r-x1-redos-runtime-deadline-residual,p-2-…,p-3-…}.md`, `docs/KNOWN_ISSUES.md`, `README.md`, `scripts/**/.AGENTS.md`, `docs/ROADMAP.md`, `CLAUDE.md` | Flip 3 issues `open→fixed`; re-render ledger (`wiki-index-render --auto-indexes`); `wiki-lint` PW-Q clean; README external-deps += `regex`; AGENTS/ROADMAP/CLAUDE status. | AC-017-6, NF6 |

## Dependency / order

```
017-00 (anchor + deps; stays green throughout)
  → 017-01 (stub helper + provenance fields + budget const)
  → 017-02 (provenance set in loader)         ─┐ Phase 1 (R-X1-REDOS-RT, SEV-2)
  → 017-03 (implement guard helper)            │
  → 017-04 (wire extract_refs)                 │  needs 02 (flag) + 03 (helper)
  → 017-05 (wire _derive_project)              │  needs 02 + 03
  → 017-06 (align load-gate + dialect docs)   ─┘
  → 017-07 (DiscoveredPage.mtime single-stat)  ─┐ Phase 2 (P-2)
  → 017-08 (reindex_delta reuse mtime)         ─┘  needs 07
  → 017-09 (type: regex fast-path)             ─┐ Phase 3 (P-3)
  → 017-10 (stub --mtime-skip + param)          │
  → 017-11 (implement check_drift trust_mtime) ─┘  needs 10; benefits 07 (mtime reuse)
  → 017-12 (benchmark evidence + full regression)
  → 017-13 (close issues + docs gate)
```

## Verification (end-to-end)

1. `pytest -q` ≥ 879 (+4 skipped) + `mypy --strict scripts/` clean at **every** bead.
2. **AC-017-1** (ReDoS): operator-custom catastrophic ref regex on a 100 KB single line →
   reindex skips the file + WARN, completes < budget+ε; the same test **hangs** with the
   guard removed (xfail/timeout guard).
3. **AC-017-2** (byte-identity): `test_karpathy_byte_identity` green; a spy asserts the
   `regex` engine is **not** imported/called on a built-in-layout reindex.
4. **AC-017-3** (P-3): `_extract_frontmatter_type` ≡ PyYAML on the matrix; default mode
   detects a preserved-mtime tamper; `--mtime-skip` skips on match, hashes on change.
5. **AC-017-4** (P-2): stat-count spy → exactly one stat per discovered file on a no-op
   delta; iteration order byte-identical.
6. **AC-017-5** (gates): `user_version` still 5; benchmark before/after recorded in TASK.
7. **AC-017-6** (docs): 3 issues `fixed`; ledger re-rendered; `wiki-lint` PW-Q clean.

## Use Case Coverage

| Use Case | Beads |
|----------|-------|
| UC-1 (operator catastrophic pattern → skip+WARN) | 017-01, 017-03, 017-04, 017-05 |
| UC-2 (built-in byte-identity, regex untouched) | 017-02, 017-04, 017-07 |
| UC-3 (drift integrity default + `--mtime-skip`) | 017-09, 017-10, 017-11 |
| UC-4 (delta no-op single-stat) | 017-07, 017-08 |

## Out of scope (per TASK §6)

- P-1 / P-4 / R-X1-CFG-COST and other SEV-3 perf items; any DDL / `file_size` column;
  RE2; replacing the load-time `_redos_budget_check` (kept as defense-in-depth).
