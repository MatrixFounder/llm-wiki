# Task 061-03 — [LOGIC] `wiki-lint`: denominators for **BOTH** config-driven checks

RTM: **R-061-2** (spec v6). Depends on: `061-00`, `061-01`. 

> **Renamed** from `task-061-03-lint-drift-denominators.md`. The old filename asserted
> "drift only" — which was the **7th recurrence** of this task's fractal (a mechanism claimed to
> cover a surface without enumerating the surfaces it covers). `wiki-lint` runs **two**
> config-driven semantic checks and **both gate `--strict`** (the CI rail):
>
> - `lint.py:185 check_lifecycle_drift` → `find_lifecycle_drift`
> - `lint.py:221 check_ontology_violations` → `find_ontology_violations`
>
> Wiring denominators into only the first would leave `wiki-lint` printing
> `ontology-violation: 0` with **no denominator on the one surface that gates CI** — while
> `061-01` has *already computed* `edges_examined` / `property_pages_examined` and would throw
> them away.

## Goal

Both checks report what they examined, per-check-keyed, in the `wiki-lint` envelope.

**Drift needs `pages_examined` on top of `matched`** because the drift precondition is
`$.type = class` **AND** `EXISTS(ref_type = edge)` (`_health_rules.py:59-65`) — so a bare
`matched: 0` **cannot distinguish**:

