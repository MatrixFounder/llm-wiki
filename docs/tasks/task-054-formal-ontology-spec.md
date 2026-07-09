# TASK 054 — Formal ontology spec: a declared, validated type/edge/property contract (R-19)

## 0. Meta Information
- **Task ID**: 054
- **Slug**: formal-ontology-spec
- **Roadmap**: R-19 (P2, Enterprise-readiness / ontology-layer hardening; ADR-009 pillar-2
  "ontology is tribal convention" gap). Recommended order R-16→R-17→R-18→R-19; R-16/17/18
  shipped (TASK 049/050/051) — R-19 is the last, independent slice.
- **Type**: Feature (config contract + load-gate validation + read-only DAL analysis + lint/health surfacing)
- **Effort**: M (schema + dataclasses + one load-gate validator + one DAL method + one lint
  category + one `wiki-health` subcommand + a cybos reference block + tests + docs)
- **Context**: The typed-knowledge ontology (allowed classes, edge domain/range, status
  vocabularies) lives today only as **tribal convention** — `type_mapping` keys,
  `templates/page-types/*.md` prose comments, and the `reindex._INVERSE_REF_TYPE` table.
  Nothing declares that `implements` goes `decision→requirement`, and nothing catches a
  `decision` with `status: frobnicate`. R-19 promotes the ontology from convention to a
  **declared, per-vault, machine-checked YAML contract** an orchestrator can also be fed as
  context — Palantir's ontology-*schema* without its ontology-*enforcement* (the right trade
  for a markdown-canonical system).
- **Architecture**: no structural change. Rides the exact R-15/TASK-036 "derived knowledge
  health" machinery (config-driven rules → load-gate validator → `NOT EXISTS`/COUNT=1 DAL
  walk → `wiki-lint` advisory category + read-only `wiki-health` subcommand). **Zero-DDL,
  `user_version` stays 7**; the karpathy byte-identity anchor and Decision-17 (no
  `import anthropic`) are preserved. `docs/ARCHITECTURE.md` gets one section under R-15's
  neighbourhood; ADR-009 R-19 status flips Proposed→shipped.

## Problem / Motivation (verified against source)

Three facts about a typed vault are asserted nowhere machine-checkable:

1. **The type roster is open.** A page can carry any `type:` frontmatter; the only guard is
   reindex's `UnmappedTypeError` for a path-routed type absent from `type_mapping`. There is
   no declaration that "these classes and only these are the vault's ontology".
2. **Edge domain/range is undeclared.** `reindex._INVERSE_REF_TYPE` knows `implements ↔
   implemented-by` exists, but nothing says `implements` is authored **on a decision/task and
   points at a requirement**. A `risk` page that authors `implements: [[some-incident]]` is
   silently indexed as a valid edge.
3. **Status vocabularies live in comments.** The legal `status` values per class sit in
   `templates/page-types/*.md` prose (and the `drift_rules` encode a couple implicitly). A
   `decision` with `status: done` (should be `accepted`) is invisible.

R-19 lifts all three into an **optional** `ontology:` block in the layout YAML (per-vault
override via `.wiki/layout.yaml`, STRICT schema), validated at load and surfaced as a
`wiki-lint` contradiction + an always-exit-0 `wiki-health ontology` report. **A missing
`ontology:` block ⇒ byte-identical behaviour** (only `cybos.yaml` ships a reference block).

**Deliberately NOT a write gate**: reindex keeps indexing violating pages — markdown is
canonical, Class B must never be lossy vs Class A (ADR-002 §D8). A violation is a
*contradiction between the page and the declared contract*, reported, never enforced.

## Requirements Traceability Matrix

