# PLAN 039 — unify the construct path (content-type dispatch + layout-aware filing)

Modify-existing refactor of TASK 038's package (stub-light; green throughout; `mypy --strict`;
zero-DDL; zero deps; no `import anthropic`). Internal Python module stays `wiki_import_article`
(cosmetic — avoids import churn, Q-039-1); the **CLI/skill/command/workflow** become content-neutral
`wiki-import`, with `wiki-import-article` kept as a **back-compat alias**.

## Atomic checklist (stub-first per step; Red→Green)

- **S0 — Branch + alias scaffold.** Branch `task-039-unified-construct-path`. `git mv` skill dir
  `skills/wiki-import-article` → `skills/wiki-import` (reason-contract moves with it); update the
  reason-contract references (summarizing-articles SKILL, ARCHITECTURE, manuals) to the new path.
  `bin/wiki-import` (primary) + `bin/wiki-import-article` (alias → same module). `commands/` +
  `workflows/` renamed to `wiki-import.md` + a thin `wiki-import-article.md` alias. argparse `prog`
  → `wiki-import`. Relink symlinks. *Gate:* `wiki-import --help` works; `wiki-import-article` alias works.
- **S1 — Content-type detection (R-2).** Add `_detect.py` (or extend `prepare`): `--kind
  {meeting,article,paper,thread,summary,auto}`; `auto` heuristics (speaker-turns/timestamps→meeting;
  `concepts:`+`related:`/`type: *-summary` frontmatter→summary; arXiv/PDF-dense→paper; X host→thread;
  else article) returning `(kind, confidence)`. `prepare` envelope gains `kind` + `reason_harness`
  (`summarizing-meetings` for all content-types | `none` for finished summary) + `kind_confidence`. Tests: each kind detected;
  explicit `--kind` overrides; low-confidence surfaced. *Gate:* S1 tests green.
- **S2 — Layout-aware note filing in `apply` (R-3).** Today `apply` writes the note to `--folder`
  + per-kind nothing. Generalize: derive the note target from `resolve_layout_config` —
  **Karpathy** → `_sources/<slug>.md` (+ root `_concepts/` already via extract-concepts);
  **PARA** → `<folder>/<slug>.md` (+ sibling `_concepts/`). Per-kind note `type:`
  (`meeting-summary`/`article-summary`/`summary`) by kind, not hard-coded. Keep the symlink-refusal +
  validate_inside_vault + collision guard. Tests: Karpathy filing + PARA filing + per-kind type.
  *Gate:* S2 tests green.
- **S3 — REASON dispatch docs (R-4, R-5).** `skills/wiki-import/SKILL.md`: the loop now documents
  **kind → harness** — all content-types → the ONE universal [`summarizing-meetings`] harness
  (no redundant `summarizing-articles`), summary → register directly, each fed `known_concepts`. Add `--kind`
  to prepare/apply usage. `workflows/wiki-import.md`: single + batch, both kinds.
- **S4 — Wire the alias + content-neutrality.** `wiki-import-article` bin/skill/command/workflow are
  aliases that forward to `wiki-import` (documented as deprecated-but-supported). Update SKILL
  `description`/triggers to cover meeting + article. *Gate:* alias e2e.
- **S5 — Architecture/manuals (already drafted).** functional-arch §2.3 = the unified single diagram +
  orthogonality matrix (done); ARCHITECTURE §2.3 (done); manual on-ramp tree + Construct table +
  quick-ref updated to `wiki-import` + `--kind` (the EN/RU on-ramp mermaid gets the meeting branch).
- **S6 — e2e on `samples/` fixtures, BOTH layouts + the headline proof.**
  (a) **PARA meeting transcript** → `--kind meeting` → summarizing-meetings REASON → PARA note
  `type: meeting-summary` + sibling `_concepts/` → reindex --full collisions==0 (the TASK 038 hole, closed);
  (b) PARA article (TASK 038 parity); (c) **Karpathy** article/summary → `_sources/` filing.
  Gates: `mypy --strict scripts/`, full `pytest`, `grep import anthropic` empty. Clean scratch after.
- **S7 — VDD.** self-improvement-verificator on this plan (done at design time); after S6,
  `/vdd-multi` (code-reviewer + critic-security + critic-logic) → fix → re-green. Commit on user request.

## Invariants / guards
- **Back-compat (R-6):** every existing `wiki-import-article` invocation + the committed #01/#04 flows
  keep working via the alias; the existing 23 import tests pass under the rename (update import paths/labels only).
- **NF-2:** no new fetch/concept/index/harness logic — compose `resolve_layout_config` + extract-concepts
  + index-upsert + the two existing harnesses.
- **Decision-17 / zero-DDL / mypy --strict** throughout.
- **Rollback:** isolated branch; the change is rename + additive dispatch/filing on a net-new-in-038
  package (no foreign-module edits beyond doc references) → revert = drop the branch; zero-DDL, no migration.

## Out of plan
- Editing external `wiki-ingest`/`summarizing-meetings` (separate postanovka).
- Retiring `wiki-enrich` or routing `wiki-sync ingest`→`wiki-import` (future task).