- *"no `decision` pages at all"* (today's LIVE state), from
- *"50 `decision` pages, none carrying a `superseded-by` edge"* (the state right after TASK 062).

## Populations (state them; do not leave `matched` undefined — MAJOR-3)

| Number | Population | Source |
|---|---|---|
| drift `pages_examined` | pages whose authored `$.type` ∈ ⋃ `drift_rules[].class` | `_health_rules.py` (`061-01`'s `_count_pages_of_classes`) |
| drift per-rule `matched` | pages where `$.type = rule.page_class` **AND** `EXISTS(ref_type = rule.edge)` — i.e. the rule's **precondition**, exactly as the finder's SQL builds it (`_health_rules.py:59-65`). The `json_type($.status) = 'text'` scalar filter is part of the **drift condition**, NOT the precondition. | `_health_rules.py` |
| ontology `edges_examined` / `property_pages_examined` / per-rule `matched` | as defined in `061-01` (declared edge vocabulary; ⋃ `ontology.properties[].class`) | reuse `find_ontology_violations_report` — **compute nothing new here** |

### The skipped-rule branch (MAJOR-3, second half)

`find_lifecycle_drift` **`continue`s** a rule carrying neither `expect_status` nor
`forbid_status` (`_health_rules.py:86-90` — a hand-built rule bypassing the config load-gate).
**Decision: such a rule still gets a `RuleStat`** — `matched` counted (its precondition is
well-defined), `findings = {"drift": 0}` — and the report notes it was skipped:
`RuleStat.ref` is set, and `061-01`'s `DriftReport` carries it like any other. Rationale: a rule
that examined N pages and produced 0 findings **because the rule itself is degenerate** is
precisely the state this task refuses to render as a silent green. TC-03-4's `∀ rule` quantifier
is therefore over **every declared rule**, with no exceptions — which is what makes it a real
quantifier.

### The `pages_examined` noun appears twice — and that is safe *here only*

Coverage's `pages_examined` = ⋃ `coverage_rules[].class`; drift's = ⋃ `drift_rules[].class`.
Two populations, one noun. It is safe **only** because they never share an envelope
(`wiki-health` vs `wiki-lint`), **and** because lint's payload is **per-check-keyed**
(`lifecycle-drift.pages_examined` vs `ontology-violation.{edges_examined,property_pages_examined}`).
**Any future surface that merges these payloads MUST re-qualify the noun** — collapsing them
reruns C6 (the two-populations-one-denominator bug) on a new surface. Keep this paragraph in the
`LintReport` docstring.

## Context

- `scripts/wiki_index/lint.py:33-133` — `run_all_checks(repo, *, vaults, strict, mtime_skip)
  -> list[LintIssue]`; `:185-218` drift; `:221-249` ontology.
- **Other callers of `run_all_checks`:** `scripts/benchmark.py:217` + the lint test modules —
  grep before changing anything; the CLI is not the only caller.
- `scripts/wiki_skills/wiki_lint.py:34-63` — the envelope.

## Changes

### `scripts/wiki_index/lint.py`

```python
@dataclass(frozen=True)
class LintReport:
    """TASK 061 / R-061-2 — issues PLUS what EACH config-driven check examined.

    `denominators` is keyed {vault_id: {check_category: payload}} — per-CHECK, so the
    `pages_examined` noun (drift's population = U drift_rules[].class) can never collide
    with the ontology check's edge/property populations in one envelope. A future surface
    that flattens these payloads MUST re-qualify the noun."""
    issues: list[LintIssue]
    denominators: dict[str, dict[str, Any]]

def run_all_checks_report(repo, *, vaults=None, strict=False, mtime_skip=False) -> LintReport: ...

def run_all_checks(repo, *, vaults=None, strict=False, mtime_skip=False) -> list[LintIssue]:
    """Back-compat wrapper (benchmark.py + tests). Signature UNCHANGED."""
    return run_all_checks_report(...).issues

def check_lifecycle_drift_report(repo, vault_id, vault_root, *, strict, config=None
                                 ) -> tuple[list[LintIssue], dict[str, Any] | None]:
    """`None` denominators when the layout ships no `drift_rules` — the existing no-op
    (NO DAL call) is preserved verbatim."""

def check_ontology_violations_report(repo, vault_id, vault_root, *, strict, config=None
                                     ) -> tuple[list[LintIssue], dict[str, Any] | None]:
    """`None` denominators when `config.ontology is None` — the existing no-op (NO DAL
    call) is preserved verbatim."""

def check_lifecycle_drift(...) -> list[LintIssue]:      # wrapper, signature UNCHANGED
def check_ontology_violations(...) -> list[LintIssue]:  # wrapper, signature UNCHANGED
```

Both `*_report` functions call the `061-01` DAL report methods (`find_lifecycle_drift_report` /
`find_ontology_violations_report`) — **no new counting code lives in lint.py**.

Per-vault payload:

```json
{
  "lifecycle-drift":    {"pages_examined": 11,
                         "by_rule": [{"class":"decision","kind":"drift","ref":"superseded-by",
                                      "matched":4,"findings":{"drift":2}}]},
  "ontology-violation": {"edges_examined": 6, "property_pages_examined": 17,
                         "by_rule": [{"class":"","kind":"edge","ref":"implements","matched":2,
                                      "findings":{"domain":0,"range":1}},
                                     {"class":"decision","kind":"property","ref":"status",
                                      "matched":8,"findings":{"property":1}}]}
}
```

### `scripts/wiki_skills/wiki_lint.py`

Call `run_all_checks_report`; add the **additive** `"denominators": report.denominators` key.
`--strict` gating, `total_issues`, `by_category` and the exit-code policy are **unchanged**
(denominators never gate, never become issues).

## Test cases — `tests/test_lint_denominators.py` (new) + `tests/test_lifecycle_drift.py`

1. **TC-03-1 (drift: typed + edges ⇒ matched > 0)** — `build_health_vault` (typed pages **AND**
   the derived inverse edges — `dec-old2` gets `superseded-by` from `dec-new`'s `supersedes`;
   RTM constraint 5): `pages_examined == <decisions + workflows in _FILES>`, `matched > 0`,
   `findings.drift ≤ matched`.
2. **TC-03-2 (drift: typed, NO edges — the E2 distinction)** — `build_cybos_vault` with
   `decision` pages carrying **no** lifecycle edges: `pages_examined > 0` **while** every
   `matched == 0` and `drift == 0`. One test, docstring naming the two states it distinguishes.
3. **TC-03-3 (untyped ⇒ 0)** — untyped fixture: drift `pages_examined == 0`; ontology
   `edges_examined == 0` and `property_pages_examined == 0`.
4. **TC-03-4 (invariants, ∀ DECLARED rule — incl. the skipped-rule branch)** —
   `drift_r ≤ matched_r ≤ pages_examined`; and for ontology (P-061-A): `domain_e ≤ matched_e`
   **AND** `range_e ≤ matched_e` **AND** `matched_e ≤ edges_examined`;
   `property_p ≤ matched_p ≤ property_pages_examined`.
5. **TC-03-5 (THE LIVE 8836-REF TRAP, now on the CI rail)** — a vault whose `page_entity_refs`
   holds **only `mentioned`** rows (thousands of them) and zero typed pages: `wiki-lint` reports
   **0** `ontology-violation` issues **and** `edges_examined == 0`. Proves the CI-gating check
   was inert and now says so. (Without this bead, that surface stayed vacuous.)
6. **TC-03-6 (no-ops preserved)** — a **karpathy** vault: no `drift_rules` **and** no
   `ontology:` block ⇒ **no DAL call for either check** (assert with a spy/monkeypatched DAL
   method that raises) and `denominators == {}`.
7. **TC-03-7 (back-compat)** — `run_all_checks(...)` still returns `list[LintIssue]`;
   `check_lifecycle_drift` / `check_ontology_violations` keep their signatures;
   `python3 -c "import scripts.benchmark"` succeeds.

## Verification

```bash
source .venv/bin/activate
pytest tests/test_lint_denominators.py tests/test_lifecycle_drift.py tests/test_ontology_violations.py \
       tests/test_wiki_search_lint_cli.py tests/test_lint_classification.py \
       tests/test_lint_auto_generated.py tests/test_wiki_lint_alias_collision.py -q
mypy --strict scripts/
# the census, re-run: every config-driven check WITH A RULE POPULATION must appear in the payload
grep -n "issues.extend(\|def check_" scripts/wiki_index/lint.py
```

## Acceptance criteria

- [ ] **Both** `lifecycle-drift` **and** `ontology-violation` carry denominators; the grep above
      is pasted into the commit message as the enumeration of config-driven checks.
- [ ] `LintReport`'s docstring says "**each** config-driven check" **and that is true**.
- [ ] Payload is **per-check-keyed**; the two-populations-one-noun hazard is documented in it.
- [ ] Every declared drift rule gets a `RuleStat` — including the degenerate/skipped branch.
- [ ] Both no-ops preserved (no rules / no ontology ⇒ no DAL call); `--strict` gating, exit codes
      and `by_category` byte-identical on every pre-existing fixture.


## Enumerated, deliberate exclusions (state the boundary, don't merely satisfy it)

`lint.py` defines **four** `check_*` functions. Two are wired here; two are **deliberately** not, and
that boundary is stated rather than left merely-true:

| `def check_*` | Wired? | Why |
|---|---|---|
| `check_lifecycle_drift` (`:185`) | ✅ | config-driven, has a rule population, gates `--strict` |
| `check_ontology_violations` (`:221`) | ✅ | config-driven, has a rule population, gates `--strict` |
| `check_auto_generated_unchanged` (`:136`) | ❌ | PW-Q ledger **hash-drift** — compares a render hash; there is **no rule population**, so there is no denominator to state |
| `check_classification_policy` (`:252`) | ❌ | R-16 policy; gated on a `policy:` block that TASK §5 deliberately leaves **declared-but-OFF** |

> A boundary that is **stated** is honest; a boundary that is merely **true** is the disease this task exists to kill.
