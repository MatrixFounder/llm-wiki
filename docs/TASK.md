# TASK 040 — config-driven write-grammar (eliminate the Karpathy/PARA code forks)

## 0. Meta
- **Task ID:** 040 · **Slug:** `task-040-config-driven-write-grammar` · **ADR:** [ADR-007](adr/ADR-007-config-driven-write-grammar.md)
- **Mode:** VDD (code-reviewer + critic-security + critic-logic + self-improvement-verificator on
  the plan). Code task (`scripts/`, `config/`, `layouts/*.yaml`, `tests/`, `docs/`), green-throughout,
  `mypy --strict scripts/`. **Zero DDL** (`user_version` 7 — this is layout *config*, not SQLite
  schema), **zero new deps**, **no `import anthropic`**. **Karpathy byte-identity is the golden gate.**
- **Branch:** `task-040-config-driven-write-grammar`.

## 1. Problem / motivation

The framework's **read side is config-driven** (`layout_config` + `layouts/*.yaml`; TASK 012/024/037),
but the **write side is hardcoded as `if karpathy` / `parent.name == SOURCES_SUBDIR` forks** in
three construct sites — so "Karpathy" exists both as a YAML (read) AND as scattered Python branches
(write), and a new layout can't get karpathy-style filing from YAML. TASK 037 added one such fork,
TASK 039 added two more. ADR-007 decides: **move the write-grammar into the layout YAML; Karpathy
becomes a pure config special-case, like the read side.**

## 2. Scope

### In scope — the forks to collapse (per ADR-007)
- **Add an additive `write:` block to `LayoutConfig` + the schema + the built-in YAMLs:**
  `source_subdir` (`_sources` / `""`), `source_filename` (`slug` / `title`). Concepts-anchor is
  DERIVED from `source_subdir` (non-empty → container `_concepts`; empty → sibling). Optional keys
  default to the karpathy-compatible legacy when absent (back-compat).
- **`wiki-extract-concepts`** — `_sourcing.py` + `__init__.py`: replace the literal `SOURCES_SUBDIR`
  / `parent.name == SOURCES_SUBDIR` checks with `layout.write.source_subdir`. Byte-identical for
  karpathy (the value IS `"_sources"`).
- **`wiki-import`** (`scripts/wiki_skills/wiki_import_article/`) — `_note_dir` + karpathy-fname read
  `source_subdir`/`source_filename`; drop `resolve_alias(...)=="karpathy"`.
- **`wiki-init`** — AUDIT ONLY (no change): already config-driven via `is_two_tier_scaffold` (TASK 031),
  not a layout-name fork; the grep fork-guard does not flag it. `SCAFFOLD_DIRS` stays (the gated two-tier
  scaffold dir-set). Comment added; see PLAN S4.
- Built-ins: `karpathy.yaml` (`source_subdir: _sources`, `source_filename: slug`),
  `obsidian-personal.yaml`/`dev-project.yaml`/`cybos.yaml` (`source_subdir: ""`, `source_filename: title`).

### Out of scope
- The external vendored `wiki_ingest` (Karpathy-only by design — ADR-001; not the shared abstraction).
- SQLite schema / DDL; new deps; LLM-in-CLI.
- Retiring `wiki-enrich` (separate; TASK 039 out-of-scope).
- Any *read*-side behaviour (`paths`/`type_mapping`/`slug_strategy` unchanged).

## 3. Requirements (RTM)

| ID | Requirement | Verify |
|----|-------------|--------|
| **R-1** | `LayoutConfig` carries `write.source_subdir` + `write.source_filename` (parsed from the YAML `write:` block; schema-validated; optional with karpathy-legacy defaults). | unit: parse + defaults |
| **R-2** | `wiki-extract-concepts` source-resolution + concepts-dir use `layout.write.source_subdir` instead of the hardcoded `SOURCES_SUBDIR`/`parent.name==` checks. **No `if karpathy` / literal `SOURCES_SUBDIR` fork remains** in the construct skills. | grep + unit |
| **R-3** | `wiki-import` `_note_dir`/filename read `source_subdir`/`source_filename`; `resolve_alias(...)=="karpathy"` removed. | unit: both layouts |
| **R-4** | `wiki-init` is verified ALREADY config-driven (`is_two_tier_scaffold`, TASK 031) — NOT a layout-name fork; grep-guard excludes it. Audit comment only. | grep-guard + existing init tests |
| **R-5** | **Karpathy byte-identity** — extract-concepts + wiki-import + reindex output byte-identical to pre-040 for a karpathy vault (the value substituted equals the old constant). | golden test + `wiki-reindex --full` diff |
| **R-6** | Back-compat: a vault/override predating `write:` still works (defaults reproduce TASK 037/039 behaviour); the TASK 038/039 import tests + the e2e (PARA meeting + Karpathy article) pass unchanged. | full suite + e2e |
| **NF-1** | Zero-DDL (`user_version` 7), zero deps, no `import anthropic`; `mypy --strict scripts/` clean. | grep + mypy |
| **NF-2** | One parameterized write path — the `write:` grammar is the SINGLE source of truth a NEW layout uses; no construct skill branches on a layout name. | code review |

## 4. Acceptance / definition of done
1. `grep -rE "parent\.name *== *SOURCES_SUBDIR|resolve_alias\([^)]*\) *== *.karpathy" scripts/wiki_skills/` → empty.
2. `pytest tests/` green incl. new write-grammar tests + karpathy byte-identity; `mypy --strict scripts/` clean.
3. e2e on `samples/` fixtures, BOTH layouts (PARA meeting + Karpathy article) reproduce identically; `wiki-reindex --full` collisions==0.
4. A drop-in proof: a NEW throwaway layout YAML declaring `write.source_subdir`/`source_filename` files correctly with ZERO Python change.
5. VDD: code-reviewer + critic-security + critic-logic APPROVE; self-improvement-verificator validates the PLAN.

## 5. Risks / open questions
- **Q-040-1** Concepts-anchor: derive from `source_subdir` (non-empty→container, empty→sibling) vs an explicit field? (Lean: DERIVE — the two are coupled in every real layout; one field, less to misconfigure.)
- **Q-040-2** Course-tier (`COURSE_TIER_DIR` glob in `_sourcing.py`) is a karpathy-specific search; keep it gated on `source_subdir != ""` (so PARA never globs `*/_sources/`). Karpathy behaviour unchanged.
- **Q-040-3** Byte-identity risk on extract-concepts: the substitution must be a pure constant-rename (`SOURCES_SUBDIR` → `layout.write.source_subdir` whose karpathy value == `SOURCES_SUBDIR`). Guard with the golden test BEFORE refactoring (capture current karpathy output, assert unchanged after).
- **Q-040-4** `source_filename: slug` minting reuses `_MINT_SLUG` (TASK 039) — keep the validity gate (a title that slugifies to "" → INVALID_SLUG).

(Design rationale → ADR-007 + `docs/architectures/open-questions.md` Q-040-*.)
