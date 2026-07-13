# TASK 063-08 — **G1**: ontology validation (roster · domain · **RANGE** · status enum)

**Phase**: 3 (apply validation) · **RTM**: R-063-2, R-063-1 · **Type**: code · **Effort**: 4h
**Depends on**: 063-05, 063-06, 063-07 · **Unblocks**: 063-09, 063-13

## Goal

`apply` validates **every** candidate against the declared ontology **BEFORE any write**. Failure ⇒
`ONTOLOGY_VIOLATION`, **exit 4, ZERO files written**.

This is the check the TASK-062 agent hand-wrote in Python before staging the pilot's pages — which is
why `wiki-lint --strict` was clean on the first try. **It must live in the code, not in the agent.**
The ontology is already a machine-readable contract: `OntologyConfig` / `OntologyEdge` /
`OntologyProperty` (`scripts/wiki_index/models.py:461-486`).

## The four checks

| check | rule | data source |
|---|---|---|
| roster | `class ∈ {decision, requirement, risk}` ∩ `type_mapping` | 063-05's roster |
| **domain** | for edge `e`: `candidate.class ∈ ontology.edges[e].frm` | `OntologyEdge.frm` |
| **RANGE** | for edge `e`: `target.class ∈ ontology.edges[e].to` | in-batch target ⇒ its own `class`; **out-of-batch target ⇒ resolved FROM THE DB** |
| status | `status ∈ ontology.properties[(class, "status")].enum` | `OntologyProperty.enum` |

> ⚠️ **The RANGE check is the one that is easy to fake.** A domain-only validator would pass v1's own
> example **vacuously**. Resolving an out-of-batch target's class means a DB read — do it
> (`_db.load_typed_pages` / a `$.type` lookup by slug). A range check that skips out-of-batch targets
> is a range check that does not exist.

**A target that resolves to nothing** is **not** a G1 concern — G1 *skips* unresolved targets by
design (exactly as `find_ontology_violations` does). That surface belongs to **G2** (063-10), and the
split is deliberate: *the ontology check CANNOT catch an orphan link.*

## ★ ALL violations at once

`violations: [{index, class, kind, detail}, …]` — `kind ∈ {roster, domain, range, status}`.
**One repair round, not N.** A validator that stops at the first violation makes the operator (or the
model) iterate blindly; the payload is cheap and the round-trip is not.

## ★ Denominators (R-063-1)

The envelope carries `validation: {roster_size, edges_checked, properties_checked, links_checked}` and
`vacuous_validation: true` when the layout declares **no** `ontology:` block (dev-project). *A
validator that examined nothing must not look green.* — the TASK-061 rule, applied to this rail's own
output.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_extract_decisions/_validation.py` (`validate_ontology`),
  `_db.py` (target-class resolution), `__init__.py` (wire into `apply` **before** the repo write).
- **Read** `scripts/wiki_index/models.py:461-486` (the three ontology dataclasses).
- **Read** `scripts/wiki_index/lint.py::check_ontology_violations_report` (line 342) + the
  `find_ontology_violations_report` DAL — the **read-side** semantics this write-side gate must
  agree with. Any disagreement between them is a page that `apply` accepts and `wiki-lint --strict`
  then rejects: the delta property broken by our own hand.

## Tests (RED first) — `tests/test_extract_decisions_ontology.py` (new)

- `test_bad_domain_refused` — `risk` carrying `implements:` (cybos `implements.frm` =
  `[decision, task, agent, tool]`) ⇒ exit 4, `kind: domain`, zero writes.
- `test_bad_range_refused_via_db_lookup` — `decision implements: [[some-summary-page]]` where that
  page exists in the DB with class `summary` ∉ `implements.to` ⇒ exit 4, `kind: range`.
  **MUT:** skip out-of-batch targets in the range check ⇒ RED. *This is the vacuous-pass trap.*
- `test_bad_status_refused` — `decision.status: "done"` ∉ `[proposed, accepted, superseded, rejected]`
  ⇒ exit 4, `kind: status`.
- `test_all_violations_listed_at_once` — one payload with a domain error, a range error AND a status
  error ⇒ **3** entries in `violations`. **MUT:** fail-fast on the first ⇒ RED.
- `test_zero_writes_on_violation` — assert the typed dirs are **empty** on disk. The envelope saying
  "refused" is not evidence that nothing was written.
- `test_dev_project_is_vacuous_and_marked` — no `ontology:` ⇒ roster check only,
  `vacuous_validation: true`, `edges_checked == 0`. Green **and honest**.
  ⚠️ **Reachable only after 063-02** (plan-review **C-2**): stock `dev-project` maps the typed classes
  but has **no `paths[]` glob** for them ⇒ `prepare` **refuses** the layout ⇒ this test could never
  have passed as v1 wrote it. 063-02 adds the three globs. It is a hard dependency, not a detail.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "validates against the ontology" is a denominator claim, and the check
      populations must be READ FROM CONFIG, never restated.** In the test:
      ```python
      cfg = resolve_layout_config(cybos_vault)
      assert env["validation"]["edges_checked"]      == len(cfg.ontology.edges)
      assert env["validation"]["properties_checked"] == len(cfg.ontology.properties)
      assert set(env["roster"]) <= set(cfg.type_mapping)
      ```
      A literal `7` or `11` in the test is a second source of truth and **will** drift from
      `cybos.yaml`.
- [ ] **MUT (each check, independently):** disable roster / domain / range / status ⇒ its named test
      goes RED. Four mutations, four reds. *A gate that cannot fail is the disease.*

## Rollback

`validate_ontology` reverts to a no-op returning `[]`; `apply` writes unvalidated (⇒ 063-15's property
test would fail, which is the correct signal).
