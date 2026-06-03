# Architecture RE-REVIEW — TASK 018 `wiki-sync` (post-adversarial amendments)

- **Date:** 2026-06-03
- **Reviewer:** Architecture Reviewer (05) — re-gate after the `/vdd-adversarial` amendments
- **Method:** 4-panel fan-out (run `wf_29fce9ba-39b`, 25 agents) — each panel VERIFIES the
  adversarial fixes landed *and are correct* against code/schema, HUNTS new flaws, applies the
  checklist; new findings refuted (default-refuted) before counting.
- **Target:** the amended `docs/TASK.md` + `docs/ARCHITECTURE.md` §11a (Q-018-1..9) + chunks.
- **Status:** **BLOCKING → AMENDED → ✅ APPROVED.** The re-gate found my amendment set itself
  introduced new holes (1 BLOCKING + 3 fixes-not-fully-correct + 4 lower); all corrected inline
  (Q-018-3/8/9 refined + **new Q-018-10**). Residual is LOW/Planning only.

## 1. Executive Summary
- **Verdict:** APPROVED after the re-gate amendments (was BLOCKING).
- **Confidence:** High (panels verified against code + SQL; new findings refuted).
- **Summary:** Re-gating was worth it — it caught that my own fixes regressed/over-claimed in
  four places, most importantly a **false security claim** (`safe_load` does *not* stop an
  anchor-bomb) and a **new self-ingest loop** (the staged converter output was a `.md` in `_raw/`
  → re-discovered). Both fixed.

## 2. Fixes that needed correction (verified NOT-fully-correct → re-amended)

| Prior fix | Re-gate finding | Correction |
|---|---|---|
| **SEC-A5** (`safe_load` → "no anchor expansion") | **SEC-N3** — *empirically false*: `safe_load` expands aliases (232 B bomb → 531 k nodes); only blocks `!!python/object`. Size-cap alone insufficient. | security §7.5 + interfaces §5.4 + Q-018-10: strike the claim; real bound = **256 KiB size-cap + a custom `SafeLoader` that forbids anchors/aliases**. |
| **AM-1→Q-018-8** uniform `sha256(file bytes)` key | **W-2/am-2 regression** — uniform byte-hash means `scan` reads every eligible file; the old "no-re-read fast-path" no longer holds. | functional-arch *read-cost* note + Q-018-10: state it honestly; acceptable (scoped zones, binaries skipped pre-read, `_daily` excluded); optional mtime short-circuit = Planning YAGNI. |
| **META-2** per-vault `flock` | **SEC-N4** — precedent (per-append log lock) ≠ a multi-minute per-vault lock; scope/lifetime/`NB` unspecified. | security §7.5 + Q-018-10: `LOCK_EX\|LOCK_NB` on `<vault>/.wiki/sync.lock`, exit 2 `SYNC_IN_PROGRESS`, fd-scoped auto-release, guards wiki-sync runs only. |
| **Q-018-3** staging `_raw/<slug(stem)>-<ext>.md` | **RG-1 (BLOCKING)/W-3/SEC-N5** — the staged `.md` is in `_raw/` → re-walked → re-summarised (convert+ingest non-convergent; falsifies AC-5). | functional-arch + Q-018-3/10 + AC-14: stage to **non-walked `_raw/.staging/`**; walk excludes `_raw/.staging/**`+`.locks`+`failed`. |
| **EC-2** unmappable-type predictor | **W-1** — predictor was karpathy-specific; diverges from `normalize_frontmatter` on other layouts. | functional-arch + Q-018-9(b): predict against the **same layout resolution `wiki-index-upsert` uses**. |

## 3. New findings (7 confirmed; 1 BLOCKING) — disposition
- **RG-1** HIGH (BLOCKING) / **W-3**, **SEC-N5** MED — convert+ingest self-ingest loop → **fixed** (non-walked `.staging/`, AC-14).
- **SEC-N3** MED — `safe_load` false defense → **fixed** (anchor-ban loader).
- **W-1** MED — layout-general unmappable-type → **fixed**.
- **SEC-N1** LOW — empty-slug staging target → **recorded** as a Planning constraint (`sync-<sha8(path)>-<ext>.md` fallback) in §7.5 + Q-018-3.
- **RG-5** BIKESHED — `register_summary` precedent wording → **reworded** (refuses on existence; here refined to content).

## 4. Panel results & checklist
- **idempotency** fix_verified ✅ — confirmed `source_state` has no `source_kind` CHECK (SQL §10) ⇒ `'sync'` partition is legal + zero-DDL; commit-marker partial-resume sound. (The convergence gap was a *walk* issue, caught by the walk/consistency panels, not the keying.)
- **walk-upsert** fix_verified ⚠️→fixed — own-walk + unmappable-type correct after the `.staging/` exclusion + layout-general predictor.
- **security** fix_verified ⚠️→fixed — after SEC-N3 (anchor-ban) + SEC-N4 (flock spec) + `.staging/`.
- **checklist-consistency** fix_verified ✅ — data-model (zero-DDL upheld), SRP/YAGNI, doc-size (ARCHITECTURE.md ≤1500, Index-Mode intact), cross-doc consistency confirmed after the re-amendments; all 33+4 adversarial findings closed-or-deferred-with-reason.

## 5. Final Recommendation
**APPROVED — PROCEED to `/vdd-plan`.** The architecture survived a second adversarial gate; the
two rounds (adversarial → re-gate) converged the idempotency, walk, conversion, and config-safety
designs. Planning must carry the operationalised details: the only-a-view body matcher (RC-4), the
`_count_md_structure` reuse decision (RC-5), the empty-slug staging fallback (SEC-N1), and the
anchor-ban `SafeLoader` (SEC-N3). **Zero DDL** holds (`user_version` 5).

## 6. Hallucination Check
- [x] `source_state` no-`source_kind`-CHECK + PK confirmed in `sql/wiki-index-v2.sql` §10.
- [x] `safe_load` anchor-expansion verified empirically by the security panel.
- [x] `_raw/` is a vault-root dir (`layout.py RAW_SUBDIR`); `.locks`/`failed` are existing non-walked operational dirs (`SCAFFOLD_DIRS`).

```json
{ "review_file": "docs/reviews/architecture-018-rereview.md", "verdict": "APPROVED_AFTER_AMENDMENT", "blocking_resolved": 1, "fixes_corrected": 4, "new_confirmed": 7, "has_critical_issues": false }
```