| ID | Requirement | Location |
|----|-------------|----------|
| R1 | **Schema.** Add an OPTIONAL `ontology` object to `config/layout-config.schema.yaml` (STRICT, `additionalProperties: false`, sibling of `drift_rules`/`coverage_rules`): `closed_types` (bool, default false), `edges` (array of `{edge: str, from: [str], to: [str]}`), `properties` (array of `{class: str, field: str, enum: [str]}`). New `$defs` `OntologyConfig`/`OntologyEdge`/`OntologyProperty`. | `config/layout-config.schema.yaml` |
| R2 | **Models.** `OntologyConfig` + `OntologyEdge` + `OntologyProperty` dataclasses (mirror `DriftRule`/`CoverageRule`), parsed into a new `LayoutConfig.ontology: Optional[OntologyConfig]` field (default `None`); OFF layouts keep `None`. | `scripts/wiki_index/models.py`, `scripts/wiki_index/layout_config.py` (parse) |
| R3 | **Load-gate `_validate_ontology`** (sibling of `_validate_health_rules`, called from the same config-load path, same exit-6 exception on failure): each `edge` ∈ the **forward** ref_types of `reindex._INVERSE_REF_TYPE`; every `from`/`to`/`class` ∈ `type_mapping` keys (roster derived from `type_mapping`, no second roster — enforced whenever the ontology block is present, which is what `closed_types` asserts); each property `field` validated through `validate_filter_field`; a non-empty `enum`. A typo is **exit 6**, never a silent never-fires rule. | `scripts/wiki_index/layout_config.py` |
| R4 | **DAL `find_ontology_violations`** (clone of `find_lifecycle_drift` structure + the `find_classification_leaks` target-join/COUNT=1 guard). Two read-side violation families, all params bound: **(a) edge domain/range** — for each `edges` rule, walk `page_entity_refs` of the declared (forward) ref_type via a **LEFT JOIN** to the source page + resolved target page; emit `kind=domain` if the *source* page's `$.type` ∉ `from` (**fires independent of whether the target resolves** — a dangling edge is still a domain error; critic-logic fix), `kind=range` if the *resolved target* page's `$.type` ∉ `to`. The **COUNT=1 same-slug guard** (in the LEFT-JOIN ON-clause, verbatim from `find_classification_leaks`) collapses the target to one row or all-NULL, so `range` never phantom-hits an orphan/entity/ambiguous target. **(b) property enum** — for each `properties` rule, pages of `class` whose `$.<field>` is a non-null *scalar* (`json_type=='text'`) ∉ `enum`; absent/null/list/object is NOT a violation (coverage concern, not contradiction). **`closed_types` yields NO read-side family** — reindex resolves a typed page's class *from* its frontmatter `$.type` and SKIPS any page whose `$.type` ∉ `type_mapping` (verified: reported in `--full`'s `skipped[]`), so an out-of-roster type can never be indexed → a read-side sweep is a guaranteed no-op. The closed-world stance is enforced at **INDEX time** (a hard classification failure); `closed_types` is a declared flag the load-gate validates edge/property classes against (Q-054). Returns typed `OntologyViolation` rows (slug, project, kind, edge/field, offending value, target_slug?). | `scripts/wiki_index/repository.py` (abstract), `scripts/wiki_index/sqlite_repository.py` (concrete) |
| R5 | **`wiki-lint` category `ontology-violation`** — a new `LintIssue` category + a check loop in `run_all_checks()` that reads `layout.ontology` and calls `find_ontology_violations`; **advisory by default, gates `--strict`** (a violation is a contradiction — ADR-006 D-036-2, same posture as `lifecycle-drift`). No `ontology` block ⇒ the check is a no-op (zero rows). | `scripts/wiki_index/lint.py` |
| R6 | **`wiki-health ontology` subcommand** (clone the `coverage` subcommand): single JSON envelope, allow-listed args, **always exit 0** (a report, never a gate — mirrors `coverage`). Reuses `find_ontology_violations`. `bin/wiki-health` unchanged (dispatch is inside). | `scripts/wiki_skills/wiki_health.py` |
| R7 | **Reference `ontology:` block in `cybos.yaml` ONLY** (declaring the real cybos edges e.g. `implements: decision/task→requirement`, `causes: incident→…`, and the decision/incident/task `status` enums lifted from `templates/page-types/*`). Every other built-in layout (`karpathy`/`dev-project`/`obsidian-personal`/`flat`/`per-project`) ships **no** `ontology:` block ⇒ zero behaviour change. | `scripts/wiki_index/layouts/cybos.yaml` |
| R8 | **Tests.** (a) load-gate: unknown `edge`, unknown `from`/`to`/`class`, bad `field`, empty `enum` each → exit 6 (`SystemExit`/`LayoutConfigError` per the `_validate_health_rules` convention); (b) `find_ontology_violations`: seeded domain violation, range violation, property-enum violation each surfaced; orphan/entity target NOT flagged (COUNT=1 guard); absent field / valid value NOT flagged; (c) `wiki-lint`: `ontology-violation` advisory (exit 0) + `--strict` non-zero; (d) `wiki-health ontology`: exits 0 with the violations envelope; (e) **OFF ≡ no-op**: a layout with no `ontology:` block produces zero ontology findings and byte-identical lint/health output (ADR-005-D2-style equivalence). | `tests/` |
| R9 | **Docs.** ADR-009 R-19 Proposed→shipped; `docs/ARCHITECTURE.md` ontology-contract section (near R-15); ROADMAP R-19 entry marked SHIPPED (TASK 054); `skills/wiki-lint/SKILL.md` (new category) + `skills/wiki-health/SKILL.md` (new subcommand) + their `commands/*.md`; `docs/architectures/open-questions.md` Q-054-* for the settled design calls. Regenerate the KNOWN_ISSUES ledger only if a per-issue file changes. | `docs/adr/ADR-009-*`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `skills/wiki-{lint,health}/SKILL.md`, `docs/architectures/open-questions.md` |

