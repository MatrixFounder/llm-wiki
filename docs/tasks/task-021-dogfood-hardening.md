# TASK 021 — dogfood-hardening (re-dogfood findings on `samples/Demand-generation`)

**Status:** in progress · **Mode:** VDD (ultracode) · **Schema:** v5 (zero DDL) ·
**Origin:** the 2026-06-08 repeat comprehensive dogfood of TASK 019 + TASK 020 on
`samples/Demand-generation`, hardened by two `critic-logic` adversarial passes whose
two HIGH findings were **empirically reproduced** before acceptance.

## Problem

The repeat dogfood confirmed TASK 019/020 ship correctly (1044 pytest green, zero
data loss on the frozen fixture), but adversarial verification + reproduction surfaced
two genuine gaps and three minor ones:

- **HIGH-1 — D2b mirror is a key-equality proxy, not a "this raw was summarized" proof.**
  Under N:1 group-keying, a *new* raw file sharing a key with an already-summarized
  sibling is silently skipped. Reproduced on the fixture:
  `+ Lessons/Transcripts/20260420 - extra brand-new session.txt → skip:summary-exists:mirror`.
  This is the operator's *intended* "group summarized → don't re-summarize" semantics
  (the original TASK 019 design) — but the coarse-key risk (merge-vs-split ambiguity)
  is invisible.
- **HIGH-2 — cross-batch `--delta` slug-collision is silent.** `_detect_slug_collision`
  consults only the in-batch `seen_keys`, never the DB. Reproduced: `run1 full a/01.md`;
  `run2 delta + b/01.md` (same `(slug,project)`) → b silently clobbers a, `slug_collisions=[]`,
  no WARN. The field comment even concedes "within-batch only" — but `--reindex --delta`
  is the documented primary workflow, so the silent overwrite class TASK 020 set out to
  kill survives across batches.
