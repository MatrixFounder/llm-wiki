# Task 012-01: PW-A — layout-config schema + loader + built-in karpathy.yaml

## Use Case Connection
- UC-29: byte-identical Karpathy (the karpathy.yaml-as-validated-projection invariant).
- UC-34: custom config (schema validation + the loader's resolution/override path).

## Task Goal
Lay the **foundation** the whole engine consumes (PW-A): a new **parallel** config layer
(D-012-2) that carries per-layout-class *grammar*, separate from the existing per-vault
identity config. After this bead the engine can *load* a validated `LayoutConfig`; later
beads make `discover_pages`/`normalize`/`extract_refs`/`derive_slug` *consume* it.

## Changes Description

### New Files

#### File: `scripts/wiki_index/layout_config.py` (NEW)
- `@dataclass(frozen=True) class PathEntry`: `glob: str`, `type: str | None`,
  `project: str | None`, `project_pattern: str | None`, `project_template: str | None`,
  `project_slug_strategy: str | None`, `default_tags: tuple[str, ...]`,
  `extra_tags: tuple[str, ...]`.
- `@dataclass(frozen=True) class RefRule`: `kind: str`, `regex: str`, `target_group: int`,
  `transform: str | None`.
- `@dataclass(frozen=True) class LayoutConfig`: `layout: str`, `ignore: tuple[str,...]`,
  `file_extensions: tuple[str,...]`, `slug_strategy: str`, `paths: tuple[PathEntry,...]`,
  `type_mapping: dict[str, tuple[str, str|None]]`,
  `path_type_fallback: dict[str, str]`, `ref_extraction: tuple[RefRule,...]`,
  `frontmatter_synthesis: dict[str, Any]`, `auto_indexes: tuple[dict, ...]`.
- `LAYOUTS_DIR = Path(__file__).parent / "layouts"`.
- `_ALIAS = {"flat": "karpathy", "per-project": "karpathy"}`.
- `class LayoutConfigError(ValueError)` — raised on schema-invalid / regex-compile-fail /
  template-missing-group; the caller exits **6**.
- `load_layout_config(vault_root: Path, root_config: dict) -> LayoutConfig`:
  (1) `name = _ALIAS.get(root_config["layout"], root_config["layout"])`;
  (2) load `LAYOUTS_DIR / f"{name}.yaml"` (base) — `LayoutConfigError` if unknown name;
  (3) resolve optional override: `root_config.get("layout_config")` (relative to
  `vault_root`, `validate_inside_vault` + `O_NOFOLLOW`) **or** `<vault_root>/.wiki/layout.yaml`
  (frontmatter target wins); deep-merge over base with **REPLACE on `paths`/`ref_extraction`**,
  scalar overlay (Q-012-f);
  (4) validate merged dict against `config/layout-config.schema.yaml`;
  (5) **ReDoS pre-check is deferred to 012-04** (the gate lives with ref extraction); this
  bead validates the *schema* only;
  (6) build + return the frozen `LayoutConfig` (cache per `vault_root`).

#### File: `config/layout-config.schema.yaml` (NEW)
- Draft-2020-12. `$defs`: `LayoutConfig`, `PathEntry`, `RefRule`, `TypeMappingEntry`,
  `AutoIndex`, `FrontmatterSynthesis`.
- **`additionalProperties: false` at the `PathEntry` level** (stricter than
  `wiki-config.schema.yaml` — a misspelled key is a load-time error, not a silent
  `_unmatched_` flood).
- `slug_strategy` enum: `[identity, preserve-unicode, transliterate, ascii-only]`.
- `db_type` (in TypeMappingEntry) enum constrained to the live `pages.type` CHECK:
  `[summary, concept, query, brief, research, index, verification]`.

#### File: `scripts/wiki_index/layouts/karpathy.yaml` (NEW)
- A **validated projection of `layout.py`**: root-tier globs `{sub}/**/*.md` for each
  `PAGE_SUBDIRS` member (`_vault_` project); course-tier globs
  `Lessons/*/{sub}/**/*.md` with `project_pattern: '^Lessons/(?P<course>[^/]+)/'` +
  `project_template: '${course}'` + `project_slug_strategy: course-slug`.
- `slug_strategy: identity` (verbatim `path.stem`).
- `type_mapping`: the **15-entry** `TYPE_MAPPING` verbatim.
- `path_type_fallback`: `{_concepts: concept, _entities: external, _queries: query,
  _verifications: verification}` (mirrors `_PATH_TYPE_FALLBACK`).
- `ref_extraction`: one `wiki-link` rule `regex: '\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'`,
  `target_group: 1` (byte-identical to `_WIKILINK_RE`).
- `frontmatter_synthesis: {enabled: false}`. `auto_indexes: []`. `ignore: []`.
  `file_extensions: ['.md']`.

### Changes in Existing Files

#### File: `config/wiki-config.schema.yaml`
- `$defs/Layout` enum: `[flat, per-project]` → `[flat, per-project, karpathy, dev-project, obsidian-personal]`.
  Update the description to note the alias semantics.

### Changes in Test Files

#### File: `tests/test_layout_config.py` (NEW)
- `test_karpathy_config_matches_layout_constants`: load karpathy.yaml; assert root-tier
  globs == `{sub}/**/*.md` ∀ `PAGE_SUBDIRS`; course prefix == `COURSE_TIER_DIR`; `_vault_`
  literal == `VAULT_TIER_PROJECT`; `type_mapping` == `normalization.TYPE_MAPPING`;
  `path_type_fallback` == `_PATH_TYPE_FALLBACK` (keyed by subdir constant).
- `test_alias_resolution`: `flat`/`per-project` resolve to `karpathy.yaml`.
- `test_schema_rejects_misspelled_pathentry_key`: a `paths[]` entry with `projct_pattern`
  → `LayoutConfigError` (additionalProperties:false).
- `test_override_merge_replaces_paths`: a `.wiki/layout.yaml` with `paths` REPLACES base.
- `test_override_symlink_escape_refused`: a symlinked `.wiki/layout.yaml` → refused.
- `test_unknown_layout_name`: `layout: bogus` → `LayoutConfigError`.

## Acceptance Criteria
- ✅ karpathy.yaml validates against the new schema; the invariant test ties it to `layout.py`.
- ✅ `flat`/`per-project` → karpathy; unknown name → error; misspelled key → error.
- ✅ Override resolution (frontmatter target > conventional `.wiki/layout.yaml`) + path guard.
- ✅ 012-00 golden snapshot still green (no engine wiring yet — pure additive).
- ✅ `mypy --strict` clean.

## Stub-First
Phase 1: `load_layout_config` returns a hardcoded karpathy `LayoutConfig`; write the
invariant + schema-reject tests (RED on the hardcoded stub where they assert real
resolution). Phase 2: real loader + alias + override-merge + schema validation.
