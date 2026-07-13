# TASK 063-14 — re-extraction reconciliation: **Class-A ownership is sacred**

**Phase**: 4 (write) · **RTM**: R-063-9 · **Type**: code · **Effort**: 3–4h
**Depends on**: 063-12, 063-13 · **Unblocks**: 063-15

## Goal

Re-running the rail on an edited source must **never destroy operator work** — and must never leave
the vault drifted either. Those two goals collide exactly once, and the spec resolves the collision.

## (a) The write hash is OUT-OF-BAND

Generated pages carry `extracted_from: <source_slug>`. The write-time **content hash is stored in the
DB** (`source_state`, legitimate Class-C operational state, ADR-002 §D8).

> ⚠️ **A hash stored INSIDE the file cannot be a hash OF the file.** v2's in-file stamp was
> self-referential — the guard would have **silently never fired**. Store it out-of-band or do not
> claim the guard.

## (b) NEVER clobber — for WHOLE-PAGE REWRITES

Current hash ≠ recorded write hash ⇒ **hand-edited** ⇒ **skip the content rewrite**, report
`TYPED_PAGE_HAND_EDITED` **loudly**.

> ⚠️ This **inverts the concepts precedent**, which atomically rewrites + warns. Deliberate: if the
> operator hand-set `status: superseded`, the concepts behaviour would **revert it on the next run**,
> resurrecting the very drift this task exists to kill.

## (b′) ★ PRECEDENCE — "never clobber" governs REWRITES, **not** the R-063-8 patch

Read as absolute, (b) would **skip the R-063-8 status patch** on a *hand-edited generated decision*
that is a supersede target — **the single most likely operator action** (adding rationale) — leaving
`lifecycle-drift` standing and **breaking the property**. That is the exact failure fixed in
R-063-8(3″), one requirement to the left.

The patch is safe on a hand-edited page **by construction**: one frontmatter scalar, body bytes +
comments preserved (ruamel sandwich), backup, reported diff. Therefore:

| page state | content rewrite | R-063-8 status patch |
|---|---|---|
| generated, unmodified | ✅ rewrite | ✅ patch |
| generated, **hand-edited** | ⛔ skip + `TYPED_PAGE_HAND_EDITED` | ✅ **PATCH** (body edits preserved) |
| **hand-authored** (no recorded hash) — *the only case that exists in production today* | ⛔ never | ✅ **PATCH**, inside the authority envelope |
| supersede target with a **protected terminal status** | — | ⛔ **REFUSE THE BATCH** (063-13) |

**(a′)** A page with **no recorded write hash** is **operator-owned** — and that is the ONLY case that
exists in production today (**the 20 pilot pages are all hand-authored**). Refusing to patch them
would make **G3 unreachable on the only vault that has typed pages.** So: patch, strictly inside
R-063-8's authority envelope. Never a body edit, never a rewrite.

**The ONLY refusal remains (3″)** — a protected terminal status — *because that is a conflict of
INTENT, not of BYTES.*

## (c) Stale pages are REPORTED, never auto-deleted

Prior-run pages absent from the new candidate set ⇒ `stale: [{slug, reason}]`. **`--prune` is opt-in.**
A re-worded decision must not silently delete its predecessor.

## Context — files

- **Edit** `_db.py` (`record_write_hash` / `load_write_hashes` — `source_state`, kind
  `extract-decisions`, a per-page key), `_pages.py`, `__init__.py`.
- **Read** `wiki_extract_concepts/_pages.py` content-hash-skip semantics (**and note where we
  deliberately diverge** — write the divergence in the docstring).

## Tests (RED first) — `tests/test_extract_decisions_reextraction.py` (new)

- `test_hand_edited_generated_page_survives_reextraction` — body edited by hand ⇒ re-run ⇒ **body
  bytes unchanged**, `TYPED_PAGE_HAND_EDITED` reported, exit 0.
- `test_hand_edited_page_is_STILL_status_patched` — the same page is a supersede target ⇒
  `status` **patched**, body edits **preserved**. **MUT:** read (b) as absolute (skip the patch) ⇒
  `lifecycle-drift` fires ⇒ 063-15's delta test RED. *This is the (b′) trap, pinned.*
- `test_hand_authored_target_is_patched` — a page with **no** recorded write hash (a pilot page) ⇒
  patched inside the envelope. **MUT:** refuse hand-authored targets ⇒ **G3 becomes unreachable on the
  only vault that has typed pages** ⇒ RED.
- `test_write_hash_is_stored_out_of_band` — the written page's **text contains no hash**; the hash is
  in `source_state`. **MUT:** stamp it in the file ⇒ assert the guard **never fires** on a hand-edit ⇒
  RED. *A self-referential hash is a guard that silently does nothing — test for the silence.*
- `test_stale_page_reported_not_deleted` — re-worded decision ⇒ old page **still on disk**,
  `stale[]` names it, exit 0.
- `test_prune_is_opt_in` — `--prune` ⇒ deleted; without it ⇒ kept. Two assertions, one behaviour flag.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **The 4×2 precedence table above is covered cell-by-cell** — one test per row. This is a
      population claim ("every page state is handled"): enumerate the rows in a parametrised test and
      assert the parameter set equals the table, so a new page-state cannot be added without a test.
- [ ] **MUT:** each of (a)/(b)/(b′)/(a′)/(c) reverted ⇒ its named test RED. Five mutations, five reds.

## Rollback

Reconciliation → always-rewrite (the concepts behaviour) ⇒ the hand-edit tests go RED. Correct signal.
