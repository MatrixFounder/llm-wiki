# Task 061-00 — [STUB CREATION] Health-report models + DAL `find_*_report` stubs

RTM: **R-061-1** (structure half). Depends on: nothing. Blocks: `061-01`, `061-02`, `061-03`.

## Goal

Introduce the report-shaped return types and the three new DAL methods **as stubs**
(denominators hardcoded `0`, `rule_stats` empty), with a contract test that passes on the
stubs. No counting logic yet — that is `061-01`. Zero behavior change to any existing caller.

## Context (read first)

- `scripts/wiki_index/models.py:383-483` — `DriftRule` / `CoverageRule` / `DriftHit` /
  `CoverageGap` / `OntologyEdge` / `OntologyProperty` / `OntologyViolation` / `OntologyConfig`.
- `scripts/wiki_index/repository.py:369-410` — the three abstract finders (the ABC has exactly
  ONE implementation: `SQLiteRepositoryBase` → `scripts/wiki_index/sqlite_repository/`).
- `scripts/wiki_index/sqlite_repository/_health_rules.py` — the three finders' SQL.
- `tests/_health_fixtures.py` — `build_health_vault` (typed cybos vault, **with** inverse
  edges) and `build_cybos_vault(tmp_path, files, vault_id=…)` (arbitrary fixture).

## Changes

### `scripts/wiki_index/models.py` — new frozen dataclasses (zero DDL; pure read-side)

```python
@dataclass(frozen=True)
class RuleStat:
    """TASK 061 / R-061-1: one rule's DENOMINATOR row — how many rows met that
    rule's precondition (`matched`), and what it found (`findings`, keyed by
    finding kind). `findings` is a DICT, not an int: one examined edge row can be
    BOTH a `domain` and a `range` violation, so the invariant is asserted per
    (rule x kind) — see PLAN 061 P-061-A."""
    page_class: str            # "" for an ontology EDGE rule (it declares from/to sets, not one class)
    kind: str                  # coverage: "edge"|"field" · drift: "drift" · ontology: "edge"|"property"
    ref: str                   # the edge name / field name the rule keys on
    matched: int
    findings: dict[str, int]   # coverage {"gaps": n} · drift {"drift": n} · ontology edge {"domain": n, "range": n} · property {"property": n}

    def to_json(self) -> dict[str, Any]: ...   # {"class","kind","ref","matched","findings"}


@dataclass(frozen=True)
class CoverageReport:
    gaps: list[CoverageGap]
    pages_examined: int          # pages whose AUTHORED $.type in U coverage_rules[].class
    rule_stats: list[RuleStat]


@dataclass(frozen=True)
class DriftReport:
    hits: list[DriftHit]
    pages_examined: int          # pages whose AUTHORED $.type in U drift_rules[].class
    rule_stats: list[RuleStat]


@dataclass(frozen=True)
class OntologyReport:
    violations: list[OntologyViolation]
    edges_examined: int              # refs whose ref_type in the DECLARED edge vocabulary
    property_pages_examined: int     # pages whose $.type in U ontology.properties[].class
    rule_stats: list[RuleStat]
```

Docstrings MUST state the population each denominator counts (positive definition) and that
`property_pages_examined` is deliberately NOT named `pages_examined` (coverage owns that noun
for a different population — RTM constraint 4).

### `scripts/wiki_index/repository.py` — three new abstract methods

```python
@abc.abstractmethod
def find_coverage_gaps_report(self, vault_id: str, rules: list[CoverageRule]) -> CoverageReport: ...
@abc.abstractmethod
def find_lifecycle_drift_report(self, vault_id: str, rules: list[DriftRule]) -> DriftReport: ...
@abc.abstractmethod
def find_ontology_violations_report(self, vault_id: str, ontology: OntologyConfig) -> OntologyReport: ...
```

The three existing list-returning methods stay **exactly as they are** (public API, called by
`lint.py`, `wiki_health.py` and 4 test modules).

### `scripts/wiki_index/sqlite_repository/_health_rules.py` — STUB the three report methods

Each stub calls the existing finder and wraps its result:

```python
def find_coverage_gaps_report(self, vault_id, rules) -> CoverageReport:
    # STUB (061-00): findings are REAL, denominators are not yet computed — 061-01
    # replaces the zeros with the three population counts and per-rule `matched`.
    return CoverageReport(gaps=self.find_coverage_gaps(vault_id, rules),
                          pages_examined=0, rule_stats=[])
```

## Test cases — `tests/test_health_denominators.py` (new)

1. **TC-00-1 (shape)** — on `build_health_vault`: each report has the declared attributes with
   the declared types (`int` denominators, `list[RuleStat]`).
2. **TC-00-2 (findings parity)** — `repo.find_coverage_gaps_report(v, rules).gaps ==
   repo.find_coverage_gaps(v, rules)` (same for drift hits and ontology violations). This is
   the contract that lets `061-01` collapse the legacy methods into wrappers **without** a
   behavior change.
3. **TC-00-3 (stub values)** — denominators are `0` and `rule_stats == []` **at this commit**
   (deleted/flipped by `061-01`; the test file's docstring says so explicitly).

## Verification

```bash
source .venv/bin/activate
pytest tests/test_health_denominators.py tests/test_wiki_health.py tests/test_lifecycle_drift.py \
       tests/test_ontology_violations.py tests/test_health_rules_config.py -q
mypy --strict scripts/
```

## Acceptance criteria

- [ ] Four new dataclasses; three new abstract methods; three stub implementations.
- [ ] `pytest tests/` green; `mypy --strict scripts/` green.
- [ ] **No existing method signature changed**, no envelope changed, no SQL changed.
- [ ] `sql/wiki-index-v2.sql` untouched (`user_version` still 7).
