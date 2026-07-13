# TASK 063-10 — **G2**: ref-resolution via the layout's **OWN** `ref_extraction` rules

**Phase**: 3 (apply validation) · **RTM**: R-063-2 (G2) · **Type**: code · **Effort**: 3–4h
**Depends on**: 063-08, 063-09 · **Unblocks**: 063-12

## Goal

`apply` runs **the resolved layout's own `ref_extraction` rules** over the **fully-rendered candidate
page** (frontmatter **and** body) and requires **every extracted target** to resolve — to an existing
page, an entity, an **alias**, or a page **in the same (post-drop) batch**. Any unresolved target ⇒
`UNRESOLVED_REF`, **exit 4, zero writes**.

## ⚠️ NOT "wikilinks" — **PROSE CREATES REFS**

`cybos.yaml` ships an `id-ref` rule:

```yaml
- kind: id-ref
  regex: '\b(ADR-\d+|R-\d+(?:\.\d+)*|task-\d+(?:-\d+)*|DEC-\d+|INC-\d+|RISK-\d+|REQ-\d+|HYP-\d+)\b'
```

So **"отменяет DEC-004" in body text is an `orphan-link` surface.** The v2 spec said "wikilinks" —
**the wrong surface**, caught by a grep, not by reasoning. And `find_orphan_links` scans **all** of
`page_entity_refs` with **no `ref_type` filter**, so there is nowhere for such a ref to hide.

> The write side must be validated against the layout's **READ GRAMMAR**, never against an assumption
> about it. *This is the same invariant as G4, wearing the ref-extraction costume.*

## Why G1 cannot do this job

The ontology check **skips unresolved targets by design** (it can only judge a target whose class it
can resolve). So an orphan link is **structurally invisible** to G1. G2 is a different surface and
gets a different bead — which is precisely why the spec split them.

## Steps

1. Render the candidate to its **final page text** (the same renderer 063-12 writes with — call it,
   do not approximate it, or G2 validates a page that is not the page that ships).
2. `extract_refs(page_text, config.ref_extraction, operator_supplied=config.ref_extraction_operator_supplied)`
   — `scripts/wiki_source/parsing.py:90`, the engine's own extractor, under the existing ReDoS
   deadline.
3. Slugify each target with `_apply_slug_strategy(target, config.slug_strategy)` — **exactly as
   `reindex._body_refs` does** (`reindex.py:452`), or a `[[Идеи]]` link "resolves" here and orphans at
   reindex.
4. Resolve against: `existing_page_slugs` ∪ `entity_slugs` ∪ **`entity_aliases`** ∪
   `{post-drop batch slugs}`. Unresolved ⇒ collect.
5. Report `links_checked: N` in the denominators (R-063-1).

## Context — files

- **Edit** `_validation.py` (`validate_refs`), `_pages.py` (share the renderer), `__init__.py`.
- **Read** `scripts/wiki_source/parsing.py::extract_refs`; `scripts/wiki_index/reindex.py::_body_refs`
  (lines 431-465 — the slugify + `_raw/` exclusion semantics); `cybos.yaml` `ref_extraction`.

## Tests (RED first) — `tests/test_extract_decisions_refs.py` (new)

- `test_bare_id_in_prose_is_a_ref_and_must_resolve` — a candidate body containing
  `"Это отменяет DEC-004"` where `dec-004` does **not** exist ⇒ **exit 4, `UNRESOLVED_REF`**, zero
  writes. **MUT:** validate only wikilinks (the v2 assumption) ⇒ RED. *This is the test the whole bead
  exists for; it is also the exact failure the operator would otherwise experience as "the rail is
  flaky".*
- `test_bare_id_that_resolves_is_accepted` — same body, `dec-004` exists ⇒ exit 0.
- `test_in_batch_wikilink_resolves` — D links `[[req-latency]]`, R is in the same batch ⇒ accepted.
- `test_alias_target_resolves` — target matches an `entity_aliases` row ⇒ accepted (the spec says
  page/entity/**alias**; an alias-blind check would reject a legitimate page).
- `test_frontmatter_edges_are_also_scanned` — an unresolvable slug in `edges.supersedes` (frontmatter,
  not body) ⇒ refused. **The rules run over the FULL rendered page.**
- `test_refs_use_the_layout_rules_not_a_hardcoded_regex` — monkeypatch the layout to add a bespoke
  `ref_extraction` rule; assert the new rule **fires**. **MUT:** hardcode the wiki-link regex ⇒ RED.
- `test_slugify_matches_reindex` — a `[[Идеи]]` target validates iff `reindex._body_refs` would
  resolve it. Compare against the engine function, not a literal.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "every extracted target" is a denominator claim.** Prove the rule
      population comes from config:
      ```bash
      grep -rn "ref_extraction" scripts/wiki_skills/wiki_extract_decisions/
      #   → must reference config.ref_extraction; ZERO literal regexes in this package
      grep -rnE "\[\[|\\\\b\(ADR-" scripts/wiki_skills/wiki_extract_decisions/*.py
      #   → no hits (no hand-copied link/id regex)
      ```
      and in the test: `assert env["validation"]["links_checked"] == <count computed by extract_refs>`.
- [ ] **MUT:** point `validate_refs` at a hardcoded wiki-link regex ⇒ two tests RED
      (`…bare_id_in_prose…`, `…layout_rules_not_a_hardcoded_regex`).

## Rollback

`validate_refs` → no-op. The batch then writes pages that can orphan-link ⇒ 063-15's delta test fails.
Correct signal.
