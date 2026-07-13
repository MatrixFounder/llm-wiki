# TASK 063-03 — `wiki-config validate`: the cross-system coverage finding

**Phase**: 1 (the gate) · **RTM**: R-063-3′(b) · **Type**: code · **Effort**: 2–3h
**Depends on**: 063-00, 063-02 · **Unblocks**: — (ships value alone)
**Revision**: v2 — plan-review **C-2b** (this bead contradicted itself) and **C-3** applied (PLAN §8).

## Goal

`wiki-config validate` gains a new finding: a `dirs.*` value in `sync.yaml` that **the resolved
layout's walker cannot see**.

⚠️ **"the walker cannot see it" is NOT "no `paths[]` glob covers it"** — `paths[]` is **1 of 5**
conjuncts (plan-review C-3). The finding fires on the **full filter chain** via `glob_covers`
(063-02), so `dirs.decision: "_raw"` — which *does* match a PARA glob but is killed by
`ignore: **/_raw/**` — is **refused here**, not silently lost at write time.

`wiki-config` already validates all **three** config systems (`_lint.py:642` `sibling_systems`) while
*editing* only `sync.yaml` — so it is the one place in the codebase with a legitimate view of both
halves. This finding is the **cross-system** half of the G4 load gate; the rail's `prepare` preflight
(063-05) is the other. **Both call `resolve_typed_write_dir` (063-02).**

## Why a validate finding at all — the honest statement

Without it, an uncovered `dirs.*` writes a **glob-invisible page**: never discovered by
`discover_pages`, therefore never reported by `find_pages_missing_in_index`, therefore **zero lint
issues** — the delta property passes perfectly while a decision is silently lost. **Lint is
structurally incapable of seeing it.** This gate is the only *preventive* defence, and it must fire at
config-edit time, where the operator can still act.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_config/_findings.py` — one new `FindingKind` in `_KINDS` (the
  taxonomy is API; codes are stable):
  `FindingKind("TYPED_DIR_NOT_COVERED_BY_LAYOUT", SEV_ERROR, TIER_MANUAL)` — **manual**, because the
  fix is a human decision (rename the folder, or widen the read grammar), never a safe auto-edit.
- **Edit** `scripts/wiki_skills/wiki_config/_lint.py` — `_check_typed_dirs(rel, raw)` in the per-file
  advisory pass (`advise_sync_file`, `:299`). It needs the **resolved layout**, which `_lint.py`
  already imports (`resolve_layout_config`, `:43`).
- **Read** `_findings.py::safe_key` (`:89`) — the operator-typed folder name goes through it.

## The message (actionable — the whole point of REFUSE-not-autogenerate)

> `dirs.decision` is not visible to the walker of layout `cybos` (no matching `paths[]` glob).
> Use `decisions`, or add `<name>/**/*.md` to `.wiki/layout.yaml`.

and the ignore-conjunct variant:

> `dirs.decision` matches a `paths[]` glob but is excluded by `ignore` — the walker will never
> index pages written there.

**Value-free posture (CWE-209/117):** the folder NAME is operator-typed input ⇒ it passes through
`safe_key()`. The layout name and the suggested glob shape are **schema/config constants** ⇒ safe.

## Steps

1. Register the code in `_KINDS`.
2. In `advise_sync_file`, when the raw dict carries an `extract_decisions.dirs` block: resolve the
   layout once per lint run (cache on the `_Linter`); for each `dirs.*` value call
   `resolve_typed_write_dir(cfg, dir_name=value, source_rel=<the folder this sync.yaml governs>)`.
   `None` ⇒ `add("TYPED_DIR_NOT_COVERED_BY_LAYOUT", "sync", rel,
   pointer=f"/extract_decisions/dirs/{cls}", …)`.
3. **`system="sync"`** — the finding is *about* a sync.yaml key (that is where the pointer lives and
   where the operator edits), even though the *evidence* comes from the layout. Say so in the message.
4. A layout that maps **zero typed classes** — **`karpathy` and stock `obsidian-personal`** (verified;
   PLAN §1): the dirs are moot ⇒ still refuse, with the *"this layout maps no typed classes"* variant,
   so the operator learns it here rather than at the first `prepare`.

## Tests (RED first) — `tests/test_wiki_config_validate.py` (extend)

⚠️ **Fixtures come from the PLAN §1 ROSTER; this bead may not invent its own.** v1 did — and produced
**two mutually exclusive tests inside one bead** (plan-review C-2b): it used **stock**
`obsidian-personal` as the *supported* Cyrillic fixture while step 4 declared zero-typed-class layouts
**refused**. Both cannot be true.

- `test_typed_dir_not_covered_is_a_finding` — `cybos` + a custom Cyrillic `dirs.decision` ⇒ exactly 1
  finding, `TYPED_DIR_NOT_COVERED_BY_LAYOUT`, severity `error`, pointer
  `/extract_decisions/dirs/decision`. **MUT:** delete the check ⇒ RED.
- `test_covered_dir_is_clean` — same vault, `dirs.decision: decisions` ⇒ **0** findings
  (`total_findings == 0`, not merely "no error-severity" — a spurious warning is a false alarm too).
- `test_cyrillic_dir_is_clean_on_para_typed` — fixture **`para-typed`** (obsidian-personal **+ a
  `.wiki/layout.yaml`** unioning in the typed classes — the operator's LIVE vault, and what the spec
  means by *"obsidian-personal + the operator's `paths`"*): a Cyrillic dir name ⇒ **0 findings**.
  *cybos is not "broken" — it is STRICT BY DESIGN; a PARA vault's generic glob makes the name free.
  Both are correct, and the gate is what makes the difference **visible** instead of silently lost.*
- ★ `test_raw_dir_name_is_refused_even_though_a_glob_matches` — **the C-3 case at the validate
  surface**: `para-typed` + `dirs.decision: "_raw"` ⇒ a **finding**, because `ignore: **/_raw/**`
  makes the walker skip it *even though* a `paths[]` glob matches. **MUT:** back `glob_covers` with a
  bare `paths[]` match ⇒ **0 findings** ⇒ RED — and every decision written there is silently lost.
- `test_message_never_echoes_an_unsafe_value` — `dirs.decision: "evil\n---"` ⇒ the rendered message
  carries no control chars (through `safe_key`).
- `test_zero_typed_class_layout_refuses` — **`karpathy` AND stock `obsidian-personal`** (both, not
  one — they fail G4's *first* conjunct, and step 4 says so) + any `dirs` ⇒ finding.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed, 0 failed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES:** the new code must be renderable by **every** finding sink. Enumerate them
      from the code, then verify — do not assume the generic taxonomy tests cover it:
      ```bash
      grep -rn "TAXONOMY\|\.kind\b" scripts/wiki_skills/wiki_config/ | grep -v _findings.py
      #  → the sinks: histogram · render_findings_report · _report.py · _doctor.py tiers
      ```
      A code registered in `_KINDS` but unrenderable is a `KeyError` at the worst possible moment.
- [ ] **MUT:** revert `_check_typed_dirs` ⇒ `test_typed_dir_not_covered_is_a_finding` RED.
- [ ] **Back-compat:** `wiki-config validate` on a vault with **no** `extract_decisions` block ⇒ exit
      code + histogram **byte-identical** to pre-change. Absence is silent.

## Rollback

Remove the `FindingKind` row + `_check_typed_dirs`. Taxonomy codes are API — this one has never
shipped, so removal is clean.