- **MED — `wiki-reindex --all-vaults` silently ignores `--delta`** ([wiki_reindex.py:37](../scripts/wiki_skills/wiki_reindex.py#L37)):
  unconditionally calls `reindex_full`; the aggregation block is hard-wired to `r["pages"]`
  (would `KeyError` if ever routed to delta).
- **LOW (test) — collision tests assert `kept`/`dropped` as a SET**, not direction +
  DB-content — an attribution regression would pass silently.
- **LOW (doc) — stale config doc contradicts the shipped ignore-UNION fix**
  ([samples/target-obsidian-vault/.wiki/layout.yaml:3-4](../samples/target-obsidian-vault/.wiki/layout.yaml#L3)):
  "deep-merge ЗАМЕНЯЕТ списки целиком … ignore заменяет базовый" — now false. This is
  the *draft of the user's real vault config*, so the wrong mental model would follow
  to production.

## Decision (operator-confirmed)

**HIGH-1 → Option A** (operator-confirmed 2026-06-08): keep the skip (preserve the
original TASK 019 design intent), but **surface** the merge-vs-split moment with a WARN.
The tool must neither silently re-summarize nor silently drop; `sources:` provenance is
the authoritative merge/split record, the regex key only the default grouping. The two
resolution levers — **MERGE** (`--force` → regenerate the group summary + AC-13 `sources:`
writeback) and **SPLIT** (a finer key / own scope, or author a 2nd summary citing the
raw) — already exist; the WARN points at them. No bespoke merge/split CLI subcommands
(YAGNI).

## Requirements Traceability Matrix

| ID | Requirement | Acceptance test | Verify |
|----|-------------|-----------------|--------|
| **R-021-1** | HIGH-1 Option A: an N:1 **group-key** mirror match that results in a `skip` emits a one-line merge/split WARN **when provenance is enabled but does not cite this raw** (the precise uncited-same-key case). The WARN names the composed key, the raw file, a representative colliding summary, and both levers (`--force` / re-key). **Skip behavior is unchanged** (monotone gate untouched); `stem-relpath` (1:1) never warns. Provenance disabled → no per-file warn (operator opted into pure-key grouping). | `tests/test_wiki_sync_resummarize.py`: same-key uncited raw → still `skip:summary-exists:mirror` AND a `caplog` WARN naming the key + both levers; cited raw → `skip:provenance`, NO warn; provenance-disabled → skip, NO warn; stem-relpath match → NO warn. | pytest + dogfood repro |
| **R-021-2** | HIGH-2: `reindex_delta` seeds `seen_keys` from existing DB rows (`slug, project, file_path`) **before** the touched-file loop, so a delta file colliding with a prior-batch DB row (mtime ≤ cutoff, not re-walked) is reported in `slug_collisions` + WARN. Self-updates (`prior == rel`) never false-positive. `slug_collisions` is no longer "within-batch only". | `tests/test_wiki_reindex_delta.py`: cross-batch repro (full a/01.md → delta + b/01.md future mtime) → `slug_collisions` reports `{kept:b, dropped:a}`, DB holds b; self-update of a/01.md → `slug_collisions == []`. | pytest + dogfood repro |
| **R-021-3** | MED: `wiki-reindex --all-vaults` honors `--delta` (delegates to `reindex_delta`); the envelope reports `mode` and aggregates the correct shape (`touched` for delta, `pages_indexed` for full) + `slug_collisions` across vaults for both. No `KeyError`. | `tests/test_wiki_reindex_cli.py` (or existing CLI test): `--all-vaults --delta` → `mode=delta`, `touched` present, no crash; `--all-vaults --full` unchanged (`pages_indexed`). | pytest + CLI smoke |
| **R-021-4** | LOW (test): the full + delta collision tests assert `kept`/`dropped` **by direction** (`kept == later`, `dropped == earlier`) AND that the surviving DB row's `file_path` equals `kept`. | strengthened existing assertions in `tests/test_wiki_reindex_{full,delta}.py`. | pytest |
| **R-021-5** | LOW (doc): `samples/target-obsidian-vault/.wiki/layout.yaml` header corrected — `ignore` now **extends** the base (union); the REPLACE warning scoped to `paths`/`ref_extraction`/`file_extensions` only. (Belt-and-braces: also re-check `samples/personal-vault-dogfood`.) | manual read; `wiki-lint`/resolve check unaffected. | manual + resolve_layout_config |
| **R-021-6** | LOW (doc): document the two latent mirror sharp-edges in `config/sync-config.schema.yaml` (+ `_resummarize` docstring): `^(\d+)`+`_norm` define a **leading-zero-insensitive numeric equivalence class** (recommend a delimited key for multi-component), and `summary_ext` is **single-valued** (the mirror sees one extension). | manual read. | manual |

## Non-goals / constraints

- **Zero DDL** (`user_version` stays 5) — HIGH-2 reuses the `pages` table; HIGH-1 is
  log-only. **No new deps. No `import anthropic`** in the scanner (grep-guarded).
- HIGH-1 must NOT change the skip decision (Option A = behavior-preserving + visibility).
- Stub-First, green-throughout; mypy `--strict` clean; re-run the full dogfood incl.
  the HIGH-1/HIGH-2 reproductions (now expected fixed/surfaced).

## Review outcome (adversarial Workflow — logic/security/performance + verify)

3 findings confirmed (0 dismissed), ALL in the HIGH-2 delta seed, ALL fixed by ONE refinement
(seed only prior-batch rows that are still-on-disk AND not-re-walked; single coalesced `pages`
read):
- **L-1 (MED)** — both colliding files re-walked on a pre-populated DB double-counted the
  collision (1→2) with an inverted first record → refined seed leaves re-walked rows to the
  within-batch loop → exactly one correctly-directed record. Guard: `test_delta_both_touched_on_populated_db_single_record`.
- **L-2 (LOW)** — a rename preserving the slug flagged a false collision naming the gone file →
  off-disk prior rows excluded from the seed. Guard: `test_delta_rename_same_slug_no_false_collision`.
- **PERF-021-1 (LOW)** — the seed duplicated the orphan-detection `pages` scan → one read reused
  for both.

**Final gates:** 1056 pytest (+4 skipped), mypy `--strict` clean (73 files), canonical dogfood
unchanged (53==53, 84 backed skips, 3 gaps, 0 data-loss), `user_version` 5, no new deps, no
`import anthropic`.
