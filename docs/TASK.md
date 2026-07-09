# TASK 055 — wiki-import note-processing fixes (WI-1/2/3 + P-6 residual)

## 0. Meta Information
- **Task ID**: 055
- **Slug**: wiki-import-note-processing-fixes
- **Type**: Bug-fix batch (4 filed issues found while dogfooding `arxiv.org/abs/2510.08369`)
- **Effort**: S (localized fixes in `wiki_import_article` + the REASON contract + tests; zero DDL, zero schema bump)
- **Context**: A prior agent filed four issues against the `wiki-import` construct path while
  importing an arXiv paper (`--kind paper --mode summary`). All four are on the per-source
  authoring/plumbing layer, none touch the DB schema or Class A/B invariants. This task fixes
  and closes them.
- **Architecture**: No structural change. The fixes ride existing components
  (`wiki_import_article/{_authoring.py,_context.py,__init__.py}`, `skills/wiki-import/references/reason-contract.md`).
  Decision-17 preserved (no `import anthropic`); one JSON envelope + stable exit code unchanged;
  `user_version 7` unchanged.

## 1. Source issues
- [docs/issues/wi-1-tldr-truncated-mid-word-in-summary-body.md](issues/wi-1-tldr-truncated-mid-word-in-summary-body.md) — SEV-3 correctness
- [docs/issues/wi-2-summary-mode-quote-fallback-unclear.md](issues/wi-2-summary-mode-quote-fallback-unclear.md) — SEV-3 robustness/docs
- [docs/issues/wi-3-published-drops-month-only-source-date.md](issues/wi-3-published-drops-month-only-source-date.md) — SEV-4 robustness
- [docs/issues/p-6-known-concepts-payload-o-n-per-prepare-invocation.md](issues/p-6-known-concepts-payload-o-n-per-prepare-invocation.md) — SEV-2 residual (wiki-import path uncovered by R-015-3)

## Requirements Traceability

| ID | Requirement | Acceptance criteria | Affected component |
|---|---|---|---|
| WI-1 | The rendered `## Кратко`/`## Саммари` body must carry the **full** tldr — never a mid-word `[:300]` cut. Only the frontmatter `tldr:` scalar stays capped, and that cap cuts on a word boundary with a trailing `…` (character-based, Cyrillic-safe). | A tldr > 300 chars renders in full in the body; the frontmatter scalar ends on a whole word + `…`; a tldr ≤ 300 chars is byte-identical to today in BOTH slots. | `_authoring.py::assemble_note` |
| WI-2 | The REASON contract must state precisely, for `mode=summary` (where `body` is null), that every `entities[].quote` must be a verbatim substring of `tldr`/`summary_bullets`, and that the "body-line" fallback searches the **rendered** summary note (tldr + bullets), with `no-verbatim-quote` drops surfaced via the `CONCEPTS_DROPPED` warning. | Contract text carves out summary-mode explicitly; a regression test proves the fallback resolves a bullet-line mention and that a bullet-less drop is reported. | `skills/wiki-import/references/reason-contract.md`; verified against `_authoring.verbatim_quote` |
| WI-3 | A month-precision source date (`YYYY`/`YYYY-MM`, e.g. arXiv `2025-10`) must survive into `published:`. The contract accepts partial dates, and `apply` falls back to prepare's extracted `date` when the note JSON leaves `published` null. | Importing a source whose only date is `2025-10` yields `published: "2025-10"` in the note; a full `YYYY-MM-DD` in the note JSON still wins over the fallback. | `reason-contract.md` (`published` type); `__init__.py::apply` (new `--published`); `_authoring.py` passthrough (already correct) |
| P-6R | `wiki-import prepare` must expose `--known-concepts-format {full,slugs-only}` (mirroring R-015-3 on `wiki-extract-concepts`), plumbed through `_context.known_concepts`, so a large vault can avoid the full O(N×~200 B) known-concepts payload. Default `full` (backward-compatible). | `prepare --known-concepts-format slugs-only` emits `known_concepts: [slug, …]`; default/omitted emits `[{slug,name}, …]` (byte-identical to today). | `__init__.py::prepare` (argparse + call); `_context.known_concepts` |

## 3. Non-goals / constraints
- **No schema change / no DDL** (zero-DDL posture; `user_version 7`).
- **Backward-compat**: every change is additive; existing envelopes/notes for the ≤300-char /
  `full`-mode / default-format paths stay byte-identical (guarded by existing tests).
- **Decision-17**: no reasoning added to the CLIs; the REASON contract stays the single LLM step.
- **P-6 residual scope**: implement the `--known-concepts-format` plumbing (the primary documented
  fix). The optional lexical-overlap rank/cap is deferred (riskier — could drop a concept the
  orchestrator needs; not required to close the residual).

## 4. Definition of done
- All four fixes implemented with unit/regression tests (TDD).
- Full `pytest tests/` green; `mypy --strict scripts/` clean.
- Adversarial multi-critic review (logic/security/performance) converged (0 CRITICAL).
- The four issue files set `status: fixed` with a dated Resolution note; `docs/KNOWN_ISSUES.md`
  regenerated via `wiki-index-render --auto-indexes` (Class-B ledger — never hand-edited).
