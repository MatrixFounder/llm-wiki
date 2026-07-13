# TASK 063-05 — **[LOGIC]** `prepare`: the ontology contract, the G4 preflight, the handshake

**Phase**: 2 (the rail) · **RTM**: R-063-1, R-063-3, R-063-5 · **Type**: code · **Effort**: 4h
**Depends on**: 063-01, **063-02 (hard — it is what makes `dev-project` supported at all)**, 063-04
· **Unblocks**: 063-06 … 063-14
**Revision**: v2 — plan-review **C-2** (the supported-set gate measured one conjunct), **C-2b**, **m-10**
applied. PLAN §8.

> ⚠️ **Fixtures come from the PLAN §1 ROSTER.** `dev-project` is the `vacuous_validation` fixture — and
> it is **only supported after 063-02 adds its three `paths[]` globs**. Before that, `prepare` refuses
> it via its own preflight and every `vacuous_validation` test below is **unreachable**.

## Goal

Replace the `prepare` stub with the real deterministic recon. **No LLM call** (Decision-17).

The envelope the orchestrator consumes:

```jsonc
{
  "vault_id": "...", "source_slug": "...", "source_path": "...",   // vault-RELATIVE (CWE-209)
  "source_hash": "<sha256>",          // the apply handshake
  "is_unchanged": false,              // R-063-5 idempotency (source_state, kind "extract-decisions")
  "layout": "cybos",
  "roster": ["decision", "requirement", "risk"],                   // the v1 roster ∩ the layout's type_mapping
  "ontology": {                                                    // ★ THE CONTRACT — R-063-1
    "edges":      [{"edge": "supersedes", "from": [...], "to": [...]}, ...],
    "properties": [{"class": "decision", "field": "status", "enum": [...]}, ...],
    "closed_types": true
  },
  "drift_rules": [{"class": "decision", "edge": "superseded-by", "expect_status": "superseded"}],
  "typed_dirs":  {"decision": "decisions", "requirement": "requirements", "risk": "risks"},
  "known_typed_pages":   [{"slug": "...", "class": "decision", "status": "accepted"}, ...],
  "existing_page_slugs": ["...", ...],     // the collision-guard SNAPSHOT (apply RE-CHECKS it)
  "validation": {"roster_size": 3, "edges_checked": 0, "properties_checked": 0, "links_checked": 0},
  "vacuous_validation": false,             // ★ true on dev-project (no `ontology:` block)
  "open_commitments": 4                    // R-063-7 / Q-063-4: a GAP is DATA, not a defect
}
```

## ★ `vacuous_validation` — the TASK-061 lesson, applied to ourselves

`dev-project` **maps the typed classes but ships NO `ontology:` block and NO `drift_rules`.** There,
G1 degrades to a roster-only check and G3 is moot. The delta property still HOLDS (both sides
vacuous) — so this is **not a lie**. But a green `apply` there means **"validated almost nothing"**,
and per TASK 061 that must be **ANNOUNCED, not inferred**. Hence the house-standard denominators plus
an explicit `vacuous_validation: true`.

> *A validator that examined nothing must not look green.*

**Read `lint.py:40-70`** for the house form of this: `None` (not `{}`) means *"this check does not
apply to this layout"*, which is a different statement from *"examined 0 pages"*. Mirror that
distinction here.

## The G4 PREFLIGHT — refuse early, refuse loudly

Two independent refusals, both **exit 2**, both before any candidate exists:

1. **`LAYOUT_CANNOT_INDEX_CLASSES`** — the resolved layout's `type_mapping` maps **none** of
   `{decision, requirement, risk}`. **karpathy and obsidian-personal map ZERO typed classes** (verified
   by grep, not by reasoning — the v1 spec claimed all three layouts "file correctly" and was wrong).
   Message names the layout and the missing classes, and points at `.wiki/layout.yaml`.
   *(This mirrors the existing `concepts_indexable` precedent.)*
