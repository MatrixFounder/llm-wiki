# TASK 037 — `wiki-extract-concepts` layout-aware (PARA `_concepts/` support)

## 0. Meta
- **Task ID:** 037 · **Slug:** `task-037-extract-concepts-layout-aware`
- **Mode:** VDD (code-reviewer + critic-security). Code task (`scripts/`, `tests/`,
  `config/layouts`, `docs/`), green-throughout, `mypy --strict`. **Zero DDL**
  (`user_version` stays **7**), **zero new deps**, **no `import anthropic`**.
  Karpathy byte-identity preserved (the `_sources/`-nesting branch is unchanged).
- **Branch:** `task-037-extract-concepts-layout-aware`.

## 1. Problem / motivation

Surfaced by a real article-import pilot (a16z quantum-computing article → the user's
PARA Obsidian vault `05 - Материалы/Квантовые вычисления/`). The pilot ran end-to-end
(download → deterministic HTML→md via the `docx` skill → RU translation → article
note → layout-aware `wiki-index-upsert`) **except** entity extraction:
`wiki-extract-concepts` hard-required the Karpathy `_sources/` layout and refused any
PARA note in its native folder:

- `_sourcing._resolve_source_inside_sources` enforced `source_path.parent.name == "_sources"` (H-1).
- `__init__._apply_write` wrote to `source_path.parent.parent / _concepts`.
- `_all_concepts_dirs` scanned only vault-/course-tier.
- `_db` hard-coded `_concepts/{slug}.md` for `entities.file_path` + manifest.
- ASCII-only `_SLUG_RE` (`^[a-z0-9][a-z0-9-]{0,62}$`) rejected preserve-unicode (Cyrillic) slugs.

Result: a PARA note's `[[Entity]]` wikilinks stay permanent orphan-links; no `_concepts/`
pages, no `entities` rows, no entity graph. The user chose to make the skill layout-aware
(mirroring TASK 024 for `wiki-index-upsert`) rather than bury notes under `_sources/`.

## 2. Requirements (RTM)

| ID | Requirement | Verified by |
|----|-------------|-------------|
| **R-1** | Layout-aware source resolution: a PARA note resolves by vault-relative path; slug derived via the layout slug_strategy (== `pages.slug`). Karpathy `_sources/` slug/path unchanged. | `test_para_source_resolved_by_relpath_with_layout_slug`; real-pilot `prepare` |
| **R-2** | H-1 anti-loop preserved: refuse a source inside a generated dir (`_concepts/_entities/_queries/_verifications/`), case-insensitively. | `test_para_source_in_generated_dir_refused`, `test_anti_loop_case_insensitive` |
| **R-3** | Concepts dir: Karpathy = `parent.parent/_concepts` (byte-identical); PARA = `<source-note-folder>/_concepts/`. | `test_para_round_trip…`, `test_karpathy_concepts_rel_byte_identical` |
| **R-4** | `_all_concepts_dirs` finds nested PARA `_concepts/` (symlink-safe `os.walk`, no loop/out-of-vault). | `test_all_concepts_dirs_finds_nested_para` |
| **R-5** | `entities.file_path` + manifest `path` carry the REAL vault-relative path (not hard-coded `_concepts/<slug>.md`). | `test_para_round_trip…`, `test_karpathy_course_tier_concepts_rel` |
| **R-6** | `obsidian-personal.yaml` `type_mapping` += `concept/external/person/company/product/group` + `path_type_fallback {_concepts,_entities}` so generated concept pages index as db_type concept (no UnmappedTypeError). | `test_para_round_trip…` (reindex → type=concept) |
| **R-7** | Preserve-unicode slug support: `_is_valid_slug` (Unicode kebab, lowercase, `\Z`-anchored, traversal-safe) replaces ASCII `_SLUG_RE.match` at all 3 sites. Length cap (120) bounds concept/candidate slugs only; SOURCE slug opts out (`max_len=None`) so a long-titled PARA note stays extractable. | `test_is_valid_slug_*`, `test_para_long_title_slug_stays_extractable` |
| **NF-1** | Karpathy byte-identity; `mypy --strict` clean; zero-DDL. | full suite 1534 passed; mypy clean |

## 3. Non-goals
- `wiki-graph` CLI wrapper (absent on PATH) — orthogonal; edges verified via DB.
- Other PARA-ish layouts (`dev-project`, `cybos`) getting concept mappings — trivial follow-up.

## 4. Outcome (shipped)
Files: `scripts/wiki_skills/wiki_extract_concepts/{_sourcing,_pages,_validation,_db,__init__}.py`,
`scripts/wiki_index/layouts/obsidian-personal.yaml`, `scripts/wiki_index/layout_config.py`
(`full_match` guard), `tests/test_extract_concepts_layout_aware.py` (NEW, 12 cases),
`tests/test_wiki_extract_concepts.py` (1 message assertion), `skills/wiki-extract-concepts/SKILL.md`.
**Real-vault proof:** 19 `_concepts/` pages created in `05 - Материалы/Квантовые вычисления/_concepts/`,
indexed as db_type concept, `wiki-lint` orphan-links **6561 → 6542 (−19)**, bidirectional graph,
`wiki-search` surfaces the concept pages.
**Reviews:** code-reviewer + critic-security (round 1 → MED-1 `\Z`-anchor, MAJOR-1 length-cap
decoupling, LOW-1 case-insensitive anti-loop, LOW-2 symlink-safe walk) then `/vdd-multi` 3-critic
(round 2 → MED root-level concept glob, SEV-2/R-26 walk prune, LOW `full_match` guard; verdict
PASS, Logic/Security/Perf all converged). All resolved with regression tests; residuals in Q-037.
**Gates:** 1536 pytest, mypy --strict clean, zero-DDL. See `docs/architectures/open-questions.md` Q-037-1..4.
