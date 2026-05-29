# Task 008-05: `wiki-verify-multi prepare` — assemble the verification envelope (layout-agnostic)

## Use Case Connection
- UC-22: Verify a filed answer (the `prepare` half).
- UC-24: Idempotent re-verify (`is_unchanged`).
- UC-27: `NO_SOURCES` refusal (empty `cites:`).
- UC-28: Layout-agnostic source access (cited bodies read via `pages.file_path`).

## Task Goal
Add the `wiki-verify-multi prepare <query-slug>` subcommand (R-8.1), the `bin/wiki-verify-multi` wrapper, and the argparse skeleton (`prepare`/`apply` subparsers; `apply` stubbed → handled in 008-06/07). `prepare` is deterministic — **no LLM call**. It loads the audited query page + its cited source bodies (read via `pages.file_path`, **never** a reconstructed `<subdir>/<slug>.md` path — the binding C-8/NFR-7 invariant) and emits the verification envelope.

## Changes Description

### New Files

#### File: `scripts/wiki_skills/wiki_verify_multi.py` (NEW)
- `argparse` with `add_subparsers(required=True)`: `prepare` + `apply` (apply parser defined but its handler returns a "not implemented" stub in this bead).
- `prepare(args) -> int`:
  - `get_page(vault_id, slug=query_slug, project)` → if absent or `type != "query"` → `QUERY_NOT_FOUND` (exit 2).
  - Read the query page body + `question:` + `cites:` from the page (via its `pages.file_path` resolved against `--vault-root`; reuse the existing frontmatter/body read helper — `frontmatter` lib + bounded read with `O_NOFOLLOW`).
  - If `cites:` is empty/absent → `NO_SOURCES` (exit 2) — refuse to verify an answer that cites nothing (R-8.8a).
  - For each cited `"<project>/<slug>"`: `get_page` it; read its body via **its** `pages.file_path` (layout-agnostic — the cited source may be `_sources/`, `_concepts/`, or any layout; resolve from the stored relative path, not a constructed one). **A cited slug with no `pages` row is EXCLUDED from the `examined` set and recorded in a `missing_cites` report field** (plan-review m-3 — single chosen behaviour, not "or skip"; do not crash). Consequence: a verdict finding that cites a missing source correctly trips `FINDING_SOURCE_NOT_EXAMINED` in 008-06 (the grounding key is the examined set, which excludes missing cites).
  - `answer_hash = sha256(answer body)`.
  - `verification_slug` = `--slug` if given (kebab-validated → `INVALID_SLUG`) else **`verify-<query-slug>`** — NOT the bare `query_slug`. **(Found-in-dev fix, operator-approved 2026-05-29):** the `pages` PK `(vault_id, slug, project)` is subdir-independent, so a verdict at `_verifications/<query-slug>.md` (slug=`<query-slug>`, project=`_vault_`) would collide with — and `upsert_page`-overwrite — the audited query page row (slug=`<query-slug>`, project=`_vault_`). The `verify-` prefix gives the verdict page a distinct PK; `verifies:` still points at `_vault_/<query-slug>`. Regression: `test_wiki_verify_index.py::test_query_page_row_survives_verification`.
  - `check_verify_state(vault_id, verification_slug)`; compute `verify_hash = sha256(answer_hash ‖ ordered examined project/slug set)`; `is_unchanged = (recorded == verify_hash)`.
  - Emit the envelope JSON (exit 0): `{vault_id, query_slug, question, answer_excerpt, answer_hash, is_unchanged, verification_slug, examined:[{project,slug,title,body_excerpt}], examined_count}`. Bodies/excerpts vault-relative (no absolute-path disclosure).
- Reuse `_common` primitives (`validate_inside_vault`, bounded `O_NOFOLLOW` read) and the config/`make_repo` factory. **No literal page-subdir string anywhere in this module** (C-8/NFR-7 — enforced by a grep guard test).

#### File: `bin/wiki-verify-multi` (NEW, +x)
- Thin wrapper: `exec python3 -m scripts.wiki_skills.wiki_verify_multi "$@"` (mirror `bin/wiki-query`).

## Test Cases

### End-to-end Tests
1. **TC-E2E-01 (envelope):** fixture vault with a filed `_queries/q.md` (`cites: [_vault_/foo]`) + the `foo` source page indexed. `prepare q` → envelope with `examined_count == 1`, `examined[0].slug == "foo"`, a non-empty `answer_hash`, `verification_slug`. Exit 0.
2. **TC-E2E-02 (QUERY_NOT_FOUND):** `prepare nonexistent` → exit 2 `QUERY_NOT_FOUND`; `prepare <a-concept-slug>` (not `type=query`) → `QUERY_NOT_FOUND`.
3. **TC-E2E-03 (NO_SOURCES):** a query page with empty `cites:` → exit 2 `NO_SOURCES`.
4. **TC-E2E-04 (is_unchanged):** after `record_verify_state` with the matching `verify_hash`, `prepare` → `is_unchanged: true`.
5. **TC-E2E-05 (layout-agnostic):** a cited source whose `pages.file_path` is in a **non-Karpathy** directory (e.g. `notes/foo.md`, not `_sources/`) is still read — `examined[0].body_excerpt` is non-empty (proves the read path uses `file_path`, not a reconstructed `_sources/<slug>.md`).
6. **TC-E2E-06 (`--help`):** `wiki-verify-multi --help` and `… prepare --help` exit 0.

### Unit Tests
1. **TC-UNIT-01:** `answer_hash` is stable for identical answer bodies, differs for changed.
2. **TC-UNIT-02:** `verify_hash` folds in the ordered examined set (changing a cited slug changes it).
3. **TC-UNIT-03 (grep guard):** the module source contains **no** `PAGE_SUBDIRS` literal (`"_sources"`, `"_concepts"`, `"_entities"`, `"_queries"`, `"_verifications"`) — a `grep`/AST scan over `wiki_verify_multi.py`.

### Regression Tests
- `apply` subcommand exists (stub) and `--help` works; no other skill affected.

## Acceptance Criteria
- [ ] `prepare <query-slug>` emits the verification envelope; cited bodies read via `pages.file_path` (layout-agnostic).
- [ ] `QUERY_NOT_FOUND` / `NO_SOURCES` / `INVALID_SLUG` exit-2 envelopes; `is_unchanged` short-circuit.
- [ ] **Grep guard green** — no `PAGE_SUBDIRS` literal in the module.
- [ ] `bin/wiki-verify-multi --help` exits 0; full `pytest` green; `mypy --strict` clean.

## Notes
Stub-First: Phase-1 argparse + `bin` wrapper + `apply` stub + RED envelope/error tests; Phase-2 the `get_page`/`file_path`-read/hash/slug/`check_verify_state` logic. Depends on 008-04 (verify-state DAL). The layout-agnostic read path is the operator-binding constraint — the grep guard (TC-UNIT-03) is non-negotiable.
