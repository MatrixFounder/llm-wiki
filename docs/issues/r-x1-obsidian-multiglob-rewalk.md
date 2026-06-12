---
id: R-X1-OBS-WALK
type: known-issue
status: fixed
opened_at: 2026-06-01
resolved_at: 2026-06-12
category: performance
severity: SEV-3
slug: r-x1-obsidian-multiglob-rewalk
---

# obsidian-personal multi-glob subtree re-walk

- **Symptom**: `iter_pages` ran one `Path.glob` per `paths[]` entry. The
  `obsidian-personal` layout's overlapping recursive globs scandir'd the vault root 4×
  and every `NN - <Area>/` dir 2× (measured baseline: 140 scandirs over 69 dirs at 2k
  files — `docs/benchmarks/030-walk-baseline.md`).
- **Root cause**: per-glob walk instead of a single walk + in-memory matching.
- **RESOLVED (TASK 030 / R-030-3+R-030-6, beads 030-04+030-05; YAGNI gate
  operator-overridden on record)**: single-pass **iterative explicit-stack**
  `os.scandir` walk with per-pattern **alive-sets** (NFA over glob segments; `**` never
  consumes a symlinked dir segment → exact per-entry `Path.glob` union semantics) +
  first-match attribution among patterns alive at the containing dir + a **descent
  predicate** that prunes both unmatchable subtrees (karpathy "root subtrees never
  walked" holds BY CONSTRUCTION, instrumented) and `<prefix>/**`-shaped `ignore[]`
  subtrees. **Measured**: PARA 2k-file fixture — scandirs **140 → 61** (every dir
  exactly once), wall **94.1 → 77.0 ms**; fat-karpathy 25 → 6; delta-noop @10k
  246.3 → 191.8 ms. Enumerated matcher deltas: ARCHITECTURE Q-030-2 v4 (i)–(iv).
- **Prevention note (corrected at close)**: the original "ignore[] evaluated before
  paths prunes service dirs" line OVERSTATED the old engine — `ignore[]` was a
  post-walk per-candidate string filter (it saved stats, not directory I/O; only
  `**/_raw/**` subtrees were actually traversed-then-filtered). REAL ignore-pruning
  (zero scandirs into `<prefix>/**`-covered subtrees) ships with this fix.
