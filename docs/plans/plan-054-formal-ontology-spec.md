# PLAN — TASK 054: Formal ontology spec (R-19)

Stub-First, green-throughout. Each bead ends at a verification checkpoint (imports +
`mypy --strict scripts/` + the named tests). RTM IDs (R1–R9) from `docs/TASK.md`.

**Clone map** (from the R-15/TASK-036 machinery recon):
- `_validate_ontology` ← sibling of `layout_config.py:_validate_health_rules` (lazy-import
  `reindex._INVERSE_REF_TYPE` + `repository.validate_filter_field`; `LayoutConfigError` → exit 6).
- `find_ontology_violations` ← `sqlite_repository.py:find_lifecycle_drift` structure + the
  `find_classification_leaks:1092-1095` target-JOIN + COUNT=1 same-slug guard (for the range check).
- `check_ontology_violations` ← `lint.py:check_lifecycle_drift` (severity `error if strict else
  warning`; early-return on no rules; reuse the already-resolved `config`).
- `wiki-health ontology` ← `wiki_health.py` `coverage` subcommand (envelope + exit 0/2/6 + `--class`).
- Models ← `models.py:CoverageRule`/`CoverageGap`; schema ← `layout-config.schema.yaml`
  `CoverageRule` `$def`; reference block ← `cybos.yaml` `coverage_rules`.

---

## Bead 054-00 — Stub skeleton: schema + models + wiring (Red, no logic) · [R1][R2]
**Stub-First structure before any logic.**
1. `models.py` — add frozen dataclasses `OntologyEdge(edge, frm, to)`, `OntologyProperty(page_class, field, enum)`, `OntologyConfig(closed_types=False, edges=(), properties=())`, and the hit `OntologyViolation(vault_id, page_slug, page_project, kind, edge_or_field, offending, target_slug=None)`. (`frm`/`page_class` avoid the `from`/`class` keywords; YAML keys are `from`/`class`.)
2. `layout_config.py` — `LayoutConfig.ontology: OntologyConfig | None = None`; parse the nested `ontology:` mapping in `_build` (edges/properties → tuples; `None` when the key is absent); add `_validate_ontology(cfg)` **STUB** (`return`) called immediately after `_validate_health_rules(cfg)` at ~line 646.
3. `config/layout-config.schema.yaml` — `$defs` `Ontology` (object: `closed_types` bool, `edges` array→`OntologyEdge`, `properties` array→`OntologyProperty`, `additionalProperties: false`), `OntologyEdge` (`required [edge, from, to]`; `from`/`to` arrays `minItems: 1`), `OntologyProperty` (`required [class, field, enum]`; `enum` array `minItems: 1`); top-level optional `ontology: {$ref}` (mandatory because `additionalProperties: false`).
4. `repository.py` — abstract `find_ontology_violations(self, vault_id, ontology)` under the R-15 section header (~line 362).
5. `sqlite_repository.py` — `find_ontology_violations` **STUB** (`return []`).
6. `lint.py` — `check_ontology_violations(...)` **STUB** (`return []`); NOT yet wired into `run_all_checks`.
7. `wiki_health.py` — add the `ontology` subparser + a `main` `args.cmd` branch that emits an empty ontology envelope (**STUB**, exit 0); update the module-docstring exit-code line.
- **✅ Checkpoint:** `python -c import` of each module clean; `mypy --strict scripts/` clean; **full existing suite still green** (nothing reads `ontology` yet → OFF ≡ no-op; cybos ships no `ontology:` block yet).

## Bead 054-01 — Load-gate `_validate_ontology` (logic + tests) · [R3][R8]
1. Implement `_validate_ontology(config)`: early-return if `config.ontology is None`. Lazy-import `_INVERSE_REF_TYPE` + `validate_filter_field`. `valid_edges = set(_INVERSE_REF_TYPE)`, `roster = set(config.type_mapping)`. Per edge: `edge ∈ valid_edges`; `frm`/`to` non-empty and every member ∈ `roster`. Per property: `page_class ∈ roster`; `field` via `validate_filter_field`; `enum` non-empty with non-empty members. Each failure `raise LayoutConfigError(...naming the offending token...)` (→ exit 6). (`closed_types` needs no extra gate — its classes are the roster.)
2. Tests `tests/test_ontology_config.py` (mirror `test_health_rules_config.py`, `.wiki/layout.yaml` override helper): unknown `edge`; unknown `from`/`to` class; unknown property `class`; bad `field`; empty `enum`; empty `from`/`to` → each `pytest.raises(LayoutConfigError, match=...)`. Plus `test_cybos_ships_ontology` (the real block parses with the right counts) after 054-04.
- **✅ Checkpoint:** new load-gate tests green; `mypy --strict` clean; existing suite green.

## Bead 054-02 — DAL `find_ontology_violations` (logic + tests) · [R4][R8]
1. Implement the two read-side families in `sqlite_repository.py`, all values bound `?`:
   - **edge domain/range** — per edge rule, one query: `page_entity_refs r` JOIN `pages src` (`src.slug=r.page_slug AND src.project=r.page_project`) JOIN `pages t` (`t.slug=r.entity_slug`) WHERE `r.vault_id=? AND r.ref_type=?` AND the `COUNT(*)…=1` same-slug guard (verbatim from `find_classification_leaks`). Python: emit `kind=domain` when `src.$.type ∉ frm`, `kind=range` when `t.$.type ∉ to`.
   - **property enum** — per property rule: pages of `$.type==class` with `json_type($.<field>)=='text'` (bound path) AND value `NOT IN (<enum placeholders>)` → `kind=property`.
   - **NO closed-type read-side family** (Red-phase finding): reindex resolves a typed page's class from frontmatter `$.type` and SKIPS an out-of-roster type (reported in `--full`'s `skipped[]`), so such a page never enters the DB → a sweep is a no-op. `closed_types` is enforced at index time + declared/validated at load. Signature `find_ontology_violations(vault_id, ontology)` (no roster param).
