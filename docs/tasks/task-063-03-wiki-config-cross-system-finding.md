# TASK 063-03 — `wiki-config validate`: the cross-system glob-coverage finding

**Phase**: 1 (the gate) · **RTM**: R-063-3′(b) · **Type**: code · **Effort**: 2–3h
**Depends on**: 063-00, 063-02 · **Unblocks**: — (ships value alone)

## Goal

`wiki-config validate` gains a new finding: a `dirs.*` value in `sync.yaml` that **no `paths[]` glob
of the resolved layout covers**.

`wiki-config` already validates all **three** config systems (`_lint.py:642` `sibling_systems`) while
*editing* only `sync.yaml` — so it is the one place in the codebase with a legitimate view of both
halves. This finding is the **cross-system** half of the G4 load gate; the rail's `prepare` preflight
(063-05) is the other. **Both call `resolve_typed_write_dir` (063-02).**

## Why a validate finding at all — the honest statement

Without it, `dirs.decision: "решения"` on cybos writes a **glob-invisible page**: never discovered by
`discover_pages`, therefore never reported by `find_pages_missing_in_index`, therefore **zero lint
issues** — the delta property passes perfectly while a decision is silently lost.
**Lint is structurally incapable of seeing it.** This gate is the only *preventive* defence, and it
must fire at config-edit time, where the operator can act.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_config/_findings.py` — one new `FindingKind` in `_KINDS`
  (the taxonomy is API; codes are stable):
  `FindingKind("TYPED_DIR_NOT_COVERED_BY_LAYOUT", SEV_ERROR, TIER_MANUAL)` — **manual**, because the
  fix is a human decision (rename the folder, or widen the read grammar), never a safe auto-edit.
- **Edit** `scripts/wiki_skills/wiki_config/_lint.py` — a `_check_typed_dirs(rel, raw)` in the
  per-file advisory pass (`advise_sync_file`, line 299). It needs the **resolved layout**, which
  `_lint.py` already imports (`resolve_layout_config`, line 43).
- **Read** `_findings.py` `safe_key()` (line 89) — the operator-typed folder name goes through it.

## The message (actionable — the whole point of REFUSE-not-autogenerate)

> `dirs.decision: 'решения'` is not covered by any `paths[]` glob of layout `cybos`.
> Use `decisions`, or add `решения/**/*.md` to `.wiki/layout.yaml`.

**Value-free posture (CWE-209/117):** the folder NAME is operator-typed input, so it passes through
`safe_key()`; the layout name and the suggested glob are **schema/config constants**, safe to echo.

## Steps

1. Register the code in `_KINDS`.
2. In `advise_sync_file`, when the raw dict has an `extract_decisions.dirs` block: resolve the layout
   once per lint run (cache it on the `_Linter`); for each `dirs.*` value call
   `resolve_typed_write_dir(cfg, dir_name=value, source_rel=<the folder this sync.yaml governs>)`.
   `None` ⇒ `add("TYPED_DIR_NOT_COVERED_BY_LAYOUT", "sync", rel, pointer=f"/extract_decisions/dirs/{cls}", …)`.
3. **`system="sync"`** — the finding is *about* a sync.yaml key (that is where the pointer lives and
   where the operator edits), even though the *evidence* comes from the layout. Say so in the message.
4. A layout that maps **zero typed classes** (karpathy / obsidian-personal): the dirs are moot —
   still refuse, with the *"this layout maps no typed classes"* variant of the message, so the
   operator learns it here rather than at the first `prepare`.

## Tests (RED first) — `tests/test_wiki_config_validate.py` (extend)

- `test_typed_dir_not_covered_is_a_finding` — cybos vault, `dirs.decision: решения` ⇒ exactly 1
  finding, code `TYPED_DIR_NOT_COVERED_BY_LAYOUT`, severity `error`, pointer
  `/extract_decisions/dirs/decision`. **MUT:** delete the check ⇒ RED.
- `test_covered_dir_is_clean` — same vault, `dirs.decision: decisions` ⇒ **0** findings
  (`total_findings == 0`, not "no error-severity" — a warning would be a false alarm too).
- `test_cyrillic_dir_is_clean_on_a_generic_glob_layout` — obsidian-personal + `решения` ⇒ **0**
  findings. *cybos is not "broken" — it is STRICT BY DESIGN; a PARA vault's generic glob makes the
  name free. Both are correct, and the gate is what makes the difference visible.*
- `test_message_never_echoes_an_unsafe_value` — `dirs.decision: "evil\n---"` ⇒ the rendered
  message contains no control chars (through `safe_key`).
- `test_zero_typed_class_layout_refuses` — karpathy vault + any `dirs` ⇒ finding.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES:** the new code appears in **every** finding sink. Enumerate them:
      ```bash
      grep -rn "TAXONOMY\|FindingKind" scripts/wiki_skills/wiki_config/ | grep -v _findings.py
      # → the sinks: histogram / render_findings_report / _report.py / _doctor.py tiers
      ```
      and assert the new code is renderable by each (a code registered in `_KINDS` but unrenderable
      is a `KeyError` at the worst possible time). The existing taxonomy tests should already cover
      this generically — **verify that, do not assume it**.
- [ ] **MUT:** revert `_check_typed_dirs` ⇒ `test_typed_dir_not_covered_is_a_finding` RED.
- [ ] `wiki-config validate` on the repo's own `samples/` cybos fixture: exit code + histogram
      unchanged when no `extract_decisions` block exists (**back-compat: absence is silent**).

## Rollback

Remove the `FindingKind` row + `_check_typed_dirs`. Taxonomy codes are API — since this one has never
shipped, removal is clean.
