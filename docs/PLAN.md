# PLAN 052 — wiki-import: participants → `participants:`, not person concept pages

Stub-First / TDD: write the failing tests (RED) first, then the minimal implementation
(GREEN), then verify the full regression + mypy. Each item is tagged with its RTM ID.

## Phase 0 — Tests first (RED)

- [ ] **[R5]** Create `tests/test_import_participants.py` with unit tests that FAIL against
  current code:
  - `derive_candidates(..., grammar="pyramid")` on entities
    `[{name:"Сергей",type:person}, {name:"MasterData",type:company}, {name:"Метамодель",type:concept}, {name:"Айва",type:product}, {name:"ArchiMate",type:external}, {name:"Комитет",type:group}]`
    (each with a body-verbatim quote) ⇒ candidates EXCLUDE the `person`, INCLUDE the rest;
    the person appears in `skipped` with reason `participant-not-concept`.
  - `derive_candidates(..., grammar="article")` on the same input ⇒ the `person` IS a
    candidate (back-compat).
  - `derive_candidates(...)` with NO `grammar` kwarg keeps `person` (default `article`).
- [ ] **[R5]** In the same file, `assemble_note` tests:
  - `grammar="pyramid"`, `note["participants"]=["Сергей — MasterData","Алексей — Айва"]`
    ⇒ output frontmatter CONTAINS a `participants:` block with both entries.
  - `grammar="article"` with the same `note` ⇒ NO `participants:` in frontmatter.
  - `grammar="pyramid"` with no/empty `participants` ⇒ NO `participants:` block
    (byte-identity vs today).
  - H-6: a participant string containing `"\ninjected: evil"` / control chars ⇒ sanitized
    (no injected YAML key, single-line scalar).
- [ ] **[R5]** Integration test (extend the existing wiki-import apply harness /
  `tests/` fixture): a `--kind meeting` `apply` with a `person` entity + a `participants`
  list ⇒ envelope `skipped` has `participant-not-concept`, NO `_concepts/<person>.md`
  written, and the note frontmatter has `participants:`. Confirm a `company`/`product`
  entity IS still filed.

## Phase 1 — Implementation (GREEN)

- [ ] **[R1]** `scripts/wiki_skills/wiki_import_article/_authoring.py` — `derive_candidates`:
  add `grammar: str = "article"` kwarg (keyword-only, after `existing_page_slugs`). Right
  after `name = sanitize_name(...)` + `name_is_filable` guard, insert:
  `if grammar == "pyramid" and str(e.get("type", "")).strip().lower() == "person": skipped.append({"name": name, "reason": "participant-not-concept"}); continue`.
  Update the docstring's skip list.
- [ ] **[R1]** `scripts/wiki_skills/wiki_import_article/__init__.py` — pass `grammar=grammar`
  into the `derive_candidates(...)` call (L701 region). `grammar` is already in scope (L613).
- [ ] **[R2]** `scripts/wiki_skills/wiki_import_article/_authoring.py` — `assemble_note`:
  build a participants block `parts = [ _fm_scalar(p) for p in (note.get("participants") or []) if _fm_scalar(p) ]`; when `grammar == "pyramid" and parts`, insert
  `"participants:\n" + "".join(f'  - "{p.replace(chr(34), chr(39))}"\n' for p in parts)`
  into `fm` immediately after the `lang:` line. No change for article grammar / empty parts.
- [ ] **[R4]** Confirm `participant-not-concept` is NOT added to `_LOSSY_DROP_HINTS` /
  `_LOSSY_SKIP_REASONS` in `__init__.py` (stays a quiet, non-warning skip, observable only in
  `skipped[]`). No DDL, no `import anthropic`.
- [ ] **[R3]** `skills/wiki-import/references/reason-contract.md` — add
  `"participants": ["string", …]` (meeting/lesson attendees) to the note-JSON schema; add a
  Hard rule: attendees → `participants[]`, domain concepts → `entities[]`; state that `apply`
  drops `person` entities for pyramid kinds (so listing an attendee there is silently a no-op).
- [ ] **[R3]** `skills/wiki-import/SKILL.md` — mirror the `participants[]` schema line + the
  participants-vs-entities rule.

## Phase 2 — Verify (GREEN gate)

- [ ] **[R5]** `pytest tests/test_import_participants.py -q` green (RED→GREEN).
- [ ] **[R4][R5]** Full regression `pytest tests/ -q` green (no byte-identity regressions in
  existing wiki-import/article tests — article grammar untouched).
- [ ] **[R4][R5]** `mypy --strict scripts/` green (the new kwarg + participants block typed).
- [ ] **[R3]** Manual doc read-through: schema + rule consistent between `reason-contract.md`
  and `SKILL.md` (single source-of-truth discipline).

## Phase 3 — Adversarial Review (VDD Phase 4)

- [ ] `/vdd-multi` critics (logic / security / performance) + code-reviewer on the diff;
  fix findings; converge (0 CRITICAL, no legitimate logic/security/slop findings).