2. `repository.py` docstring finalized.
3. Tests `tests/test_ontology_violations.py` (DAL section) via `build_cybos_vault` ontology fixtures (a valid control, a domain violator, a range violator via a resolvable bad-type target, a property violator, two orphan-target edges). Assert exact slug/kind sets; orphan-target NOT flagged; controls disjoint.
- **✅ Checkpoint:** DAL tests green; `mypy --strict` clean; existing suite green.

## Bead 054-03 — Surfacing: lint category + wiki-health subcommand (logic + tests) · [R5][R6][R8]
1. `lint.py` — implement `check_ontology_violations(repo, vault_id, vault_root, *, strict, config=None)`: resolve config if None; early-return if `config.ontology is None`; `sev = "error" if strict else "warning"`; emit one `LintIssue(category="ontology-violation", …)` per hit (details carry kind/edge_or_field/offending/target). Wire into `run_all_checks()` reusing the already-resolved `config` (next to `check_lifecycle_drift`).
2. `wiki_health.py` — implement the `ontology` handler: `layout.ontology` → `find_ontology_violations`; envelope `{action:"ontology", vault, total_violations, by_kind, by_class, violations:[…]}`; **always exit 0**; optional `--class` validated against the ontology's declared classes → `INVALID_CLASS` (exit 2, no echo); `VAULT_NOT_FOUND` exit 6; `note` when `ontology is None`.
3. Tests: extend `test_lifecycle_drift.py`-style → `test_ontology_violations.py` lint section (advisory `rc==0`; `--strict` `rc==1`; `by_category["ontology-violation"]` count); extend `test_wiki_health.py` (ontology exit 0 + envelope; INVALID_CLASS; VAULT_NOT_FOUND).
- **✅ Checkpoint:** surfacing tests green; `mypy --strict` clean; existing suite green.

## Bead 054-04 — cybos.yaml reference block + OFF-equivalence + regression · [R7][R8][AC-5]
1. Add the `ontology:` block to `scripts/wiki_index/layouts/cybos.yaml` — real edges (`implements`/`supersedes`/`causes`/`invalidates`/`uses`/`owns` with domain/range from the typed-class conventions) + property `status` enums lifted from `templates/page-types/*.md`. Every `edge` ∈ the 15 ref_types; every `from`/`to`/`class` ∈ `type_mapping` keys (load-gate proves it).
2. OFF-equivalence test: `karpathy`/`dev-project`/`obsidian-personal` resolve with `ontology is None`; `check_ontology_violations` and `wiki-health ontology` yield zero findings; lint envelope byte-identical to pre-054 (ADR-005-D2 style).
3. **Full regression:** `pytest tests/` green; `mypy --strict scripts/` clean; a `wiki-reindex --full` over a seeded cybos vault still **indexes an ontology-violating page** unchanged (NOT a write gate); `user_version` == 7 (grep the schema — zero DDL); no touched skill imports `anthropic`.
- **✅ Checkpoint:** all AC-1..AC-5 mechanically demonstrated.

## Bead 054-05 — Docs closeout · [R9]
1. `docs/adr/ADR-009-*` — pillar-2 row: mark "no declared edge domain/range or property enums (→ R-19)" gap **closed** (TASK 054); note the read-only/not-a-write-gate posture.
2. `docs/ARCHITECTURE.md` — Lint Layer row mentions `ontology-violation`; add an `[x]` shipped-checklist entry (TASK 054 / R-19).
3. `docs/ROADMAP.md` — R-19 entry → **✅ SHIPPED (TASK 054)** with a one-paragraph ship summary.
4. `docs/architectures/open-questions.md` — new §11l Q-054-* (closed_types-as-runtime-check rationale; the orphan-target-domain boundary; the target-JOIN COUNT=1 reuse; lint-`--strict`-vs-health split per ADR-006 D-036-2).
5. Skills: `skills/wiki-lint/SKILL.md` (+ `commands/wiki-lint.md`) new `ontology-violation` category; `skills/wiki-health/SKILL.md` (+ `commands/wiki-health.md`) new `ontology` subcommand. Regenerate the KNOWN_ISSUES ledger only if a per-issue file changed (none expected).
- **✅ Checkpoint:** docs consistent; `wiki-lint` self-run on this repo clean; final full suite green.

---

## Adversarial pass (Phase 4, after 054-05)
`/vdd-multi` (critic-logic / critic-security / critic-performance) over the net diff; converge to
0 CRITICAL + no legitimate logic/security/perf finding per `vdd-adversarial`. Focus lenses:
SQL injection surface (bound params only; the only string-composed parts are placeholder *counts*
and fixed `$.type` literals — the user field name rides `validate_filter_field` + bound path),
COUNT=1 guard correctness (phantom cross-project range hits), OFF ≡ byte-identical, and the
not-a-write-gate invariant.

## RTM coverage
R1→00 · R2→00 · R3→01 · R4→02 · R5→03 · R6→03 · R7→04 · R8→01/02/03/04 (per-bead) · R9→05.
