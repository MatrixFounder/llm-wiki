---
id: DF-072-10
type: known-issue
status: open
opened_at: 2026-08-09
category: correctness
severity: SEV-2
slug: df-072-10-sync-upserts-raw-captures-the-layout-ignores
---

# `wiki-sync` upserts `_raw/` captures that the LAYOUT ignores — 31 index rows a `wiki-reindex --full` silently DROPS, reported by `wiki-lint` as `missing-on-disk` for files that exist

- **Symptom**: `wiki-sync scan` classifies a `_raw/<slug>.md` capture (a `wiki-import` artifact —
  clean markdown WITH frontmatter) as `action: upsert`, `reason: ready-note`. `wiki-index-upsert`
  then indexes it, exit 0. But the vault's layout ignores `**/_raw/**`, so the canonical walk
  (`iter_pages`) never yields that page. The index gains a row that **no rebuild can reproduce**.

- **Measured on the LIVE `personal` vault** (2026-08-09, `03 - Learning` zone, `obsidian-personal`
  layout, 1192 planned entries):

  ```console
  $ wiki-sync scan "03 - Learning" …        # 31 of the 1112 upserts are under _raw/
  upsert  03 - Learning/WEB3/12 Days of Dune/Summaries/_raw/day-01-….md  — ready-note
  …
  pages before: 3359   ← exactly what iter_pages yields
  pages after : 3390   ← 3359 + 31 phantom rows
  $ wiki-reindex --full …                    → 3359    # the 31 are silently dropped, skipped[] EMPTY
  ```

- **Three consequences, in severity order.**

  1. **ADR-002 §D8 is violated.** Class B is defined as a 100%-rebuildable cache of Class A. Here
     the DB held 31 pages the rebuild cannot reproduce — and dropped them with **`skipped: []`**,
     so the rebuild reported a clean pass while losing rows. The Class-A files were never at risk,
     but the "rebuildable" invariant was, and *nothing announced it*.
  2. **`wiki-lint` mislabels it.** The 31 surface as `missing-on-disk` (**severity `error`**) —
     and the files are *present on disk*. The real condition is "a DB row the layout walker cannot
     see", which is the mirror image of the message. An operator who follows the label goes looking
     for deleted files and finds them all there.
  3. **The workflow's promise reads as broader than it is.** `workflows/wiki-sync.md` §4c says
     `wiki-index-upsert` "is **layout-aware** … files the page under the layout's
     project/slug/type/refs, byte-identically to `reindex` (so a later `reindex --full` won't
     duplicate it)". True as written — it does not *duplicate*. What it does not say is that the
     page may not **survive** the rebuild at all, because layout-awareness covers project/slug/type
     resolution but **not** the layout's `ignore` globs.

- **Root cause — the two config systems disagree, and nothing reconciles them.**
  `wiki-sync`'s walk is driven by `.wiki/sync.yaml` `exclude:`; the index walk is driven by the
  layout grammar's `ignore:`. On this vault `**/_raw/**` is shipped by the **built-in**
  `obsidian-personal` layout (not authored in `.wiki/layout.yaml`), while `sync.yaml`'s `exclude`
  names `_inbox/**`, `_daily/**`, `Attachments/**`, … and **no `_raw` rule**. The operator sees two
  config files, neither of which contains the rule that causes the divergence.

  ⚠️ `_raw/` being walked by sync is **deliberate** — §4 item 4 of the workflow describes exactly
  this file and instructs recording a `source_state` marker for it so the next scan does not
  re-`ingest` it. That guard exists **on the `ingest` branch only**. A capture that carries
  frontmatter never reaches it: it classifies as `ready-note` → `upsert`, a branch with no such
  reconciliation.

- **Nothing failed.** `scan` exit 0, 1112/1112 upserts exit 0 (31 `inserted`, 1081 `unchanged`),
  1112/1112 markers recorded, `wiki-index-render --concept-mentions` converged, `wiki-reindex
  --full` exit 0 with `skipped: []`. The only signal in the entire run was a lint category whose
  name asserts the opposite of the truth.

- **Fix shape** (not done here — the choice is a real decision, not a detail):
  - **(a) Refuse at the writer.** `wiki-index-upsert` resolves the layout already; have it check
    the resolved path against the layout's `ignore` globs and refuse (a `PATH_IGNORED_BY_LAYOUT`
    envelope) rather than write a row the rebuild will drop. Strongest: it also covers direct
    callers and `/wiki-import`, not just the sync driver. Risk: some caller may legitimately want
    to index an ignored path — needs a census before it becomes a refusal.
  - **(b) Filter at the planner.** `wiki-sync scan` drops (or `skip:layout-ignored`s) any entry the
    layout ignores. Narrower blast radius, but leaves the hole open for every other caller.
  - **(c) Fix the label regardless of (a)/(b).** `missing-on-disk` must not fire for a row whose
    file exists; that case is a distinct category (`unwalkable-row` / `layout-ignored-row`) with an
    accurate message. This one is worth doing on its own — it is what turns the next occurrence
    from a 40-minute investigation into a one-line read.
  - Pin whichever lands with a test that asserts **`reindex --full` reproduces exactly the row set
    a preceding `upsert` batch produced** — the invariant that actually broke. A per-call assertion
    on `upsert` alone cannot see this class.

- **Relation to DF-072-7.** Same shape, opposite direction: there, a layout declared the classes in
  `type_mapping` with **no read glob that could see them**, so an imported note was written, exited
  0, and was never indexed — with `skipped[]` EMPTY. Here a note IS indexed that the read glob
  excludes, and the rebuild drops it — with `skipped[]` EMPTY. Both are the write-side and read-side
  halves of one unenumerated surface: **nothing cross-checks the writer's path against the walker's
  globs**, in either direction. Closing this without closing that symmetry buys one of two.

- **Found by**: the live `wiki-sync` dogfood of 2026-08-09 (`03 - Learning`, 1192 entries). Vault
  remediated in the same session — `wiki-reindex --full` → 3359 pages, `wiki-lint`
  `missing-on-disk` 31 → 0 and `hash-mismatch` 3 → 0 (the 3 were unrelated, genuinely stale rows
  the rebuild also fixed). No Class-A file was touched at any point.

## Related

- [[df-072-7-cybos-and-dev-project-half-support-imported-sources]] — the read-side half of the
  same unenumerated surface.
- [[the-unenumerated-surface-lens]] — every command exited 0; only a mislabelled lint category
  dissented.
- `scripts/wiki_index/sqlite_repository/_health_scan.py:271` — `missing_on_disk` is "DB rows not
  in `seen_on_disk`", and the comment above it asserts the walk "still mirrors the reindex walk
  (no false missing-on-disk)". That assertion is what this defect falsifies.
