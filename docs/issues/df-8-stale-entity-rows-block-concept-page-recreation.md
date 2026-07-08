---
id: DF-8
type: known-issue
status: fixed
opened_at: 2026-07-08
resolved_at: 2026-07-08
resolved_by: TASK 053 (R3)
category: correctness
severity: SEV-2
slug: df-8-stale-entity-rows-block-concept-page-recreation
---

# `wiki-import apply --concepts` classifies against ghost `entities` rows as "mentioned" instead of "created", with no signal that the target file doesn't exist

> **Resolution (TASK 053 / R3, fixed 2026-07-08).** `_apply_write` now dedups to
> `mention` ONLY for a slug that is BOTH a known entity AND present on disk:
> `effective_known = known_slugs & present_concept_files`, where the present-set is
> the `_concepts/*.md` files found by a shared `_present_concept_slugs(vault_root)`
> helper (the same FS ground-truth `prepare`'s `missing_concept_files` uses). A
> known-but-missing slug (a ghost row) reclassifies `create` and self-heals; the
> re-creation surfaces in the manifest `written[]` list (the operator signal — no
> new warnings field, zero-DDL). The batch path scans the present-set ONCE and
> grows it in place per create (no O(N·walk); no double-create). Delegated to by
> `wiki-import apply --concepts` unchanged. **Both sides of the intersection are
> NFC-normalized** (a VDD-review fix-up: the FS-derived present-set is normalized
> at its `os.scandir` source and `known_slugs` is normalized at the intersection)
> so a present Cyrillic concept on macOS/iCloud (NFD on disk, NFC in the DB/LLM
> slug) dedups to `mention` instead of re-`create`ing every run — the same NFC/NFD
> boundary R1 closes for `source_state`. Regressions:
> `tests/test_wiki_extract_concepts.py::test_apply_self_heals_ghost_entity_row`,
> `::test_apply_present_concept_still_mentions_no_double_write`,
> `::test_present_concept_slugs_nfc_normalizes`, and
> `::test_apply_cyrillic_concept_present_nfd_still_mentions`.

- **Symptom**: re-running `wiki-import prepare → REASON → apply --concepts` for a source
  whose 12 concept entities were already present in the vault-wide `known_concepts` list
  (from a prior run whose *pages* had since gone missing on disk — see
  [[df-7-resummarize-gate-trusts-source-state-without-disk-check]]) produced an envelope
  reporting **success** — `"written": []`, all 12 candidates under `"mentioned"` — with no
  warning field anywhere indicating that the "already existing" concept these were matched
  against had **no backing file**. The summary note was correctly filed and correctly links
  to these 12 concept slugs, but the concept pages themselves were never (re-)created. This
  is silent, apparent data loss: the envelope reads exactly like a normal, successful
  de-duplication (R-2 "reuse an existing concept, don't recreate it"), and the only way to
  discover that the "existing" concept was a ghost is an unrelated `wiki-lint` run.
- **Root cause**: the `known_concepts`/de-duplication path (both the `wiki-import` REASON
  contract's R-2 and `wiki-extract-concepts`'s de-dup rule R-34) matches a proposed entity
  against `known_concepts` **by slug/name presence in the `entities` table alone**. It never
  checks `entities.file_path` (or the equivalent for whatever the concept page's expected
  location would be) to confirm the file backing that entity row still exists before
  deciding "mention, don't create". A `pages`/`entities` row surviving after its file was
  deleted (the exact class of drift `wiki-lint`'s `missing-on-disk` exists to catch) is
  silently treated as proof the concept page is fine.
- **Affected components**: `scripts/wiki_skills/wiki_extract_concepts/__init__.py` (the
  create-vs-mention classification in `apply`), and by extension `wiki-import apply
  --concepts`, which delegates to the same logic in-process.
- **Fix**: before classifying a candidate as "mention" (skip creation), stat the matched
  `known_concepts` entry's `file_path` (or resolve it via the layout the same way
  `wiki-lint`'s `missing-on-disk` check does); if the file is absent, either (a) fall back to
  `create` for that candidate (self-healing — the exact fresh-import case this repro needed),
  or (b) at minimum surface a `warnings[]` entry like `{"code": "STALE_ENTITY_NO_FILE",
  "slug": "..."}` so the operator/orchestrator is told to investigate rather than assuming
  success. Option (a) is preferable — it makes the concept-extraction step actually
  idempotent-and-self-healing rather than idempotent-and-silently-lossy.
- **Workaround (used in this session)**: run `wiki-reindex --full` before re-running
  concept extraction — it wipes the `entities` table (rebuilding purely from files that
  actually exist on disk), so the ghost rows disappear and the next `wiki-extract-concepts
  apply` correctly classifies the same candidates as `create`. This works but is a heavy,
  whole-vault hammer for a single-source fix, and isn't documented anywhere as the intended
  remediation for this failure mode.
- **Related**: [[df-7-resummarize-gate-trusts-source-state-without-disk-check]] (identical
  "DB row believed without checking the file it names still exists" pattern one layer up, at
  the raw-source/summary level rather than the concept-entity level).
