# Task 001-29: `wiki-lint` CLI impl — SQL-level + cross-vault duplicates + `--fix` [LOGIC IMPLEMENTATION]

## Use Case Connection
- UC-04 (`wiki-lint`)
- R-11, R-29

## Task Goal
Replace `wiki-lint` stub with full impl: run SQL-level checks (orphan_links, missing_backlinks, index drift with §6.1 mapping, required frontmatter, tag taxonomy, cross-vault concept duplicates R-29), render markdown report + JSON sidecar, optionally apply safe fixes (`--fix`).

## Changes Description

### New Files
- `scripts/wiki_index/lint.py`:
  - `@dataclass(frozen=True) class LintIssue: category: str; severity: Literal['error','warning','info']; vault_id: str; page_slug: str | None; details: dict`.
  - `def run_all_checks(repo: IndexRepository, *, vaults: list[str] | None = None, strict: bool = False) -> list[LintIssue]:`
    - Iterate vaults (all if None).
    - Per vault, collect:
      - `orphan_links` via `repo.find_orphan_links(vault_id)`.
      - `missing_in_index` via `repo.find_pages_missing_in_index(vault_id, vault_root)`.
      - `drift` via `repo.check_drift(vault_id)`.
      - `required_frontmatter` via in-process check (filter by `layout` setting).
      - `tag_taxonomy_violations` via SQL JOIN against `taxonomy` table (TBD if defined; skip gracefully if not).
      - `stale_claims` via `pages WHERE date < now() - 18 months` query.
    - Across vaults:
      - `cross_vault_concept_duplicates` via `repo.find_cross_vault_concept_duplicates()`.
    - Optional under `--strict`: `duplicate_concepts` via Levenshtein < 3 (use `python-Levenshtein` if available; else stub OFF).
    - Build `LintIssue` list.
  - `def render_markdown_report(issues: list[LintIssue], output_path: Path) -> None`.
  - `def render_json_sidecar(issues: list[LintIssue], output_path: Path) -> None`.
  - `def apply_safe_fixes(repo: IndexRepository, issues: list[LintIssue]) -> int:` — operates only on `index-drift` and `missing-backlinks`; returns number of fixes applied.

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_lint.py`

**Function `main()`:**
- Args:
  - `--vault <id>` (optional; default all).
  - `--report <path>` (optional; if given, write markdown report).
  - `--json-sidecar <path>` (optional; write JSON).
  - `--fix` (apply safe fixes).
  - `--strict` (treat info → warning, warning → error; enable duplicate-concepts check).
- `config = load_config()`; `repo = make_repo(config)`.
- `issues = run_all_checks(repo, vaults=[args.vault] if args.vault else None, strict=args.strict)`.
- If `args.report`: `render_markdown_report(issues, Path(args.report))`.
- If `args.json_sidecar`: `render_json_sidecar(issues, Path(args.json_sidecar))`.
- If `args.fix`: `applied = apply_safe_fixes(repo, issues)`; emit log_event (`event_type='lint'`).
- Exit code: 0 if no errors (after severity adjustment); 1 if errors present (`--strict` may elevate warnings).
- JSON to stdout: `{"vaults_checked": [...], "issues_count": N, "errors": N1, "warnings": N2, "info": N3, "applied_fixes": M | null}`.

### Component Integration
- Idempotent: re-run with `--fix` produces `applied_fixes: 0`.
- Cross-vault section in report contains the R-29 duplicates: e.g., `## Cross-vault concept duplicates (1)\n- shadow-ai: vault-alpha, vault-beta`.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: Clean vault → report contains exact phrase `✅ Healthy. No issues found.` (matches UC-04 AC).
2. **TC-E2E-02**: Vault with orphan link `[[Школа менеджмента Стратоплан]]` → report contains exact orphan line (UC-04 AC).
3. **TC-E2E-03**: §6.1 mapping: after ingest of `type: lesson-summary` file → lint does NOT report drift (UC-04 AC type-mapping aware).
4. **TC-E2E-04**: Multi-vault fixture (shared `shadow-ai.md`) → `cross_vault_concept_duplicates` section present.
5. **TC-E2E-05**: `--fix` idempotent: second run = `applied_fixes: 0`.

### Unit Tests
1. **TC-UNIT-01**: JSON sidecar is parseable JSON.
2. **TC-UNIT-02**: Latency: lint on 1K-page fixture < 2s (SLO).
3. **TC-UNIT-03**: `--strict` escalates info → warning.

### Regression Tests
- task-001-18 lint queries still pass.

## Acceptance Criteria
- [ ] All UC-04 ACs met.
- [ ] R-29 cross-vault duplicates section appears.
- [ ] `--fix` safe ops only (no orphan-target creation).
- [ ] SLO met.

## Notes
- File-level lint (dangling links inside markdown body, footnote inconsistencies) is **Phase 3b** (delegate to `wiki-ingest lint --output-format json`).
- The `stale_claims` check uses `date < datetime.now() - 18 months` — see UC-04 step 3.
- `--report 00-Vault-Index/lint-report.md` is the canonical path per UC-04.
