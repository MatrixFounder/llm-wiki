# VDD Adversarial Review — TASK 008 PLAN (`wiki-verify-multi`, R-8)

**Date:** 2026-05-29
**Mode:** `/vdd-adversarial` on the **plan** (pre-implementation), run as a multi-critic
workflow: 4 independent adversarial lenses (decomposition-sequencing,
durability-datamodel, security-grounding, completeness-fidelity) probing
`docs/PLAN.md` + the 11 bead specs, **each finding independently refuted** to kill
bikeshedding / already-covered nitpicks.
**Outcome:** probed **18** → confirmed-real **11** (deduped to **6 distinct issues**) →
**0 CRITICAL** · 6 must-fix (1 HIGH + 5 MEDIUM) + 1 LOW · **7 refuted**. All 6 applied
in place. **Objective Convergence reached** (0 critical, 0 unresolved legitimate findings).

## The value this pass added
The three formal gates (task / architecture / plan reviewers) all PASSed the plan,
but adversarial **failure-simulation of the execution** surfaced real gaps none caught
— chiefly **cross-file fan-out of a rename** and **operator-facing migration
inaccuracy**, both invisible to a static spec read.

## Confirmed findings (6 distinct) — all FIXED

| # | Lens(es) | Sev | Issue | Fix applied |
|---|---|---|---|---|
| 1 | CMP-2 + DEC-1 + DUR-1 (3 lenses converged) | HIGH | 008-03 renames `_cited_refs_from_frontmatter` → `_frontmatter_refs(db_type,…)` but its changed-files list named only `reindex.py`. The old name is imported+called in `wiki_query.py:311,325` (the `wiki-query apply` self-index) + `test_reindex_cites.py:16,150,164,171,172` (module-top import → **whole-suite collection ImportError**). → green-throughout break at a strict-TDD boundary. | **008-03**: added explicit "RENAME FANOUT, MUST land in this bead" subsections for `wiki_query.py` + `test_reindex_cites.py` (update to `_frontmatter_refs("query", …)`), **or** a one-line back-compat shim `_cited_refs_from_frontmatter = partial(_frontmatter_refs, "query")`; + regression bullet (`wiki-query apply` self-index still imports) + AC. |
| 2 | DEC-2 | MED | 008-07 uses `_frontmatter_refs("verification", …)` (created by 008-03) but **008-03 was missing from 008-07's deps + the DAG**; plan marketed the skill chain as parallel-safe → 008-07 reachable before 008-03. | **008-07** Notes + **PLAN** §1 deps + §2 DAG edge + §1 parallel-safe parenthetical: added 008-03 as a dependency. |
| 3 | DEC-3 + DUR-3 (2 lenses) | MED | 008-01 bumps `user_version` 4→5 but **THREE** tests assert `== 4` (`test_schema_v4.py:27`, `test_schema_smoke.py:67`+`:51` docstring, `test_schema_v3.py:31`) — bead named only the first → other two go RED at the first bead. | **008-01** §Changes-in-Test-Files + AC + **PLAN** §1/§3/R-10: enumerate all three; added "grep tests/ shows no remaining `== 4`" AC. |
| 4 | DUR-2 + DEC-4 (2 lenses) | MED/LOW | "migration = `wiki-reindex --full`" is **wrong for a populated v4 DB**: `apply_schema_if_missing` no-ops on an existing file, `reindex_full` only DELETEs rows (no DROP/recreate) → old v4 CHECK persists → `verification` insert raises `IntegrityError`. Also the **"`wiki-init` reads `user_version` and reseeds" claim is false** (no such code) — present in 008-01 **and** TASK.md R-8.9(d). | **008-01** + **TASK** R-8.9(d)/NFR-6/C-5 + **PLAN** inv#11/R-10 + **data-model §4.4** + **ADR-002 §D8 amendment**: corrected to **delete `.db`/`-wal`/`-shm` → `wiki-init --register-existing` → `wiki-reindex --full`**; struck the false reseed claim. |
| 5 | SEC-1 | MED | 008-09 durability recipe ("delete DB → `wiki-reindex --full`") omits the mandatory `apply_schema()` + `register_vault()` re-seed (the `vaults` row is wiped → `reindex_full` raises `ValueError("vault not registered")`). The precedent `test_wiki_query_durability.py::_rebuild_db` does both. | **008-09**: added the re-seed step citing the `_rebuild_db` UC-20 precedent. |
| 6 | CMP-4 | MED | 008-06 `apply` write jumps straight to `atomic_write_text` (which `mkstemp(dir=parent)` → `FileNotFoundError` if `_verifications/` absent). A **migrated v4 vault** has no `_verifications/` until the first apply → first apply crashes. `wiki-query apply` does `mkdir(parents=True)` + `validate_inside_vault` first. | **008-06**: added the mkdir+validate step (via the imported `layout.VERIFICATIONS_SUBDIR` — keeps the grep guard green); **008-10**: UC-22 fixture now uses a vault with **no pre-existing `_verifications/`**. |
| 7 | SEC-4 | LOW | `exit 6` is the wiki-family's **generic error** code (`_common.emit` / `.AGENTS.md`), but `wiki-verify-multi` returns 6 as a *verdict-fail SUCCESS* signal → a naive `$?==6 ⇒ errored` consumer discards a filed FAIL verdict. | **008-06** + **008-08** + **PLAN** inv#7/R-8: documented as a **deliberate divergence**; callers MUST branch on the stdout envelope (`verdict:"fail"`, no `error` key), not `$?`. (Kept code 6 + documented; proportionate to LOW + the off-by-default consumer.) |

## Refuted (7) — correctly dismissed by the per-finding verifiers
- **SEC-2** (O_NOFOLLOW on TOCTOU/source reads): already mandated by 008-05 lines 20+27 + TASK NFR-3 + the `_common` symlink-refuse norm — prose-symmetry nit only.
- **SEC-3** (apply re-reads raw `cites:` vs prepare's examined set): foreclosed by the defined term "examined set" + 008-05's explicit cross-bead consequence clause (plan-review m-3) + the shared-`_retrieve` template.
- **SEC-5** (grep guard defeatable): misreading — the binding constraint is the `pages.file_path` read path + the non-Karpathy behavioural fixture (UC-28); the grep is belt-and-braces, already so framed.
- **CMP-1** (no `--project` flag): query pages are always vault-tier (`_vault_`), so no course-tier query page exists; the CLI contract is settled architecture; residue is a one-line `layout.VAULT_TIER_PROJECT` clarification.
- **CMP-3** (examined-set TOCTOU weaker than R-6): misreads R-6 (`question_hash` folds the slug *set*, not bodies — same as `verify_hash`); the static-`cites:` design has no volatile-retrieval drift; doubly-exotic precondition.
- **CMP-5** (where `verify_hash` comes from): already covered by 008-07 TC-E2E-04 (prepare→apply→prepare `is_unchanged`) + the `wiki-query --question-hash` template.
- **CMP-6** (record on content-hash-skip path): the first apply always `changed=True` (arms idempotency); the only failing scenario is the explicitly-accepted Class-C rebuildable contract (a lost row → correct recompute).

## Convergence
0 CRITICAL; all 6 confirmed must-fix issues amended in place; the 7 refuted items are
bikeshedding / already-covered / misreadings (no action). Per the `vdd-adversarial`
Objective-Convergence bar, the plan is **zero-slop** for execution. A re-run is
available on request but the fixes are mechanical doc/spec amendments (no new logic),
so a second full adversarial sweep would re-probe now-closed surfaces.