2. **`TYPED_DIR_NOT_COVERED_BY_LAYOUT`** — `resolve_typed_write_dir` (063-02) returns `None` for any
   class in the roster. **Same helper `wiki-config validate` calls (063-03).** Same actionable message.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_extract_decisions/__init__.py` (`prepare`), `_db.py`.
- **Read** `wiki_extract_concepts/__init__.py::_recon_single` (the resolve → bounded-read →
  sha256 → `check_idempotency` shape, incl. `O_NOFOLLOW`, `SOURCE_TOO_LARGE`, the **relative**
  `source_path` for CWE-209) and `_db.py::check_idempotency` (`source_state`; our
  `_SOURCE_KIND = "extract-decisions"` — a **distinct partition key**, so this rail's idempotency can
  never collide with the concepts rail's).
- **Read** `layout_config.LayoutConfig` — `.ontology` (`OntologyConfig | None`), `.drift_rules`,
  `.type_mapping`, `.slug_strategy`, `.ref_extraction`.
- **Read** `_resummarize.resolve_extract_decisions` (063-01) for the `dirs`.

`_db.py` reads (raw SQL via `repo._connect()` — the established zero-DAL-extension pattern, see
`wiki_extract_concepts/_db.py:38-41`):
- `load_typed_pages(repo, vault_id, roster)` → `slug, project, $.type, $.status` for pages whose
  `$.type` ∈ roster.
- `load_existing_page_slugs(repo, vault_id)` → every `pages.slug` (the collision snapshot).
- `load_resolvable_targets(repo, vault_id)` → page slugs ∪ entity slugs ∪ **entity aliases**
  (G2 needs all three — R-063-2's *"an existing page/entity/**alias**"*).

## Tests (RED first) — `tests/test_extract_decisions_prepare.py` (new)

- `test_prepare_emits_the_ontology_contract` — cybos: `ontology.edges` contains the `supersedes` row
  with its real `from`/`to`; `properties` contains `decision.status` with the real 4-value enum.
  **Assert against the layout YAML, not against a literal copy** (read `resolve_layout_config` in the
  test) — a literal copy is a second source of truth and will drift.
- `test_dev_project_is_vacuous_and_says_so` — dev-project: `vacuous_validation is True`,
  `validation.edges_checked == 0`, `validation.properties_checked == 0`, `roster_size == 3`.
  **MUT:** drop the marker ⇒ RED. *This is the bead's most important test: it is the one that stops
  "validated nothing" from reading as "validated fine".*
- `test_karpathy_prepare_refuses` / `test_obsidian_personal_prepare_refuses` — exit 2,
  `LAYOUT_CANNOT_INDEX_CLASSES`, message names the layout.
- `test_uncovered_dir_refuses_in_prepare_too` — cybos + `dirs.decision: решения` ⇒ exit 2,
  **same code** as `wiki-config validate` emits. *One gate, two callers.*
- `test_is_unchanged_second_run` — R-063-5: same source ⇒ `is_unchanged: true`.
- `test_source_path_is_relative` — CWE-209: no absolute path in the envelope.
- `test_open_commitments_is_reported` — a `requirement` with no `implemented-by` counts. It is
  **DATA, exit 0** — never a defect to close. (Q-063-4: otherwise the model "helpfully" invents a
  closing decision so nothing looks unfinished.)

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] ★ **GREP-THE-SURFACES — "which layouts are supported" is a denominator claim. The spec got it
      wrong in v1. PLAN v1 then got it wrong AGAIN, in the very gate written to stop it** (plan-review
      **C-2**): it measured `type_mapping` **alone**, which is **1 of G4's 2 conjuncts**, and would
      have stayed **green while the rail refused `dev-project`**.
      **G4 support is a CONJUNCTION** — the layout must *map* the classes **AND** its walker must *see*
      the write path:
      ```python
      SUPPORTED = {"cybos", "dev-project"}          # PLAN §1 roster; dev-project only AFTER 063-02
      for name in layout_choices():                 # the population, from the registry
          cfg  = _config_for(name)                  # real API (m-10): resolve_layout_config /
                                                    # load_layout_config / _builtin_registry
          maps = bool({"decision","requirement","risk"} & set(cfg.type_mapping))
          sees = all(resolve_typed_write_dir(cfg, dir_name=d, source_rel=PROBE_SRC) is not None
                     for d in ("decisions","requirements","risks"))
          assert (maps and sees) == (name in SUPPORTED)      # ★ the CONJUNCTION, not either half
      ```
      **MUT:** assert on `maps` alone ⇒ the test passes **in the broken state**. Run that mutation
      once, see the false green, then restore the conjunction. *A gate that passes in the broken state
      is not a gate.*
      A new built-in layout that maps typed classes **and** can see them then fails this test until
      someone updates `SUPPORTED` **deliberately** — which is the entire point.
- [ ] ⚠️ `resolve_layout_config_by_name` **does not exist** (plan-review m-10). The real APIs are
      `resolve_layout_config(vault_root)`, `load_layout_config(vault_root, root_config)`,
      `_builtin_registry()`, `layout_choices()`. Build `_config_for(name)` in conftest from those.
- [ ] The 063-04 stub E2E test is **rewritten** to assert real values (TDD stub-first step 4), not
      deleted.
- [ ] **MUT:** delete the preflight ⇒ `test_karpathy_prepare_refuses` RED.

## Rollback

`prepare` reverts to the stub; `apply` is still a stub. Tree green.
