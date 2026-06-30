# Task 046-01 (P1) — wiki-import output-grammar + toggles

Beads: B1 (stub) · B2 (R-2) · B3 (R-1) · B4 (R-4) · B5 (R-5) · B6 (R-3). Stub-First.

## Goal
`wiki-import apply` files a **pyramid** note for `--kind meeting|lesson` (vs the article
wrapper for `article|paper|thread`), adds the `lesson` kind, and gains `--diagrams` +
`--concepts/--no-concepts`. `--kind article` stays byte-identical.

## Context (files to edit)
- `scripts/wiki_skills/wiki_import_article/_detect.py` — `KINDS` (line ~13), `KIND_HARNESS` (~20).
- `scripts/wiki_skills/wiki_import_article/__init__.py` — kind→type map (~68), `_note_type` (~338),
  apply argparse, `_file_concepts` call (~659), grammar derivation before `assemble_note`.
- `scripts/wiki_skills/wiki_import_article/_authoring.py` — `assemble_note` (~175): add `grammar` param + pyramid path.
- New test: `tests/test_import_grammar_toggles.py`. Reference style: `tests/test_import_article_apply.py`.

## Steps
1. **B1** — branch `task-046-converge-construct`; create the test file with 6 `@pytest.mark.skip` stubs.
2. **B2** — `KINDS += ("lesson",)`; `KIND_HARNESS["lesson"]="summarizing-meetings"`; kind→type map
   `"lesson":"lesson-summary"`. (KINDS stays a tuple; keep ordering.)
3. **B3** — `assemble_note(..., grammar: str = "article")`. `if grammar == "pyramid":` build
   `fm + "\n# {title}\n\n{src_line}\n> **{raw}:** {raw_link}\n\n" + body_text` (+ `## {entities}` footer
   only when `san_names`), skipping the `## {full_text}` wrapper. In `__init__.py` apply:
   `grammar = "pyramid" if args.kind in {"meeting","lesson"} else "article"`; pass to `assemble_note`.
3. **B4** — apply argparse `--diagrams` (store_true); add `"diagrams": args.diagrams` to the manifest.
4. **B5** — mutually-exclusive `--concepts`(default True)/`--no-concepts`; wrap `_file_concepts(...)`
   in `if concepts_on:` else append `{"concepts":"deferred"}` to manifest.
5. **B6** — verify `--kind article` path unchanged (grammar="article").

## Test Cases
- **TC-E2E-01 (B3/R-1, B2/R-2)** `test_import_apply_pyramid_grammar[meeting|lesson]` (parametrized):
  apply `--kind meeting|lesson` with a note-JSON whose `body` is a pyramid → on-disk note has
  `type: meeting-summary|lesson-summary`, `grammar == "pyramid"`, contains the body + entity footer,
  has **no** `## Полный текст (перевод)`/`## Саммари` wrapper, source line reads as a digest ("саммари").
  `test_import_apply_pyramid_thread_mode_keeps_digest_origin`: pyramid kind + `--mode thread` keeps the
  digest origin (not the "тред" label).
- **TC-UNIT-03 (B6/R-3)** `test_import_apply_article_unchanged`: `--kind article` → output structurally
  identical to current (TL;DR/Key findings/Key entities/Full-text wrapper present).
- **TC-UNIT-04 (B4/R-4)** `test_import_apply_diagrams_flag`: `--diagrams` → manifest `diagrams: true`.
- **TC-UNIT-05 (B5/R-5)** `test_import_apply_concepts_toggle`: `--no-concepts` → 0 concept pages +
  manifest `concepts: deferred`; default → concepts filed.

## Verification
`source .venv/bin/activate && pytest tests/test_import_grammar_toggles.py tests/test_import_article_apply.py -v`
→ all green. `mypy --strict scripts/` clean. No `import anthropic`.

## Acceptance
- [ ] 6 tests green; existing import tests green (regression).
- [ ] `--kind article` byte-identical; concepts default ON.
- [ ] mypy --strict clean.
