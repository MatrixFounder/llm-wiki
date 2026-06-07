# PLAN 021 — dogfood-hardening

Stub-First, green-throughout. Beads ordered so each lands with its RED→GREEN test.
Zero DDL (`user_version` 5). No new deps. Re-run the dogfood repros at the end.

| Bead | RTM | Change | Test (RED→GREEN) |
|------|-----|--------|------------------|
| **021-1** | R-021-2 | `reindex_delta`: seed `seen_keys` from `SELECT slug,project,file_path FROM pages` before the loop; update the "within-batch only" comment. | `test_delta_surfaces_cross_batch_collision` (full a → delta b/future) + `test_delta_self_update_no_collision`. |
| **021-2** | R-021-4 | Strengthen `test_reindex_full_surfaces_slug_collision` + delta test: assert `kept==later`, `dropped==earlier`, and DB `file_path==kept`. | the two existing tests, tightened. |
| **021-3** | R-021-3 | `wiki_reindex.main`: `--all-vaults` delegates to `reindex_delta` when `--delta`; envelope reports `mode` + aggregates `touched`(delta)/`pages_indexed`(full) + `slug_collisions`. | `test_all_vaults_delta_mode` + keep `--all-vaults --full` shape. |
| **021-4** | R-021-1 | `_resummarize`: `_scope_key_index` → `Mapping[str,str]` (key→representative summary stem, deterministic min); `_mirror_match(..., warn_uncited=False)`; `summary_exists` passes `warn_uncited=pr.enabled` so a group-key skip with an uncited raw emits the merge/split WARN. Skip unchanged. | `test_groupkey_uncited_warns` / `test_cited_no_warn` / `test_provenance_disabled_no_warn` / `test_stem_relpath_no_warn`. |
| **021-5** | R-021-1 | `workflows/wiki-sync.md`: document the WARN + MERGE/SPLIT/SUPERSEDE recipes (operator runbook). | n/a (doc). |
| **021-6** | R-021-5/6 | Doc-drift: fix `samples/target-obsidian-vault/.wiki/layout.yaml` header (ignore extends; REPLACE scoped to paths/ref_extraction); re-check personal-vault-dogfood. Schema/docstring notes: leading-zero equivalence class + single-valued `summary_ext`. | manual + `resolve_layout_config` union still holds. |
| **021-7** | all | Full pytest + mypy strict + dogfood re-run (HIGH-1 now WARNs, HIGH-2 now reported); grep-guards. | green gate. |

**Risk notes:** 021-4 changes the `Caches.mirror` value type (`frozenset[str]`→`Mapping[str,str]`);
membership (`rkey in keys`) and falsiness (`not keys`, dead-detector guard) are preserved for a
dict. 021-1 reuses `repo._connect()` (consistent with the existing within-batch query). All
log-only / read-only — no schema, no envelope-shape break for existing consumers (delta gains a
populated `slug_collisions`, already present since TASK 020).