## Acceptance Criteria
- **AC-1 (OFF ≡ byte-identical, R2/R5/R7):** a layout **without** an `ontology:` block resolves
  with `LayoutConfig.ontology is None`; `wiki-lint` emits zero `ontology-violation` findings
  and its envelope is unchanged; `wiki-health` has no `ontology` output unless the subcommand
  is invoked (and then it reports zero). Non-cybos built-in layouts are unaffected.
- **AC-2 (load-gate, R3):** a cybos-shaped ontology with an unknown `edge`, an unknown
  `from`/`to`/`class` (∉ `type_mapping`), a bad property `field`, or an empty `enum` each
  fails config load with **exit 6** and a message naming the offending token — never a
  silently-inert rule.
- **AC-3 (DAL, R4):** with a seeded cybos vault: a page whose class ∉ an edge's `from` (domain
  violation), a page whose edge target class ∉ `to` (range violation), and a page of `class`
  whose `status` ∉ `enum` (property violation) are each returned by `find_ontology_violations`;
  an edge whose target is an orphan/entity (unresolved slug) is **not** a range violation
  (COUNT=1 guard); a page with the field absent or a valid value is **not** returned. A page
  authored with an out-of-roster `$.type` is not a *read-side* violation because reindex
  **skips** it at index time (reported in `wiki-reindex --full`'s `skipped[]`) — the closed-type
  contract is enforced at the write boundary, not re-swept.
- **AC-4 (surfacing, R5/R6):** `wiki-lint <cybos-vault>` lists the `ontology-violation`
  findings and **exits 0**; `wiki-lint --strict` **exits non-zero** when any are present;
  `wiki-health ontology <cybos-vault>` emits the JSON envelope and **exits 0** regardless.
- **AC-5 (invariants):** `pytest tests/` green; `mypy --strict scripts/` clean; `wiki-reindex
  --full` still indexes ontology-violating pages unchanged (**NOT a write gate**);
  `user_version` == 7 (**zero DDL**); no touched skill gains `import anthropic`.

## Out of scope (deferred residuals — recorded, not shipped here)
- **OWL/RDF/SHACL/reasoner**, and any cross-vault ontology unification (R-X5's territory).
- **Cardinality constraints** ("exactly one implementer") — `coverage_rules` already cover
  "at least one"; cardinality is YAGNI here.
- **Edge-property schemas** (typed attributes *on* an edge) — the rejected authored-state
  anti-pattern (Q-036 precedent).
- **Untyped quick-captures escape the checks (Q-054-4, known limitation).** The checks key on
  frontmatter `$.type` (the R-15 precedent); a note filed under a typed folder with no authored
  `type:` indexes with its db-class from the path glob but a NULL `$.type`, so it is not checked.
  Templates author `type:` (primary path covered); the robust fix (derived-class-tag keying or
  reindex `$.type` injection) is a machinery-wide R-15+R-19 change, deferred. Codified by
  `test_typeless_note_escapes_checks`. *(Domain-on-orphan-target was originally deferred here but
  is now IMPLEMENTED — domain fires independent of target resolution via the LEFT JOIN, R4.)*
- **`closed_types` as a read-side page-type sweep.** Rejected after the Red-phase finding that
  reindex resolves a typed page's class from frontmatter `$.type` and **skips** any page whose
  `$.type` ∉ `type_mapping` (a hard classification failure, reported in `--full`'s `skipped[]`).
  Such a page never enters the DB, so a read-side sweep is a guaranteed no-op. The closed-world
  stance is therefore enforced at **index time**; `closed_types` remains a declared flag (fed to
  an orchestrator as context; validated by the load-gate) — Q-054.
- **Any auto-fix / write path** that mutates a Class-A page toward the ontology — would need a
  `prepare`/`apply` write contract, outside this read-only slice.

## Risks / invariants to preserve
- **Zero-DDL / `user_version` 7:** ontology data is layout-config only; the DAL walk reuses the
  existing `page_entity_refs` + `frontmatter_json` columns. No `ALTER`, no new table.
- **Not a write gate:** reindex must remain lossless — an ontology-violating page still indexes
  identically. Only lint/health *report*.
- **Derive-don't-author roster:** the class roster is the `type_mapping` keys — never a second
  authored list (the TASK-034 `valid_to` precedent).
- **Load-gate strictness:** a typo must be exit 6 at load, not a rule that silently never
  fires (the stated R-19 failure to avoid — mirror `_validate_health_rules`).
- **Forward ref_types only:** ontology edges declare the **forward** authored edge (e.g.
  `implements`), matching the domain/range direction; the DAL walks forward refs and applies
  the COUNT=1 orphan/entity guard so unresolved targets never masquerade as range violations.
- **OFF ≡ byte-identical:** the equivalence test is the headline gate (ADR-005-D2 style).
- **Decision-17:** all touched skills stay `import anthropic`-free (pure config/SQL/filing).
