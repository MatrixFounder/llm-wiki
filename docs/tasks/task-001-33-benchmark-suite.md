# Task 001-33: Benchmark suite — synthetic vault generator + latency harness + multi-vault scaling

## Use Case Connection
- All UCs (validates SLOs across the stack)
- R-14

## Task Goal
Provide `scripts/benchmark.py` that generates synthetic vaults at N = 100 / 1000 / 10000 pages, runs every Phase 3a operation, measures per-op latency, asserts SLOs from [TASK.md §5.1](../TASK.md), and supports multi-vault scaling (5 × 1K, 10 × 5K).

## Changes Description

### New Files
- `scripts/benchmark.py`:
  - `def generate_synthetic_vault(target_dir: Path, vault_id: str, n_pages: int, *, with_wikilinks: bool = True) -> None:` — generates `target_dir/_sources/page-NNNN.md` with markdown body, frontmatter (`type`, `title`, `date`, `tags`), and random `[[wiki-link]]` references between pages.
  - `def measure(op_name: str, callable: Callable[[], Any], runs: int = 5) -> dict:` — runs the callable `runs` times, returns `{op: ..., min_ms: ..., p50_ms: ..., p95_ms: ..., max_ms: ..., runs: ...}`.
  - `def run_suite(n_pages: int, output_json_path: Path) -> bool:` — generates vault, runs all six operations (search, upsert, render, lint, reindex --full, reindex --delta), measures, compares to SLOs, returns True if all pass.
  - `def run_multivault_scaling(n_vaults: int, pages_per_vault: int) -> bool:` — generates N vaults, registers each, runs `wiki-search --vaults all` and `wiki-lint --cross-vault-duplicates`, measures.
  - CLI: `python scripts/benchmark.py --n 100 [--multivault N M] [--output path]`.
- `tests/test_benchmark.py` — smoke tests that the harness runs (does not assert SLOs in CI by default; CI flag `--enforce-slos` enables).

### Changes in Existing Files
None.

### SLO Targets ([TASK.md §5.1](../TASK.md))

| Operation | 100 | 1000 | 10000 |
|---|---|---|---|
| `wiki-search` | < 30 ms | < 50 ms | < 100 ms |
| `wiki-index-upsert` | < 50 ms | < 100 ms | < 100 ms |
| `wiki-index-render` | < 200 ms | < 1 s | < 5 s |
| `wiki-lint` full | < 500 ms | < 2 s | < 30 s |
| `wiki-reindex --full` | < 2 s | < 20 s | < 3 min |
| `wiki-reindex --delta` (no changes) | < 100 ms | < 500 ms | < 2 s |

Multi-vault scaling:
- 5 vaults × 1K pages → `wiki-search --vaults all` < 50 ms.
- 10 vaults × 5K pages → `wiki-search --vaults all` < 100 ms.

### Component Integration
- Output JSON consumed by CI (separate workflow file out of scope here).
- Synthetic vault generator reused in task-001-34.

## Test Cases

### End-to-end Tests
1. **TC-E2E-01**: `python scripts/benchmark.py --n 100` runs to completion, exits 0, prints summary JSON.
2. **TC-E2E-02**: All six operations measured.
3. **TC-E2E-03**: `--enforce-slos` flag causes exit 1 on any miss.

### Unit Tests
1. **TC-UNIT-01**: Synthetic vault has correct page count (frontmatter parseable).
2. **TC-UNIT-02**: `measure` returns expected statistics keys.

### Regression Tests
- All earlier task tests still pass on synthetic vaults.

## Acceptance Criteria
- [ ] All SLOs met on macOS dev machine (TASK.md acceptance baseline).
- [ ] Multi-vault scaling targets met.
- [ ] Output JSON well-formed.
- [ ] Synthetic generator deterministic with seed.

## Notes
- Cost budget: zero LLM calls in Phase 3a benchmarks (per task brief). All operations are pure SQL/Python.
- 10K-page benchmark takes ~5 min total — consider parallelism for CI.
- Performance regression policy: a 20% miss on any SLO blocks Phase 3a exit criteria.
