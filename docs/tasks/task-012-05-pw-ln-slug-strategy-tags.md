# Task 012-05: PW-L/N — slug strategy + default/extra tags (+ C1 converge `_derive_source_project`)

> **`skill-tdd-strict`** (the slug-derivation convergence is a PK-drift surface — C-4/C1).

## Use Case Connection
- UC-29: Karpathy slugs unchanged (`identity` = verbatim `path.stem`).
- UC-30: Cyrillic `Квартиры` preserved (preserve-unicode) vs transliterated; APFS/NFC collision warns.
- UC-30: `default_tags`/`extra_tags` injected per-glob (PW-N).

## Task Goal
Route page-slug + course-project derivation through the config `slug_strategy` /
`project_slug_strategy` (PW-L), merge per-glob `default_tags`/`extra_tags` (PW-N), and
**converge the last C1 walk** (`wiki_extract_concepts._derive_source_project`) onto the
shared config path.

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_source/parsing.py` + a shared slug helper
- `_apply_slug_strategy(stem: str, strategy: str) -> str`:
  - `identity` → `stem` verbatim (Karpathy — no slugify);
  - `preserve-unicode` → `slugify(stem, lowercase=True, separator="-", allow_unicode=True, regex_pattern=r"[^\w\-]")`;
  - `transliterate` → `slugify(stem, lowercase=True, separator="-")` (current loose default — transliterates);
  - `ascii-only` → `slugify(stem, lowercase=True, separator="-", regex_pattern=r"[^a-z0-9\-]")` (lossy).
- `derive_slug(path, vault_root, config)` becomes config-aware: page slug via
  `config.slug_strategy`; project via the matched `PathEntry` (`project` literal or
  `project_pattern`+`project_template`+`project_slug_strategy` — `course-slug` = the loose
  default slugify, byte-identical to today's course project). Shares the `iter_pages`
  derivation (012-02) — extract a common `derive_slug_project(rel_path, config)` so the
  ingest path (manual adapter) and the discovery path agree (C-4).
- `_slugify_concept` (concept-tag slug) **left untouched**.

#### File: `scripts/wiki_index/normalization.py`
- `normalize_frontmatter` merges the matched `PathEntry.default_tags` + `extra_tags` into the
  page `tags` (dedup, order-preserving — same idiom as the existing marker/concept merge).

#### File: `scripts/wiki_skills/wiki_extract_concepts.py`  ← C1
- `_derive_source_project` (~1140-1165): delete the inline copy of the two-tier logic; call
  the shared `derive_slug_project` so apply-side project == reindex-side project.

### Changes in Test Files
#### File: `tests/test_slug_strategy.py` (NEW) + `tests/test_default_tags.py` (NEW)
- Karpathy (`identity`): a `OAuth 2.0.md` page → slug `OAuth 2.0` (verbatim); 012-00 green.
- `preserve-unicode`: `Квартиры` → `Квартиры`; `transliterate`: `Квартиры` → `kvartiry`;
  `ascii-only`: lossy.
- **Collision (known-limitation, UC-30 A1):** two preserve-unicode slugs differing only by
  case / NFC-vs-NFD → the engine SURFACES a collision warning, never silently overwrites a
  `(vault_id, slug, project)` PK row.
- `default_tags: [inbox, draft]` on `_inbox/**` → both tags on every matched page, dedup-merged.
- `_derive_source_project` returns the same project as `discover_pages` for a course-tier source.

## Acceptance Criteria
- ✅ Karpathy slugs byte-identical (012-00 green); Cyrillic preserve/transliterate correct.
- ✅ default/extra tags merged + deduped; collision warns (never silent overwrite).
- ✅ `_derive_source_project` converged onto the shared helper (C1). `mypy --strict` clean; suite green.

## Stub-First (`skill-tdd-strict`)
Phase 1: `_apply_slug_strategy` returns `stem` for all strategies (karpathy-equivalent) →
012-00 green. Phase 2: per-strategy logic + tag merge + the `_derive_source_project`
convergence + collision-warning, each RED-first.
