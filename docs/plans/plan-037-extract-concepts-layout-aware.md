# PLAN 037 — `wiki-extract-concepts` layout-aware (PARA `_concepts/` support)

Stub-light modification of an existing, well-tested skill (TASK 024 pattern). Green
throughout; `mypy --strict`; zero-DDL; Karpathy byte-identity. All steps SHIPPED.

## Atomic checklist

- [x] **P-1 (R-7) Unicode slug gate** — `_validation.py`: `_SLUG_RE` → charset-only
  `^[^\W_][\w-]*\Z` (Unicode, `\Z`-anchored, no length); add `_SLUG_MAX_LEN=120` +
  `_is_valid_slug(slug, max_len=120)` (charset ∧ lowercase ∧ optional length). Switch
  the candidate-schema check to `_is_valid_slug`.
- [x] **P-2 (R-7) rollout** — `_pages.py write_concept_page` + `_sourcing.py` use
  `_is_valid_slug`; facade re-export in `__init__.py`. (Karpathy ASCII slugs are a subset.)
- [x] **P-3 (R-1/R-2) source resolution** — `_sourcing._resolve_source_inside_sources`:
  keep the `_sources/` branch (slug = stem, `max_len=None`); add a PARA branch that
  (a) refuses generated dirs via a case-folded `parts` membership check, (b) derives the
  slug from `derive_discovered_page(...).slug` (lazy import), `max_len=None`.
- [x] **P-4 (R-4) drift sweep** — `_all_concepts_dirs` → `os.walk(followlinks=False)`
  collecting non-symlink `_concepts` dirs (symlink-loop / out-of-vault safe).
- [x] **P-5 (R-3/R-5) concepts dir + paths** — `__init__._apply_write`: branch
  `parent.name == _sources ? parent.parent/_concepts : parent/_concepts`; compute
  `concepts_rel = rel(vault_root).as_posix()`; thread into `upsert_extracted_entity`
  (`file_path`) + `build_manifest` (`written[].path`) — both keyword-default `"_concepts"`
  (back-compat; vault-tier byte-identical).
- [x] **P-6 (R-6) layout** — `obsidian-personal.yaml`: `type_mapping` += concept/entity
  classes (mirror karpathy) + `path_type_fallback {_concepts: concept, _entities: external}`.
- [x] **P-7 tests** — `tests/test_extract_concepts_layout_aware.py` (10 cases: R-1..R-7,
  Karpathy anchor, course-tier, long-slug, anti-loop case-fold, trailing-newline);
  update 1 message assertion in `tests/test_wiki_extract_concepts.py`.
- [x] **P-8 review** — code-reviewer + critic-security; resolve MED-1/MAJOR-1/LOW-1/LOW-2.
- [x] **P-9 docs** — SKILL.md layout-aware note; Q-037; this PLAN + TASK; archive 036.

## Verification (all green)
`pytest tests/` → 1534 passed, 5 skipped · `mypy --strict scripts/` → clean (77 files) ·
real-vault end-to-end: 19 `_concepts/` pages, reindex→concept, lint orphan −19, search/graph.
