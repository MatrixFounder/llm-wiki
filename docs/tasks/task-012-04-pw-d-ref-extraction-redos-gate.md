# Task 012-04: PW-D — config-driven ref extraction + stdlib-`re` ReDoS load-gate

> **`skill-tdd-strict`** (security surface per NFR-4 — promoted by plan-review MAJOR-2).

## Use Case Connection
- UC-29: Karpathy wiki-link refs byte-identical (the `mentioned` rows in the golden anchor).
- UC-31: dev-project adds markdown-link + id-ref extraction.
- UC-34 A1: a pathological operator regex → config-load **exit 6** before any file is read.

## Task Goal
Make cross-reference extraction config-driven (PW-D): iterate `config.ref_extraction[]`
instead of the hardcoded `_WIKILINK_RE`, and add a **stdlib-`re` ReDoS load-time budget
gate** (D-012-3 — no `regex` dependency).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_source/parsing.py`
- Add `extract_refs(body: str, rules: tuple[RefRule, ...]) -> list[tuple[str, int, str]]`:
  per rule, compile + `finditer` per line; apply `transform: stem` (basename без `.md`) when
  set; return `(target, line_no, quote[:200])` (same shape as `extract_wiki_links`).
- Keep `_WIKILINK_RE` + `extract_wiki_links` as the **karpathy wrapper** (byte-identical);
  `extract_wiki_links(body)` may delegate to `extract_refs(body, (<karpathy wiki-link rule>,))`
  IFF the output is proven byte-identical by the 012-00 anchor — otherwise leave it untouched
  and have the reindex layer call `extract_refs(body, config.ref_extraction)`.

#### File: `scripts/wiki_index/reindex.py`
- Replace the wiki-link extraction call in the page-rebuild with
  `extract_refs(body, config.ref_extraction)` (karpathy config carries only the wiki-link
  rule → identical `mentioned` rows; the `cited`/`verifies` frontmatter read-sides are
  unchanged).

#### File: `scripts/wiki_index/layout_config.py`
- **ReDoS load-gate** in `load_layout_config` (after `_validate`, before `_build`): for each
  operator-supplied regex, `re.compile` (compile-fail → `LayoutConfigError`/exit-6), then
  measure median-of-**N≥5** `pattern.search(payload)` wall-clock against a versioned
  adversarial payload fixture; if the median exceeds a fixed **ceiling constant** → raise
  `LayoutConfigError` (exit-6) naming the offending pattern. Built-in layouts are pre-vetted
  (they pass). Constants `_REDOS_N` + `_REDOS_CEILING_S` live in the module (explicit, not
  one-shot — plan-review m2 / architecture-review m2).
- **Scope = BOTH operator regex sources** (012-02 Roast finding): the gate covers
  `ref_extraction[].regex` **AND** `paths[].project_pattern` (the latter is compiled +
  run per-file in `iter_pages::_derive_project`; an un-budgeted pathological project_pattern
  would hang discovery just as a ref pattern would). Fold the budget check into the existing
  `_validate_path_patterns` (which already compiles `project_pattern` at load) so both
  surfaces share one gate.

### New Test Fixture
#### Dir: `tests/fixtures/redos_payloads/` (NEW)
- `catastrophic.txt` — a ~100 KB adversarial payload (e.g. `("a"*100 + "!") * 1000`) that
  triggers exponential backtracking on a nested-quantifier pattern. Versioned + named so the
  gate is reproducible.

### Changes in Test Files
#### File: `tests/test_ref_extraction.py` (NEW)
- `extract_refs` with the karpathy wiki-link rule == `extract_wiki_links` byte-identical on a
  multi-link body (incl. `[[a|display]]`).
- dev-project rules: a markdown-link `[x](foo.md#h)` → `foo` (stem transform); an id-ref
  `ADR-002`/`R-6.5`/`task-012-04` captured.
- **ReDoS:** a `LayoutConfig` override carrying a catastrophic regex → `load_layout_config`
  raises `LayoutConfigError` (exit-6) against the payload fixture; the built-in karpathy/
  dev-project/obsidian-personal patterns all pass the budget.
- 012-00 golden snapshot green (karpathy `mentioned` rows unchanged).

## Acceptance Criteria
- ✅ Karpathy wiki-link extraction byte-identical; dev markdown-link + id-ref work.
- ✅ Pathological pattern rejected at config-load (exit-6); built-ins pass.
- ✅ stdlib `re` only — no `regex` in `requirements.txt`. `mypy --strict` clean; suite green.

## Stub-First (`skill-tdd-strict`, test-first)
Phase 1: `extract_refs` stub returns `extract_wiki_links` output; the ReDoS gate is a no-op.
Write the byte-identity + dev-rule + ReDoS-reject tests RED. Phase 2: real iteration + the
median-of-N budget gate; full edge-case coverage (compile-fail, transform=stem, empty rules).
